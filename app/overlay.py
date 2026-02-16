"""
Screen overlays — area selector and click-through monitor overlays.
Supports multiple simultaneous overlays with adjustable transparency.
"""

import ctypes
import logging
import tkinter as tk

logger = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


# ---------------------------------------------------------------------------
# Area selector  (Lightshot-style drag)
# ---------------------------------------------------------------------------

class ScreenSelector:
    """Full-screen overlay for area selection."""

    def __init__(self, root, on_selected):
        self.root = root
        self.on_selected = on_selected
        self._start = None
        self._rect_id = None

    def open(self):
        self.root.withdraw()
        self.root.after(250, self._create)

    def _create(self):
        self._win = tk.Toplevel()
        self._win.attributes("-fullscreen", True)
        self._win.attributes("-alpha", 0.30)
        self._win.attributes("-topmost", True)
        self._win.configure(bg="black")
        self._win.config(cursor="crosshair")

        self._canvas = tk.Canvas(self._win, bg="black", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.create_text(
            self._win.winfo_screenwidth() // 2, 48,
            text="Arraste para selecionar a área  |  ESC para cancelar",
            fill="white", font=("Segoe UI", 15, "bold"),
        )

        self._canvas.bind("<ButtonPress-1>", self._press)
        self._canvas.bind("<B1-Motion>", self._drag)
        self._canvas.bind("<ButtonRelease-1>", self._release)
        self._win.bind("<Escape>", lambda _: self._cancel())

    def _press(self, e):
        self._start = (e.x, e.y)
        if self._rect_id:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(
            e.x, e.y, e.x, e.y,
            outline="#89b4fa", width=2, fill="#89b4fa", stipple="gray25",
        )

    def _drag(self, e):
        if self._start and self._rect_id:
            self._canvas.coords(self._rect_id, *self._start, e.x, e.y)

    def _release(self, e):
        if not self._start:
            return
        x1, y1 = self._start
        left, top = min(x1, e.x), min(y1, e.y)
        w, h = abs(e.x - x1), abs(e.y - y1)

        self._win.destroy()
        self.root.deiconify()

        if w > 10 and h > 10:
            self.on_selected((left, top, w, h))
            logger.info("Area selected: (%d, %d) %d×%d", left, top, w, h)

    def _cancel(self):
        self._win.destroy()
        self.root.deiconify()
        logger.debug("Area selection cancelled")


# ---------------------------------------------------------------------------
# Monitor overlay  (click-through, multiple areas, transparency)
# ---------------------------------------------------------------------------

class MonitorOverlay:
    """Click-through overlay supporting multiple areas with adjustable alpha."""

    def __init__(self, root, *, alpha: float = 0.13, always_visible: bool = True):
        self.root = root
        self._alpha = alpha
        self._always_visible = always_visible
        self._overlays: list[tuple[tuple, tk.Toplevel]] = []

    # -- properties ------------------------------------------------------

    @property
    def alpha(self) -> float:
        return self._alpha

    @alpha.setter
    def alpha(self, value: float):
        self._alpha = max(0.01, min(1.0, value))
        for _, win in self._overlays:
            if win and win.winfo_exists():
                win.attributes("-alpha", self._alpha)
        logger.info("Overlay alpha → %.2f", self._alpha)

    @property
    def always_visible(self) -> bool:
        return self._always_visible

    @always_visible.setter
    def always_visible(self, value: bool):
        self._always_visible = value
        for _, win in self._overlays:
            if win and win.winfo_exists():
                win.attributes("-topmost", value)
        logger.info("Overlay always_visible → %s", value)

    @property
    def areas(self) -> list[tuple]:
        return [area for area, _ in self._overlays]

    @property
    def count(self) -> int:
        return len(self._overlays)

    # -- show / remove ---------------------------------------------------

    def show(self, area: tuple, *,
             color: str = "#0055ff", border_color: str = "#89b4fa"):
        x, y, w, h = area

        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.geometry(f"{w}x{h}+{x}+{y}")
        window.attributes("-topmost", self._always_visible)
        window.attributes("-alpha", self._alpha)
        window.configure(bg=color)

        tk.Canvas(
            window, bg=color,
            highlightthickness=2, highlightbackground=border_color,
        ).pack(fill="both", expand=True)

        self._overlays.append((area, window))
        self.root.after(150, lambda: self._make_clickthrough(window))
        logger.info("Overlay shown for (%d, %d) %d×%d", x, y, w, h)

    def remove_last(self):
        if self._overlays:
            area, win = self._overlays.pop()
            if win and win.winfo_exists():
                win.destroy()
            logger.info("Removed last overlay")

    def destroy(self):
        for _, win in self._overlays:
            if win and win.winfo_exists():
                win.destroy()
        self._overlays.clear()
        logger.info("All overlays destroyed")

    # -- internals -------------------------------------------------------

    @staticmethod
    def _make_clickthrough(window):
        if not window or not window.winfo_exists():
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Text overlay  (draws translated text on top of game, covering original)
# ---------------------------------------------------------------------------

class TextOverlay:
    """Click-through overlay that renders translated text over the game screen,
    covering the original text with a solid/semi-transparent background."""

    def __init__(self, root, *, bg_color: str = "#1e1e2e",
                 fg_color: str = "#cdd6f4", alpha: float = 0.92,
                 font_family: str = "Segoe UI", font_size: int = 14):
        self.root = root
        self._bg_color = bg_color
        self._fg_color = fg_color
        self._alpha = alpha
        self._font_family = font_family
        self._font_size = font_size
        self._windows: list[tk.Toplevel] = []

    # -- configuration ---------------------------------------------------

    @property
    def alpha(self) -> float:
        return self._alpha

    @alpha.setter
    def alpha(self, value: float):
        self._alpha = max(0.1, min(1.0, value))
        for win in self._windows:
            if win and win.winfo_exists():
                win.attributes("-alpha", self._alpha)

    @property
    def font_size(self) -> int:
        return self._font_size

    @font_size.setter
    def font_size(self, value: int):
        self._font_size = max(8, min(48, value))

    # -- show translation over area --------------------------------------

    def show(self, area: tuple, text: str):
        """Display *text* covering the screen region *area* (x, y, w, h)."""
        x, y, w, h = area

        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.geometry(f"{w}x{h}+{x}+{y}")
        window.attributes("-topmost", True)
        window.attributes("-alpha", self._alpha)
        window.configure(bg=self._bg_color)

        # auto-fit font size to area
        fs = self._pick_font_size(text, w, h)

        label = tk.Label(
            window, text=text,
            bg=self._bg_color, fg=self._fg_color,
            font=(self._font_family, fs),
            wraplength=w - 16,   # padding
            justify="center",
            anchor="center",
            padx=8, pady=4,
        )
        label.place(relx=0.5, rely=0.5, anchor="center")

        self._windows.append(window)
        self.root.after(150, lambda: self._make_clickthrough(window))
        logger.info("TextOverlay shown at (%d,%d) %d×%d  font=%d", x, y, w, h, fs)

    def update_text(self, text: str):
        """Update all existing text overlay windows with new text."""
        for win in self._windows:
            if win and win.winfo_exists():
                # find the label widget
                for child in win.winfo_children():
                    if isinstance(child, tk.Label):
                        w = win.winfo_width()
                        h = win.winfo_height()
                        fs = self._pick_font_size(text, w, h)
                        child.config(
                            text=text,
                            font=(self._font_family, fs),
                            wraplength=w - 16,
                        )

    def clear(self):
        """Remove all text overlay windows."""
        for win in self._windows:
            if win and win.winfo_exists():
                win.destroy()
        self._windows.clear()
        logger.info("TextOverlay cleared")

    def hide(self):
        """Temporarily hide all text overlay windows (no destroy)."""
        for win in self._windows:
            if win and win.winfo_exists():
                win.withdraw()

    def unhide(self):
        """Re-show previously hidden text overlay windows."""
        for win in self._windows:
            if win and win.winfo_exists():
                win.deiconify()
                win.attributes("-topmost", True)

    def _pick_font_size(self, text: str, width: int, height: int) -> int:
        """Choose a font size that fills the area well without overflowing."""
        fs = self._font_size
        # rough heuristic: chars per line ~ width / (fs * 0.6)
        # lines needed ~ total_chars / chars_per_line
        for candidate in range(fs, 7, -1):
            chars_per_line = max(1, int(width / (candidate * 0.65)))
            import textwrap
            lines = textwrap.wrap(text, width=chars_per_line)
            line_height = candidate * 1.4
            total_h = len(lines) * line_height
            if total_h <= height - 8:
                return candidate
        return 8

    @staticmethod
    def _make_clickthrough(window):
        if not window or not window.winfo_exists():
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT,
            )
        except Exception:
            pass
