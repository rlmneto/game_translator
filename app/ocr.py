"""
OCR engine — supports EasyOCR, Tesseract, RapidOCR, and PaddleOCR
with configurable quality presets.
"""

import logging

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .config import EASYOCR_LANG_MAP, TESSERACT_LANG_MAP, OCR_PRESETS

logger = logging.getLogger(__name__)

OCR_ALLOWLIST = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789 .,!?;:'-\"()…"
)

# -- optional imports (graceful degradation) -----------------------------

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from rapidocr_onnxruntime import RapidOCR as _RapidOCR
    RAPIDOCR_AVAILABLE = True
except ImportError:
    RAPIDOCR_AVAILABLE = False

try:
    from paddleocr import PaddleOCR as _PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False


# -- PaddleOCR language map ----------------------------------------------

PADDLEOCR_LANG_MAP: dict[str, str] = {
    "auto": "en", "en": "en", "pt-br": "pt", "es": "es",
    "fr": "fr", "de": "de", "it": "it", "ja": "japan",
    "ko": "korean", "zh-cn": "ch", "zh-tw": "chinese_cht",
    "ru": "ru", "pl": "pl", "nl": "nl", "tr": "tr",
}


class OCREngine:
    def __init__(self):
        self._easyocr_readers: dict[str, object] = {}
        self._rapidocr_engine = None
        self._paddleocr_engines: dict[str, object] = {}
        self._current_engine = "easyocr"
        self._current_quality = "balanced"
        self._current_lang = "auto"

    # -- configuration ---------------------------------------------------

    def configure(self, engine: str | None = None,
                  quality: str | None = None,
                  source_lang: str | None = None):
        if engine is not None:
            self._current_engine = engine
        if quality is not None:
            self._current_quality = quality
        if source_lang is not None:
            self._current_lang = source_lang
        logger.info(
            "OCR configured: engine=%s  quality=%s  lang=%s",
            self._current_engine, self._current_quality, self._current_lang,
        )

    # -- main extraction -------------------------------------------------

    def extract(self, image: Image.Image, *,
                on_status=None,
                engine: str | None = None,
                quality: str | None = None,
                source_lang: str | None = None) -> str:
        eng = engine or self._current_engine
        qual = quality or self._current_quality
        lang = source_lang or self._current_lang

        preset = OCR_PRESETS.get(qual, OCR_PRESETS["balanced"])
        img = self._preprocess(image, preset)

        if on_status:
            on_status("🔍 Reconhecendo texto...")

        # choose engine
        if eng == "tesseract" and TESSERACT_AVAILABLE:
            return self._extract_tesseract(img, lang)
        if eng == "rapidocr" and RAPIDOCR_AVAILABLE:
            return self._extract_rapidocr(img, on_status)
        if eng == "paddleocr" and PADDLEOCR_AVAILABLE:
            return self._extract_paddleocr(img, lang, on_status)
        if eng == "easyocr" and EASYOCR_AVAILABLE:
            return self._extract_easyocr(img, lang, preset, on_status)
        # fall-backs
        if RAPIDOCR_AVAILABLE:
            logger.warning("Engine '%s' unavailable, falling back to RapidOCR", eng)
            return self._extract_rapidocr(img, on_status)
        if EASYOCR_AVAILABLE:
            logger.warning("Engine '%s' unavailable, falling back to EasyOCR", eng)
            return self._extract_easyocr(img, lang, preset, on_status)
        if PADDLEOCR_AVAILABLE:
            logger.warning("Engine '%s' unavailable, falling back to PaddleOCR", eng)
            return self._extract_paddleocr(img, lang, on_status)
        if TESSERACT_AVAILABLE:
            logger.warning("Engine '%s' unavailable, falling back to Tesseract", eng)
            return self._extract_tesseract(img, lang)
        raise RuntimeError("No OCR engine available. Install easyocr, rapidocr-onnxruntime, paddleocr, or pytesseract.")

    # -- EasyOCR ---------------------------------------------------------

    @staticmethod
    def _detect_gpu() -> bool:
        try:
            import torch
            available = torch.cuda.is_available()
            if available:
                logger.info("GPU detected: %s", torch.cuda.get_device_name(0))
            return available
        except ImportError:
            return False

    def _get_easyocr_reader(self, lang_key: str, on_status=None):
        if lang_key not in self._easyocr_readers:
            langs = EASYOCR_LANG_MAP.get(lang_key, ["en"])
            use_gpu = self._detect_gpu()
            if on_status:
                gpu_label = "GPU" if use_gpu else "CPU"
                on_status(f"🔍 Carregando EasyOCR ({', '.join(langs)}) [{gpu_label}]...")
            logger.info("Initialising EasyOCR reader for %s (gpu=%s)", langs, use_gpu)
            self._easyocr_readers[lang_key] = easyocr.Reader(langs, gpu=use_gpu)
        return self._easyocr_readers[lang_key]

    def _extract_easyocr(self, img: Image.Image, lang: str,
                         preset: dict, on_status=None) -> str:
        reader = self._get_easyocr_reader(lang, on_status)
        is_document = preset.get("preprocess") == "document"
        use_allowlist = lang in ("auto", "en") and not is_document
        results = reader.readtext(
            np.array(img),
            detail=1,
            paragraph=True,
            text_threshold=preset["text_threshold"],
            low_text=preset["low_text"],
            contrast_ths=preset["contrast_ths"],
            adjust_contrast=preset["adjust_contrast"],
            allowlist=OCR_ALLOWLIST if use_allowlist else None,
        )
        text = "\n".join(r[1] for r in results).strip()
        logger.info("EasyOCR extracted %d chars (lang=%s)", len(text), lang)
        return text

    # -- Tesseract -------------------------------------------------------

    def _extract_tesseract(self, img: Image.Image, lang: str) -> str:
        tess_lang = TESSERACT_LANG_MAP.get(lang, "eng")
        text = pytesseract.image_to_string(img, lang=tess_lang).strip()
        logger.info("Tesseract extracted %d chars (lang=%s)", len(text), tess_lang)
        return text

    # -- RapidOCR --------------------------------------------------------

    def _get_rapidocr(self):
        if self._rapidocr_engine is None:
            logger.info("Initialising RapidOCR engine")
            self._rapidocr_engine = _RapidOCR()
        return self._rapidocr_engine

    def _extract_rapidocr(self, img: Image.Image, on_status=None) -> str:
        if on_status:
            on_status("🔍 Reconhecendo texto (RapidOCR)...")
        engine = self._get_rapidocr()
        result, _ = engine(np.array(img))
        if not result:
            return ""
        text = "\n".join(line[1] for line in result).strip()
        logger.info("RapidOCR extracted %d chars", len(text))
        return text

    # -- PaddleOCR -------------------------------------------------------

    def _get_paddleocr(self, lang: str, on_status=None):
        paddle_lang = PADDLEOCR_LANG_MAP.get(lang, "en")
        if paddle_lang not in self._paddleocr_engines:
            if on_status:
                on_status(f"🔍 Carregando PaddleOCR ({paddle_lang})...")
            logger.info("Initialising PaddleOCR for lang=%s", paddle_lang)
            self._paddleocr_engines[paddle_lang] = _PaddleOCR(
                use_angle_cls=True, lang=paddle_lang, show_log=False,
            )
        return self._paddleocr_engines[paddle_lang]

    def _extract_paddleocr(self, img: Image.Image, lang: str,
                           on_status=None) -> str:
        if on_status:
            on_status("🔍 Reconhecendo texto (PaddleOCR)...")
        engine = self._get_paddleocr(lang, on_status)
        result = engine.ocr(np.array(img), cls=True)
        if not result or not result[0]:
            return ""
        text = "\n".join(line[1][0] for line in result[0]).strip()
        logger.info("PaddleOCR extracted %d chars (lang=%s)", len(text), lang)
        return text

    # -- preprocessing ---------------------------------------------------

    @staticmethod
    def _preprocess(img: Image.Image, preset: dict) -> Image.Image:
        mode = preset.get("preprocess", "game")
        if mode == "document":
            return OCREngine._preprocess_document(img, preset)
        return OCREngine._preprocess_game(img, preset)

    @staticmethod
    def _preprocess_game(img: Image.Image, preset: dict) -> Image.Image:
        """Preprocessing for game screens: bright text on dark backgrounds."""
        arr = np.array(img)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        mask = (luminance > 130) | ((r > 140) & (g > 140))
        binary = np.where(mask, 255, 0).astype(np.uint8)

        out = Image.fromarray(binary, mode="L")

        scale = preset.get("scale_factor", 4)
        out = out.resize((out.width * scale, out.height * scale), Image.LANCZOS)

        blur = preset.get("blur_radius", 1.5)
        out = out.filter(ImageFilter.GaussianBlur(radius=blur))
        out = out.point(lambda p: 255 if p > 80 else 0)
        out = out.filter(ImageFilter.MaxFilter(size=3))
        return ImageOps.invert(out)

    @staticmethod
    def _preprocess_document(img: Image.Image, preset: dict) -> Image.Image:
        """Preprocessing for documents/PDFs: dark text on light backgrounds.

        Uses minimal processing to preserve letter shapes that aggressive
        game-oriented binarization would destroy.  Handles both large bold
        headings and small body text.
        """
        # Convert to grayscale
        gray = img.convert("L")

        # Auto-contrast to normalise brightness & improve readability
        gray = ImageOps.autocontrast(gray, cutoff=0.5)

        # Scale up so thin strokes in small text survive binarization
        scale = preset.get("scale_factor", 3)
        if scale > 1:
            gray = gray.resize(
                (gray.width * scale, gray.height * scale), Image.LANCZOS,
            )

        # Light sharpening to crisp up edges
        gray = gray.filter(ImageFilter.SHARPEN)

        # Local adaptive thresholding ---------------------------------
        # A single global threshold fails when the page has both heavy
        # headings and thin body text.  We approximate local adaptive
        # thresholding by comparing each pixel to a heavily-blurred
        # (local-mean) version of itself.
        arr = np.array(gray, dtype=np.float32)

        # Local mean via large-radius box blur (kernel ~1/15 of height)
        radius = max(arr.shape[0] // 15, 15)
        local_mean = np.array(
            Image.fromarray(arr.astype(np.uint8), mode="L")
            .filter(ImageFilter.BoxBlur(radius)),
            dtype=np.float32,
        )

        # Pixel is "ink" when it is noticeably darker than its surround
        offset = 12                       # sensitivity — lower = more text kept
        binary = np.where(arr < local_mean - offset, 0, 255).astype(np.uint8)

        return Image.fromarray(binary, mode="L")

    # -- class helpers ---------------------------------------------------

    @staticmethod
    def available_engines() -> list[str]:
        engines: list[str] = []
        if EASYOCR_AVAILABLE:
            engines.append("easyocr")
        if TESSERACT_AVAILABLE:
            engines.append("tesseract")
        if RAPIDOCR_AVAILABLE:
            engines.append("rapidocr")
        if PADDLEOCR_AVAILABLE:
            engines.append("paddleocr")
        return engines
