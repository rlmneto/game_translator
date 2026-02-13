import ctypes
import tkinter as tk

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


class ScreenSelector:
    """Full-screen overlay for area selection (Lightshot-style)."""

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

    def _cancel(self):
        self._win.destroy()
        self.root.deiconify()


class MonitorOverlay:
    """Click-through blue overlay on the monitored area."""

    def __init__(self, root):
        self.root = root
        self.window = None

    def show(self, area):
        self.destroy()
        x, y, w, h = area

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.geometry(f"{w}x{h}+{x}+{y}")
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.13)
        self.window.configure(bg="#0055ff")

        tk.Canvas(
            self.window, bg="#0055ff",
            highlightthickness=2, highlightbackground="#89b4fa",
        ).pack(fill="both", expand=True)

        self.root.after(150, self._make_clickthrough)

    def _make_clickthrough(self):
        if not self.window:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT,
            )
        except Exception:
            pass

    def destroy(self):
        if self.window:
            self.window.destroy()
            self.window = None
