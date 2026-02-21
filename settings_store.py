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
    "watermark_text": "SNERK503",
    "ascii_chars": "@%#*+=-:. ",
    "contrast": 100,
    "invert": False,
    "keep_size": False
    ,
    "theme": "dark",
    "custom_theme_background": "",
    "custom_theme_bg": "#0c1018",
    "custom_theme_fg": "#e8f2ff",
    "custom_theme_accent": "#5ec8ff",
    "custom_theme_panel": "#151c29",
    "icon_pack_path": "",
    "icon_pack_url": "",
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
    "render_device": "cpu",
    "render_fps": 24,
    "gamma_pct": 100,
    "denoise": False,
    "sharpen": False,
    "edge_boost": False,
    "tutorial_done": False,
    "keep_source_audio": True,
    "pro_scanlines": False,
    "pro_bloom": 0,
    "pro_vignette": 0,
    "pro_poster_bits": 0,
    "pro_grain": 0,
    "pro_chroma": 0,
    "pro_scan_strength": 28,
    "pro_scan_step": 3,
    "pro_glitch": 0,
    "pro_glitch_density": 35,
    "pro_glitch_shift": 42,
    "pro_glitch_rgb": 1,
    "pro_glitch_block": 10,
    "pro_glitch_jitter": 1,
    "pro_glitch_noise": 12,
    "pro_curvature": 0,
    "pro_ribbing": 0,
    "live_preview": False,
    "update_feed_url": "update_manifest.json",
    "auto_check_updates": True,
    "last_update_check": 0,
    "last_known_version": "",
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
