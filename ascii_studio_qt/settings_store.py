import json
from pathlib import Path

DEFAULTS = {
    "lang": "en",
    "style": "bw",
    "width_chars": 320,
    "font_size": 12,
    "fg_hex": "#FFFFFF",
    "bg_hex": "#0F1013",
    "trail_level": "med",
    "device_choice": "cpu",
    "show_watermark": True,
    "ascii_chars": "@%#*+=-:. ",
    "contrast": 100,
    "invert": False,
    "keep_size": False
    ,
    "theme": "dark",
    "pro_mode": False,
    "trail_length": 96,
    "trail_decay_ms": 2200,
    "trail_color": "#FFF7E6",
    "export_gif_fps": 10
    ,
    "pro_tools": False,
    "render_threads": 4,
    "render_codec": "libx264",
    "render_bitrate": "2M",
    "render_device": "cpu"
}


def settings_path():
    p = Path.home() / ".ascii_studio_settings.json"
    return p


def load_settings():
    p = settings_path()
    if not p.exists():
        return DEFAULTS.copy()
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        out = DEFAULTS.copy(); out.update(data or {})
        return out
    except Exception:
        return DEFAULTS.copy()


def save_settings(d):
    p = settings_path()
    try:
        with p.open("w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
