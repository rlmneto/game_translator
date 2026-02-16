import logging
import threading
import time

from pynput import keyboard as pynput_keyboard

logger = logging.getLogger(__name__)

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class InputManager:
    PYGAME_AVAILABLE = PYGAME_AVAILABLE

    def __init__(self, config, on_trigger, root):
        self.config = config
        self.on_trigger = on_trigger
        self.root = root
        self._kb_listener = None
        self._waiting_hotkey = False
        self._waiting_gamepad = False
        self._gamepad_combo_buf: list[int] = []
        self._gamepad_running = False
        self._on_hotkey_done = None
        self._on_gamepad_update = None
        self._on_gamepad_done = None

    # -- Keyboard --------------------------------------------------------

    def setup_hotkey(self):
        if self._kb_listener:
            self._kb_listener.stop()

        target = self._resolve_key(self.config["keyboard_hotkey"])

        def on_press(key):
            try:
                if self._waiting_hotkey:
                    name = self._key_name(key)
                    if name:
                        self.config["keyboard_hotkey"] = name.lower()
                        self.config.save()
                        self._waiting_hotkey = False
                        if self._on_hotkey_done:
                            self.root.after(0, self._on_hotkey_done)
                    return
                if key == target:
                    self.root.after(0, self.on_trigger)
            except Exception:
                logger.debug("Key press handler error", exc_info=True)

        self._kb_listener = pynput_keyboard.Listener(on_press=on_press)
        self._kb_listener.daemon = True
        self._kb_listener.start()

    def record_hotkey(self, on_done):
        self._waiting_hotkey = True
        self._on_hotkey_done = on_done

    # -- Gamepad ---------------------------------------------------------

    def setup_gamepad(self):
        if not PYGAME_AVAILABLE:
            return
        pygame.init()
        pygame.joystick.init()
        self._gamepad_running = True
        threading.Thread(target=self._gamepad_loop, daemon=True).start()

    def record_gamepad(self, on_update, on_done):
        if not PYGAME_AVAILABLE:
            return
        self._gamepad_combo_buf = []
        self._waiting_gamepad = True
        self._on_gamepad_update = on_update
        self._on_gamepad_done = on_done

    @property
    def gamepad_combo_buf(self):
        return self._gamepad_combo_buf

    def _gamepad_loop(self):
        joystick = None
        cooldown = 0.0

        while self._gamepad_running:
            try:
                pygame.event.pump()

                if joystick is None and pygame.joystick.get_count() > 0:
                    joystick = pygame.joystick.Joystick(0)
                    joystick.init()
                elif joystick and pygame.joystick.get_count() == 0:
                    joystick = None

                if joystick is None:
                    time.sleep(1)
                    continue

                # Recording mode
                if self._waiting_gamepad:
                    for btn in range(joystick.get_numbuttons()):
                        if joystick.get_button(btn) and btn not in self._gamepad_combo_buf:
                            self._gamepad_combo_buf.append(btn)
                            if self._on_gamepad_update:
                                self.root.after(0, self._on_gamepad_update)
                            self.root.after(800, self._check_gamepad_release)
                    time.sleep(0.05)
                    continue

                # Normal mode: check combo
                combo = self.config.get("gamepad_buttons", [])
                if combo and time.time() > cooldown:
                    all_pressed = all(
                        joystick.get_button(b)
                        for b in combo
                        if b < joystick.get_numbuttons()
                    )
                    if all_pressed:
                        cooldown = time.time() + 1.0
                        self.root.after(0, self.on_trigger)

                time.sleep(1 / 60)
            except Exception:
                logger.debug("Gamepad loop error", exc_info=True)
                time.sleep(0.5)

    def _check_gamepad_release(self):
        if not self._waiting_gamepad:
            return
        try:
            pygame.event.pump()
            if pygame.joystick.get_count() == 0:
                self._finish_gamepad()
                return
            js = pygame.joystick.Joystick(0)
            js.init()
            any_pressed = any(
                js.get_button(b)
                for b in self._gamepad_combo_buf
                if b < js.get_numbuttons()
            )
            if not any_pressed and self._gamepad_combo_buf:
                self._finish_gamepad()
            else:
                self.root.after(200, self._check_gamepad_release)
        except Exception:
            logger.debug("Gamepad release check error", exc_info=True)
            self._finish_gamepad()

    def _finish_gamepad(self):
        self._waiting_gamepad = False
        self.config["gamepad_buttons"] = self._gamepad_combo_buf[:]
        self.config["gamepad_enabled"] = bool(self._gamepad_combo_buf)
        self.config.save()
        if self._on_gamepad_done:
            self.root.after(0, self._on_gamepad_done)

    # -- Cleanup ---------------------------------------------------------

    def stop(self):
        self._gamepad_running = False
        if self._kb_listener:
            self._kb_listener.stop()
        if PYGAME_AVAILABLE:
            pygame.quit()

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _resolve_key(name: str):
        name_lower = name.lower()
        if hasattr(pynput_keyboard.Key, name_lower):
            return getattr(pynput_keyboard.Key, name_lower)
        if len(name_lower) == 1:
            return pynput_keyboard.KeyCode.from_char(name_lower)
        return None

    @staticmethod
    def _key_name(key) -> str:
        if isinstance(key, pynput_keyboard.Key):
            return key.name.upper()
        if isinstance(key, pynput_keyboard.KeyCode):
            return (key.char or "").upper()
        return str(key)
