import numpy as np
import easyocr
from PIL import Image, ImageFilter, ImageOps

OCR_ALLOWLIST = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789 .,!?;:'-\"()…"
)


class OCREngine:
    def __init__(self):
        self._reader = None

    def _ensure_reader(self, on_status=None):
        if self._reader is None:
            if on_status:
                on_status("🔍 Carregando EasyOCR (primeira vez demora ~30s)...")
            self._reader = easyocr.Reader(["en"], gpu=False)

    def extract(self, image: Image.Image, on_status=None) -> str:
        img = self._preprocess(image)
        img.save("_debug_ocr.png")

        if on_status:
            on_status("🔍 Reconhecendo texto...")
        self._ensure_reader(on_status)

        results = self._reader.readtext(
            np.array(img),
            detail=1, paragraph=True,
            text_threshold=0.5, low_text=0.3,
            contrast_ths=0.3, adjust_contrast=0.7,
            allowlist=OCR_ALLOWLIST,
        )
        return "\n".join(r[1] for r in results).strip()

    @staticmethod
    def _preprocess(img: Image.Image) -> Image.Image:
        arr = np.array(img)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        mask = (luminance > 130) | ((r > 140) & (g > 140))
        binary = np.where(mask, 255, 0).astype(np.uint8)

        img = Image.fromarray(binary, mode="L")
        img = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
        img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
        img = img.point(lambda p: 255 if p > 80 else 0)
        img = img.filter(ImageFilter.MaxFilter(size=3))
        return ImageOps.invert(img)
