"""
Game Screen Translator — Entry Point
Captura uma área da tela, reconhece texto (OCR) e traduz EN → PT-BR.
"""

import ctypes

# DPI Awareness (deve rodar antes de criar qualquer janela)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from app.gui import App

if __name__ == "__main__":
    App().run()
