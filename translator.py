"""
Game Screen Translator — Entry Point
Captura uma área da tela, reconhece texto via OCR e traduz entre idiomas.
"""

import ctypes
import logging
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Structured logging  (file + console)
# ---------------------------------------------------------------------------

LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "translator.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DPI Awareness (must run before any window creation)
# ---------------------------------------------------------------------------

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---------------------------------------------------------------------------

from app.gui import App  # noqa: E402  (must import after logging is configured)

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Game Screen Translator starting — %s", datetime.now().isoformat())
    logger.info("=" * 60)
    try:
        App().run()
    except Exception:
        logger.exception("Fatal error")
        raise
