import threading
import tkinter as tk
from tkinter import scrolledtext

import mss
from PIL import Image

from .config import Config
from .input import InputManager
from .ocr import OCREngine
from .overlay import MonitorOverlay, ScreenSelector
from .translation import TranslationService

# -- Theme constants --
BG = "#1e1e2e"
BG_DARK = "#181825"
BG_SURFACE = "#313244"
BG_MUTED = "#585b70"
FG = "#cdd6f4"
FG_DIM = "#6c7086"
BLUE = "#89b4fa"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
RED = "#f38ba8"
PEACH = "#fab387"
ROSEWATER = "#f5e0dc"
PINK = "#f5c2e7"
TEAL = "#94e2d5"


class App:
    def __init__(self):
        self.config = Config()
        self.ocr = OCREngine()
        self.translator = TranslationService()
        self.selected_area = None
        self.last_text = ""
        self.is_busy = False

        self._build_gui()

        self.selector = ScreenSelector(self.root, self._on_area_selected)
        self.overlay = MonitorOverlay(self.root)
        self.input = InputManager(self.config, self._capture_and_translate, self.root)
        self.input.setup_hotkey()
        self.input.setup_gamepad()

        self._status(
            "Token carregado ✓" if self.translator.is_ready
            else "⚠ Configure o GITHUB_TOKEN no .env"
        )

    # -- GUI Build -------------------------------------------------------

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("🎮 Game Screen Translator")
        self.root.geometry("520x680+60+60")
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Header
        tk.Label(
            self.root, text="🎮  Game Screen Translator",
            font=("Segoe UI", 15, "bold"), fg=BLUE, bg=BG,
        ).pack(pady=(10, 2))

        self.subtitle_label = tk.Label(
            self.root, text=self.config.subtitle(),
            font=("Segoe UI", 9), fg=FG_DIM, bg=BG,
        )
        self.subtitle_label.pack()

        self._build_shortcuts_frame()
        self._build_buttons()
        self._build_text_areas()

        # Status bar
        self.status_var = tk.StringVar(value="Pronto")
        tk.Label(
            self.root, textvariable=self.status_var,
            fg=FG_DIM, bg=BG_DARK, anchor="w",
            font=("Segoe UI", 9), padx=6, pady=3,
        ).pack(fill="x", side="bottom")

    def _build_shortcuts_frame(self):
        frame = tk.LabelFrame(
            self.root, text="⌨  Atalhos", fg=FG, bg=BG,
            font=("Segoe UI", 9, "bold"), relief="flat", bd=1,
        )
        frame.pack(fill="x", padx=12, pady=(6, 2))

        # Keyboard row
        kb_row = tk.Frame(frame, bg=BG)
        kb_row.pack(fill="x", padx=8, pady=3)
        tk.Label(kb_row, text="Teclado:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=10, anchor="w").pack(side="left")
        self.hotkey_label = tk.Label(
            kb_row, text=self.config["keyboard_hotkey"].upper(),
            fg=YELLOW, bg=BG_SURFACE, font=("Consolas", 10, "bold"),
            width=14, relief="flat", padx=4,
        )
        self.hotkey_label.pack(side="left", padx=(0, 6))
        self.hotkey_btn = tk.Button(
            kb_row, text="Gravar tecla", command=self._record_hotkey,
            bg=BG_MUTED, fg=FG, activebackground=FG_DIM,
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
        )
        self.hotkey_btn.pack(side="left")

        # Gamepad row
        gp_row = tk.Frame(frame, bg=BG)
        gp_row.pack(fill="x", padx=8, pady=(3, 6))
        tk.Label(gp_row, text="Controle:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=10, anchor="w").pack(side="left")
        self.gamepad_label = tk.Label(
            gp_row, text=self.config.combo_text(),
            fg=BLUE, bg=BG_SURFACE, font=("Consolas", 10, "bold"),
            width=14, relief="flat", padx=4,
        )
        self.gamepad_label.pack(side="left", padx=(0, 6))
        self.gamepad_btn = tk.Button(
            gp_row, text="Gravar combo", command=self._record_gamepad,
            bg=BG_MUTED, fg=FG, activebackground=FG_DIM,
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
            state="normal" if InputManager.PYGAME_AVAILABLE else "disabled",
        )
        self.gamepad_btn.pack(side="left")
        if not InputManager.PYGAME_AVAILABLE:
            tk.Label(gp_row, text="(instale pygame)", fg=RED, bg=BG,
                     font=("Segoe UI", 8)).pack(side="left", padx=4)

    def _build_buttons(self):
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="x", padx=12, pady=10)

        tk.Button(
            frame, text="📐  Selecionar Área",
            command=lambda: self.selector.open(),
            bg=GREEN, fg=BG, activebackground=TEAL, relief="flat",
            font=("Segoe UI", 11, "bold"), padx=14, pady=4, cursor="hand2",
        ).pack(side="left", padx=(0, 6))

        hotkey = self.config["keyboard_hotkey"].upper()
        self.capture_btn = tk.Button(
            frame, text=f"📸  Capturar ({hotkey})",
            command=self._capture_and_translate,
            bg=YELLOW, fg=BG, activebackground=PINK, relief="flat",
            font=("Segoe UI", 11, "bold"), padx=14, pady=4,
            state="disabled", cursor="hand2",
        )
        self.capture_btn.pack(side="left", padx=(0, 6))

        tk.Button(
            frame, text="✕", command=self._clear,
            bg=RED, fg=BG, activebackground="#eba0ac", relief="flat",
            font=("Segoe UI", 11, "bold"), padx=8, pady=4, cursor="hand2",
        ).pack(side="left")

        self.area_label = tk.Label(
            self.root, text="Nenhuma área selecionada",
            fg=FG_DIM, bg=BG, font=("Segoe UI", 9),
        )
        self.area_label.pack(pady=2)

    def _build_text_areas(self):
        tk.Label(self.root, text="Texto Original (EN):", fg=PEACH, bg=BG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12)
        self.original_text = scrolledtext.ScrolledText(
            self.root, height=4, wrap="word", bg=BG_SURFACE, fg=FG,
            font=("Consolas", 11), relief="flat",
            insertbackground=FG, borderwidth=0,
        )
        self.original_text.pack(fill="x", padx=12, pady=(0, 8))

        tk.Label(self.root, text="Tradução (PT-BR):", fg=GREEN, bg=BG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12)
        self.translated_text = scrolledtext.ScrolledText(
            self.root, height=8, wrap="word", bg=BG_SURFACE, fg=ROSEWATER,
            font=("Segoe UI", 13), relief="flat",
            insertbackground=FG, borderwidth=0,
        )
        self.translated_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    # -- Actions ---------------------------------------------------------

    def _on_area_selected(self, area):
        self.selected_area = area
        x, y, w, h = area
        self.area_label.config(text=f"Área: ({x}, {y})  {w}×{h} px", fg=GREEN)
        self.capture_btn.config(state="normal")
        self.overlay.show(area)
        self._status("Área selecionada ✓  —  Pressione hotkey para capturar")

    def _clear(self):
        self.overlay.destroy()
        self.selected_area = None
        self.capture_btn.config(state="disabled")
        self.area_label.config(text="Nenhuma área selecionada", fg=FG_DIM)
        self._status("Overlay removido")

    def _capture_and_translate(self):
        if not self.selected_area:
            self._status("⚠ Selecione uma área primeiro")
            return
        if self.is_busy:
            return
        self.is_busy = True
        self._status("📸 Capturando tela...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            # Screenshot
            x, y, w, h = self.selected_area
            with mss.mss() as sct:
                shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            # OCR
            text = self.ocr.extract(img, on_status=self._status_safe)
            self.root.after(0, lambda: self._set_text(self.original_text, text))

            if not text:
                self._status_safe("⚠ Nenhum texto detectado")
                return
            if text == self.last_text:
                self._status_safe("ℹ Mesmo texto — tradução mantida")
                return
            self.last_text = text

            # Translation
            self._status_safe("🌐 Traduzindo...")
            if not self.translator.is_ready:
                self._status_safe("⚠ Configure o GitHub Token primeiro!")
                return

            corrected, translation = self.translator.translate(text)
            self.root.after(0, lambda: self._set_text(self.original_text, corrected))
            self.root.after(0, lambda: self._set_text(self.translated_text, translation))
            self._status_safe("✓ Tradução concluída!")

        except Exception as exc:
            msg = str(exc)
            if "content_filter" in msg or "ResponsibleAI" in msg:
                self._status_safe("⚠ Filtro de conteúdo ativado — tente novamente")
            else:
                self._status_safe(f"❌ Erro: {exc}")
        finally:
            self.is_busy = False

    # -- Hotkey recording ------------------------------------------------

    def _record_hotkey(self):
        self.hotkey_btn.config(text="Pressione...", bg=RED)
        self._status("Pressione a tecla desejada")
        self.input.record_hotkey(self._on_hotkey_recorded)

    def _on_hotkey_recorded(self):
        key = self.config["keyboard_hotkey"].upper()
        self.hotkey_label.config(text=key)
        self.hotkey_btn.config(text="Gravar tecla", bg=BG_MUTED)
        self.capture_btn.config(text=f"📸  Capturar ({key})")
        self.subtitle_label.config(text=self.config.subtitle())
        self.input.setup_hotkey()
        self._status(f"Tecla alterada para {key} ✓")

    def _record_gamepad(self):
        self.gamepad_btn.config(text="Solte p/ salvar", bg=RED)
        self._status("Pressione e segure os botões. Solte para salvar.")
        self.input.record_gamepad(self._on_gamepad_update, self._on_gamepad_done)

    def _on_gamepad_update(self):
        names = [self.config.button_name(b) for b in self.input.gamepad_combo_buf]
        self.gamepad_label.config(text=" + ".join(names))

    def _on_gamepad_done(self):
        self.gamepad_label.config(text=self.config.combo_text())
        self.gamepad_btn.config(text="Gravar combo", bg=BG_MUTED)
        self.subtitle_label.config(text=self.config.subtitle())
        self._status(f"Combo salvo: {self.config.combo_text()} ✓")

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _set_text(widget, text):
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def _status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _status_safe(self, msg):
        self.root.after(0, lambda: self._status(msg))

    def _on_close(self):
        self.input.stop()
        self.overlay.destroy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
