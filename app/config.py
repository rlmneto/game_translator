"""
Centralised configuration — settings, language maps, presets, profiles.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DUALSENSE_BUTTONS = {
    0: "✕ (Cross)", 1: "○ (Circle)", 2: "□ (Square)", 3: "△ (Triangle)",
    4: "Create", 5: "PS", 6: "Options", 7: "L3", 8: "R3",
    9: "L1", 10: "R1", 11: "D-Pad Up", 12: "D-Pad Down",
    13: "D-Pad Left", 14: "D-Pad Right", 15: "Touchpad", 16: "Mute",
}

# -- Languages -----------------------------------------------------------

LANGUAGES = {
    "auto": "Auto-detectar",
    "en": "English",
    "pt-br": "Português (BR)",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "ja": "日本語",
    "ko": "한국어",
    "zh-cn": "中文 (简体)",
    "zh-tw": "中文 (繁體)",
    "ru": "Русский",
    "pl": "Polski",
    "nl": "Nederlands",
    "tr": "Türkçe",
}

SOURCE_LANGUAGES = dict(LANGUAGES)                                       # includes "auto"
TARGET_LANGUAGES = {k: v for k, v in LANGUAGES.items() if k != "auto"}   # no "auto"

EASYOCR_LANG_MAP: dict[str, list[str]] = {
    "auto": ["en"],
    "en":    ["en"],
    "pt-br": ["pt"],
    "es":    ["es"],
    "fr":    ["fr"],
    "de":    ["de"],
    "it":    ["it"],
    "ja":    ["ja"],
    "ko":    ["ko"],
    "zh-cn": ["ch_sim"],
    "zh-tw": ["ch_tra"],
    "ru":    ["ru"],
    "pl":    ["pl"],
    "nl":    ["nl"],
    "tr":    ["tr"],
}

TESSERACT_LANG_MAP: dict[str, str] = {
    "auto": "eng",
    "en":    "eng",
    "pt-br": "por",
    "es":    "spa",
    "fr":    "fra",
    "de":    "deu",
    "it":    "ita",
    "ja":    "jpn",
    "ko":    "kor",
    "zh-cn": "chi_sim",
    "zh-tw": "chi_tra",
    "ru":    "rus",
    "pl":    "pol",
    "nl":    "nld",
    "tr":    "tur",
}

# -- OCR engines / quality -----------------------------------------------

OCR_ENGINES = {
    "easyocr":    "EasyOCR",
    "tesseract":  "Tesseract",
    "rapidocr":   "RapidOCR",
    "paddleocr":  "PaddleOCR",
}

# -- Translation engines -------------------------------------------------

TRANSLATION_ENGINES = {
    "openai":          "OpenAI (GitHub)",
    "deep_translator": "Google Translate",
    "marian":          "MarianMT (offline)",
}

# -- MarianMT model map (Helsinki-NLP) -----------------------------------

MARIAN_MODEL_MAP: dict[tuple[str, str], str] = {
    ("en", "pt-br"): "Helsinki-NLP/opus-mt-en-ROMANCE",
    ("en", "es"):    "Helsinki-NLP/opus-mt-en-es",
    ("en", "fr"):    "Helsinki-NLP/opus-mt-en-fr",
    ("en", "de"):    "Helsinki-NLP/opus-mt-en-de",
    ("en", "it"):    "Helsinki-NLP/opus-mt-en-it",
    ("en", "nl"):    "Helsinki-NLP/opus-mt-en-nl",
    ("en", "ru"):    "Helsinki-NLP/opus-mt-en-ru",
    ("en", "pl"):    "Helsinki-NLP/opus-mt-en-pl",
    ("en", "tr"):    "Helsinki-NLP/opus-mt-en-tr",
    ("ja", "en"):    "Helsinki-NLP/opus-mt-ja-en",
    ("ko", "en"):    "Helsinki-NLP/opus-mt-ko-en",
    ("zh-cn", "en"): "Helsinki-NLP/opus-mt-zh-en",
    ("zh-tw", "en"): "Helsinki-NLP/opus-mt-zh-en",
    ("fr", "en"):    "Helsinki-NLP/opus-mt-fr-en",
    ("de", "en"):    "Helsinki-NLP/opus-mt-de-en",
    ("es", "en"):    "Helsinki-NLP/opus-mt-es-en",
    ("ru", "en"):    "Helsinki-NLP/opus-mt-ru-en",
}

OCR_QUALITY_OPTIONS = {
    "fast":     "Rápido",
    "balanced": "Balanceado",
    "quality":  "Qualidade",
    "pdf":      "PDF / Documento",
}

OCR_PRESETS: dict[str, dict] = {
    "fast": {
        "text_threshold": 0.7,
        "low_text":       0.4,
        "contrast_ths":   0.5,
        "adjust_contrast": 0.5,
        "scale_factor":   2,
        "blur_radius":    1.0,
        "preprocess":     "game",
    },
    "balanced": {
        "text_threshold": 0.5,
        "low_text":       0.3,
        "contrast_ths":   0.3,
        "adjust_contrast": 0.7,
        "scale_factor":   4,
        "blur_radius":    1.5,
        "preprocess":     "game",
    },
    "quality": {
        "text_threshold": 0.3,
        "low_text":       0.2,
        "contrast_ths":   0.2,
        "adjust_contrast": 0.8,
        "scale_factor":   6,
        "blur_radius":    2.0,
        "preprocess":     "game",
    },
    "pdf": {
        "text_threshold": 0.4,
        "low_text":       0.2,
        "contrast_ths":   0.2,
        "adjust_contrast": 0.7,
        "scale_factor":   3,
        "blur_radius":    0,
        "preprocess":     "document",
    },
}

# -- API models ----------------------------------------------------------

API_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4",
    "gpt-3.5-turbo",
    "o3-mini",
]

# Friendly labels for the translation engine dropdown
TRANSLATION_ENGINE_LABELS = {v: k for k, v in TRANSLATION_ENGINES.items()}

# -- Game profiles -------------------------------------------------------

GAME_PRESETS: dict[str, dict] = {
    "default": {
        "label":           "Padrão",
        "description":     "Configuração balanceada para a maioria dos jogos",
        "ocr_quality":     "balanced",
        "source_language": "auto",
        "target_language": "pt-br",
        "api_model":       "gpt-4o-mini",
    },
    "retro_games": {
        "label":           "Jogos Retro",
        "description":     "Pixel art / jogos retro com fontes bitmap",
        "ocr_quality":     "quality",
        "source_language": "en",
        "target_language": "pt-br",
        "api_model":       "gpt-4o-mini",
    },
    "modern_games": {
        "label":           "Jogos Modernos",
        "description":     "Jogos 3D modernos com texto anti-aliased",
        "ocr_quality":     "balanced",
        "source_language": "auto",
        "target_language": "pt-br",
        "api_model":       "gpt-4o-mini",
    },
    "visual_novel": {
        "label":           "Visual Novel",
        "description":     "Visual novels com texto claro em fundos sólidos",
        "ocr_quality":     "fast",
        "source_language": "ja",
        "target_language": "pt-br",
        "api_model":       "gpt-4o",
    },
    "jrpg": {
        "label":           "JRPG",
        "description":     "JRPGs com menus e diálogos",
        "ocr_quality":     "balanced",
        "source_language": "ja",
        "target_language": "pt-br",
        "api_model":       "gpt-4o-mini",
    },
    "pdf_document": {
        "label":           "PDF / Documento",
        "description":     "Livros, PDFs e documentos com texto impresso",
        "ocr_quality":     "pdf",
        "source_language": "en",
        "target_language": "pt-br",
        "api_model":       "gpt-4o-mini",
    },
}

# -- Config defaults -----------------------------------------------------

DEFAULTS = {
    "keyboard_hotkey":        "f1",
    "gamepad_buttons":        [],
    "gamepad_enabled":        False,
    "source_language":        "auto",
    "target_language":        "pt-br",
    "ocr_engine":             "easyocr",
    "ocr_quality":            "balanced",
    "translation_engine":     "openai",
    "api_model":              "gpt-4o-mini",
    "overlay_alpha":          0.13,
    "overlay_always_visible": True,
    "auto_translate":         False,
    "auto_translate_interval": 1,
    "active_profile":         "default",
}

# ---------------------------------------------------------------------------
# Config class
# ---------------------------------------------------------------------------


class Config:
    def __init__(self):
        self.data: dict = {**DEFAULTS}
        self._load()

    # -- persistence -----------------------------------------------------

    def _load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
                logger.info("Config loaded from %s", CONFIG_PATH)
            except Exception as exc:
                logger.warning("Failed to load config: %s", exc)

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        logger.info("Config saved")

    # -- dict-like access ------------------------------------------------

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    # -- profiles --------------------------------------------------------

    def apply_profile(self, profile_name: str):
        preset = GAME_PRESETS.get(profile_name, GAME_PRESETS["default"])
        for key in ("ocr_quality", "source_language", "target_language", "api_model"):
            if key in preset:
                self.data[key] = preset[key]
        self.data["active_profile"] = profile_name
        self.save()
        logger.info("Profile applied: %s", profile_name)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def button_name(btn_id: int) -> str:
        return DUALSENSE_BUTTONS.get(btn_id, f"Btn {btn_id}")

    def combo_text(self) -> str:
        btns = self.data.get("gamepad_buttons", [])
        if not btns:
            return "Nenhum"
        return " + ".join(self.button_name(b) for b in btns)

    def subtitle(self) -> str:
        kb = self.data["keyboard_hotkey"].upper()
        parts = [f"Selecione uma área → {kb}"]
        btns = self.data.get("gamepad_buttons", [])
        if btns:
            parts.append(" + ".join(self.button_name(b) for b in btns))
        return " | ".join(parts) + " para traduzir"
