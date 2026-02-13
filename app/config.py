import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DUALSENSE_BUTTONS = {
    0: "✕ (Cross)", 1: "○ (Circle)", 2: "□ (Square)", 3: "△ (Triangle)",
    4: "Create", 5: "PS", 6: "Options", 7: "L3", 8: "R3",
    9: "L1", 10: "R1", 11: "D-Pad Up", 12: "D-Pad Down",
    13: "D-Pad Left", 14: "D-Pad Right", 15: "Touchpad", 16: "Mute",
}

DEFAULTS = {
    "keyboard_hotkey": "f1",
    "gamepad_buttons": [],
    "gamepad_enabled": False,
}


class Config:
    def __init__(self):
        self.data = {**DEFAULTS}
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

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
