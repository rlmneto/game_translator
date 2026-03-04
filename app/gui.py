"""
Main GUI — full-featured Game Screen Translator interface.

Features: multi-language, profiles, auto-translate toggle, translation
history, export, overlay transparency, multiple capture areas, settings panel.
"""

import logging
import threading
import time as _time
import tkinter as tk
from tkinter import filedialog, scrolledtext

import mss
from PIL import Image

from .config import (
    Config,
    SOURCE_LANGUAGES,
    TARGET_LANGUAGES,
    API_MODELS,
    OCR_ENGINES,
    OCR_QUALITY_OPTIONS,
    OCR_PRESETS,
    GAME_PRESETS,
    TRANSLATION_ENGINES,
)
from .history import TranslationHistory
from .input import InputManager
from .ocr import OCREngine
from .overlay import MonitorOverlay, ScreenSelector, TextOverlay
from .translation import TranslationService
from .tts import TTSEngine

logger = logging.getLogger(__name__)

# -- Theme (Catppuccin Mocha) -------------------------------------------

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
LAVENDER = "#b4befe"
MAUVE = "#cba6f7"

OVERLAY_COLORS = ["#0055ff", "#00aa55", "#aa5500", "#5500aa", "#aa0055"]
OVERLAY_BORDERS = ["#89b4fa", "#a6e3a1", "#fab387", "#cba6f7", "#f5c2e7"]


class App:
    """Application controller & GUI builder."""

    def __init__(self):
        self.config = Config()
        self.ocr = OCREngine()
        self.translator = TranslationService()
        self.history = TranslationHistory()
        self.tts = TTSEngine()

        self.capture_areas: list[tuple] = []
        self.last_text = ""
        self.is_busy = False

        self._auto_translate_active = False
        self._auto_job_id = None
        self._settings_visible = False
        self._history_window = None

        # auto-translate: change-detection state
        self._last_screen_hash: str | None = None
        self._screen_translated: bool = False
        self._stable_since: float = 0.0
        self._rehash_pending: bool = False   # recapture hash after overlay shown

        # apply persisted settings to services
        self.ocr.configure(
            engine=self.config["ocr_engine"],
            quality=self.config["ocr_quality"],
            source_lang=self.config["source_language"],
        )
        # determine content type from saved OCR quality
        _init_preset = OCR_PRESETS.get(
            self.config["ocr_quality"], OCR_PRESETS["balanced"],
        )
        _init_content = (
            "document" if _init_preset.get("preprocess") == "document" else "game"
        )
        self.translator.configure(
            model=self.config["api_model"],
            source_lang=self.config["source_language"],
            target_lang=self.config["target_language"],
            engine=self.config.get("translation_engine", "openai"),
            content_type=_init_content,
        )

        self._build_gui()

        self.selector = ScreenSelector(self.root, self._on_area_selected)
        self.overlay = MonitorOverlay(
            self.root,
            alpha=self.config["overlay_alpha"],
            always_visible=self.config.get("overlay_always_visible", True),
        )
        self.text_overlay = TextOverlay(
            self.root, bg_color="#3b3b4f", alpha=0.82, font_size=18,
        )
        self._text_overlay_enabled = self.config.get("text_overlay", False)
        self.input = InputManager(
            self.config, self._capture_and_translate, self.root,
        )
        self.input.setup_hotkey()
        self.input.setup_gamepad()

        self._status(
            "Token carregado ✓" if self.translator.is_ready
            else "⚠ Configure o GITHUB_TOKEN no .env"
        )
        logger.info("Application initialised")

    def run(self):
        self.root.mainloop()

    # ===================================================================
    # GUI construction
    # ===================================================================

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("🎮 Game Screen Translator")
        self.root.geometry("580x900+60+60")
        self.root.minsize(520, 700)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # header
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
        self._build_settings_toggle()
        self._build_settings_frame()   # created hidden
        self._build_buttons()
        self._build_text_areas()
        self._build_bottom_bar()

        # status bar (pinned to bottom via side="bottom")
        self.status_var = tk.StringVar(value="Pronto")
        tk.Label(
            self.root, textvariable=self.status_var,
            fg=FG_DIM, bg=BG_DARK, anchor="w",
            font=("Segoe UI", 9), padx=6, pady=3,
        ).pack(fill="x", side="bottom")

        # F2 → speak translation aloud
        self.root.bind_all("<F2>", lambda e: self._speak_translation())

    # -- shortcuts -------------------------------------------------------

    def _build_shortcuts_frame(self):
        frame = tk.LabelFrame(
            self.root, text="⌨  Atalhos", fg=FG, bg=BG,
            font=("Segoe UI", 9, "bold"), relief="flat", bd=1,
        )
        frame.pack(fill="x", padx=12, pady=(6, 2))

        # keyboard row
        kb = tk.Frame(frame, bg=BG)
        kb.pack(fill="x", padx=8, pady=3)
        tk.Label(kb, text="Teclado:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=10, anchor="w").pack(side="left")
        self.hotkey_label = tk.Label(
            kb, text=self.config["keyboard_hotkey"].upper(),
            fg=YELLOW, bg=BG_SURFACE, font=("Consolas", 10, "bold"),
            width=14, relief="flat", padx=4,
        )
        self.hotkey_label.pack(side="left", padx=(0, 6))
        self.hotkey_btn = tk.Button(
            kb, text="Gravar tecla", command=self._record_hotkey,
            bg=BG_MUTED, fg=FG, activebackground=FG_DIM,
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
        )
        self.hotkey_btn.pack(side="left")

        # gamepad row
        gp = tk.Frame(frame, bg=BG)
        gp.pack(fill="x", padx=8, pady=(3, 6))
        tk.Label(gp, text="Controle:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=10, anchor="w").pack(side="left")
        self.gamepad_label = tk.Label(
            gp, text=self.config.combo_text(),
            fg=BLUE, bg=BG_SURFACE, font=("Consolas", 10, "bold"),
            width=14, relief="flat", padx=4,
        )
        self.gamepad_label.pack(side="left", padx=(0, 6))
        self.gamepad_btn = tk.Button(
            gp, text="Gravar combo", command=self._record_gamepad,
            bg=BG_MUTED, fg=FG, activebackground=FG_DIM,
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
            state="normal" if InputManager.PYGAME_AVAILABLE else "disabled",
        )
        self.gamepad_btn.pack(side="left")
        if not InputManager.PYGAME_AVAILABLE:
            tk.Label(gp, text="(instale pygame)", fg=RED, bg=BG,
                     font=("Segoe UI", 8)).pack(side="left", padx=4)

    # -- settings toggle -------------------------------------------------

    def _build_settings_toggle(self):
        self._settings_btn = tk.Button(
            self.root, text="⚙  Configurações  ▼",
            command=self._toggle_settings,
            bg=BG_SURFACE, fg=FG, activebackground=BG_MUTED,
            relief="flat", font=("Segoe UI", 9, "bold"),
            cursor="hand2", padx=8, pady=2,
        )
        self._settings_btn.pack(fill="x", padx=12, pady=(6, 0))

    # -- settings panel --------------------------------------------------

    def _build_settings_frame(self):
        self._settings_frame = tk.LabelFrame(
            self.root, text="", fg=FG, bg=BG,
            font=("Segoe UI", 9), relief="flat", bd=1,
        )
        # NOT packed yet — toggled by button

        # reverse-lookups for OptionMenu ↔ config keys
        self._src_name2code = {v: k for k, v in SOURCE_LANGUAGES.items()}
        self._tgt_name2code = {v: k for k, v in TARGET_LANGUAGES.items()}
        self._profile_name2code = {v["label"]: k for k, v in GAME_PRESETS.items()}
        self._quality_name2code = {v: k for k, v in OCR_QUALITY_OPTIONS.items()}
        self._engine_name2code = {v: k for k, v in OCR_ENGINES.items()}

        # --- row 1: languages ---
        r1 = tk.Frame(self._settings_frame, bg=BG)
        r1.pack(fill="x", padx=8, pady=3)

        tk.Label(r1, text="Origem:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=9, anchor="w").pack(side="left")
        self._src_var = tk.StringVar(
            value=SOURCE_LANGUAGES.get(self.config["source_language"], "Auto-detectar"),
        )
        self._src_var.trace_add("write", self._on_source_change)
        self._styled_om(r1, self._src_var, *SOURCE_LANGUAGES.values()).pack(
            side="left", padx=(0, 10),
        )

        tk.Label(r1, text="Destino:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=8, anchor="w").pack(side="left")
        self._tgt_var = tk.StringVar(
            value=TARGET_LANGUAGES.get(self.config["target_language"], "Português (BR)"),
        )
        self._tgt_var.trace_add("write", self._on_target_change)
        self._styled_om(r1, self._tgt_var, *TARGET_LANGUAGES.values()).pack(
            side="left",
        )

        # --- row 2: OCR engine & quality ---
        r2 = tk.Frame(self._settings_frame, bg=BG)
        r2.pack(fill="x", padx=8, pady=3)

        tk.Label(r2, text="OCR:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=9, anchor="w").pack(side="left")
        self._engine_var = tk.StringVar(
            value=OCR_ENGINES.get(self.config["ocr_engine"], "EasyOCR"),
        )
        self._engine_var.trace_add("write", self._on_engine_change)
        avail = OCREngine.available_engines()
        engine_names = [OCR_ENGINES[e] for e in avail] or ["EasyOCR"]
        self._styled_om(r2, self._engine_var, *engine_names).pack(
            side="left", padx=(0, 10),
        )

        tk.Label(r2, text="Qualidade:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=8, anchor="w").pack(side="left")
        self._quality_var = tk.StringVar(
            value=OCR_QUALITY_OPTIONS.get(self.config["ocr_quality"], "Balanceado"),
        )
        self._quality_var.trace_add("write", self._on_quality_change)
        self._styled_om(r2, self._quality_var, *OCR_QUALITY_OPTIONS.values()).pack(
            side="left",
        )

        # --- row 3: translation engine, model & profile ---
        r3 = tk.Frame(self._settings_frame, bg=BG)
        r3.pack(fill="x", padx=8, pady=3)

        tk.Label(r3, text="Tradutor:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=9, anchor="w").pack(side="left")
        self._trans_engine_name2code = {v: k for k, v in TRANSLATION_ENGINES.items()}
        cur_trans_engine = self.config.get("translation_engine", "openai")
        self._trans_engine_var = tk.StringVar(
            value=TRANSLATION_ENGINES.get(cur_trans_engine, "OpenAI (GitHub)"),
        )
        self._trans_engine_var.trace_add("write", self._on_trans_engine_change)
        avail_trans = TranslationService.available_engines()
        trans_names = [TRANSLATION_ENGINES[e] for e in avail_trans if e in TRANSLATION_ENGINES] or list(TRANSLATION_ENGINES.values())
        self._styled_om(r3, self._trans_engine_var, *trans_names).pack(
            side="left", padx=(0, 10),
        )

        tk.Label(r3, text="Modelo:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=7, anchor="w").pack(side="left")
        self._model_var = tk.StringVar(value=self.config["api_model"])
        self._model_var.trace_add("write", self._on_model_change)
        self._styled_om(r3, self._model_var, *API_MODELS).pack(
            side="left", padx=(0, 10),
        )

        # --- row 3b: profile ---
        r3b = tk.Frame(self._settings_frame, bg=BG)
        r3b.pack(fill="x", padx=8, pady=3)

        tk.Label(r3b, text="Perfil:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=9, anchor="w").pack(side="left")
        profile_labels = [p["label"] for p in GAME_PRESETS.values()]
        active = self.config.get("active_profile", "default")
        active_label = GAME_PRESETS.get(active, GAME_PRESETS["default"])["label"]
        self._profile_var = tk.StringVar(value=active_label)
        self._profile_var.trace_add("write", self._on_profile_change)
        self._styled_om(r3b, self._profile_var, *profile_labels).pack(side="left")

        # --- row 4: overlay transparency + always visible ---
        r4 = tk.Frame(self._settings_frame, bg=BG)
        r4.pack(fill="x", padx=8, pady=3)

        tk.Label(r4, text="Overlay:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=9, anchor="w").pack(side="left")
        self._alpha_var = tk.DoubleVar(value=self.config["overlay_alpha"])
        tk.Scale(
            r4, from_=0.01, to=0.50, resolution=0.01,
            orient="horizontal", variable=self._alpha_var,
            command=self._on_alpha_change, length=140,
            bg=BG, fg=FG, troughcolor=BG_SURFACE,
            highlightbackground=BG, font=("Segoe UI", 8),
        ).pack(side="left", padx=(0, 8))

        self._always_vis_var = tk.BooleanVar(
            value=self.config.get("overlay_always_visible", True),
        )
        tk.Checkbutton(
            r4, text="Sempre visível", variable=self._always_vis_var,
            command=self._on_always_vis_change,
            bg=BG, fg=FG, selectcolor=BG_SURFACE,
            activebackground=BG, activeforeground=FG,
            font=("Segoe UI", 9),
        ).pack(side="left")

        self._text_overlay_var = tk.BooleanVar(
            value=self.config.get("text_overlay", False),
        )
        tk.Checkbutton(
            r4, text="Sobrescrever texto", variable=self._text_overlay_var,
            command=self._on_text_overlay_change,
            bg=BG, fg=FG, selectcolor=BG_SURFACE,
            activebackground=BG, activeforeground=FG,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(10, 0))

        # --- row 5: auto-translate interval ---
        r5 = tk.Frame(self._settings_frame, bg=BG)
        r5.pack(fill="x", padx=8, pady=(3, 6))

        tk.Label(r5, text="Intervalo:", fg=FG, bg=BG,
                 font=("Segoe UI", 9), width=9, anchor="w").pack(side="left")
        self._interval_var = tk.IntVar(
            value=self.config.get("auto_translate_interval", 3),
        )
        tk.Scale(
            r5, from_=1, to=15, resolution=1,
            orient="horizontal", variable=self._interval_var,
            command=self._on_interval_change, length=140,
            bg=BG, fg=FG, troughcolor=BG_SURFACE,
            highlightbackground=BG, font=("Segoe UI", 8),
        ).pack(side="left", padx=(0, 4))
        tk.Label(r5, text="seg (auto-traduzir)", fg=FG_DIM, bg=BG,
                 font=("Segoe UI", 8)).pack(side="left")

    # -- action buttons --------------------------------------------------

    def _build_buttons(self):
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="x", padx=12, pady=(10, 0))

        tk.Button(
            frame, text="📐  Selecionar Área",
            command=lambda: self.selector.open(),
            bg=GREEN, fg=BG, activebackground=TEAL, relief="flat",
            font=("Segoe UI", 10, "bold"), padx=10, pady=4, cursor="hand2",
        ).pack(side="left", padx=(0, 4))

        hotkey = self.config["keyboard_hotkey"].upper()
        self.capture_btn = tk.Button(
            frame, text=f"📸  Capturar ({hotkey})",
            command=self._capture_and_translate,
            bg=YELLOW, fg=BG, activebackground=PINK, relief="flat",
            font=("Segoe UI", 10, "bold"), padx=10, pady=4,
            state="disabled", cursor="hand2",
        )
        self.capture_btn.pack(side="left", padx=(0, 4))

        self._auto_btn = tk.Button(
            frame, text="🔄 Auto",
            command=self._toggle_auto_translate,
            bg=BG_MUTED, fg=FG, activebackground=FG_DIM, relief="flat",
            font=("Segoe UI", 10, "bold"), padx=10, pady=4,
            state="disabled", cursor="hand2",
        )
        self._auto_btn.pack(side="left", padx=(0, 4))

        self._tts_btn = tk.Button(
            frame, text="🔊",
            command=self._speak_translation,
            bg=LAVENDER, fg=BG, activebackground=MAUVE, relief="flat",
            font=("Segoe UI", 10, "bold"), padx=8, pady=4, cursor="hand2",
        )
        self._tts_btn.pack(side="left", padx=(0, 4))

        tk.Button(
            frame, text="✕", command=self._clear,
            bg=RED, fg=BG, activebackground="#eba0ac", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=8, pady=4, cursor="hand2",
        ).pack(side="left")

        self.area_label = tk.Label(
            self.root, text="Nenhuma área selecionada",
            fg=FG_DIM, bg=BG, font=("Segoe UI", 9),
        )
        self.area_label.pack(pady=2)

    # -- text areas ------------------------------------------------------

    def _build_text_areas(self):
        src_code = self.config["source_language"]
        src_name = SOURCE_LANGUAGES.get(src_code, src_code)
        self._orig_label = tk.Label(
            self.root, text=f"Texto Original ({src_name}):",
            fg=PEACH, bg=BG, font=("Segoe UI", 10, "bold"),
        )
        self._orig_label.pack(anchor="w", padx=12)
        self.original_text = scrolledtext.ScrolledText(
            self.root, height=4, wrap="word", bg=BG_SURFACE, fg=FG,
            font=("Consolas", 11), relief="flat",
            insertbackground=FG, borderwidth=0,
        )
        self.original_text.pack(fill="x", padx=12, pady=(0, 8))

        tgt_code = self.config["target_language"]
        tgt_name = TARGET_LANGUAGES.get(tgt_code, tgt_code)
        self._trans_label = tk.Label(
            self.root, text=f"Tradução ({tgt_name}):",
            fg=GREEN, bg=BG, font=("Segoe UI", 10, "bold"),
        )
        self._trans_label.pack(anchor="w", padx=12)
        self.translated_text = scrolledtext.ScrolledText(
            self.root, height=8, wrap="word", bg=BG_SURFACE, fg=ROSEWATER,
            font=("Segoe UI", 13), relief="flat",
            insertbackground=FG, borderwidth=0,
        )
        self.translated_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    # -- bottom bar (history / export) -----------------------------------

    def _build_bottom_bar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=12, pady=(0, 4))

        tk.Button(
            bar, text="📜 Histórico", command=self._show_history,
            bg=BG_SURFACE, fg=FG, activebackground=BG_MUTED,
            relief="flat", font=("Segoe UI", 9), cursor="hand2", padx=6,
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            bar, text="💾 Exportar", command=self._export_translations,
            bg=BG_SURFACE, fg=FG, activebackground=BG_MUTED,
            relief="flat", font=("Segoe UI", 9), cursor="hand2", padx=6,
        ).pack(side="left", padx=(0, 4))

        self._cache_label = tk.Label(
            bar, text=f"Cache: {self.translator.cache.size}",
            fg=FG_DIM, bg=BG, font=("Segoe UI", 8),
        )
        self._cache_label.pack(side="right")

        self._hist_count = tk.Label(
            bar, text=f"Histórico: {self.history.count}",
            fg=FG_DIM, bg=BG, font=("Segoe UI", 8),
        )
        self._hist_count.pack(side="right", padx=(0, 12))

    # ===================================================================
    # Settings callbacks
    # ===================================================================

    def _toggle_settings(self):
        if self._settings_visible:
            self._settings_frame.pack_forget()
            self._settings_btn.config(text="⚙  Configurações  ▼")
        else:
            self._settings_frame.pack(
                fill="x", padx=12, pady=(2, 0), after=self._settings_btn,
            )
            self._settings_btn.config(text="⚙  Configurações  ▲")
        self._settings_visible = not self._settings_visible

    def _on_source_change(self, *_):
        code = self._src_name2code.get(self._src_var.get(), "auto")
        self.config["source_language"] = code
        self.config.save()
        self.ocr.configure(source_lang=code)
        self.translator.configure(source_lang=code)
        self._orig_label.config(
            text=f"Texto Original ({self._src_var.get()}):",
        )
        logger.info("Source language → %s", code)

    def _on_target_change(self, *_):
        code = self._tgt_name2code.get(self._tgt_var.get(), "pt-br")
        self.config["target_language"] = code
        self.config.save()
        self.translator.configure(target_lang=code)
        self._trans_label.config(text=f"Tradução ({self._tgt_var.get()}):")
        logger.info("Target language → %s", code)

    def _on_engine_change(self, *_):
        code = self._engine_name2code.get(self._engine_var.get(), "easyocr")
        self.config["ocr_engine"] = code
        self.config.save()
        self.ocr.configure(engine=code)
        logger.info("OCR engine → %s", code)

    def _on_quality_change(self, *_):
        code = self._quality_name2code.get(self._quality_var.get(), "balanced")
        self.config["ocr_quality"] = code
        self.config.save()
        self.ocr.configure(quality=code)
        # update translator content type based on preset
        preset = OCR_PRESETS.get(code, OCR_PRESETS["balanced"])
        content_type = "document" if preset.get("preprocess") == "document" else "game"
        self.translator.configure(content_type=content_type)
        logger.info("OCR quality → %s (content_type=%s)", code, content_type)

    def _on_model_change(self, *_):
        model = self._model_var.get()
        self.config["api_model"] = model
        self.config.save()
        self.translator.configure(model=model)
        logger.info("API model → %s", model)

    def _on_trans_engine_change(self, *_):
        code = self._trans_engine_name2code.get(self._trans_engine_var.get(), "openai")
        self.config["translation_engine"] = code
        self.config.save()
        self.translator.configure(engine=code)
        self._status(f"Tradutor: {self._trans_engine_var.get()}")
        logger.info("Translation engine → %s", code)

    def _on_profile_change(self, *_):
        label = self._profile_var.get()
        code = self._profile_name2code.get(label, "default")
        preset = GAME_PRESETS.get(code, GAME_PRESETS["default"])
        self.config.apply_profile(code)

        # sync widgets
        self._src_var.set(
            SOURCE_LANGUAGES.get(preset["source_language"], "Auto-detectar"),
        )
        self._tgt_var.set(
            TARGET_LANGUAGES.get(preset["target_language"], "Português (BR)"),
        )
        self._quality_var.set(
            OCR_QUALITY_OPTIONS.get(preset["ocr_quality"], "Balanceado"),
        )
        self._model_var.set(preset.get("api_model", "gpt-4o-mini"))

        self.ocr.configure(
            quality=preset["ocr_quality"],
            source_lang=preset["source_language"],
        )
        # determine content type from OCR preset
        ocr_preset = OCR_PRESETS.get(preset["ocr_quality"], OCR_PRESETS["balanced"])
        content_type = "document" if ocr_preset.get("preprocess") == "document" else "game"
        self.translator.configure(
            model=preset.get("api_model", "gpt-4o-mini"),
            source_lang=preset["source_language"],
            target_lang=preset["target_language"],
            content_type=content_type,
        )
        self._status(f"Perfil aplicado: {label} ✓")

    def _on_alpha_change(self, value):
        alpha = float(value)
        self.config["overlay_alpha"] = alpha
        self.config.save()
        self.overlay.alpha = alpha

    def _on_always_vis_change(self):
        vis = self._always_vis_var.get()
        self.config["overlay_always_visible"] = vis
        self.config.save()
        self.overlay.always_visible = vis

    def _on_text_overlay_change(self):
        enabled = self._text_overlay_var.get()
        self._text_overlay_enabled = enabled
        self.config["text_overlay"] = enabled
        self.config.save()
        if not enabled:
            self.text_overlay.clear()
        self._status("Sobrescrever texto: " + ("ON" if enabled else "OFF"))

    def _on_interval_change(self, value):
        interval = int(float(value))
        self.config["auto_translate_interval"] = interval
        self.config.save()
        logger.info("Auto-translate interval → %ds", interval)

    # ===================================================================
    # Core actions
    # ===================================================================

    def _on_area_selected(self, area):
        self.capture_areas.append(area)
        x, y, w, h = area
        idx = len(self.capture_areas) - 1
        self.overlay.show(
            area,
            color=OVERLAY_COLORS[idx % len(OVERLAY_COLORS)],
            border_color=OVERLAY_BORDERS[idx % len(OVERLAY_BORDERS)],
        )

        if len(self.capture_areas) == 1:
            self.area_label.config(
                text=f"Área: ({x}, {y})  {w}×{h} px", fg=GREEN,
            )
        else:
            self.area_label.config(
                text=f"{len(self.capture_areas)} áreas selecionadas", fg=GREEN,
            )
        self.capture_btn.config(state="normal")
        self._auto_btn.config(state="normal")
        self._status("Área selecionada ✓  —  Pressione hotkey para capturar")

    def _clear(self):
        self._stop_auto_translate()
        self.tts.stop()
        self.overlay.destroy()
        self.text_overlay.clear()
        self.capture_areas.clear()
        self.capture_btn.config(state="disabled")
        self._auto_btn.config(state="disabled")
        self.area_label.config(text="Nenhuma área selecionada", fg=FG_DIM)
        self._status("Áreas e overlays removidos")
        logger.info("All capture areas cleared")

    def _show_text_overlay(self, text: str):
        """Display translated text over each capture area."""
        self.text_overlay.clear()
        for area in self.capture_areas:
            self.text_overlay.show(area, text)
        # Tell auto_check to recapture baseline hash (now includes overlay)
        self._rehash_pending = True

    def _capture_and_translate(self):
        if not self.capture_areas:
            self._status("⚠ Selecione uma área primeiro")
            return
        if self.is_busy:
            return
        self.is_busy = True
        self._status("📸 Capturando tela...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _speak_translation(self):
        """Read the current translation aloud via TTS (F2 hotkey)."""
        if not self.tts.is_available:
            self._status("⚠ Nenhum motor TTS disponível — instale pyttsx3 ou gTTS")
            return

        # if already playing, stop
        if self.tts.is_playing:
            self.tts.stop()
            self._tts_btn.config(text="🔊")
            self._status("🔇 Áudio interrompido")
            return

        # get current translation text
        text = self.translated_text.get("1.0", "end").strip()
        if not text:
            self._status("⚠ Nenhuma tradução para ler")
            return

        lang = self.config["target_language"]
        self._tts_btn.config(text="⏹")
        self._status("🔊 Reproduzindo áudio...")

        def on_done():
            self.root.after(0, lambda: self._tts_btn.config(text="🔊"))

        self.tts.speak(
            text, lang=lang,
            on_status=self._status_safe,
            on_done=on_done,
        )


    def _worker(self):
        try:
            # 0. hide text overlay so it won't be captured by OCR
            if self._text_overlay_enabled:
                hide_done = threading.Event()
                self.root.after(0, lambda: (self.text_overlay.clear(), hide_done.set()))
                hide_done.wait(timeout=1.0)
                _time.sleep(0.05)  # small delay for window to actually disappear

            # 1. screenshot all areas
            all_texts: list[str] = []
            with mss.mss() as sct:
                for area in self.capture_areas:
                    x, y, w, h = area
                    shot = sct.grab(
                        {"left": x, "top": y, "width": w, "height": h},
                    )
                    img = Image.frombytes(
                        "RGB", shot.size, shot.bgra, "raw", "BGRX",
                    )
                    text = self.ocr.extract(img, on_status=self._status_safe)
                    if text:
                        all_texts.append(text)

            combined = "\n".join(all_texts).strip()
            self.root.after(0, lambda: self._set_text(self.original_text, combined))

            if not combined:
                self._status_safe("⚠ Nenhum texto detectado")
                return
            if combined == self.last_text:
                # same text → re-show previous overlay if enabled
                if self._text_overlay_enabled and hasattr(self, '_last_translation'):
                    self.root.after(0, lambda t=self._last_translation: self._show_text_overlay(t))
                self._status_safe("ℹ Mesmo texto — tradução mantida")
                return
            self.last_text = combined

            # 2. translate
            self._status_safe("🌐 Traduzindo...")
            if not self.translator.is_ready:
                self._status_safe("⚠ Tradutor não disponível — verifique configuração")
                return

            corrected, translation = self.translator.translate(combined)
            self.root.after(
                0, lambda: self._set_text(self.original_text, corrected),
            )
            self.root.after(
                0, lambda: self._set_text(self.translated_text, translation),
            )

            # show translation on screen overlay
            if self._text_overlay_enabled:
                self._last_translation = translation
                self.root.after(0, lambda t=translation: self._show_text_overlay(t))

            # 3. history
            self.history.add(
                original=combined,
                corrected=corrected,
                translation=translation,
                source_lang=self.config["source_language"],
                target_lang=self.config["target_language"],
                model=self.config["api_model"],
            )
            self.root.after(0, self._update_counts)
            self._status_safe("✓ Tradução concluída!")

        except Exception as exc:
            msg = str(exc)
            logger.exception("Worker error")
            if "content_filter" in msg or "ResponsibleAI" in msg:
                self._status_safe("⚠ Filtro de conteúdo ativado — tente novamente")
            elif "86400" in msg or "UserByModelByDay" in msg:
                self._status_safe(
                    "⚠ Limite diário da API esgotado — troque para Google Translate"
                )
            elif "429" in msg or "rate" in msg.lower():
                self._status_safe("⚠ Rate limit da API — aguarde alguns segundos e tente novamente")
            else:
                self._status_safe(f"❌ Erro: {exc}")
        finally:
            self.is_busy = False

    # ===================================================================
    # Auto-translate
    # ===================================================================

    def _toggle_auto_translate(self):
        if self._auto_translate_active:
            self._stop_auto_translate()
        else:
            self._start_auto_translate()

    def _start_auto_translate(self):
        if not self.capture_areas:
            self._status("⚠ Selecione uma área primeiro")
            return
        self._auto_translate_active = True
        self._auto_btn.config(text="⏹ Parar", bg=RED, fg=BG)
        self._last_screen_hash = None
        self._screen_translated = False
        self._stable_since = 0.0
        self._rehash_pending = False
        delay = self.config.get("auto_translate_interval", 3)
        self._status(f"🔄 Auto-tradução ligada (detecta mudanças, espera {delay}s)")
        logger.info("Auto-translate ON (stability=%ds)", delay)
        self._auto_loop()

    def _stop_auto_translate(self):
        self._auto_translate_active = False
        if self._auto_job_id:
            self.root.after_cancel(self._auto_job_id)
            self._auto_job_id = None
        self._auto_btn.config(text="🔄 Auto", bg=BG_MUTED, fg=FG)
        self._status("⏹ Tradução automática desligada")
        logger.info("Auto-translate OFF")

    def _auto_loop(self):
        """Fast polling loop: detect screen changes, translate when stable."""
        if not self._auto_translate_active:
            return

        if not self.is_busy:
            threading.Thread(target=self._auto_check, daemon=True).start()

        # poll every 300ms for responsiveness
        self._auto_job_id = self.root.after(300, self._auto_loop)

    def _auto_check(self):
        """Hash the capture area as-is (never hide overlay) and decide action."""
        import hashlib
        try:
            with mss.mss() as sct:
                parts = []
                for area in self.capture_areas:
                    x, y, w, h = area
                    shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                    parts.append(shot.rgb)
            current_hash = hashlib.md5(b"".join(parts)).hexdigest()
        except Exception:
            return

        # After showing overlay we need to capture the new baseline hash
        if self._rehash_pending:
            self._last_screen_hash = current_hash
            self._rehash_pending = False
            return

        now = _time.time()

        if current_hash != self._last_screen_hash:
            # Screen pixels changed
            self._last_screen_hash = current_hash
            self._stable_since = now

            if self._screen_translated:
                # Was translated — game moved on, clear overlay
                self._screen_translated = False
                if self._text_overlay_enabled:
                    self.root.after(0, self.text_overlay.clear)
                self._status_safe("👀 Detectou mudança — aguardando estabilizar...")
            return

        # Screen is stable (hash unchanged)
        if self._screen_translated:
            # Already translated this screen, do nothing
            return

        # Check if stable long enough
        stability_secs = self.config.get("auto_translate_interval", 3)
        if now - self._stable_since < stability_secs:
            return

        # Stable and not yet translated → translate now
        self._screen_translated = True
        self.root.after(0, self._capture_and_translate)

    # ===================================================================
    # History window
    # ===================================================================

    def _show_history(self):
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.lift()
            return

        win = tk.Toplevel(self.root)
        win.title("📜 Histórico de Traduções")
        win.geometry("620x500")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        self._history_window = win

        # header
        hdr = tk.Frame(win, bg=BG)
        hdr.pack(fill="x", padx=10, pady=6)
        tk.Label(
            hdr, text=f"📜 Histórico ({self.history.count} entradas)",
            fg=BLUE, bg=BG, font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        tk.Button(
            hdr, text="🗑 Limpar", command=self._clear_history,
            bg=RED, fg=BG, relief="flat", font=("Segoe UI", 9),
            cursor="hand2", padx=6,
        ).pack(side="right")

        # scrollable list
        txt = scrolledtext.ScrolledText(
            win, wrap="word", bg=BG_SURFACE, fg=FG,
            font=("Consolas", 10), relief="flat", borderwidth=0,
        )
        txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        for entry in self.history.entries:
            ts = _time.strftime(
                "%H:%M:%S", _time.localtime(entry["timestamp"]),
            )
            lang = f"{entry.get('source_lang', '?')} → {entry.get('target_lang', '?')}"
            txt.insert("end", f"[{ts}] ({lang}) {entry.get('model', '')}\n", "hdr")
            txt.insert("end", f"  Original: {entry['original'][:120]}\n")
            txt.insert("end", f"  Tradução: {entry['translation'][:120]}\n\n")

        txt.tag_config("hdr", foreground=YELLOW, font=("Consolas", 10, "bold"))
        txt.config(state="disabled")

    def _clear_history(self):
        self.history.clear()
        self._update_counts()
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.destroy()
        self._status("Histórico limpo ✓")

    # ===================================================================
    # Export
    # ===================================================================

    def _export_translations(self):
        if self.history.count == 0:
            self._status("⚠ Nenhuma tradução para exportar")
            return
        path = filedialog.asksaveasfilename(
            title="Exportar Traduções",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                self.history.export_csv(path)
            else:
                self.history.export_json(path)
            self._status(f"✓ Exportado: {path}")
        except Exception as exc:
            self._status(f"❌ Erro ao exportar: {exc}")
            logger.exception("Export error")

    # ===================================================================
    # Hotkey / gamepad recording
    # ===================================================================

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

    # ===================================================================
    # Helpers
    # ===================================================================

    @staticmethod
    def _set_text(widget, text):
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def _status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _status_safe(self, msg):
        self.root.after(0, lambda: self._status(msg))

    def _update_counts(self):
        self._cache_label.config(text=f"Cache: {self.translator.cache.size}")
        self._hist_count.config(text=f"Histórico: {self.history.count}")

    def _on_close(self):
        self._stop_auto_translate()
        self.tts.stop()
        self.input.stop()
        self.overlay.destroy()
        self.text_overlay.clear()
        self.root.destroy()
        logger.info("Application closed")

    @staticmethod
    def _styled_om(parent, var, *values):
        """Create an OptionMenu styled for the dark theme."""
        om = tk.OptionMenu(parent, var, *values)
        om.config(
            bg=BG_SURFACE, fg=FG, activebackground=BG_MUTED,
            activeforeground=FG, relief="flat", font=("Segoe UI", 9),
            highlightthickness=0, bd=0,
        )
        om["menu"].config(
            bg=BG_SURFACE, fg=FG, activebackground=BLUE,
            activeforeground=BG, font=("Segoe UI", 9),
        )
        return om
