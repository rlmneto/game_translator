"""
Translation service — multi-engine, multi-language, with caching.
Supports: OpenAI (GitHub Models), deep-translator (Google), MarianMT (offline).
"""

import logging
import os
import time

from .cache import TranslationCache
from .config import BASE_DIR, LANGUAGES, MARIAN_MODEL_MAP

logger = logging.getLogger(__name__)

# -- optional imports (graceful degradation) -----------------------------

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    DEEP_TRANSLATOR_AVAILABLE = True
except ImportError:
    DEEP_TRANSLATOR_AVAILABLE = False

try:
    from transformers import MarianMTModel, MarianTokenizer
    MARIAN_AVAILABLE = True
except ImportError:
    MARIAN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a translator for video game dialog text. "
    "The user provides {source_desc} text extracted via OCR from game dialog boxes. "
    "The OCR may contain small errors. Your task:\n"
    "1. Fix any obvious OCR errors in the original text.\n"
    "2. Translate the corrected text to {target_language}.\n"
    "3. Keep proper nouns (character names, location names, item names) "
    "in their original language.\n"
    "Reply with ONLY: first the corrected original text on one line, then '---', "
    "then the {target_language} translation. No explanations."
)

DETECT_PROMPT = (
    "You are a translator for video game dialog text. "
    "The user provides text extracted via OCR from game dialog boxes "
    "(the source language is unknown). The OCR may contain small errors. "
    "Your task:\n"
    "1. Detect the source language.\n"
    "2. Fix any obvious OCR errors in the original text.\n"
    "3. Translate the corrected text to {target_language}.\n"
    "4. Keep proper nouns (character names, location names, item names) "
    "in their original language.\n"
    "Reply with ONLY: first the corrected original text on one line, then '---', "
    "then the {target_language} translation. No explanations."
)

# -- Document / PDF specific prompts ------------------------------------

DOCUMENT_SYSTEM_PROMPT = (
    "You are a translator for printed documents and books. "
    "The user provides {source_desc} text extracted via OCR from a document page. "
    "The OCR may contain small errors or formatting issues. Your task:\n"
    "1. Fix any obvious OCR errors in the original text.\n"
    "2. Translate the corrected text to {target_language}.\n"
    "3. PRESERVE the original formatting: keep line breaks, paragraph spacing, "
    "indentation, bullet points, and the overall visual structure of the text.\n"
    "4. Keep proper nouns (names, titles, places) in their original language.\n"
    "Reply with ONLY: first the corrected original text (preserving formatting), "
    "then '---', then the {target_language} translation (also preserving formatting). "
    "No explanations."
)

DOCUMENT_DETECT_PROMPT = (
    "You are a translator for printed documents and books. "
    "The user provides text extracted via OCR from a document page "
    "(the source language is unknown). The OCR may contain small errors. "
    "Your task:\n"
    "1. Detect the source language.\n"
    "2. Fix any obvious OCR errors in the original text.\n"
    "3. Translate the corrected text to {target_language}.\n"
    "4. PRESERVE the original formatting: keep line breaks, paragraph spacing, "
    "indentation, bullet points, and the overall visual structure of the text.\n"
    "5. Keep proper nouns (names, titles, places) in their original language.\n"
    "Reply with ONLY: first the corrected original text (preserving formatting), "
    "then '---', then the {target_language} translation (also preserving formatting). "
    "No explanations."
)

# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TranslationService:
    def __init__(self):
        self.client = None
        self.cache = TranslationCache()
        self._model = "gpt-4o-mini"
        self._source_lang = "auto"
        self._target_lang = "pt-br"
        self._engine = "openai"
        self._content_type = "game"   # "game" or "document"
        self._marian_models: dict[str, tuple] = {}  # model_name → (model, tokenizer)

        token = self._load_token()
        if token and OPENAI_AVAILABLE:
            self.client = OpenAI(
                base_url="https://models.inference.ai.azure.com",
                api_key=token,
                max_retries=0,          # we handle retries ourselves
            )
            logger.info("TranslationService initialised with API token")
        else:
            logger.warning("No API token found — OpenAI translation unavailable")

    # -- public ----------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        if self._engine == "openai":
            return self.client is not None
        if self._engine == "deep_translator":
            return DEEP_TRANSLATOR_AVAILABLE
        if self._engine == "marian":
            return MARIAN_AVAILABLE
        return False

    def configure(self, model: str | None = None,
                  source_lang: str | None = None,
                  target_lang: str | None = None,
                  engine: str | None = None,
                  content_type: str | None = None):
        if model is not None:
            self._model = model
        if source_lang is not None:
            self._source_lang = source_lang
        if target_lang is not None:
            self._target_lang = target_lang
        if engine is not None:
            self._engine = engine
        if content_type is not None:
            self._content_type = content_type
        logger.info(
            "Translation configured: engine=%s  model=%s  %s → %s  content=%s",
            self._engine, self._model, self._source_lang, self._target_lang,
            self._content_type,
        )

    def translate(self, text: str, *,
                  source_lang: str | None = None,
                  target_lang: str | None = None,
                  model: str | None = None) -> tuple[str, str]:
        """Returns (corrected_original, translation)."""
        src = source_lang or self._source_lang
        tgt = target_lang or self._target_lang
        mdl = model or self._model

        # 1. cache lookup
        cache_key_engine = self._engine if self._engine != "openai" else mdl
        cached = self.cache.get(text, src, tgt, cache_key_engine)
        if cached:
            logger.info("Translation served from cache")
            return cached

        # 2. dispatch to engine
        if self._engine == "deep_translator":
            corrected, translation = self._translate_deep(text, src, tgt)
        elif self._engine == "marian":
            corrected, translation = self._translate_marian(text, src, tgt)
        else:
            try:
                corrected, translation = self._translate_openai(text, src, tgt, mdl)
            except Exception as exc:
                err_msg = str(exc)
                is_rate_limit = (
                    "429" in err_msg
                    or "rate" in err_msg.lower()
                )
                if is_rate_limit and DEEP_TRANSLATOR_AVAILABLE:
                    logger.warning(
                        "OpenAI rate limit — falling back to Google Translate"
                    )
                    corrected, translation = self._translate_deep(text, src, tgt)
                    # cache under the fallback engine label
                    self.cache.put(text, src, tgt, "google_fallback",
                                   corrected, translation)
                    return corrected, translation
                raise

        # 3. store in cache
        self.cache.put(text, src, tgt, cache_key_engine, corrected, translation)
        return corrected, translation

    # -- OpenAI (GitHub Models) ------------------------------------------

    def _translate_openai(self, text: str, src: str, tgt: str,
                          mdl: str) -> tuple[str, str]:
        if not self.client:
            raise RuntimeError("OpenAI não configurado — adicione GITHUB_TOKEN no .env")

        target_name = LANGUAGES.get(tgt, tgt)
        is_doc = self._content_type == "document"
        if src == "auto":
            if is_doc:
                system = DOCUMENT_DETECT_PROMPT.format(target_language=target_name)
            else:
                system = DETECT_PROMPT.format(target_language=target_name)
        else:
            source_name = LANGUAGES.get(src, src)
            if is_doc:
                system = DOCUMENT_SYSTEM_PROMPT.format(
                    source_desc=source_name, target_language=target_name,
                )
            else:
                system = SYSTEM_PROMPT.format(
                    source_desc=source_name, target_language=target_name,
                )

        user_prefix = "[Document OCR]" if is_doc else "[Game dialog OCR]"
        max_tok = 2048 if is_doc else 600

        logger.info("OpenAI request: model=%s  %s → %s  chars=%d  type=%s",
                    mdl, src, tgt, len(text), self._content_type)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{user_prefix}: {text}"},
        ]

        # Retry with exponential backoff on transient rate-limits.
        # Daily quota exhaustion ("per 86400s") is NOT retried.
        max_retries = 3
        base_delay = 3.0
        for attempt in range(max_retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=mdl,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=max_tok,
                )
                break
            except Exception as exc:
                err_msg = str(exc)
                is_rate_limit = (
                    "429" in err_msg
                    or "rate" in err_msg.lower()
                )
                # Daily quota exhausted — do NOT retry, fail fast
                if "86400" in err_msg or "UserByModelByDay" in err_msg:
                    logger.error(
                        "Daily API quota exhausted for model %s. "
                        "Wait until tomorrow or switch engine.", mdl,
                    )
                    raise
                # Transient rate limit — retry with backoff
                if is_rate_limit and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Rate limit hit (attempt %d/%d), retrying in %.1fs...",
                        attempt + 1, max_retries, delay,
                    )
                    time.sleep(delay)
                else:
                    raise

        raw = resp.choices[0].message.content.strip()
        logger.debug("OpenAI response (first 200): %s", raw[:200])

        if "---" in raw:
            corrected, translation = raw.split("---", 1)
            corrected, translation = corrected.strip(), translation.strip()
        else:
            corrected, translation = text, raw

        return corrected, translation

    # -- deep-translator (Google Translate) ------------------------------

    def _translate_deep(self, text: str, src: str, tgt: str) -> tuple[str, str]:
        if not DEEP_TRANSLATOR_AVAILABLE:
            raise RuntimeError("deep-translator não instalado (pip install deep-translator)")

        # map language codes
        src_code = "auto" if src == "auto" else self._deep_lang_code(src)
        tgt_code = self._deep_lang_code(tgt)

        logger.info("Google Translate: %s → %s  chars=%d", src_code, tgt_code, len(text))
        translator = GoogleTranslator(source=src_code, target=tgt_code)
        translation = translator.translate(text)
        return text, translation or ""

    @staticmethod
    def _deep_lang_code(code: str) -> str:
        """Convert our lang codes to deep-translator / Google codes."""
        mapping = {
            "pt-br": "pt",
            "zh-cn": "zh-CN",
            "zh-tw": "zh-TW",
        }
        return mapping.get(code, code)

    # -- MarianMT (Hugging Face, offline) --------------------------------

    def _translate_marian(self, text: str, src: str, tgt: str) -> tuple[str, str]:
        if not MARIAN_AVAILABLE:
            raise RuntimeError("transformers não instalado (pip install transformers sentencepiece)")

        model_name = self._resolve_marian_model(src, tgt)
        if not model_name:
            raise RuntimeError(
                f"Modelo MarianMT não disponível para {src} → {tgt}. "
                "Tente usar Google Translate ou OpenAI."
            )

        model, tokenizer = self._get_marian(model_name)

        logger.info("MarianMT: %s  %s → %s  chars=%d", model_name, src, tgt, len(text))
        inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        outputs = model.generate(**inputs, max_length=512)
        translation = tokenizer.decode(outputs[0], skip_special_tokens=True)

        return text, translation

    def _get_marian(self, model_name: str):
        if model_name not in self._marian_models:
            logger.info("Loading MarianMT model: %s", model_name)
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name)
            self._marian_models[model_name] = (model, tokenizer)
        return self._marian_models[model_name]

    @staticmethod
    def _resolve_marian_model(src: str, tgt: str) -> str | None:
        # direct match
        if (src, tgt) in MARIAN_MODEL_MAP:
            return MARIAN_MODEL_MAP[(src, tgt)]
        # for pt-br target, try via en pivot
        # (many models only go en→X or X→en)
        return MARIAN_MODEL_MAP.get((src, tgt))

    @staticmethod
    def available_engines() -> list[str]:
        engines: list[str] = []
        if OPENAI_AVAILABLE:
            engines.append("openai")
        if DEEP_TRANSLATOR_AVAILABLE:
            engines.append("deep_translator")
        if MARIAN_AVAILABLE:
            engines.append("marian")
        return engines

    # -- token loading ---------------------------------------------------

    @staticmethod
    def _load_token() -> str:
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GITHUB_TOKEN="):
                        token = line.strip().split("=", 1)[1].strip()
                        logger.info("Token loaded from .env")
                        return token
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            logger.info("Token loaded from environment variable")
        return token
