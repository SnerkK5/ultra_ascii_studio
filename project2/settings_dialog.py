# settings_dialog.py
import json
import os

DEFAULT_SETTINGS = {
    "theme": "dark",
    "language": "en",
    "render_device": "cpu",
    "default_mode": "Auto",
    "trail_intensity": "med",
    "ascii_chars": "@%#*+=-:. ",
    "brightness": 1.0,
    "contrast": 1.0,
    "gamma": 1.0,
    "invert": False,
    "watermark": True
}

class SettingsManager:
    def __init__(self, path="settings.json"):
        self.path = path
        self.data = DEFAULT_SETTINGS.copy()

    def load_settings(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception as e:
                print("Settings load error:", e)

    def save_settings(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
            print("Settings saved:", self.path)
        except Exception as e:
            print("Settings save error:", e)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
