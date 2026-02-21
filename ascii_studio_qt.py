# ascii_studio_qt.py
# Ultra ASCII Studio РІР‚вЂќ PySide6 version
# Features: iPhone-glass-like UI, animated blurred background, smoke trail, localization (en/ru/zh), settings (CPU/GPU), preview, gallery, image/video render
#
# Dependencies:
# pip install PySide6 pillow numpy opencv-python imageio imageio-ffmpeg

import sys, os, threading, time, math, random, subprocess, copy, json, hashlib
import io, base64
import urllib.request
import urllib.error
import importlib.metadata as _importlib_metadata
from functools import partial
from pathlib import Path
from collections import deque

from PySide6.QtCore import Qt, QSize, QRect, QTimer, QPoint, QThread, Signal, Slot, QEvent, QPropertyAnimation, QEasingCurve, QObject, QUrl
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QIcon, QRadialGradient, QBrush, QCursor, QMovie, QPolygon, QKeySequence, QShortcut, QDesktopServices, QPen, QRegion, QPainterPath, QFontMetrics
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QSoundEffect
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox, QFileDialog,
    QColorDialog, QSlider, QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QListWidget,
    QListWidgetItem, QProgressBar, QDialog, QFormLayout, QSpinBox, QCheckBox, QLineEdit,
    QGraphicsBlurEffect, QGraphicsOpacityEffect, QScrollArea, QAbstractButton, QStackedWidget,
    QSizePolicy, QTabWidget, QTextEdit, QFontComboBox, QSplitter
)

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance, ImageChops
import numpy as np
import cv2

def _pick_resource_path(*names):
    """Resolve bundled/local resource path for icon/assets."""
    base = Path(__file__).resolve().parent
    bundle = Path(getattr(sys, "_MEIPASS", base))
    for root in (bundle, base):
        for name in names:
            p = root / name
            if p.exists():
                return p
    return None

# imageio can fail in frozen builds when dist metadata is missing.
try:
    _orig_version = _importlib_metadata.version
    def _safe_version(pkg_name):
        try:
            return _orig_version(pkg_name)
        except Exception:
            if str(pkg_name).lower() == "imageio":
                return "2.0.0"
            raise
    _importlib_metadata.version = _safe_version
except Exception:
    pass

import imageio
import tempfile
try:
    import psutil
except Exception:
    psutil = None
try:
    from PySide6.QtSvg import QSvgRenderer
except Exception:
    QSvgRenderer = None

# import new modules
from settings_store import load_settings, save_settings
from core_utils import pil_to_qpixmap, image_to_ascii_data, render_ascii_pil, DEFAULT_ASCII
from core_utils import WATERMARK as CORE_WATERMARK
from render_worker import RenderWorker
from export_progress import ExportProgressDialog
from advanced_editor import AdvancedEditorDialog

APP_VERSION = "1.2.0"
DEFAULT_UPDATE_FEED_URL = "update_manifest.json"
PRESET_PREVIEW_SAMPLE = "e6b71d9a95c6c61398bb77477207317a.jpg"
THEME_NAMES = [
    "dark",
    "light",
    "solarized",
    "midnight",
    "retro",
    "sketch",
    "cyberpunk 2077",
    "aphex twin",
    "dedsec",
    "custom",
]


# Small helper worker for saving a PIL image to video/gif without blocking UI
class SaveImageWorker(QThread):
    progress = Signal(int)
    finished_path = Signal(str)
    error = Signal(str)

    def __init__(self, pil_image, out_path, fps=24):
        super().__init__()
        self.pil = pil_image
        self.out = out_path
        self.fps = fps
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            ext = self.out.split('.')[-1].lower()
            arr = np.array(self.pil.convert('RGBA'))
            if ext == 'gif':
                try:
                    imageio.mimsave(self.out, [arr], fps=self.fps)
                except Exception as e:
                    self.error.emit(str(e)); return
            else:
                try:
                    kw = {'fps': self.fps, 'format': 'FFMPEG'}
                    try:
                        w = imageio.get_writer(self.out, **kw)
                    except Exception:
                        w = imageio.get_writer(self.out, fps=self.fps)
                    data = np.array(self.pil.convert('RGB'))
                    if data.dtype != np.uint8:
                        data = data.astype(np.uint8)
                    w.append_data(data)
                    try: w.close()
                    except Exception: pass
                except Exception as e:
                    self.error.emit(str(e)); return
            self.finished_path.emit(self.out)
        except Exception as e:
            self.error.emit(str(e))

# bring translations into file for backwards compat
from core_utils import DEFAULT_ASCII as UNUSED_DEFAULT

# -------------------- Translations --------------------
TRANSLATIONS = {
    "en": {
        "app": "ASCII Studio", "load": "Load", "render": "Render", "export": "Export",
        "settings": "Settings", "device": "Render device", "cpu": "CPU", "gpu": "GPU (if available)",
        "file": "File", "language": "Language",
        "style": "Style", "width": "Width (chars)", "font": "Font size",
        "text_color": "Text color", "bg_color": "BG color", "gallery": "Gallery",
        "trail": "Trail intensity", "off": "Off", "low": "Low", "med": "Medium", "high": "High",
        "watermark": "Watermark", "author": "Author", "ok": "OK", "cancel": "Cancel",
        "charset": "Charset", "contrast": "Contrast (%)", "invert": "Invert", "keep_size": "Keep original output size",
        "batch": "Batch", "palette": "Palette", "dither": "Dither", "pro_tools": "Pro Tools",
        "enable_pro_tools": "Enable Pro Tools", "theme": "Theme",
    }
}

TRANSLATIONS["en"].update({
    "edit": "Edit",
    "tools": "Tools",
    "pro_menu": "Pro Tools",
    "trail_len": "Trail length",
    "processor": "Processor",
    "cpu_threads": "CPU threads",
    "codec": "Codec",
    "bitrate": "Bitrate",
    "export_fps": "Export FPS",
    "remove": "Remove",
    "toggle": "Toggle enabled",
    "preview": "Preview",
    "batch_done": "Batch processing complete",
    "tool_invert": "Invert selected",
    "tool_edges": "Edge detect",
    "tool_posterize": "Posterize",
    "tool_sharpen": "Sharpen",
    "tool_mirror": "Mirror",
    "no_selection": "No gallery item selected.",
    "advanced": "Advanced",
    "fps": "FPS",
    "gamma": "Gamma (%)",
    "denoise": "Denoise",
    "sharpen": "Sharpen",
    "edge_boost": "Edge boost",
    "gallery_empty": "No items yet",
    "trail_settings_only": "Trail intensity is in Settings",
    "theme_settings_only": "Theme is in Settings",
    "cpu_load": "CPU load",
    "help": "Help",
    "help_open": "Open help",
    "defaults": "Defaults",
    "recommended": "Recommended",
    "scale": "Scale",
    "output_size": "Output (W x H)",
    "auto_size": "Auto size",
    "tutorial": "Tutorial",
    "start_tutorial": "Start tutorial",
    "tutorial_confirm": "Ready to start the tutorial?",
    "tutorial_skip": "Skip (Esc)",
    "done": "Done",
    "section_style": "STYLE",
    "section_style_desc": "ASCII visual style and base parameters",
    "section_fx": "IMAGE FX",
    "section_fx_desc": "Contrast, gamma and filters",
    "section_render": "RENDER",
    "section_render_desc": "Codec and export parameters",
    "device_auto": "Auto",
    "device_cpu": "CPU",
    "device_gpu": "GPU (if available)",
    "preset": "Preset",
    "crf": "CRF",
    "editor": "Editor",
    "live_preview": "Live preview (realtime)",
    "brightness": "Brightness",
    "saturation": "Saturation",
    "hue": "Hue",
    "apply": "Apply",
    "gpu_load": "GPU load",
    "eta": "ETA",
    "render_speed": "Speed",
})

CLEAN_RU = {
    "app": "ASCII Studio",
    "load": "Р—Р°РіСЂСѓР·РёС‚СЊ",
    "render": "Р РµРЅРґРµСЂ",
    "export": "Р­РєСЃРїРѕСЂС‚",
    "settings": "РќР°СЃС‚СЂРѕР№РєРё",
    "device": "РЈСЃС‚СЂРѕР№СЃС‚РІРѕ СЂРµРЅРґРµСЂР°",
    "cpu": "CPU",
    "gpu": "GPU (РµСЃР»Рё РґРѕСЃС‚СѓРїРµРЅ)",
    "file": "Р¤Р°Р№Р»",
    "language": "РЇР·С‹Рє",
    "style": "РЎС‚РёР»СЊ",
    "width": "РЁРёСЂРёРЅР° (СЃРёРјРІ.)",
    "font": "Р Р°Р·РјРµСЂ С€СЂРёС„С‚Р°",
    "text_color": "Р¦РІРµС‚ С‚РµРєСЃС‚Р°",
    "bg_color": "Р¦РІРµС‚ С„РѕРЅР°",
    "gallery": "Р“Р°Р»РµСЂРµСЏ",
    "trail": "РРЅС‚РµРЅСЃРёРІРЅРѕСЃС‚СЊ С…РІРѕСЃС‚Р°",
    "off": "Р’С‹РєР»",
    "low": "РќРёР·РєРёР№",
    "med": "РЎСЂРµРґРЅРёР№",
    "high": "Р’С‹СЃРѕРєРёР№",
    "watermark": "Р’РѕРґСЏРЅРѕР№ Р·РЅР°Рє",
    "author": "РђРІС‚РѕСЂ",
    "ok": "OK",
    "cancel": "РћС‚РјРµРЅР°",
    "charset": "РќР°Р±РѕСЂ СЃРёРјРІРѕР»РѕРІ",
    "contrast": "РљРѕРЅС‚СЂР°СЃС‚ (%)",
    "invert": "РРЅРІРµСЂС‚РёСЂРѕРІР°С‚СЊ",
    "keep_size": "РЎРѕС…СЂР°РЅСЏС‚СЊ РѕСЂРёРіРёРЅР°Р»СЊРЅС‹Р№ СЂР°Р·РјРµСЂ",
    "batch": "РџР°РєРµС‚РЅРѕ",
    "palette": "РџР°Р»РёС‚СЂР°",
    "dither": "Р Р°СЃС‚РµСЂРёР·Р°С†РёСЏ",
    "pro_tools": "РџСЂРѕС„. РёРЅСЃС‚СЂСѓРјРµРЅС‚С‹",
    "enable_pro_tools": "Р’РєР»СЋС‡РёС‚СЊ Pro Tools",
    "theme": "РўРµРјР°",
    "tools": "РРЅСЃС‚СЂСѓРјРµРЅС‚С‹",
    "pro_menu": "Pro Tools",
    "trail_len": "Р”Р»РёРЅР° С…РІРѕСЃС‚Р°",
    "processor": "РџСЂРѕС†РµСЃСЃРѕСЂ",
    "cpu_threads": "РџРѕС‚РѕРєРё CPU",
    "codec": "РљРѕРґРµРє",
    "bitrate": "Р‘РёС‚СЂРµР№С‚",
    "export_fps": "FPS СЌРєСЃРїРѕСЂС‚Р°",
    "remove": "РЈРґР°Р»РёС‚СЊ",
    "toggle": "РџРµСЂРµРєР»СЋС‡РёС‚СЊ Р°РєС‚РёРІРЅРѕСЃС‚СЊ",
    "preview": "РџСЂРµРІСЊСЋ",
    "batch_done": "РџР°РєРµС‚РЅР°СЏ РѕР±СЂР°Р±РѕС‚РєР° Р·Р°РІРµСЂС€РµРЅР°",
    "tool_invert": "РРЅРІРµСЂС‚ РІС‹Р±СЂР°РЅРЅРѕРіРѕ",
    "tool_edges": "РџРѕРёСЃРє РіСЂР°РЅРёС†",
    "tool_posterize": "РџРѕСЃС‚РµСЂРёР·Р°С†РёСЏ",
    "tool_sharpen": "Р РµР·РєРѕСЃС‚СЊ",
    "tool_mirror": "Р—РµСЂРєР°Р»Рѕ",
    "no_selection": "РќРµ РІС‹Р±СЂР°РЅ СЌР»РµРјРµРЅС‚ РіР°Р»РµСЂРµРё.",
    "advanced": "Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ",
    "fps": "FPS",
    "gamma": "Р“Р°РјРјР° (%)",
    "denoise": "РЁСѓРјРѕРїРѕРґР°РІР»РµРЅРёРµ",
    "sharpen": "Р РµР·РєРѕСЃС‚СЊ",
    "edge_boost": "РЈСЃРёР»РµРЅРёРµ РєРѕРЅС‚СѓСЂРѕРІ",
    "gallery_empty": "РџРѕРєР° РЅРµС‚ СЌР»РµРјРµРЅС‚РѕРІ",
    "trail_settings_only": "РРЅС‚РµРЅСЃРёРІРЅРѕСЃС‚СЊ С…РІРѕСЃС‚Р° РІ РќР°СЃС‚СЂРѕР№РєР°С…",
    "theme_settings_only": "РўРµРјР° РІС‹Р±РёСЂР°РµС‚СЃСЏ РІ РќР°СЃС‚СЂРѕР№РєР°С…",
    "cpu_load": "РќР°РіСЂСѓР·РєР° CPU",
    "help": "РЎРїСЂР°РІРєР°",
    "help_open": "РћС‚РєСЂС‹С‚СЊ СЃРїСЂР°РІРєСѓ",
    "defaults": "РџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ",
    "recommended": "Р РµРєРѕРјРµРЅРґРѕРІР°РЅРЅС‹Рµ",
    "scale": "РњР°СЃС€С‚Р°Р±",
    "output_size": "Р Р°Р·РјРµСЂ (РЁ x Р’)",
    "auto_size": "РђРІС‚РѕСЂР°Р·РјРµСЂ",
    "tutorial": "РћР±СѓС‡РµРЅРёРµ",
    "start_tutorial": "РџСЂРѕР№С‚Рё РѕР±СѓС‡РµРЅРёРµ",
    "tutorial_confirm": "Р“РѕС‚РѕРІС‹ РїСЂРѕР№С‚Рё РѕР±СѓС‡РµРЅРёРµ?",
    "tutorial_skip": "РџСЂРѕРїСѓСЃС‚РёС‚СЊ (Esc)",
    "done": "Р“РѕС‚РѕРІРѕ",
    "section_style": "STYLE",
    "section_style_desc": "Р’РёР·СѓР°Р»СЊРЅС‹Р№ СЃС‚РёР»СЊ ASCII Рё Р±Р°Р·РѕРІС‹Рµ РїР°СЂР°РјРµС‚СЂС‹",
    "section_fx": "IMAGE FX",
    "section_fx_desc": "РљРѕРЅС‚СЂР°СЃС‚, РіР°РјРјР° Рё С„РёР»СЊС‚СЂС‹",
    "section_render": "RENDER",
    "section_render_desc": "РљРѕРґРµРє Рё РїР°СЂР°РјРµС‚СЂС‹ СЃРѕС…СЂР°РЅРµРЅРёСЏ",
    "device_auto": "РђРІС‚Рѕ",
    "device_cpu": "CPU",
    "device_gpu": "GPU (РµСЃР»Рё РґРѕСЃС‚СѓРїРµРЅ)",
    "preset": "РџСЂРµСЃРµС‚",
    "crf": "CRF",
}

CLEAN_ZH = {
    "app": "ASCII Studio",
    "load": "еЉ иЅЅ",
    "render": "жёІжџ“",
    "export": "еЇје‡є",
    "settings": "и®ѕзЅ®",
    "device": "жёІжџ“и®ѕе¤‡",
    "cpu": "CPU",
    "gpu": "GPU (е¦‚еЏЇз”Ё)",
    "file": "ж–‡д»¶",
    "language": "иЇ­иЁЂ",
    "style": "йЈЋж ј",
    "width": "е®Ѕеє¦(е­—з¬¦)",
    "font": "е­—дЅ“е¤§е°Џ",
    "text_color": "ж–‡е­—йўњи‰І",
    "bg_color": "иѓЊж™Їйўњи‰І",
    "gallery": "з”»е»Љ",
    "trail": "ж‹–е°ѕејєеє¦",
    "off": "е…і",
    "low": "дЅЋ",
    "med": "дё­",
    "high": "й«",
    "watermark": "ж°ґеЌ°",
    "author": "дЅњиЂ…",
    "ok": "зЎ®е®љ",
    "cancel": "еЏ–ж¶€",
    "charset": "е­—з¬¦й›†",
    "contrast": "еЇ№жЇ”еє¦ (%)",
    "invert": "еЏЌз›ё",
    "keep_size": "дїќжЊЃеЋџе§‹иѕ“е‡єе°єеЇё",
    "batch": "ж‰№е¤„зђ†",
    "palette": "и°ѓи‰Іжќї",
    "dither": "жЉ–еЉЁ",
    "pro_tools": "дё“дёље·Ґе…·",
    "enable_pro_tools": "еђЇз”Ё Pro Tools",
    "theme": "дё»йў",
    "tools": "е·Ґе…·",
    "pro_menu": "Pro Tools",
    "trail_len": "ж‹–е°ѕй•їеє¦",
    "processor": "е¤„зђ†е™Ё",
    "cpu_threads": "CPU зєїзЁ‹",
    "codec": "зј–з Ѓе™Ё",
    "bitrate": "з ЃзЋ‡",
    "export_fps": "еЇје‡є FPS",
    "remove": "з§»й™¤",
    "toggle": "е€‡жЌўеђЇз”Ё",
    "preview": "йў„и§€",
    "batch_done": "ж‰№е¤„зђ†е®Њж€ђ",
    "tool_invert": "еЏЌз›ёж‰ЂйЂ‰",
    "tool_edges": "иѕ№зјжЈЂжµ‹",
    "tool_posterize": "и‰Іи°ѓе€†з¦»",
    "tool_sharpen": "й”ђеЊ–",
    "tool_mirror": "й•њеѓЏ",
    "no_selection": "жњЄйЂ‰ж‹©з”»е»ЉйЎ№з›®гЂ‚",
    "advanced": "й«зє§",
    "fps": "FPS",
    "gamma": "дјЅй©¬ (%)",
    "denoise": "й™Ќе™Є",
    "sharpen": "й”ђеЊ–",
    "edge_boost": "иѕ№зјеўћејє",
    "gallery_empty": "жљ‚ж— йЎ№з›®",
    "trail_settings_only": "ж‹–е°ѕејєеє¦ењЁи®ѕзЅ®дё­",
    "theme_settings_only": "дё»йўењЁи®ѕзЅ®дё­йЂ‰ж‹©",
    "cpu_load": "CPU иґџиЅЅ",
    "help": "её®еЉ©",
    "help_open": "ж‰“ејЂеё®еЉ©",
    "defaults": "й»и®¤",
    "recommended": "жЋЁиЌђ",
    "scale": "зј©ж”ѕ",
    "output_size": "иѕ“е‡єе°єеЇё(е®Ѕ x й«)",
    "auto_size": "и‡ЄеЉЁе°єеЇё",
    "tutorial": "ж•™зЁ‹",
    "start_tutorial": "ејЂе§‹ж•™зЁ‹",
    "tutorial_confirm": "е‡†е¤‡ејЂе§‹ж•™зЁ‹еђ—?",
    "tutorial_skip": "и·іиї‡ (Esc)",
    "done": "е®Њж€ђ",
    "section_style": "STYLE",
    "section_style_desc": "ASCII и§†и§‰йЈЋж јдёЋеџєзЎЂеЏ‚ж•°",
    "section_fx": "IMAGE FX",
    "section_fx_desc": "еЇ№жЇ”еє¦гЂЃдјЅй©¬дёЋж»¤й•њ",
    "section_render": "RENDER",
    "section_render_desc": "зј–з Ѓе™ЁдёЋеЇје‡єеЏ‚ж•°",
    "device_auto": "и‡ЄеЉЁ",
    "device_cpu": "CPU",
    "device_gpu": "GPU (е¦‚еЏЇз”Ё)",
    "preset": "йў„и®ѕ",
    "crf": "CRF",
}

TRANSLATIONS["ru"] = CLEAN_RU
TRANSLATIONS["zh"] = CLEAN_ZH

TRANSLATIONS["en"].update({
    "yes": "Yes",
    "no": "No",
    "info": "Info",
    "open_player": "Open player",
    "preview_prev": "Previous file",
    "preview_next": "Next file",
    "keep_source_audio": "Keep source audio",
    "keep_source_audio_desc": "Use audio track from the original loaded video when exporting rendered video.",
    "section_pro": "PRO TOOLS",
    "section_pro_desc": "Advanced filters and stylization",
    "pro_scanlines": "Scanlines",
    "pro_bloom": "Bloom (%)",
    "pro_vignette": "Vignette (%)",
    "pro_poster_bits": "Posterize bits",
    "pro_grain": "Film grain (%)",
    "pro_chroma": "Chroma shift (px)",
    "pro_scan_strength": "Scanline strength (%)",
    "pro_scan_step": "Scanline spacing (px)",
    "pro_glitch": "Glitch (%)",
    "pro_glitch_density": "Glitch density (%)",
    "pro_glitch_shift": "Glitch shift (%)",
    "pro_glitch_rgb": "RGB split (px)",
    "pro_glitch_block": "Block tear size (px)",
    "pro_glitch_jitter": "Vertical jitter (px)",
    "pro_glitch_noise": "Static noise (%)",
    "pro_curvature": "CRT curvature (%)",
    "pro_ribbing": "TV ribbing (%)",
    "player_title": "Player",
    "play": "Play",
    "pause": "Pause",
    "stop": "Stop",
    "volume": "Volume",
    "repeat_once": "Once",
    "repeat_loop": "Loop",
    "tool_bloom": "Bloom",
    "tool_vignette": "Vignette",
    "tool_scanlines": "Scanlines",
    "tool_grain": "Film grain",
    "tool_chroma": "Chroma shift",
    "tool_glitch": "Glitch",
    "none_style": "None (original)",
    "player": "Player",
    "player_focus": "Focus mode",
    "player_focus_exit": "Exit focus",
    "player_fullscreen": "Fullscreen",
    "player_fullscreen_exit": "Exit fullscreen",
    "player_seek": "Seek",
    "player_speed": "Speed",
    "player_repeat": "Repeat",
    "player_playlist": "Playlist",
    "render_prompt_title": "Render mode",
    "render_prompt_body": "Choose action: render media or export current frame as TXT.",
    "render_prompt_do_render": "Render media",
    "render_prompt_do_txt": "Export TXT",
    "txt_export_done": "TXT exported successfully.",
    "txt_export_empty": "No media for TXT export.",
    "undo": "Undo",
    "redo": "Redo",
})

TRANSLATIONS["ru"].update({
    "edit": "Правка",
    "yes": "Р”Р°",
    "no": "РќРµС‚",
    "info": "РРЅС„РѕСЂРјР°С†РёСЏ",
    "open_player": "РћС‚РєСЂС‹С‚СЊ РїР»РµРµСЂ",
    "preview_prev": "РџСЂРµРґС‹РґСѓС‰РёР№ С„Р°Р№Р»",
    "preview_next": "РЎР»РµРґСѓСЋС‰РёР№ С„Р°Р№Р»",
    "keep_source_audio": "РЎРѕС…СЂР°РЅСЏС‚СЊ Р·РІСѓРє РёСЃС‚РѕС‡РЅРёРєР°",
    "keep_source_audio_desc": "РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ Р°СѓРґРёРѕРґРѕСЂРѕР¶РєСѓ РёР· РёСЃС…РѕРґРЅРѕРіРѕ Р·Р°РіСЂСѓР¶РµРЅРЅРѕРіРѕ РІРёРґРµРѕ РїСЂРё СЌРєСЃРїРѕСЂС‚Рµ РѕС‚СЂРµРЅРґРµСЂРµРЅРЅРѕРіРѕ РІРёРґРµРѕ.",
    "section_pro": "PRO TOOLS",
    "section_pro_desc": "РџСЂРѕРґРІРёРЅСѓС‚С‹Рµ С„РёР»СЊС‚СЂС‹ Рё СЃС‚РёР»РёР·Р°С†РёСЏ",
    "pro_scanlines": "РЎРєР°РЅ-Р»РёРЅРёРё",
    "pro_bloom": "РЎРІРµС‡РµРЅРёРµ (%)",
    "pro_vignette": "Р’РёРЅСЊРµС‚РєР° (%)",
    "pro_poster_bits": "Р‘РёС‚С‹ РїРѕСЃС‚РµСЂРёР·Р°С†РёРё",
    "pro_grain": "Р—РµСЂРЅРѕ (%)",
    "pro_chroma": "РЎРґРІРёРі РєР°РЅР°Р»РѕРІ (px)",
    "pro_scan_strength": "Сила скан-линий (%)",
    "pro_scan_step": "Шаг скан-линий (px)",
    "pro_glitch": "Глитч (%)",
    "pro_glitch_density": "Плотность глитча (%)",
    "pro_glitch_shift": "Сдвиг глитча (%)",
    "pro_glitch_rgb": "RGB-смещение (px)",
    "pro_glitch_block": "Размер разрыва блока (px)",
    "pro_glitch_jitter": "Вертикальный джиттер (px)",
    "pro_glitch_noise": "Шум статики (%)",
    "pro_curvature": "Выпуклость CRT (%)",
    "pro_ribbing": "Ребристость экрана (%)",
    "player_title": "РџР»РµРµСЂ",
    "play": "РџСѓСЃРє",
    "pause": "РџР°СѓР·Р°",
    "stop": "РЎС‚РѕРї",
    "volume": "Р“СЂРѕРјРєРѕСЃС‚СЊ",
    "repeat_once": "РћРґРёРЅ СЂР°Р·",
    "repeat_loop": "РџРѕРІС‚РѕСЂ",
    "tool_bloom": "РЎРІРµС‡РµРЅРёРµ",
    "tool_vignette": "Р’РёРЅСЊРµС‚РєР°",
    "tool_scanlines": "РЎРєР°РЅ-Р»РёРЅРёРё",
    "tool_grain": "Р—РµСЂРЅРѕ",
    "tool_chroma": "РЎРґРІРёРі РєР°РЅР°Р»РѕРІ",
    "tool_glitch": "Глитч",
    "none_style": "None (Р±РµР· РїСЂРµРѕР±СЂР°Р·РѕРІР°РЅРёСЏ)",
    "player": "РџР»РµРµСЂ",
    "player_focus": "Р¤РѕРєСѓСЃ-СЂРµР¶РёРј",
    "player_focus_exit": "Р’С‹Р№С‚Рё РёР· С„РѕРєСѓСЃР°",
    "player_fullscreen": "Р’Рѕ РІРµСЃСЊ СЌРєСЂР°РЅ",
    "player_fullscreen_exit": "Р’С‹Р№С‚Рё РёР· РїРѕР»РЅРѕРіРѕ СЌРєСЂР°РЅР°",
    "player_seek": "РџСЂРѕРєСЂСѓС‚РєР°",
    "player_speed": "РЎРєРѕСЂРѕСЃС‚СЊ",
    "player_repeat": "РџРѕРІС‚РѕСЂ",
    "player_playlist": "РџР»РµР№Р»РёСЃС‚",
    "render_prompt_title": "Р РµР¶РёРј СЂРµРЅРґРµСЂР°",
    "render_prompt_body": "Р’С‹Р±РµСЂРёС‚Рµ РґРµР№СЃС‚РІРёРµ: СЂРµРЅРґРµСЂ РјРµРґРёР° РёР»Рё СЌРєСЃРїРѕСЂС‚ С‚РµРєСѓС‰РµРіРѕ РєР°РґСЂР° РІ TXT.",
    "render_prompt_do_render": "Р РµРЅРґРµСЂ РјРµРґРёР°",
    "render_prompt_do_txt": "Р­РєСЃРїРѕСЂС‚ TXT",
    "txt_export_done": "TXT СѓСЃРїРµС€РЅРѕ СЌРєСЃРїРѕСЂС‚РёСЂРѕРІР°РЅ.",
    "txt_export_empty": "РќРµС‚ РјРµРґРёР° РґР»СЏ TXT-СЌРєСЃРїРѕСЂС‚Р°.",
    "undo": "РћС‚РјРµРЅРёС‚СЊ",
    "redo": "Р’РµСЂРЅСѓС‚СЊ",
})

TRANSLATIONS["zh"].update({
    "edit": "编辑",
    "yes": "жЇ",
    "no": "еђ¦",
    "info": "дїЎжЃЇ",
    "open_player": "ж‰“ејЂж’­ж”ѕе™Ё",
    "preview_prev": "дёЉдёЂдёЄж–‡д»¶",
    "preview_next": "дё‹дёЂдёЄж–‡д»¶",
    "keep_source_audio": "дїќз•™жєђйџійў‘",
    "keep_source_audio_desc": "еЇје‡єжёІжџ“еђЋи§†йў‘ж—¶пјЊдЅїз”ЁеЋџе§‹еЉ иЅЅи§†йў‘дё­зљ„йџіиЅЁгЂ‚",
    "section_pro": "PRO TOOLS",
    "section_pro_desc": "й«зє§ж»¤й•њдёЋйЈЋж јеЊ–",
    "pro_scanlines": "ж‰«жЏЏзєї",
    "pro_bloom": "иѕ‰е…‰ (%)",
    "pro_vignette": "жљ—и§’ (%)",
    "pro_poster_bits": "и‰Ій¶дЅЌж•°",
    "pro_grain": "胶片颗粒 (%)",
    "pro_chroma": "色偏位移 (px)",
    "pro_scan_strength": "扫描线强度 (%)",
    "pro_scan_step": "扫描线间距 (px)",
    "pro_glitch": "故障效果 (%)",
    "pro_glitch_density": "故障密度 (%)",
    "pro_glitch_shift": "故障位移 (%)",
    "pro_glitch_rgb": "RGB 偏移 (px)",
    "pro_glitch_block": "块撕裂尺寸 (px)",
    "pro_glitch_jitter": "垂直抖动 (px)",
    "pro_glitch_noise": "静态噪点 (%)",
    "pro_curvature": "CRT 曲面 (%)",
    "pro_ribbing": "屏幕条纹 (%)",
    "player_title": "ж’­ж”ѕе™Ё",
    "play": "ж’­ж”ѕ",
    "pause": "жљ‚еЃњ",
    "stop": "еЃњж­ў",
    "volume": "йџій‡Џ",
    "repeat_once": "еЌ•ж¬Ў",
    "repeat_loop": "еѕЄзЋЇ",
    "tool_bloom": "иѕ‰е…‰",
    "tool_vignette": "жљ—и§’",
    "tool_scanlines": "ж‰«жЏЏзєї",
    "tool_grain": "胶片颗粒",
    "tool_chroma": "色偏位移",
    "tool_glitch": "故障效果",
    "none_style": "None (еЋџе§‹)",
    "player": "ж’­ж”ѕе™Ё",
    "player_focus": "дё“жіЁжЁЎејЏ",
    "player_focus_exit": "йЂЂе‡єдё“жіЁ",
    "player_fullscreen": "е…Ёе±Џ",
    "player_fullscreen_exit": "йЂЂе‡єе…Ёе±Џ",
    "player_seek": "иї›еє¦",
    "player_speed": "йЂџеє¦",
    "player_repeat": "й‡Ќе¤Ќ",
    "player_playlist": "ж’­ж”ѕе€—иЎЁ",
    "render_prompt_title": "жёІжџ“жЁЎејЏ",
    "render_prompt_body": "иЇ·йЂ‰ж‹©пјљжёІжџ“еЄ’дЅ“пјЊж€–е°†еЅ“е‰Ќеё§еЇје‡єдёє TXTгЂ‚",
    "render_prompt_do_render": "жёІжџ“еЄ’дЅ“",
    "render_prompt_do_txt": "еЇје‡є TXT",
    "txt_export_done": "TXT еЇје‡єж€ђеЉџгЂ‚",
    "txt_export_empty": "жІЎжњ‰еЏЇеЇје‡єзљ„еЄ’дЅ“гЂ‚",
    "undo": "ж’¤й”Ђ",
    "redo": "й‡ЌеЃљ",
})

# Localized help blocks
STYLE_HELP = {
    "en": {
        "bw": "BW: classic monochrome. High contrast, fastest.",
        "red": "Red: monochrome in red tones for retro look.",
        "color": "Color: preserves original colors for richer ASCII.",
        "matrix": "Matrix: green-coded cyber look.",
        "matrix2": "Matrix2: brighter green, denser glow.",
        "neon": "Neon: saturated glow, strong contrast.",
        "pastel": "Pastel: soft colors, gentle contrast.",
        "custom": "Custom: use your own text and background colors.",
        "none": "None: no ASCII conversion, keeps original frame (with selected FX).",
    },
    "ru": {
        "bw": "BW: РєР»Р°СЃСЃРёС‡РµСЃРєРёР№ РјРѕРЅРѕС…СЂРѕРј, РјР°РєСЃРёРјСѓРј РєРѕРЅС‚СЂР°СЃС‚, СЃР°РјС‹Р№ Р±С‹СЃС‚СЂС‹Р№.",
        "red": "Red: РјРѕРЅРѕС…СЂРѕРј РІ РєСЂР°СЃРЅС‹С… С‚РѕРЅР°С… РґР»СЏ СЂРµС‚СЂРѕ-СЌС„С„РµРєС‚Р°.",
        "color": "Color: СЃРѕС…СЂР°РЅСЏРµС‚ РёСЃС…РѕРґРЅС‹Рµ С†РІРµС‚Р°, РІС‹РіР»СЏРґРёС‚ РЅР°СЃС‹С‰РµРЅРЅРѕ.",
        "matrix": "Matrix: Р·РµР»С‘РЅС‹Р№ РєРёР±РµСЂ-СЌС„С„РµРєС‚.",
        "matrix2": "Matrix2: СЏСЂС‡Рµ Рё РїР»РѕС‚РЅРµРµ \"РјР°С‚СЂРёС†Р°\".",
        "neon": "Neon: РЅР°СЃС‹С‰РµРЅРЅРѕРµ СЃРІРµС‡РµРЅРёРµ, СЃРёР»СЊРЅС‹Р№ РєРѕРЅС‚СЂР°СЃС‚.",
        "pastel": "Pastel: РјСЏРіРєРёРµ С†РІРµС‚Р°, РґРµР»РёРєР°С‚РЅС‹Р№ РєРѕРЅС‚СЂР°СЃС‚.",
        "custom": "Custom: СЃРІРѕР№ С†РІРµС‚ С‚РµРєСЃС‚Р° Рё С„РѕРЅР°.",
        "none": "None: Р±РµР· ASCII-РїСЂРµРѕР±СЂР°Р·РѕРІР°РЅРёСЏ, РѕСЂРёРіРёРЅР°Р»СЊРЅС‹Р№ РєР°РґСЂ (СЃ РІС‹Р±СЂР°РЅРЅС‹РјРё FX).",
    },
    "zh": {
        "bw": "BWпјљз»Џе…ёй»‘з™ЅпјЊй«еЇ№жЇ”пјЊйЂџеє¦жњЂеї«гЂ‚",
        "red": "Redпјљзєўи‰ІеЌ•и‰Іе¤ЌеЏ¤йЈЋгЂ‚",
        "color": "Colorпјљдїќз•™еЋџи‰ІпјЊж›ґдё°еЇЊгЂ‚",
        "matrix": "Matrixпјљз»їи‰Іиµ›еЌљйЈЋгЂ‚",
        "matrix2": "Matrix2пјљж›ґдє®ж›ґеЇ†зљ„зџ©йµйЈЋгЂ‚",
        "neon": "Neonпјљй«йҐ±е’ЊеЏ‘е…‰гЂ‚",
        "pastel": "Pastelпјљжџ”е’Њи‰ІеЅ©пјЊдЅЋеЇ№жЇ”гЂ‚",
        "custom": "Customпјљи‡Єе®љд№‰ж–‡е­—дёЋиѓЊж™Їйўњи‰ІгЂ‚",
        "none": "NoneпјљдёЌеЃљ ASCII иЅ¬жЌўпјЊдїќз•™еЋџе§‹з”»йќўпј€еє”з”Ёе·ІйЂ‰ FXпј‰гЂ‚",
    },
}

CODEC_HELP = {
    "en": {
        "libx264": "Most common MP4 codec. Best compatibility.",
        "h264": "H.264 profile, good compatibility.",
        "mpeg4": "Older codec, faster but less efficient.",
        "libvpx": "VP8/VP9 for WebM; may be slower.",
    },
    "ru": {
        "libx264": "РЎР°РјС‹Р№ СЂР°СЃРїСЂРѕСЃС‚СЂР°РЅС‘РЅРЅС‹Р№ РєРѕРґРµРє РґР»СЏ MP4. Р›СѓС‡С€Р°СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚СЊ.",
        "h264": "H.264 РїСЂРѕС„РёР»СЊ, С…РѕСЂРѕС€Р°СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚СЊ.",
        "mpeg4": "РЎС‚Р°СЂС‹Р№ РєРѕРґРµРє, Р±С‹СЃС‚СЂРµРµ, РЅРѕ РјРµРЅРµРµ СЌС„С„РµРєС‚РёРІРµРЅ.",
        "libvpx": "VP8/VP9 РґР»СЏ WebM; РјРѕР¶РµС‚ Р±С‹С‚СЊ РјРµРґР»РµРЅРЅРµРµ.",
    },
    "zh": {
        "libx264": "жњЂеёёи§Ѓзљ„ MP4 зј–з Ѓе™ЁпјЊе…је®№жЂ§жњЂеҐЅгЂ‚",
        "h264": "H.264 зј–з ЃпјЊе…је®№жЂ§еҐЅгЂ‚",
        "mpeg4": "иѕѓж—§зј–з Ѓе™ЁпјЊйЂџеє¦еї«дЅ†ж•€зЋ‡дЅЋгЂ‚",
        "libvpx": "WebM зљ„ VP8/VP9пјЊеЏЇиѓЅж›ґж…ўгЂ‚",
    },
}

PRO_PRESET_HELP = {
    "en": {
        "none": "No preset. Manual Pro Tools tuning.",
        "soft": "Mild film look: slight grain, soft bloom, light vignette.",
        "cyber": "Cyber style: scanlines, chroma shift and glitch accents.",
        "cinematic": "Cinematic contrast with controlled bloom and vignette.",
        "sketch": "Monochrome paper-like texture with subtle grain.",
        "retro": "Retro CRT flavor: ribbing, curvature and scanlines.",
        "vhs": "VHS simulation with chroma offset, noise and tape artifacts.",
        "clean": "Clean output with minimal noise and balanced contrast.",
    },
    "ru": {
        "none": "Без пресета. Ручная настройка Pro Tools.",
        "soft": "Мягкий film-look: лёгкое зерно, мягкое свечение, слабая виньетка.",
        "cyber": "Кибер-стиль: скан-линии, chroma-сдвиг и акцентный глитч.",
        "cinematic": "Киношный контраст с контролируемым bloom и виньеткой.",
        "sketch": "Монохромная бумажная фактура с лёгким зерном.",
        "retro": "Ретро CRT: ребристость, выпуклость и скан-линии.",
        "vhs": "Симуляция VHS: сдвиг цвета, шум и артефакты ленты.",
        "clean": "Чистая картинка с минимальным шумом и ровным контрастом.",
    },
    "zh": {
        "none": "无预设，手动调整 Pro Tools。",
        "soft": "柔和胶片感：轻微颗粒、柔光和暗角。",
        "cyber": "赛博风：扫描线、色偏位移与故障点缀。",
        "cinematic": "电影感对比度，适度辉光与暗角。",
        "sketch": "黑白素描纸感，带轻微颗粒。",
        "retro": "复古 CRT：屏幕曲面、条纹与扫描线。",
        "vhs": "VHS 模拟：色偏、噪点与磁带伪影。",
        "clean": "干净输出：低噪点与平衡对比。",
    },
}

def _decode_utf8_from_singlebyte_garbled(text, codec):
    if not isinstance(text, str):
        return None
    data = bytearray()
    for ch in text:
        o = ord(ch)
        if o <= 0xFF:
            data.append(o)
            continue
        try:
            b = ch.encode(codec, errors="strict")
        except Exception:
            return None
        if len(b) != 1:
            return None
        data.append(b[0])
    try:
        return data.decode("utf-8", errors="strict")
    except Exception:
        return None


def _repair_mojibake_text(text, lang_hint=None):
    if not isinstance(text, str):
        return text
    src = text.replace("\\n", "\n")
    if lang_hint in ("ru", "zh"):
        direct = _decode_utf8_from_singlebyte_garbled(src, "cp1251")
        if direct:
            return direct
    candidates = [src]

    for enc in ("cp1251", "cp1252", "latin1"):
        cand = _decode_utf8_from_singlebyte_garbled(src, enc)
        if cand and cand not in candidates:
            candidates.append(cand)
            for enc2 in ("cp1251", "cp1252", "latin1"):
                cand2 = _decode_utf8_from_singlebyte_garbled(cand, enc2)
                if cand2 and cand2 not in candidates:
                    candidates.append(cand2)

    def _score(s, hint):
        cyr = sum((("а" <= ch.lower() <= "я") or ch in "ёЁ") for ch in s)
        cjk = sum(0x4E00 <= ord(ch) <= 0x9FFF for ch in s)
        latin = sum(("a" <= ch.lower() <= "z") for ch in s)
        controls = sum((ord(ch) < 32 and ch not in "\n\t\r") or (0x7F <= ord(ch) <= 0x9F) for ch in s)
        bad_markers = sum(s.count(ch) for ch in "ÐÑÃ¤�")
        question_marks = s.count("?")
        score = latin - controls * 8 - bad_markers * 4 - question_marks * 3
        if hint == "ru":
            score += cyr * 8 - cjk * 4
        elif hint == "zh":
            score += cjk * 10 - cyr * 3
        else:
            score += cyr * 3 + cjk * 3
        return score

    return max(candidates, key=lambda s: _score(s, lang_hint))


def _repair_mojibake_tree(obj, lang_hint=None):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            next_hint = lang_hint
            if isinstance(k, str) and k in ("en", "ru", "zh"):
                next_hint = k
            out[k] = _repair_mojibake_tree(v, next_hint)
        return out
    if isinstance(obj, list):
        return [_repair_mojibake_tree(v, lang_hint) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_repair_mojibake_tree(v, lang_hint) for v in obj)
    if isinstance(obj, str):
        return _repair_mojibake_text(obj, lang_hint=lang_hint)
    return obj


TRANSLATIONS = _repair_mojibake_tree(TRANSLATIONS)
STYLE_HELP = _repair_mojibake_tree(STYLE_HELP)
CODEC_HELP = _repair_mojibake_tree(CODEC_HELP)
PRO_PRESET_HELP = _repair_mojibake_tree(PRO_PRESET_HELP)

# Final explicit fallback replacements for strings that can still stay broken
# on some Windows codepages.
TRANSLATIONS["ru"].update({
    "file": "Файл",
    "tools": "Инструменты",
    "language": "Язык",
    "help": "Справка",
    "gallery": "Галерея",
    "preview": "Превью",
    "trail": "Интенсивность хвоста",
    "invert": "Инвертировать",
    "tool_invert": "Инверт выбранного",
    "info": "Информация",
    "tutorial_confirm": "Готовы пройти обучение?",
    "trail_settings_only": "Интенсивность хвоста в Настройках",
    "keep_source_audio_desc": "Использовать аудиодорожку из исходного загруженного видео при экспорте отрендеренного видео.",
    "section_style_desc": "Визуальный стиль ASCII и базовые параметры",
    "section_fx_desc": "Контраст, гамма и фильтры",
    "section_render_desc": "Кодек и параметры сохранения",
    "section_pro_desc": "Продвинутые фильтры и стилизация",
    "none_style": "None (без преобразования)",
    "render_prompt_body": "Выберите действие: рендер медиа или экспорт текущего кадра в TXT.",
    "pro_scan_strength": "Сила скан-линий (%)",
    "pro_scan_step": "Шаг скан-линий (px)",
    "pro_glitch": "Глитч (%)",
    "pro_curvature": "Выпуклость CRT (%)",
    "pro_ribbing": "Ребристость экрана (%)",
    "tool_glitch": "Глитч",
    "editor": "Редактор",
    "live_preview": "Живое превью (в реальном времени)",
    "brightness": "Яркость",
    "saturation": "Насыщенность",
    "hue": "Тон",
    "exposure": "Экспозиция",
    "temperature": "Температура",
    "crop": "Кадрирование",
    "add_text": "Текст",
    "open_player": "Открыть плеер",
    "keep_source_audio": "Сохранять звук источника",
    "apply": "Применить",
    "gpu_load": "Нагрузка GPU",
    "eta": "Осталось",
    "render_speed": "Скорость",
})
TRANSLATIONS["zh"].update({
    "file": "文件",
    "tools": "工具",
    "language": "语言",
    "help": "帮助",
    "theme": "主题",
    "high": "高",
    "advanced": "高级",
    "yes": "是",
    "defaults": "默认",
    "output_size": "输出 (宽 x 高)",
    "tutorial_confirm": "准备开始教程吗？",
    "section_style_desc": "ASCII 视觉风格与基础参数",
    "section_fx_desc": "对比度、伽马与滤镜",
    "section_render_desc": "编码器与导出参数",
    "section_pro_desc": "高级滤镜与风格化",
    "render_prompt_body": "请选择：渲染媒体，或将当前帧导出为 TXT。",
    "pro_scan_strength": "扫描线强度 (%)",
    "pro_scan_step": "扫描线间距 (px)",
    "pro_glitch": "故障效果 (%)",
    "pro_curvature": "CRT 曲面 (%)",
    "pro_ribbing": "屏幕条纹 (%)",
    "tool_glitch": "故障效果",
    "editor": "编辑器",
    "live_preview": "实时预览",
    "brightness": "亮度",
    "saturation": "饱和度",
    "hue": "色相",
    "exposure": "曝光",
    "temperature": "色温",
    "crop": "裁剪",
    "add_text": "文字",
    "open_player": "打开播放器",
    "keep_source_audio": "保留源音频",
    "apply": "应用",
    "gpu_load": "GPU 负载",
    "eta": "剩余时间",
    "render_speed": "速度",
})
TRANSLATIONS["en"].update({
    "confirm_close": "Close application?",
    "editor_layers": "Layers",
    "editor_text": "Text",
    "editor_mask": "Mask",
    "editor_trim": "Trim",
    "editor_audio": "Audio",
    "editor_nodes": "Nodes",
    "editor_fullscreen": "Fullscreen editor",
    "editor_add_layer": "Add text layer",
    "editor_remove_layer": "Remove layer",
    "editor_import_audio": "Import audio",
    "editor_audio_from_video": "Audio from source video",
    "editor_save_script": "Save script",
    "editor_load_script": "Load script",
    "editor_timeline": "Timeline",
    "editor_interactive": "Interactive mode",
    "editor_crop_mode": "Crop area",
    "editor_mask_mode": "Mask area",
    "editor_text_mode": "Layer move",
    "editor_none_mode": "Off",
    "editor_apply": "Apply to project",
    "editor_reset": "Reset editor",
    "editor_gain": "Gain (dB)",
    "editor_lowpass": "Low-pass (Hz)",
    "editor_nodes_chain": "Node chain",
    "editor_add_node": "Add node",
    "editor_remove_node": "Remove node",
    "editor_move_up": "Up",
    "editor_move_down": "Down",
    "editor_pick_color": "Color",
    "editor_trim_start": "Trim start (ms)",
    "editor_trim_end": "Trim end (ms)",
    "editor_fullscreen_exit": "Exit fullscreen editor",
    "update_status_checking": "Checking updates...",
    "update_available": "Update available",
    "update_none": "Latest version installed",
    "update_install": "Install",
    "update_later": "Later",
    "update_error": "Update check failed",
    "update_downloading": "Downloading update...",
    "update_ready": "Starting installer...",
    "menu_check_updates": "Check for updates",
    "update_feed_help": "Set 'update_feed_url' in settings file to publish your own updates.",
    "watermark_text": "Watermark text",
    "save_preset": "Save preset",
    "load_preset": "Load preset",
    "preset_saved": "Preset saved",
    "preset_loaded": "Preset loaded",
    "custom_theme": "Custom theme",
    "custom_bg": "Custom background",
    "custom_color_bg": "BG color",
    "custom_color_fg": "Text color",
    "custom_color_accent": "Accent color",
    "icon_pack_path": "Icon pack folder",
    "icon_pack_url": "Icon pack URL",
    "editor_media_layers": "Media layers",
    "editor_add_media_layer": "Add media layer",
    "editor_remove_media_layer": "Remove media layer",
    "editor_pick_media": "Choose media",
    "editor_media_mode": "Media layer move",
    "editor_blend": "Blend",
    "font_family": "Fonts",
    "font_size": "Font size",
    "editor_ascii_tab": "ASCII + PRO",
    "editor_ascii_preview": "Preview with ASCII style + Pro Tools",
    "editor_ascii_apply": "Apply ASCII+PRO settings to main project",
    "editor_ascii_hint": "Combine editor transforms with ASCII style and Pro Tools for final look preview.",
})
TRANSLATIONS["ru"].update({
    "confirm_close": "Закрыть программу?",
    "editor_layers": "Слои",
    "editor_text": "Текст",
    "editor_mask": "Маска",
    "editor_trim": "Обрезка",
    "editor_audio": "Аудио",
    "editor_nodes": "Ноды",
    "editor_fullscreen": "Полноэкранный редактор",
    "editor_add_layer": "Добавить текстовый слой",
    "editor_remove_layer": "Удалить слой",
    "editor_import_audio": "Импорт аудио",
    "editor_audio_from_video": "Аудио из исходного видео",
    "editor_save_script": "Сохранить скрипт",
    "editor_load_script": "Загрузить скрипт",
    "editor_timeline": "Таймлайн",
    "editor_interactive": "Интерактивный режим",
    "editor_crop_mode": "Область кадрирования",
    "editor_mask_mode": "Область маски",
    "editor_text_mode": "Перемещение слоя",
    "editor_none_mode": "Выкл",
    "editor_apply": "Применить в проект",
    "editor_reset": "Сбросить редактор",
    "editor_gain": "Усиление (дБ)",
    "editor_lowpass": "Low-pass (Гц)",
    "editor_nodes_chain": "Цепочка нод",
    "editor_add_node": "Добавить ноду",
    "editor_remove_node": "Удалить ноду",
    "editor_move_up": "Вверх",
    "editor_move_down": "Вниз",
    "editor_pick_color": "Цвет",
    "editor_trim_start": "Начало обрезки (мс)",
    "editor_trim_end": "Конец обрезки (мс)",
    "editor_fullscreen_exit": "Выйти из полноэкранного редактора",
    "update_status_checking": "Проверка обновлений...",
    "update_available": "Доступно обновление",
    "update_none": "Установлена последняя версия",
    "update_install": "Установить",
    "update_later": "Позже",
    "update_error": "Ошибка проверки обновлений",
    "update_downloading": "Загрузка обновления...",
    "update_ready": "Запуск установщика...",
    "menu_check_updates": "Проверить обновления",
    "update_feed_help": "Для своих обновлений укажите 'update_feed_url' в файле настроек.",
    "watermark_text": "Текст водяного знака",
    "save_preset": "Сохранить пресет",
    "load_preset": "Загрузить пресет",
    "preset_saved": "Пресет сохранён",
    "preset_loaded": "Пресет загружен",
    "custom_theme": "Кастомная тема",
    "custom_bg": "Кастомный фон",
    "custom_color_bg": "Цвет фона",
    "custom_color_fg": "Цвет текста",
    "custom_color_accent": "Акцент",
    "icon_pack_path": "Папка иконок",
    "icon_pack_url": "URL набора иконок",
    "editor_media_layers": "Медиа-слои",
    "editor_add_media_layer": "Добавить медиа-слой",
    "editor_remove_media_layer": "Удалить медиа-слой",
    "editor_pick_media": "Выбрать медиа",
    "editor_media_mode": "Перемещение медиа-слоя",
    "editor_blend": "Смешивание",
    "font_family": "Шрифты",
    "font_size": "Размер шрифта",
    "editor_ascii_tab": "ASCII + PRO",
    "editor_ascii_preview": "Превью со стилем ASCII + Pro Tools",
    "editor_ascii_apply": "Применить настройки ASCII+PRO к основному проекту",
    "editor_ascii_hint": "Скрещивайте трансформации редактора со стилем ASCII и Pro Tools прямо в превью.",
})
TRANSLATIONS["zh"].update({
    "confirm_close": "关闭程序？",
    "editor_layers": "图层",
    "editor_text": "文字",
    "editor_mask": "遮罩",
    "editor_trim": "剪辑",
    "editor_audio": "音频",
    "editor_nodes": "节点",
    "editor_fullscreen": "全屏编辑器",
    "editor_add_layer": "添加文字图层",
    "editor_remove_layer": "删除图层",
    "editor_import_audio": "导入音频",
    "editor_audio_from_video": "使用源视频音频",
    "editor_save_script": "保存脚本",
    "editor_load_script": "加载脚本",
    "editor_timeline": "时间轴",
    "editor_interactive": "交互模式",
    "editor_crop_mode": "裁剪区域",
    "editor_mask_mode": "遮罩区域",
    "editor_text_mode": "图层拖动",
    "editor_none_mode": "关闭",
    "editor_apply": "应用到项目",
    "editor_reset": "重置编辑器",
    "editor_gain": "增益 (dB)",
    "editor_lowpass": "低通 (Hz)",
    "editor_nodes_chain": "节点链",
    "editor_add_node": "添加节点",
    "editor_remove_node": "删除节点",
    "editor_move_up": "上移",
    "editor_move_down": "下移",
    "editor_pick_color": "颜色",
    "editor_trim_start": "剪辑起点 (ms)",
    "editor_trim_end": "剪辑终点 (ms)",
    "editor_fullscreen_exit": "退出全屏编辑器",
    "update_status_checking": "正在检查更新...",
    "update_available": "发现可用更新",
    "update_none": "已是最新版本",
    "update_install": "安装",
    "update_later": "稍后",
    "update_error": "更新检查失败",
    "update_downloading": "正在下载更新...",
    "update_ready": "正在启动安装器...",
    "menu_check_updates": "检查更新",
    "update_feed_help": "在设置文件填写 'update_feed_url' 可发布你自己的更新。",
    "watermark_text": "水印文字",
    "save_preset": "保存预设",
    "load_preset": "加载预设",
    "preset_saved": "预设已保存",
    "preset_loaded": "预设已加载",
    "custom_theme": "自定义主题",
    "custom_bg": "自定义背景",
    "custom_color_bg": "背景颜色",
    "custom_color_fg": "文字颜色",
    "custom_color_accent": "强调色",
    "icon_pack_path": "图标包目录",
    "icon_pack_url": "图标包 URL",
    "editor_media_layers": "媒体图层",
    "editor_add_media_layer": "添加媒体图层",
    "editor_remove_media_layer": "删除媒体图层",
    "editor_pick_media": "选择媒体",
    "editor_media_mode": "媒体图层移动",
    "editor_blend": "混合模式",
    "font_family": "字体",
    "font_size": "字体大小",
    "editor_ascii_tab": "ASCII + PRO",
    "editor_ascii_preview": "使用 ASCII 风格 + Pro Tools 预览",
    "editor_ascii_apply": "将 ASCII+PRO 设置应用到主项目",
    "editor_ascii_hint": "把编辑器变换与 ASCII 风格和 Pro Tools 结合，直接预览最终效果。",
})
STYLE_HELP["ru"].update({
    "bw": "BW: классический монохром. Высокий контраст и максимальная скорость.",
    "red": "Red: монохром в красных тонах для ретро-эффекта.",
    "color": "Color: сохраняет исходные цвета для насыщенного ASCII.",
    "matrix": "Matrix: зелёный кибер-эффект.",
    "matrix2": "Matrix2: более яркий и плотный матричный стиль.",
    "neon": "Neon: насыщенное свечение и сильный контраст.",
    "pastel": "Pastel: мягкие цвета и деликатный контраст.",
    "custom": "Custom: собственные цвет текста и фона.",
    "none": "None: без ASCII-преобразования, сохраняет оригинальный кадр (с выбранными FX).",
})
STYLE_HELP["zh"].update({
    "bw": "BW：经典黑白，高对比，速度最快。",
    "red": "Red：红色单色复古风。",
    "color": "Color：保留原始颜色，层次更丰富。",
    "matrix": "Matrix：绿色赛博风格。",
    "matrix2": "Matrix2：更亮、更密的矩阵效果。",
    "neon": "Neon：高饱和发光风格。",
    "pastel": "Pastel：柔和色彩，低对比度。",
    "custom": "Custom：自定义文字和背景颜色。",
    "none": "None：不做 ASCII 转换，保留原图（应用所选 FX）。",
})
CODEC_HELP["ru"].update({
    "libx264": "Самый распространённый кодек для MP4. Лучшая совместимость.",
    "h264": "Профиль H.264, хорошая совместимость.",
    "mpeg4": "Старый кодек: быстрее, но менее эффективен.",
    "libvpx": "VP8/VP9 для WebM; может работать медленнее.",
})
CODEC_HELP["zh"].update({
    "libx264": "最常见的 MP4 编码器，兼容性最好。",
    "h264": "H.264 配置，兼容性良好。",
    "mpeg4": "较旧编码器，速度快但压缩效率较低。",
    "libvpx": "用于 WebM 的 VP8/VP9，可能更慢。",
})

class TutorialDialog(QDialog):
    def __init__(self, parent, steps, tr):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(tr.get("tutorial", "Tutorial"))
        self.steps = steps
        self.idx = 0
        self.tr = tr
        self.setMinimumSize(520, 220)
        layout = QVBoxLayout(self)
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight:700; font-size:15px;")
        self.body = QLabel("")
        self.body.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.body, 1)
        row = QHBoxLayout()
        self.prev_btn = QPushButton("<")
        self.next_btn = QPushButton(">")
        self.skip_btn = QPushButton(tr.get("tutorial_skip", "Skip (Esc)"))
        self.prev_btn.clicked.connect(self._prev)
        self.next_btn.clicked.connect(self._next)
        self.skip_btn.clicked.connect(self.reject)
        row.addWidget(self.prev_btn)
        row.addWidget(self.next_btn)
        row.addStretch(1)
        row.addWidget(self.skip_btn)
        layout.addLayout(row)
        self._render()

    def _render(self):
        title, body = self.steps[self.idx]
        self.title.setText(title)
        self.body.setText(body)
        self.prev_btn.setEnabled(self.idx > 0)
        self.next_btn.setText(self.tr.get("done", "Done") if self.idx == len(self.steps) - 1 else ">")

    def _prev(self):
        if self.idx > 0:
            self.idx -= 1
            self._render()

    def _next(self):
        if self.idx >= len(self.steps) - 1:
            self.accept()
            return
        self.idx += 1
        self._render()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.reject()
            return
        return super().keyPressEvent(ev)


class GuidedTourOverlay(QFrame):
    def __init__(self, parent, steps, tr):
        super().__init__(parent)
        # overlay handles click-to-advance on free space
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background: rgba(0,0,0,0.55);")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.steps = steps
        self.tr = tr
        self.idx = 0
        self.box = QFrame(self)
        self.box.setStyleSheet("background: rgba(18,22,32,0.95); border-radius:12px; color: white;")
        self.title = QLabel(self.box)
        self.title.setStyleSheet("font-weight:700; font-size:15px; color: white;")
        self.body = QLabel(self.box)
        self.body.setWordWrap(True)
        self.body.setStyleSheet("color: #dbe4f2;")
        # buttons moved to external control panel

    def showEvent(self, ev):
        self.setGeometry(self.parent().rect())
        self._render()
        try:
            self.setFocus(Qt.ActiveWindowFocusReason)
        except Exception:
            pass
        return super().showEvent(ev)

    def _render(self):
        step = self.steps[self.idx]
        target, title, body = step
        try:
            if target is not None and hasattr(self.parent(), "_ensure_tutorial_target_visible"):
                scrolled = self.parent()._ensure_tutorial_target_visible(target)
                if scrolled and not getattr(self, "_rerender_pending", False):
                    self._rerender_pending = True
                    QTimer.singleShot(0, self._rerender_after_scroll)
        except Exception:
            pass
        try:
            if hasattr(self.parent(), "_resolve_info_text"):
                title = self.parent()._resolve_info_text(title, "")
                body = self.parent()._resolve_info_text(body, "")
            else:
                if isinstance(title, dict):
                    title = title.get(getattr(self.parent(), "lang", "en"), title.get("en", ""))
                if isinstance(body, dict):
                    body = body.get(getattr(self.parent(), "lang", "en"), body.get("en", ""))
        except Exception:
            pass
        self.title.setText(str(title))
        self.body.setText(str(body))
        # layout box
        bw, bh = 360, 160
        self.box.setGeometry(20, 20, bw, bh)
        self.title.setGeometry(16, 12, bw-32, 24)
        self.body.setGeometry(16, 40, bw-32, 70)
        # position near target
        try:
            if target is not None:
                gp = target.mapTo(self.parent(), QPoint(0, 0))
                tx, ty, tw, th = gp.x(), gp.y(), target.width(), target.height()
                if tx > (self.width() // 2):
                    candidates = [
                        (tx - bw - 12, ty),         # left
                        (tx, ty + th + 12),         # below
                        (tx, ty - bh - 12),         # above
                        (tx + tw + 12, ty),         # right
                    ]
                else:
                    candidates = [
                        (tx + tw + 12, ty),         # right
                        (tx, ty + th + 12),         # below
                        (tx, ty - bh - 12),         # above
                        (tx - bw - 12, ty),         # left
                    ]
                def clamp(pos):
                    return (
                        max(12, min(self.width() - bw - 12, pos[0])),
                        max(12, min(self.height() - bh - 12, pos[1]))
                    )
                def overlap(pos):
                    bx, by = pos
                    return not (bx + bw < tx or bx > tx + tw or by + bh < ty or by > ty + th)
                chosen = None
                for c in candidates:
                    cc = clamp(c)
                    if not overlap(cc):
                        chosen = cc
                        break
                if chosen is None:
                    chosen = clamp((tx + tw + 12, ty))
                self.box.move(chosen[0], chosen[1])
        except Exception:
            pass
        self.update()

    def _rerender_after_scroll(self):
        try:
            self._rerender_pending = False
            self._render()
        except Exception:
            pass

    def _current_target_rect(self):
        try:
            step = self.steps[self.idx]
            target = step[0]
            if target is None:
                return QRect()
            gp = target.mapTo(self.parent(), QPoint(0, 0))
            return QRect(gp.x() - 6, gp.y() - 6, target.width() + 12, target.height() + 12)
        except Exception:
            return QRect()

    def _notify_panel(self):
        try:
            p = self.parent()
            panel = getattr(p, "_tour_panel", None)
            if panel is not None:
                panel._render()
        except Exception:
            pass

    def _advance(self):
        try:
            if self.idx >= len(self.steps) - 1:
                p = self.parent()
                panel = getattr(p, "_tour_panel", None)
                if panel is not None:
                    panel._skip()
                else:
                    self.hide()
                    self.deleteLater()
                return
            self.idx += 1
            self._render()
            self._notify_panel()
        except Exception:
            pass

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            step = self.steps[self.idx]
            target = step[0]
            if target is None:
                return
            gp = target.mapTo(self.parent(), QPoint(0, 0))
            rect = QRect(gp.x()-6, gp.y()-6, target.width()+12, target.height()+12)
            p.setBrush(QColor(255, 255, 255, 0))
            p.setPen(QColor(130, 180, 255, 200))
            p.drawRoundedRect(rect, 10, 10)
        finally:
            if p.isActive():
                p.end()

    def mousePressEvent(self, ev):
        try:
            if ev.button() == Qt.LeftButton:
                try:
                    pos = ev.position().toPoint()
                except Exception:
                    pos = ev.pos()
                if self.box.geometry().contains(pos):
                    return super().mousePressEvent(ev)
                target_rect = self._current_target_rect()
                if not target_rect.isNull() and target_rect.contains(pos):
                    return super().mousePressEvent(ev)
                self._advance()
                ev.accept()
                return
        except Exception:
            pass
        return super().mousePressEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()
            self.deleteLater()
            return
        return super().keyPressEvent(ev)


class TourPanel(QFrame):
    def __init__(self, parent, overlay, tr):
        super().__init__(parent)
        self.overlay = overlay
        self.tr = tr
        self.setStyleSheet("background: rgba(18,22,32,0.95); border-radius:12px;")
        self.setFixedSize(488, 92)
        self.title = QLabel(self)
        self.title.setStyleSheet("font-weight:700; color: white;")
        self.title.setGeometry(12, 10, 260, 22)
        self.step_lbl = QLabel(self)
        self.step_lbl.setStyleSheet("color:#9fc2f5; font-size:11px;")
        self.step_lbl.setGeometry(300, 12, 96, 18)
        self.step_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.prev_btn = QPushButton("<", self)
        self.next_btn = QPushButton(">", self)
        self.skip_btn = QPushButton(tr.get("tutorial_skip", "Skip (Esc)"), self)
        for b in (self.prev_btn, self.next_btn, self.skip_btn):
            b.setStyleSheet("QPushButton{background:#1f2a44;color:white;border-radius:6px;padding:6px 10px;} QPushButton:hover{background:#2b3a5c;}")
        self._layout_controls()
        self.prev_btn.clicked.connect(self._prev)
        self.next_btn.clicked.connect(self._next)
        self.skip_btn.clicked.connect(self._skip)
        self._render()

    def _layout_controls(self):
        y = 46
        h = 30
        self.prev_btn.setGeometry(12, y, 40, h)
        self.next_btn.setGeometry(58, y, 40, h)
        fm = self.skip_btn.fontMetrics()
        skip_w = max(126, min(220, fm.horizontalAdvance(self.skip_btn.text()) + 24))
        self.skip_btn.setGeometry(self.width() - 12 - skip_w, y, skip_w, h)
        step_w = 92
        self.step_lbl.setGeometry(self.skip_btn.x() - step_w - 8, 12, step_w, 18)
        self.title.setGeometry(12, 10, max(110, self.step_lbl.x() - 20), 22)

    def _render(self):
        idx = self.overlay.idx
        step = self.overlay.steps[idx]
        target = step[0] if isinstance(step, (list, tuple)) and len(step) > 0 else None
        title = step[1] if isinstance(step, (list, tuple)) and len(step) > 1 else ""
        try:
            if hasattr(self.parent(), "_resolve_info_text"):
                title = self.parent()._resolve_info_text(title, "")
        except Exception:
            pass
        self.title.setText(str(title))
        self.step_lbl.setText(f"{idx + 1}/{len(self.overlay.steps)}")
        self._layout_controls()
        self.prev_btn.setEnabled(idx > 0)
        self.next_btn.setText(self.tr.get("done", "Done") if idx == len(self.overlay.steps) - 1 else ">")
        try:
            p = self.parent()
            if p is None:
                return
            x = max(12, p.width() - self.width() - 12)
            y = 12
            if target is not None:
                gp = target.mapTo(p, QPoint(0, 0))
                # Keep control panel on the side opposite to the highlighted control.
                if gp.x() > p.width() // 2:
                    x = 12
                else:
                    x = max(12, p.width() - self.width() - 12)
                # Avoid covering target vertically.
                if gp.y() < (self.height() + 30):
                    y = min(max(12, gp.y() + target.height() + 10), max(12, p.height() - self.height() - 12))
            self.move(x, y)
        except Exception:
            pass

    def _prev(self):
        if self.overlay.idx > 0:
            self.overlay.idx -= 1
            self.overlay._render()
            self._render()

    def _next(self):
        self.overlay._advance()

    def _skip(self):
        try:
            self.overlay.hide()
            self.overlay.deleteLater()
        except Exception:
            pass
        try:
            self.hide()
            self.deleteLater()
        except Exception:
            pass


class OverlayDialog(QDialog):
    def __init__(self, parent, theme="dark", title=""):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._theme = theme
        self._panel_size = None
        self._sound_mgr = getattr(parent, "_sound_mgr", None)
        self._played_open = False
        self._open_anim_started = False
        self._open_anim = None
        self._open_anim_pos = None
        self._blur_targets = []
        self._apply_blur(True)
        self.main = QFrame(self)
        self.main.setObjectName("overlay_main")
        self.main.setStyleSheet(self._panel_css())
        self.title = QLabel(title, self.main)
        self.title.setStyleSheet("font-weight:700; font-size:15px;")
        self.title.setStyleSheet("font-weight:700; font-size:16px;")
        self.close_btn = QPushButton("x", self.main)
        self.close_btn.setFixedSize(28, 28)
        try:
            self.close_btn.setText("x")
            p = self.parent()
            if p is not None and hasattr(p, "_load_svg_icon"):
                ico_color = "#111111" if self._theme == "light" else "#e6eef6"
                ico = p._load_svg_icon("close", ico_color)
                if ico is not None:
                    self.close_btn.setText("")
                    self.close_btn.setIcon(ico)
                    self.close_btn.setIconSize(QSize(12, 12))
        except Exception:
            pass
        self.close_btn.clicked.connect(self.accept)
        self.layout_main = QVBoxLayout(self.main)
        self.layout_main.setContentsMargins(16, 12, 16, 16)
        row = QHBoxLayout()
        row.addWidget(self.title)
        row.addStretch(1)
        row.addWidget(self.close_btn)
        self.layout_main.addLayout(row)
        self.body_container = QFrame(self.main)
        self.body_layout = QVBoxLayout(self.body_container)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.layout_main.addWidget(self.body_container, 1)

    def set_panel_size(self, w, h):
        try:
            self._panel_size = (int(w), int(h))
        except Exception:
            self._panel_size = None

    def set_body_widget(self, w):
        self.body_layout.addWidget(w)

    def set_body_text(self, txt):
        lbl = QLabel(txt)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size:14px;")
        self.body_layout.addWidget(lbl)

    def _panel_css(self):
        if self._theme == "light":
            return "QFrame#overlay_main{background:rgba(255,255,255,0.98); border-radius:12px; color:#111;} QPushButton{color:#111;background:#e9edf5;border:1px solid #c9d2e1;border-radius:8px;} QPushButton:hover{background:#dde4ef;}"
        return "QFrame#overlay_main{background:rgba(18,22,32,0.96); border-radius:12px; color:#e8edf7;} QPushButton{color:#e8edf7;background:#1f2a44;border:1px solid #2a395d;border-radius:8px;} QPushButton:hover{background:#273454;}"

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        w, h = self.width(), self.height()
        if self._panel_size:
            mw, mh = self._panel_size
            mw = min(mw, w - 120)
            mh = min(mh, h - 120)
        else:
            mw, mh = min(420, w - 140), min(240, h - 140)
        self.main.setGeometry((w - mw) // 2, (h - mh) // 2, mw, mh)

    def showEvent(self, ev):
        try:
            p = self.parent()
            if p is not None:
                self.setGeometry(p.rect())
                p.installEventFilter(self)
            else:
                self.setGeometry(self.rect())
        except Exception:
            try:
                self.setGeometry(self.parent().rect())
            except Exception:
                pass
        try:
            if self._sound_mgr and not self._played_open:
                self._played_open = True
                self._sound_mgr.play_open()
        except Exception:
            pass
        out = super().showEvent(ev)
        try:
            if not bool(getattr(self, "_open_anim_started", False)):
                self._open_anim_started = True
                end_pos = self.main.pos()
                start_pos = QPoint(end_pos.x(), end_pos.y() + 14)
                self.main.move(start_pos)
                eff = QGraphicsOpacityEffect(self.main)
                eff.setOpacity(0.0)
                self.main.setGraphicsEffect(eff)
                a1 = QPropertyAnimation(eff, b"opacity", self)
                a1.setDuration(210)
                a1.setStartValue(0.0)
                a1.setEndValue(1.0)
                a1.setEasingCurve(QEasingCurve.OutCubic)
                a2 = QPropertyAnimation(self.main, b"pos", self)
                a2.setDuration(220)
                a2.setStartValue(start_pos)
                a2.setEndValue(end_pos)
                a2.setEasingCurve(QEasingCurve.OutCubic)
                a1.finished.connect(lambda: self.main.setGraphicsEffect(None))
                self._open_anim = a1
                self._open_anim_pos = a2
                a1.start()
                a2.start()
        except Exception:
            pass
        return out

    def hideEvent(self, ev):
        try:
            p = self.parent()
            if p is not None:
                p.removeEventFilter(self)
        except Exception:
            pass
        return super().hideEvent(ev)

    def eventFilter(self, obj, ev):
        try:
            if obj is self.parent() and ev.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.WindowStateChange):
                self.setGeometry(self.parent().rect())
                self.raise_()
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor(0, 0, 0, 172))
        finally:
            if p.isActive():
                p.end()

    def _apply_blur(self, on):
        try:
            if not self.parent():
                return
            if on:
                self._blur_targets = []
                targets = []
                try:
                    mb = self.parent().menuBar()
                    if mb is not None:
                        targets.append(mb)
                except Exception:
                    pass
                try:
                    cw = self.parent().centralWidget()
                    if cw is not None:
                        targets.append(cw)
                except Exception:
                    pass
                for attr in ("gallery_frame", "left_frame", "right_frame", "player_controls"):
                    try:
                        w = getattr(self.parent(), attr, None)
                        if w is not None:
                            targets.append(w)
                    except Exception:
                        pass
                for w in targets:
                    try:
                        if w in self._blur_targets:
                            continue
                        eff = QGraphicsBlurEffect(w)
                        eff.setBlurRadius(8)
                        w.setGraphicsEffect(eff)
                        self._blur_targets.append(w)
                    except Exception:
                        pass
            else:
                for w in list(getattr(self, "_blur_targets", [])):
                    try:
                        w.setGraphicsEffect(None)
                    except Exception:
                        pass
                self._blur_targets = []
        except Exception:
            pass

    def closeEvent(self, ev):
        try:
            self._apply_blur(False)
            if self._sound_mgr:
                self._sound_mgr.play_close()
        except Exception:
            pass
        return super().closeEvent(ev)

    def accept(self):
        try:
            self._apply_blur(False)
        except Exception:
            pass
        return super().accept()

    def reject(self):
        try:
            self._apply_blur(False)
        except Exception:
            pass
        return super().reject()


class WelcomeDialog(QDialog):
    def __init__(self, parent, lang="en"):
        super().__init__(parent)
        self.lang = lang
        self.selected_lang = lang if lang in ("en", "ru", "zh") else "en"
        self.selected_theme = str(getattr(parent, "theme", "dark") or "dark")
        if self.selected_theme not in THEME_NAMES:
            self.selected_theme = "dark"
        self.start_tutorial = False
        self._step = 0
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._frame_idx = 0
        self._glow_phase = 0.0
        self._ascii_frames = [
            "   ___   ____   ____ ___ ___ \n  / _ | / __/  / __/|_ _/ _ \\\n / __ |\\ \\   _/ /    / // // /\n/_/ |_|___/ /___/  /___/____/ \n        A S C I I   S T U D I O",
            "   ___   ____   ____ ___ ___ \n  / _ | / __/  / __/|_ _/ _ \\\n / __ |\\ \\   _/ /    / // // /\n/_/ |_|___/ /___/  /___/____/ \n        A S C I I   S T U D I O .",
            "   ___   ____   ____ ___ ___ \n  / _ | / __/  / __/|_ _/ _ \\\n / __ |\\ \\   _/ /    / // // /\n/_/ |_|___/ /___/  /___/____/ \n        A S C I I   S T U D I O ..",
            "   ___   ____   ____ ___ ___ \n  / _ | / __/  / __/|_ _/ _ \\\n / __ |\\ \\   _/ /    / // // /\n/_/ |_|___/ /___/  /___/____/ \n        A S C I I   S T U D I O ...",
        ]
        self.panel = QFrame(self)
        self.panel.setObjectName("welcome_panel")
        self.panel.setStyleSheet(
            "QFrame#welcome_panel{background: rgba(2,6,14,0.96); border:1px solid rgba(126,178,255,0.40); border-radius:16px;}"
        )
        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(10)
        self.title = QLabel("ASCII Studio")
        self.title.setStyleSheet("font-size:20px; font-weight:700; color:#eaf2ff;")
        lay.addWidget(self.title, 0, Qt.AlignHCenter)
        self.ascii_lbl = QLabel(self._ascii_frames[0])
        self.ascii_lbl.setStyleSheet("font-family:'Consolas'; font-size:12px; color:#9fd0ff;")
        self.ascii_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.ascii_lbl)

        self.step_lbl = QLabel("")
        self.step_lbl.setStyleSheet("font-size:12px; color:#a7cfff;")
        lay.addWidget(self.step_lbl, 0, Qt.AlignHCenter)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_welcome())
        self.stack.addWidget(self._build_page_features())
        self.stack.addWidget(self._build_page_tutorial())
        lay.addWidget(self.stack, 1)

        btn_row = QHBoxLayout()
        self.back_btn = QPushButton("<")
        self.next_btn = QPushButton(">")
        self.finish_btn = QPushButton(self._btn_text())
        for b in (self.back_btn, self.next_btn, self.finish_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background: rgba(38,62,110,0.85); color:#f0f6ff; border:1px solid rgba(140,190,255,0.45); border-radius:10px; padding:8px 18px;}"
                "QPushButton:hover{background: rgba(52,78,128,0.95);}"
            )
        self.back_btn.setFixedWidth(60)
        self.next_btn.setFixedWidth(60)
        self.back_btn.clicked.connect(self._on_back)
        self.next_btn.clicked.connect(self._on_next)
        self.finish_btn.clicked.connect(self._on_finish)
        btn_row.addWidget(self.back_btn)
        btn_row.addWidget(self.next_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.finish_btn)
        lay.addLayout(btn_row)
        self._update_step_ui()

        self._op_eff = QGraphicsOpacityEffect(self.ascii_lbl)
        self._op_eff.setOpacity(0.72)
        self.ascii_lbl.setGraphicsEffect(self._op_eff)
        self._op_anim = QPropertyAnimation(self._op_eff, b"opacity", self)
        self._op_anim.setDuration(1400)
        self._op_anim.setStartValue(0.45)
        self._op_anim.setEndValue(1.0)
        self._op_anim.setLoopCount(-1)
        self._op_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._op_anim.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(180)
        try:
            self.parent().installEventFilter(self)
        except Exception:
            pass

    def _txt(self, en, ru, zh):
        self.selected_lang = self.lang if self.lang in ("en", "ru", "zh") else self.selected_lang
        if self.lang == "ru":
            return _repair_mojibake_text(ru, lang_hint="ru")
        if self.lang == "zh":
            return _repair_mojibake_text(zh, lang_hint="zh")
        return _repair_mojibake_text(en, lang_hint="en")

    def _build_page_welcome(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)
        p1 = QLabel(self._txt(
            "Welcome! Choose language and read a short intro.",
            "Добро пожаловать! Выберите язык и кратко ознакомьтесь с программой.",
            "欢迎！请选择语言并查看简短介绍。",
        ))
        p1.setWordWrap(True)
        p1.setStyleSheet("font-size:13px; color:#dbe8ff;")
        self.welcome_lang_combo = QComboBox()
        self.welcome_lang_combo.addItems(["en", "ru", "zh"])
        self.welcome_lang_combo.setCurrentText(self.selected_lang)
        self.welcome_lang_combo.currentTextChanged.connect(self._on_lang_changed_live)
        self.welcome_theme_combo = QComboBox()
        self.welcome_theme_combo.addItems(THEME_NAMES)
        self.welcome_theme_combo.setCurrentText(self.selected_theme if self.selected_theme in THEME_NAMES else "dark")
        self.welcome_theme_combo.currentTextChanged.connect(lambda v: setattr(self, "selected_theme", str(v)))
        p2 = QLabel(self._txt(
            "ASCII Studio converts images, GIF and videos into ASCII styles with live preview.",
            "ASCII Studio преобразует изображения, GIF и видео в ASCII-стили с живым превью.",
            "ASCII Studio 可将图片、GIF 和视频转换为 ASCII 风格并实时预览。",
        ))
        p2.setWordWrap(True)
        p2.setStyleSheet("font-size:13px; color:#cfe0f7;")
        l.addWidget(p1)
        l.addWidget(self.welcome_lang_combo)
        l.addWidget(QLabel(self._txt("Theme", "Тема", "主题")))
        l.addWidget(self.welcome_theme_combo)
        l.addWidget(p2)
        l.addStretch(1)
        return w

    def _build_page_features(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)
        p = QLabel(self._txt(
            "Pros and capabilities:\n• ASCII styles and custom colors\n• Built-in gallery and media player\n• Export PNG / GIF / MP4 / TXT\n• Pro Tools filters and presets",
            "Плюсы и возможности:\n• ASCII-стили и кастомные цвета\n• Встроенная галерея и медиаплеер\n• Экспорт PNG / GIF / MP4 / TXT\n• Фильтры и пресеты Pro Tools",
            "优势与能力:\n• ASCII 风格与自定义颜色\n• 内置画廊与媒体播放器\n• 导出 PNG / GIF / MP4 / TXT\n• Pro Tools 滤镜与预设",
        ))
        p.setWordWrap(True)
        p.setStyleSheet("font-size:13px; color:#dbe8ff;")
        l.addWidget(p)
        l.addStretch(1)
        return w

    def _build_page_tutorial(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)
        p = QLabel(self._txt(
            "You can start guided tutorial now or later from Settings. Good luck!",
            "Можно сразу запустить обучение или сделать это позже через Настройки. Удачи!",
            "可以现在开始引导教程，也可稍后在设置中启动。祝你使用愉快！",
        ))
        p.setWordWrap(True)
        p.setStyleSheet("font-size:13px; color:#dbe8ff;")
        self.welcome_tutorial_chk = QCheckBox(self._txt("Start tutorial after welcome", "Запустить обучение после приветствия", "欢迎后启动教程"))
        self.welcome_tutorial_chk.setChecked(False)
        l.addWidget(p)
        l.addWidget(self.welcome_tutorial_chk)
        l.addStretch(1)
        return w

    def _update_step_ui(self):
        self.step_lbl.setText(self._txt(
            f"Step {self._step + 1}/3",
            f"Шаг {self._step + 1}/3",
            f"步骤 {self._step + 1}/3",
        ))
        self.back_btn.setEnabled(self._step > 0)
        self.next_btn.setVisible(self._step < 2)
        self.finish_btn.setVisible(self._step == 2)

    def _on_back(self):
        if self._step <= 0:
            return
        self._step -= 1
        self.stack.setCurrentIndex(self._step)
        self._update_step_ui()

    def _on_next(self):
        if self._step >= 2:
            return
        self._step += 1
        self.stack.setCurrentIndex(self._step)
        self._update_step_ui()

    def _on_finish(self):
        try:
            self.selected_lang = self.welcome_lang_combo.currentText()
        except Exception:
            pass
        try:
            self.selected_theme = self.welcome_theme_combo.currentText()
        except Exception:
            pass
        try:
            self.start_tutorial = bool(self.welcome_tutorial_chk.isChecked())
        except Exception:
            self.start_tutorial = False
        self.accept()

    def _on_lang_changed_live(self, code):
        if code not in ("en", "ru", "zh"):
            return
        self.lang = code
        self.selected_lang = code
        try:
            # Rebuild pages for instant language switch in welcome dialog.
            while self.stack.count():
                w = self.stack.widget(0)
                self.stack.removeWidget(w)
                w.deleteLater()
            self.stack.addWidget(self._build_page_welcome())
            self.stack.addWidget(self._build_page_features())
            self.stack.addWidget(self._build_page_tutorial())
            self.stack.setCurrentIndex(self._step)
            self._update_step_ui()
        except Exception:
            pass

    def _body_text(self):
        if self.lang == "ru":
            return (
                "Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ ASCII Studio.\n\n"
                "РџСЂРѕРіСЂР°РјРјР° СѓРјРµРµС‚ РєРѕРЅРІРµСЂС‚РёСЂРѕРІР°С‚СЊ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ, GIF Рё РІРёРґРµРѕ РІ ASCII-СЃС‚РёР»Рё, "
                "РґР°С‘С‚ РІСЃС‚СЂРѕРµРЅРЅС‹Р№ РїР»РµРµСЂ/РїСЂРµРІСЊСЋ, РіР°Р»РµСЂРµСЋ, Pro Tools-С„РёР»СЊС‚СЂС‹ Рё СЌРєСЃРїРѕСЂС‚ РІ PNG/GIF/MP4/TXT."
            )
        if self.lang == "zh":
            return (
                "ж¬ўиїЋдЅїз”Ё ASCII StudioгЂ‚\n\n"
                "жњ¬зЁ‹еєЏеЏЇе°†е›ѕз‰‡/GIF/и§†йў‘иЅ¬жЌўдёє ASCII йЈЋж јпјЊжЏђдѕ›е†…зЅ®ж’­ж”ѕе™ЁдёЋйў„и§€гЂЃз”»е»ЉгЂЃ"
                "Pro Tools ж»¤й•њпјЊд»ҐеЏЉ PNG/GIF/MP4/TXT еЇје‡єгЂ‚"
            )
        return (
            "Welcome to ASCII Studio.\n\n"
            "Convert image/GIF/video into ASCII styles, use embedded preview/player, gallery, "
            "Pro Tools filters, and export to PNG/GIF/MP4/TXT."
        )

    def _btn_text(self):
        if self.lang == "ru":
            return "Начать"
        if self.lang == "zh":
            return "开始"
        return "Start"

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        w, h = self.width(), self.height()
        pw = min(820, max(620, w - 140))
        ph = min(520, max(360, h - 160))
        self.panel.setGeometry((w - pw) // 2, (h - ph) // 2, pw, ph)

    def showEvent(self, ev):
        self.setGeometry(self.parent().rect())
        return super().showEvent(ev)

    def eventFilter(self, obj, ev):
        try:
            if obj is self.parent() and ev.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.WindowStateChange):
                self.setGeometry(self.parent().rect())
                self.raise_()
                QTimer.singleShot(0, lambda: self.setGeometry(self.parent().rect()))
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def _tick(self):
        try:
            self._frame_idx = (self._frame_idx + 1) % len(self._ascii_frames)
            self.ascii_lbl.setText(self._ascii_frames[self._frame_idx])
            self._glow_phase += 0.22
            c = int(170 + 60 * (0.5 + 0.5 * math.sin(self._glow_phase)))
            self.ascii_lbl.setStyleSheet(f"font-family:'Consolas'; font-size:12px; color: rgb({c//2},{c},{255});")
        except Exception:
            pass

    def paintEvent(self, ev):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor(0, 0, 0, 228))
            glow = QRadialGradient(self.width() * 0.5, self.height() * 0.42, max(160, int(min(self.width(), self.height()) * 0.35)))
            glow.setColorAt(0.0, QColor(70, 110, 210, 72))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(glow))
        finally:
            if p.isActive():
                p.end()


class CPULoadBars(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.values = [0.0] * 18
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setStyleSheet("background: rgba(0,0,0,0.18); border-radius: 8px;")

    def start(self):
        if not self._timer.isActive():
            self._timer.start(120)
        self.show()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self.hide()

    def _tick(self):
        cpu_val = 0.0
        try:
            if psutil is not None:
                cpu_val = float(psutil.cpu_percent(interval=None))
            else:
                cpu_val = random.uniform(18.0, 85.0)
        except Exception:
            cpu_val = random.uniform(18.0, 85.0)
        self.values = self.values[1:] + [max(0.0, min(100.0, cpu_val))]
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            w = max(1, self.width() - 10)
            h = max(1, self.height() - 10)
            x0, y0 = 5, 5
            n = max(1, len(self.values))
            bw = max(2, int(w / n) - 2)
            for i, v in enumerate(self.values):
                bh = int((h - 2) * (v / 100.0))
                x = x0 + i * (bw + 2)
                y = y0 + (h - bh)
                p.fillRect(x, y, bw, bh, QColor(255, 255, 255))
        finally:
            if p.isActive():
                p.end()

# -------------------- UI Sound Manager --------------------
class UISoundManager(QObject):
    def __init__(self, parent, click_files=None, slider_file=None, open_files=None, close_files=None):
        super().__init__(parent)
        self.enabled = True
        self.click_sfx = []
        self.open_sfx = []
        self.close_sfx = []
        self.slider_sfx = None
        self._last_move = 0.0
        self._dragging = set()
        self._last_slider_values = {}
        try:
            self.click_sfx = self._load_effects(click_files, 0.35)
            self.open_sfx = self._load_effects(open_files, 0.35)
            self.close_sfx = self._load_effects(close_files, 0.35)
            if slider_file:
                s1 = QSoundEffect(self)
                s1.setSource(QUrl.fromLocalFile(slider_file))
                s1.setVolume(0.4)
                self.slider_sfx = s1
        except Exception:
            self.enabled = False

    def _load_effects(self, files, volume):
        effects = []
        if not files:
            return effects
        for f in files:
            try:
                s = QSoundEffect(self)
                s.setSource(QUrl.fromLocalFile(f))
                s.setVolume(volume)
                effects.append(s)
            except Exception:
                pass
        return effects

    def play_click(self):
        if not self.enabled or not self.click_sfx:
            return
        try:
            s = random.choice(self.click_sfx)
            s.stop()
            s.play()
        except Exception:
            pass

    def play_open(self):
        if not self.enabled or not self.open_sfx:
            return
        try:
            s = random.choice(self.open_sfx)
            s.stop()
            s.play()
        except Exception:
            pass

    def play_close(self):
        if not self.enabled or not self.close_sfx:
            return
        try:
            s = random.choice(self.close_sfx)
            s.stop()
            s.play()
        except Exception:
            pass

    def slider_press(self, slider):
        if not self.enabled:
            return
        try:
            self._dragging.add(slider)
            self._last_slider_values[slider] = slider.value()
        except Exception:
            pass

    def slider_move(self, slider):
        if not self.enabled or slider not in self._dragging:
            return
        try:
            val = slider.value()
            if self._last_slider_values.get(slider) == val:
                return
            self._last_slider_values[slider] = val
            now = time.time()
            if now - self._last_move < 0.03:
                return
            self._last_move = now
            if self.slider_sfx:
                self.slider_sfx.stop()
                self.slider_sfx.play()
        except Exception:
            pass

    def slider_release(self, slider):
        if not self.enabled:
            return
        try:
            if slider in self._dragging:
                self._dragging.remove(slider)
        except Exception:
            pass


class VerticalTabButton(QPushButton):
    """Compact vertical category button (Blender-like side tabs)."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(52, 132)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._theme_name = "dark"

    def set_theme(self, theme_name):
        self._theme_name = str(theme_name or "dark")
        self.update()

    def sizeHint(self):
        return QSize(52, 132)

    def minimumSizeHint(self):
        return QSize(52, 132)

    def paintEvent(self, ev):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            r = self.rect().adjusted(1, 1, -1, -1)
            hover = self.underMouse()
            active = self.isChecked()
            pressed = self.isDown()
            light = (self._theme_name == "light")
            if light:
                bg = QColor(248, 251, 255, 220)
                bg_h = QColor(236, 245, 255, 236)
                bg_a = QColor(216, 233, 255, 248)
                border = QColor(105, 142, 192, 105)
                txt = QColor(23, 45, 79)
                txt_a = QColor(8, 29, 64)
            elif self._theme_name == "retro":
                bg = QColor(36, 66, 104, 196)
                bg_h = QColor(46, 82, 128, 214)
                bg_a = QColor(62, 104, 158, 238)
                border = QColor(190, 216, 247, 136)
                txt = QColor(235, 245, 255)
                txt_a = QColor(255, 255, 255)
            elif self._theme_name == "cyberpunk 2077":
                bg = QColor(26, 10, 14, 202)
                bg_h = QColor(58, 14, 22, 224)
                bg_a = QColor(86, 18, 28, 240)
                border = QColor(234, 48, 72, 156)
                txt = QColor(255, 236, 240)
                txt_a = QColor(255, 255, 255)
            elif self._theme_name == "aphex twin":
                bg = QColor(20, 24, 36, 196)
                bg_h = QColor(38, 45, 64, 214)
                bg_a = QColor(58, 72, 98, 236)
                border = QColor(201, 216, 237, 112)
                txt = QColor(232, 239, 248)
                txt_a = QColor(255, 255, 255)
            elif self._theme_name == "sketch":
                bg = QColor(255, 255, 255, 28)
                bg_h = QColor(255, 255, 255, 44)
                bg_a = QColor(255, 255, 255, 58)
                border = QColor(255, 255, 255, 96)
                txt = QColor(236, 241, 248)
                txt_a = QColor(255, 255, 255)
            else:
                bg = QColor(19, 25, 39, 170)
                bg_h = QColor(35, 47, 72, 188)
                bg_a = QColor(56, 92, 146, 214)
                border = QColor(154, 202, 255, 88)
                txt = QColor(206, 224, 245)
                txt_a = QColor(240, 248, 255)

            fill = bg_a if active else (bg_h if hover else bg)
            if pressed:
                fill = QColor(fill.red(), fill.green(), fill.blue(), min(255, fill.alpha() + 16))
            p.setBrush(fill)
            p.setPen(border)
            p.drawRoundedRect(r, 12, 12)

            if active:
                p.setBrush(QColor(118, 188, 255, 120) if not light else QColor(86, 148, 230, 110))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRect(r.left() + 2, r.top() + 2, 4, max(8, r.height() - 4)), 2, 2)

            p.save()
            p.translate(r.center())
            p.rotate(-90)
            tr = QRect(-r.height() // 2, -r.width() // 2, r.height(), r.width())
            f = p.font()
            f.setBold(True)
            try:
                base = int(f.pointSize())
            except Exception:
                base = 10
            if base <= 0:
                base = 10
            f.setPointSize(max(8, min(11, base)))
            fm = QFontMetrics(f)
            text = str(self.text() or "")
            max_w = max(12, int(tr.width()) - 6)
            while f.pointSize() > 7 and fm.horizontalAdvance(text) > max_w:
                f.setPointSize(int(f.pointSize()) - 1)
                fm = QFontMetrics(f)
            p.setFont(f)
            p.setPen(txt_a if active else txt)
            p.drawText(tr, Qt.AlignCenter, text)
            p.restore()
        finally:
            if p.isActive():
                p.end()

# -------------------- Main Window --------------------
class MainWindow(QMainWindow):
    update_check_done = Signal(object, str)

    def __init__(self, force_welcome=False):
        super().__init__()
        self.setWindowTitle("ASCII Studio - SNERK503")
        try:
            icon_path = _pick_resource_path(
                "QWE1R.ico", "QWE1R.png",
                "QWER.ico", "QWER.png",
                "iconASCII.ico", "iconASCII.png",
                "icons/QWE1R.ico", "icons/QWE1R.png",
                "icons/QWER.ico", "icons/QWER.png",
                "icons/iconASCII.ico", "icons/iconASCII.png"
            )
            if icon_path is not None:
                self.setWindowIcon(QIcon(str(icon_path)))
                app = QApplication.instance()
                if app is not None:
                    app.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        self.setMinimumSize(1100, 700)
        # load settings
        s = load_settings()
        self.lang = s.get("lang", "en")
        if self.lang not in TRANSLATIONS:
            self.lang = 'en'
        self.style = s.get("style", "bw")
        self.width_chars = s.get("width_chars", 320)
        self.font_size = s.get("font_size", 12)
        self.fg_hex = s.get("fg_hex", "#FFFFFF")
        self.bg_hex = s.get("bg_hex", "#0F1013")
        self.trail_level = s.get("trail_level", "med")
        self.show_watermark = s.get("show_watermark", True)
        self.device_choice = s.get("device_choice", "cpu")
        self.pro_tools = s.get("pro_tools", False)
        self.render_device = self._resolve_device_choice(self.device_choice)
        self.render_threads = s.get("render_threads", 4)
        self.render_codec = s.get("render_codec", "libx264")
        self.render_bitrate = s.get("render_bitrate", "2M")
        self.render_fps = int(s.get("render_fps", 24))
        self.render_scale = int(s.get("render_scale", 1))
        self.render_out_w = int(s.get("render_out_w", 0))
        self.render_out_h = int(s.get("render_out_h", 0))
        self.theme = str(s.get("theme", "dark") or "dark")
        if self.theme not in THEME_NAMES:
            self.theme = "dark"
        self.watermark_text = str(s.get("watermark_text", CORE_WATERMARK) or CORE_WATERMARK)
        self.custom_theme_bg = str(s.get("custom_theme_bg", "#0c1018") or "#0c1018")
        self.custom_theme_fg = str(s.get("custom_theme_fg", "#e8f2ff") or "#e8f2ff")
        self.custom_theme_accent = str(s.get("custom_theme_accent", "#5ec8ff") or "#5ec8ff")
        self.custom_theme_panel = str(s.get("custom_theme_panel", "#151c29") or "#151c29")
        self.custom_theme_background = str(s.get("custom_theme_background", "") or "")
        self.icon_pack_path = str(s.get("icon_pack_path", "") or "")
        self.icon_pack_url = str(s.get("icon_pack_url", "") or "")
        self._icon_remote_failed = set()
        self._icon_svg_raw_cache = {}
        self._icon_cache_dir = Path.home() / ".ascii_studio_icon_cache"
        self._custom_bg_video_cap = None
        self._custom_bg_video_path = ""
        self._custom_bg_video_dur = 0
        self.trail_length = int(s.get("trail_length", 96))
        self.export_fps = int(s.get("export_gif_fps", 12))
        self.gamma_pct = int(s.get("gamma_pct", 100))
        self.denoise = bool(s.get("denoise", False))
        self.sharpen = bool(s.get("sharpen", False))
        self.edge_boost = bool(s.get("edge_boost", False))
        self.ascii_chars = s.get("ascii_chars", DEFAULT_ASCII)
        self.contrast = s.get("contrast", 100)
        self.invert = s.get("invert", False)
        self.keep_size = s.get("keep_size", False)
        self.render_preset = s.get("render_preset", "medium")
        self.render_crf = int(s.get("render_crf", 20))
        self.tutorial_done = bool(s.get("tutorial_done", False))
        self.welcome_shown = bool(s.get("welcome_shown", False))
        self.keep_source_audio = bool(s.get("keep_source_audio", True))
        self.app_version = APP_VERSION
        self._force_welcome = bool(force_welcome)
        self.update_feed_url = str(s.get("update_feed_url", DEFAULT_UPDATE_FEED_URL) or DEFAULT_UPDATE_FEED_URL)
        self.auto_check_updates = bool(s.get("auto_check_updates", True))
        self.last_update_check = float(s.get("last_update_check", 0) or 0)
        self.last_known_version = str(s.get("last_known_version", "") or "")
        self.update_available_info = None
        self._update_thread = None
        self._update_installing = False
        self._update_chip_anim = None
        # Advanced editor state (non-destructive, applied from source each time).
        self.editor_state = {
            "enabled": False,
            "brightness": 100,
            "contrast": 100,
            "saturation": 100,
            "sharpness": 100,
            "hue": 0,
            "exposure": 0,
            "temperature": 0,
            "crop_enabled": False,
            "crop_x": 0,
            "crop_y": 0,
            "crop_w": 0,
            "crop_h": 0,
            "mask_enabled": False,
            "mask_x": 0,
            "mask_y": 0,
            "mask_w": 0,
            "mask_h": 0,
            "mask_use_image": False,
            "mask_image_path": "",
            "trim_enabled": False,
            "trim_start_ms": 0,
            "trim_end_ms": 0,
            "audio_path": "",
            "audio_gain_db": 0.0,
            "audio_lowpass_hz": 0,
            "nodes_enabled": False,
            "nodes_code": "",
            "node_chain": [],
            "node_links": [],
            "node_params": [],
            "node_io": [],
            "photo_paint_enabled": False,
            "photo_paint_opacity": 100,
            "photo_paint_png_b64": "",
            "photo_paint_hash": "",
            "photo_brush_size": 26,
            "photo_brush_opacity": 92,
            "photo_brush_color_rgba": [236, 244, 255, 220],
            "media_layers": [],
            "text_layers": [],
        }
        self._editor_last_preview_ms = 0
        self._editor_live_guard = False
        self._live_preview_source_pil = None
        self._media_layer_cache = {}
        self._photo_paint_cache_token = None
        self._photo_paint_cache_base = None
        self._photo_paint_cache_scaled_size = None
        self._photo_paint_cache_scaled = None
        # Easter eggs click-sequence state.
        self._egg_click_section = None
        self._egg_click_count = 0
        self._egg_click_stage = 0
        self._egg_audio = None
        self._egg_player = None
        self._egg_close_on_end = False
        self._closing_by_easter = False
        self._secret_code_buf = ""
        self._version_click_count = 0
        self._version_click_ts = 0.0
        self.confirm_on_close = True
        self._embedded_editor_frame = None
        self._embedded_editor_header = None
        self._embedded_editor_body = None
        self._embedded_editor_body_layout = None
        self._embedded_editor_widget = None
        self._embedded_editor_source = None
        self._embedded_editor_full = False
        self._embedded_editor_prev_fullscreen = False
        self._embedded_editor_full_btn = None
        self._embedded_editor_close_btn = None
        self._embedded_editor_raise_timer = None
        self._embedded_editor_active = False
        self._embedded_editor_opening = False
        self._embedded_editor_open_ts = 0.0
        self._embedded_editor_timer_state = None
        self._embedded_prev_panel_vis = None
        self._project_file_path = str(s.get("project_file_path", "") or "")
        self.pro_scanlines = bool(s.get("pro_scanlines", False))
        self.pro_bloom = int(s.get("pro_bloom", 0))
        self.pro_vignette = int(s.get("pro_vignette", 0))
        self.pro_poster_bits = int(s.get("pro_poster_bits", 0))
        self.pro_grain = int(s.get("pro_grain", 0))
        self.pro_chroma = int(s.get("pro_chroma", 0))
        self.pro_scan_strength = int(s.get("pro_scan_strength", 28))
        self.pro_scan_step = int(s.get("pro_scan_step", 3))
        self.pro_glitch = int(s.get("pro_glitch", 0))
        self.pro_glitch_density = int(s.get("pro_glitch_density", 35))
        self.pro_glitch_shift = int(s.get("pro_glitch_shift", 42))
        self.pro_glitch_rgb = int(s.get("pro_glitch_rgb", 1))
        self.pro_glitch_block = int(s.get("pro_glitch_block", 10))
        self.pro_glitch_jitter = int(s.get("pro_glitch_jitter", 1))
        self.pro_glitch_noise = int(s.get("pro_glitch_noise", 12))
        self.pro_curvature = int(s.get("pro_curvature", 0))
        self.pro_concavity = int(s.get("pro_concavity", 0))
        self.pro_curvature_center_x = int(s.get("pro_curvature_center_x", 0))
        self.pro_curvature_expand = int(s.get("pro_curvature_expand", 0))
        self.pro_curvature_type = str(s.get("pro_curvature_type", "spherical") or "spherical")
        self.pro_ribbing = int(s.get("pro_ribbing", 0))
        self.pro_clarity = int(s.get("pro_clarity", 0))
        self.pro_motion_blur = int(s.get("pro_motion_blur", 0))
        self.pro_color_boost = int(s.get("pro_color_boost", 0))
        self.live_preview = bool(s.get("live_preview", False))

        self.trail = deque(maxlen=max(16, self.trail_length))
        self._trail_last_sample_ts = 0.0
        self.bg_t = 0.0
        self.render_worker = None
        self.current_output = None
        self.current_path = None
        self.original_source_path = None
        self.processing_source_path = None
        self.current_media_size = None
        self._suppress_trail = False
        self.preview_zoom = 1.0
        self.preview_pan = [0, 0]
        self._preview_native_size = None
        self._preview_drag = None
        self._preview_base_pil = None
        self._preview_display_pil = None
        self._preview_player = None
        self._preview_audio = None
        self._preview_gif_movie = None
        self._preview_mode = "image"
        self._preview_duration_ms = 0
        self._preview_gif_frames = 0
        self._preview_gif_total_ms = 0
        self._preview_last_pos_ms = 0
        self._preview_player_seeking = False
        self._preview_loop = True
        self._preview_rate = 1.0
        self._preview_focus_mode = False
        self._preview_focus_prev_state = False
        self._preview_zoom_target = float(self.preview_zoom)
        self._preview_pan_target = [float(self.preview_pan[0]), float(self.preview_pan[1])]
        self._preview_base_stamp = 0
        self._preview_display_stamp = 0
        self._preview_scaled_cache_key = None
        self._preview_scaled_cache_size = (0, 0)
        self._preview_motion_timer = QTimer(self)
        self._preview_motion_timer.setInterval(16)
        self._preview_motion_timer.timeout.connect(self._tick_preview_motion)
        self._preview_transform_timer = QTimer(self)
        self._preview_transform_timer.setSingleShot(True)
        self._preview_transform_timer.timeout.connect(self._apply_preview_media_transform)
        self._video_soft_zoom = False
        self._timeline_hover_cache = {}
        self._timeline_hover_path = None
        self._timeline_hover_last = 0.0
        self._soft_video_refresh_ts = 0.0
        self._trail_overlay_stack_dirty = True
        self._live_preview_timer = QTimer(self)
        self._live_preview_timer.setSingleShot(True)
        self._live_preview_timer.timeout.connect(self._apply_live_preview_now)
        self._live_preview_inflight = False
        self._live_preview_pending = False
        self._live_preview_force = False
        self._live_preview_last_sig = None
        self._live_preview_last_ts = 0.0
        self._live_preview_req_ts = 0.0
        self._undo_stack = []
        self._redo_stack = []
        self._state_restore_lock = False
        self._undo_widgets = set()
        self._undo_event_ts = 0.0
        self._welcome_checked = False
        self._bg_tick = 0
        self._last_win_state_full = False
        self._info_buttons = []
        self._modal_prev_state = None
        self._modal_prev_focus = False
        self._last_panel_bg_ts = 0.0
        self._title_anim_idx = 0
        self._title_anim_tick = 0
        self._title_brand = "ISCII STUDIO"
        self._menu_prev_visible = None
        self._eco_background = True
        self._gallery_context_connected = False
        self.update_check_done.connect(self._on_update_check_done)
        self._build_ui()
        self._build_menu()
        self._apply_translations()
        self._apply_theme(self.theme)
        self._start_background_animation()
        # precompute circle pixmaps cache for faster drawing
        self._circle_cache = {}
        self._circle_cache_limit = 320
        # sample cursor position even when not moving via timer to ensure continuous trail
        self.cursor_sample_timer = QTimer(self); self.cursor_sample_timer.timeout.connect(self._sample_cursor)
        self.cursor_sample_timer.start(48)
        self.bg_anim_timer = QTimer(self); self.bg_anim_timer.timeout.connect(self._update_background)
        self.trail_timer = QTimer(self); self.trail_timer.timeout.connect(self._update_trail_overlay)
        # start animation timers
        try:
            self.bg_anim_timer.start(1000)
            self.trail_timer.start(170)
        except Exception:
            pass
        self._sync_perf_mode()
        # set pick buttons enabled state depending on style
        self._update_color_buttons_state()
        self._update_ascii_controls_visibility()
        # tutorial is manual only via Settings
        self._ui_anims = []
        self._start_ui_animations()
        self._start_title_animation()
        self._init_ui_sounds()
        self._init_shortcuts()
        self._ui_guard_timer = QTimer(self)
        self._ui_guard_timer.setInterval(480)
        self._ui_guard_timer.timeout.connect(self._guard_main_visibility)
        self._ui_guard_timer.start()
        if self.auto_check_updates:
            QTimer.singleShot(1400, self._check_updates_async)

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS['en'])
        def _i(ru, en, zh):
            if self.lang == "ru":
                return ru
            if self.lang == "zh":
                return zh
            return en
        # enable mouse tracking so mouseMoveEvent fires without mouse buttons pressed
        self.setMouseTracking(True)
        # full window background label (holds background + trail) so trail appears under panels
        self.window_bg_label = QLabel(self)
        self.window_bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.window_bg_label.setScaledContents(True)
        self.window_bg_label.lower()
        try:
            # make it a child of central widget so it covers the content area
            self.window_bg_label.setParent(central)
            self.window_bg_label.setGeometry(0,0, central.width() or self.width(), central.height() or self.height())
            self.window_bg_label.lower()
        except Exception:
            pass
        root = QHBoxLayout(central); root.setContentsMargins(8,8,8,8); root.setSpacing(12)
        # gallery on the left (always visible panel)
        self.gallery_frame = QFrame()
        self.gallery_frame.setObjectName("gallery_frame")
        self.gallery_frame.setFixedWidth(270)
        self.gallery_frame.setMinimumWidth(240)
        gallery_layout = QVBoxLayout(self.gallery_frame)
        gallery_layout.setContentsMargins(10, 10, 10, 10)
        gallery_layout.setSpacing(8)
        ghead = QHBoxLayout()
        ghead.setContentsMargins(0, 0, 0, 0)
        ghead.setSpacing(6)
        self.gallery_title = QLabel(tr.get("gallery", "Gallery"))
        self.gallery_load_btn = QPushButton(tr.get("load", "Load"))
        self.gallery_editor_btn = QPushButton(tr.get("editor", "Editor"))
        self.gallery_load_btn.setCursor(Qt.PointingHandCursor)
        self.gallery_editor_btn.setCursor(Qt.PointingHandCursor)
        self.gallery_load_btn.setFixedHeight(30)
        self.gallery_editor_btn.setFixedHeight(30)
        self.gallery_load_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.gallery_editor_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.gallery_load_btn.setStyleSheet(self._glass_btn_css())
        self.gallery_editor_btn.setStyleSheet(self._glass_btn_css())
        self.gallery_load_btn.clicked.connect(self.on_load)
        self.gallery_editor_btn.clicked.connect(self._open_in_editor)
        ghead.addWidget(self.gallery_title, 1)
        ghead.addWidget(self.gallery_load_btn, 0)
        ghead.addWidget(self.gallery_editor_btn, 0)
        gallery_layout.addLayout(ghead)
        self.gallery_list = QListWidget()
        self.gallery_list.setViewMode(QListWidget.IconMode)
        self.gallery_list.setIconSize(QSize(140, 140))
        self.gallery_list.setGridSize(QSize(164, 202))
        self.gallery_list.setUniformItemSizes(True)
        self.gallery_list.setResizeMode(QListWidget.Adjust)
        self.gallery_list.setMovement(QListWidget.Static)
        self.gallery_list.setFlow(QListWidget.TopToBottom)
        self.gallery_list.setSpacing(6)
        self.gallery_list.setWrapping(False)
        self.gallery_list.setMinimumWidth(240)
        self.gallery_list.setMinimumHeight(260)
        self.gallery_list.setWordWrap(True)
        self.gallery_list.setTextElideMode(Qt.ElideRight)
        self.gallery_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.gallery_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.gallery_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        try:
            self.gallery_list.itemDoubleClicked.connect(self.on_gallery_double_click)
        except Exception:
            pass
        gallery_layout.addWidget(self.gallery_list, 1)
        self.gallery_empty = QLabel(tr.get("gallery_empty", "No items yet"))
        self.gallery_empty.setAlignment(Qt.AlignCenter)
        gallery_layout.addWidget(self.gallery_empty)
        root.addWidget(self.gallery_frame, 0)

        left_frame = QFrame(); left_frame.setObjectName("left_frame")
        self.left_frame = left_frame
        left_frame.setMinimumWidth(360)
        left_frame.setMouseTracking(True)
        left_layout = QVBoxLayout(left_frame); left_layout.setContentsMargins(12,12,12,12)
        self.preview_title = QLabel(tr.get("preview", "Preview"))
        self.preview_title.setStyleSheet("font-weight:600;")
        left_layout.addWidget(self.preview_title)
        self.preview_label = QLabel(alignment=Qt.AlignCenter); self.preview_label.setStyleSheet("background: rgba(0,0,0,0.22); border-radius: 10px;")
        self.preview_label.setMouseTracking(True)
        self.preview_label.setMinimumSize(320, 240)
        self.preview_label.setText(tr.get("preview", "Preview"))
        self.preview_label.wheelEvent = self._preview_wheel_event
        self.preview_label.mousePressEvent = self._preview_mouse_press
        self.preview_label.mouseMoveEvent = self._preview_mouse_move
        self.preview_label.mouseReleaseEvent = self._preview_mouse_release
        self.preview_label.leaveEvent = self._preview_leave
        self.preview_label.mouseDoubleClickEvent = self._preview_double_click
        self.preview_image = QLabel(self.preview_label)
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setStyleSheet("background: transparent;")
        self.preview_image.mousePressEvent = self._preview_mouse_press
        self.preview_image.mouseMoveEvent = self._preview_mouse_move
        self.preview_image.mouseReleaseEvent = self._preview_mouse_release
        self.preview_image.leaveEvent = self._preview_leave
        self.preview_image.mouseDoubleClickEvent = self._preview_double_click
        self.preview_video = QVideoWidget(self.preview_label)
        self.preview_video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_video.setStyleSheet("background: transparent; border-radius: 10px;")
        self.preview_video.setAttribute(Qt.WA_NoSystemBackground, False)
        self.preview_video.setAttribute(Qt.WA_TranslucentBackground, False)
        # Keep video as a regular child widget so parent clipping works when zoom/pan is used.
        self.preview_video.setAttribute(Qt.WA_NativeWindow, False)
        self.preview_video.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        try:
            self.preview_video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            try:
                self.preview_video.setAspectRatioMode(Qt.KeepAspectRatio)
            except Exception:
                pass
        self.preview_video.hide()
        # make video widget interactive (zoom/pan) same as image preview
        self.preview_video.wheelEvent = self._preview_wheel_event
        self.preview_video.mousePressEvent = self._preview_mouse_press
        self.preview_video.mouseMoveEvent = self._preview_mouse_move
        self.preview_video.mouseReleaseEvent = self._preview_mouse_release
        self.preview_video.mouseDoubleClickEvent = self._preview_double_click
        # overlay on top of preview to draw cursor highlight / spotlight to improve readability
        self.preview_overlay = QLabel(self.preview_label)
        self.preview_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.preview_overlay.setStyleSheet("background: transparent;")
        try:
            self.preview_overlay.resize(self.preview_label.size())
            self.preview_overlay.hide()
        except Exception:
            pass
        # Nav buttons are parented to left_frame (not preview label) so they stay visible over native video widget.
        self.preview_prev_btn = QPushButton("<", self.left_frame)
        self.preview_next_btn = QPushButton(">", self.left_frame)
        self.preview_open_btn = QPushButton(tr.get("open_player", "Open player"), self.left_frame)
        for b in (self.preview_prev_btn, self.preview_next_btn, self.preview_open_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(self._glass_btn_css())
            b.setFixedHeight(30)
        self.preview_prev_btn.setFixedWidth(34)
        self.preview_next_btn.setFixedWidth(34)
        self.preview_prev_btn.clicked.connect(lambda: self._select_gallery_relative(-1))
        self.preview_next_btn.clicked.connect(lambda: self._select_gallery_relative(1))
        self.preview_open_btn.clicked.connect(self._toggle_player_focus_mode)
        self.preview_prev_btn.setToolTip(tr.get("preview_prev", "Previous file"))
        self.preview_next_btn.setToolTip(tr.get("preview_next", "Next file"))
        self.preview_open_btn.setToolTip(tr.get("player_focus", "Focus mode"))
        self.timeline_hover_thumb = QLabel(self)
        self.timeline_hover_thumb.hide()
        self.timeline_hover_thumb.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.timeline_hover_thumb.setStyleSheet("background: rgba(18,22,32,0.96); border:1px solid rgba(130,180,255,0.45); border-radius:8px; color:#e8edf7; padding:4px;")
        self.timeline_hover_thumb.setAlignment(Qt.AlignCenter)
        self._layout_preview_controls()
        left_layout.addWidget(self.preview_label, 1)
        self.player_controls = QFrame()
        self.player_controls.setObjectName("player_controls")
        self.player_controls.setStyleSheet("QFrame#player_controls{background: rgba(12,18,30,0.45); border:1px solid rgba(140,185,255,0.20); border-radius:10px;}")
        pcl = QVBoxLayout(self.player_controls); pcl.setContentsMargins(8,6,8,6); pcl.setSpacing(6)
        prow = QHBoxLayout()
        self.player_play_btn = QPushButton(tr.get("play", "Play"))
        self.player_stop_btn = QPushButton(tr.get("stop", "Stop"))
        self.player_repeat_btn = QPushButton(tr.get("repeat_loop", "Loop"))
        self.player_fullscreen_btn = QPushButton(tr.get("player_focus", "Focus mode"))
        for b in (self.player_play_btn, self.player_stop_btn, self.player_repeat_btn, self.player_fullscreen_btn):
            b.setCursor(Qt.PointingHandCursor); b.setStyleSheet(self._glass_btn_css())
        self.player_play_btn.clicked.connect(self._toggle_preview_play_pause)
        self.player_stop_btn.clicked.connect(self._stop_preview_playback)
        self.player_repeat_btn.clicked.connect(self._toggle_preview_repeat)
        self.player_fullscreen_btn.clicked.connect(self._toggle_player_focus_mode)
        prow.addWidget(self.player_play_btn)
        prow.addWidget(self.player_stop_btn)
        prow.addWidget(self.player_repeat_btn)
        prow.addWidget(self.player_fullscreen_btn)
        prow.addStretch(1)
        self.player_playlist_label = QLabel("-")
        self.player_playlist_label.setStyleSheet("color:#9fb3cc;")
        prow.addWidget(self.player_playlist_label)
        pcl.addLayout(prow)
        srow = QHBoxLayout()
        self.player_seek_slider = QSlider(Qt.Horizontal)
        self.player_seek_slider.setRange(0, 1000)
        self.player_seek_slider.setMouseTracking(True)
        self.player_seek_slider.sliderPressed.connect(lambda: setattr(self, "_preview_player_seeking", True))
        self.player_seek_slider.sliderReleased.connect(self._on_preview_seek_release)
        self.player_seek_slider.installEventFilter(self)
        self.player_time_label = QLabel("00:00 / 00:00")
        self.player_time_label.setMinimumWidth(110)
        srow.addWidget(self.player_seek_slider, 1)
        srow.addWidget(self.player_time_label)
        pcl.addLayout(srow)
        brow = QHBoxLayout()
        self.player_volume_label = QLabel(tr.get("volume", "Volume"))
        self.player_volume_slider = QSlider(Qt.Horizontal)
        self.player_volume_slider.setRange(0, 100)
        self.player_volume_slider.setValue(70)
        self.player_volume_slider.valueChanged.connect(self._on_preview_volume_changed)
        self.player_speed_label = QLabel(tr.get("player_speed", "Speed"))
        self.player_speed_combo = QComboBox()
        self.player_speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.player_speed_combo.setCurrentText("1.0x")
        self.player_speed_combo.currentTextChanged.connect(self._on_preview_speed_changed)
        brow.addWidget(self.player_volume_label)
        brow.addWidget(self.player_volume_slider, 1)
        brow.addWidget(self.player_speed_label)
        brow.addWidget(self.player_speed_combo)
        pcl.addLayout(brow)
        left_layout.addWidget(self.player_controls)
        self._set_preview_mode("image")
        root.addWidget(left_frame, 1)
        # create background label for left (glass) panel
        self.left_bg_label = QLabel(central)
        self.left_bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.left_bg_label.setScaledContents(True)
        self.left_bg_label.lower()
        # create background label for right panel as well
        self.right_bg_label = QLabel(central)
        self.right_bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.right_bg_label.setScaledContents(True)
        self.right_bg_label.lower()
        right_frame = QFrame()
        right_frame.setMinimumWidth(380)
        right_frame.setMaximumWidth(1220)
        right_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        right_frame.setObjectName("right_frame")
        self.right_frame = right_frame
        right_frame.setMouseTracking(True)
        # inner translucent content frame so controls appear on a glass surface
        self.right_content = QFrame(right_frame)
        self.right_content.setObjectName("right_content")
        self.right_content.setStyleSheet("background: rgba(20,20,20,0.28); border-radius:16px;")
        self.right_content.setAttribute(Qt.WA_StyledBackground, True)
        self.right_content.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.right_content.setGeometry(6,6, right_frame.width()-12, right_frame.height()-12)
        self.right_content.lower()
        right_outer_layout = QVBoxLayout(right_frame); right_outer_layout.setContentsMargins(8,8,8,8); right_outer_layout.setSpacing(6)
        # scroll area to prevent cramped UI in windowed mode
        self.right_scroll = QScrollArea(right_frame)
        self.right_scroll.setObjectName("right_scroll")
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setFrameShape(QFrame.NoFrame)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.right_scroll.setStyleSheet(self._scrollbar_css())
        try:
            self.right_scroll.viewport().setObjectName("right_scroll_view")
            self.right_scroll.viewport().setStyleSheet("background: transparent; border-radius: 12px;")
        except Exception:
            pass
        right_center_row = QHBoxLayout()
        right_center_row.setContentsMargins(0, 0, 0, 0)
        right_center_row.setSpacing(8)
        self.right_tabs_rail = QFrame(right_frame)
        self.right_tabs_rail.setObjectName("right_tabs_rail")
        self.right_tabs_rail.setFixedWidth(66)
        self.right_tabs_rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(18,24,38,0.42); border:1px solid rgba(150,200,255,0.20); border-radius:14px;}")
        rail_layout = QVBoxLayout(self.right_tabs_rail)
        rail_layout.setContentsMargins(6, 8, 6, 8)
        rail_layout.setSpacing(8)
        right_center_row.addWidget(self.right_tabs_rail, 0)
        right_center_row.addWidget(self.right_scroll, 1)
        right_outer_layout.addLayout(right_center_row, 1)
        right_inner = QWidget()
        right_inner.setMinimumWidth(500)
        right_inner_layout = QVBoxLayout(right_inner)
        right_inner_layout.setContentsMargins(10, 10, 10, 10)
        right_inner_layout.setSpacing(8)
        right_inner.setStyleSheet("background: transparent;")
        self.right_scroll.setWidget(right_inner)
        # use inner layout for controls below
        right_layout = right_inner_layout
        self._section_labels = []
        self.title_label = QLabel(self._ascii_title_text())
        self.title_label.setWordWrap(False)
        self.title_label.setMinimumWidth(240)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title_label.setStyleSheet(self._title_css())
        self.title_label.mouseDoubleClickEvent = self._title_easter_double_click
        right_layout.addWidget(self.title_label)
        # vertical section tabs (Blender-like rail)
        self.right_section_tabs = {}
        rail_layout = self.right_tabs_rail.layout()
        for tab_key, tab_fallback, section_name in (
            ("section_style", "STYLE", "style"),
            ("section_fx", "IMAGE FX", "fx"),
            ("section_pro", "PRO TOOLS", "pro"),
            ("section_render", "RENDER", "render"),
        ):
            b = VerticalTabButton(tr.get(tab_key, tab_fallback))
            b.set_theme(self.theme)
            b.clicked.connect(lambda _, s=section_name: self._jump_to_right_section(s))
            rail_layout.addWidget(b)
            self.right_section_tabs[section_name] = b
        rail_layout.addStretch(1)
        # sections
        def section(title_key, desc_key, title_fallback, desc_fallback):
            title = tr.get(title_key, title_fallback)
            desc = tr.get(desc_key, desc_fallback)
            h = QLabel(title)
            h.setStyleSheet("font-weight:700; letter-spacing:1px; font-size:12px;")
            d = QLabel(desc)
            d.setStyleSheet("color:#9fb3cc; font-size:11px;")
            line = QFrame()
            line.setObjectName("section_line")
            line.setFrameShape(QFrame.HLine)
            line.setFixedHeight(1)
            line.setStyleSheet(self._section_line_css())
            right_layout.addWidget(h)
            right_layout.addWidget(d)
            right_layout.addWidget(line)
            self._section_labels.append((h, d, title_key, desc_key, title_fallback, desc_fallback))
            return (h, d, line)
        self._section_anchor_style = section("section_style", "section_style_desc", "STYLE", "ASCII visual style and base parameters")[0]
        row = QHBoxLayout(); self.load_btn = QPushButton("Load"); self.load_btn.clicked.connect(self.on_load)
        for b in (self.load_btn,): b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(38); b.setStyleSheet(self._glass_btn_css())
        # set simple geometric icons
        try:
            def make_icon(color, shape='rect'):
                pm = QPixmap(20, 20)
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                try:
                    p.setRenderHint(QPainter.Antialiasing)
                    p.setBrush(QColor(color))
                    p.setPen(Qt.NoPen)
                    if shape == 'rect':
                        p.drawRect(2, 2, 16, 16)
                    elif shape == 'tri':
                        p.drawPolygon(QPolygon([QPoint(4, 16), QPoint(16, 10), QPoint(4, 4)]))
                    elif shape == 'circle':
                        p.drawEllipse(2, 2, 16, 16)
                finally:
                    if p.isActive():
                        p.end()
                return QIcon(pm)
            self.load_btn.setIcon(make_icon('#88c0ff','rect'))
        except Exception:
            pass
        row.addWidget(self.load_btn)
        right_layout.addLayout(row)
        self._sync_compact_button_sizes()
        right_layout.addSpacing(4)
        self.style_label = QLabel(tr.get("style", "Style"))
        self._add_labeled_row(
            right_layout, self.style_label, tr.get("style", "Style"),
            self._i3("РЎС‚РёР»СЊ", "Style", "йЈЋж ј"),
            self._i3(
                "Р’С‹Р±РµСЂРёС‚Рµ СЃС‚РёР»СЊ: bw вЂ” РєР»Р°СЃСЃРёС‡РµСЃРєРёР№ РјРѕРЅРѕС…СЂРѕРј, color вЂ” С†РІРµС‚РЅРѕР№, matrix вЂ” Р·РµР»С‘РЅС‹Р№ СЌС„С„РµРєС‚, neon/pastel вЂ” СЃС‚РёР»РёР·Р°С†РёСЏ.",
                "Choose style: bw classic mono, color preserves colors, matrix green effect, neon/pastel stylization.",
                "йЂ‰ж‹©йЈЋж јпјљbw з»Џе…ёй»‘з™ЅпјЊcolor дїќз•™йўњи‰ІпјЊmatrix з»їи‰Іж•€жћњпјЊneon/pastel йЈЋж јеЊ–гЂ‚"
            )
        )
        self.style_combo = QComboBox(); self.style_combo.addItems(["none","bw","red","color","matrix","matrix2","neon","pastel","custom"])
        self.style_combo.setCurrentText(self.style); self.style_combo.currentTextChanged.connect(self.on_style_changed)
        right_layout.addWidget(self.style_combo)
        # inline style help block (no icon click)
        self.style_help = QLabel("")
        self.style_help.setWordWrap(True)
        self.style_help.setObjectName("style_help")
        self.style_help.setStyleSheet(self._style_help_css())
        right_layout.addWidget(self.style_help)
        self._update_style_help()
        self.style_preview_label = QLabel()
        self.style_preview_label.setAlignment(Qt.AlignCenter)
        self.style_preview_label.setMinimumHeight(120)
        self.style_preview_label.setMaximumHeight(142)
        self.style_preview_label.setStyleSheet(
            "background: rgba(8,12,16,0.72); border:1px solid rgba(120,168,230,0.24); border-radius:10px;"
        )
        right_layout.addWidget(self.style_preview_label)
        self.style_preview_caption = QLabel("Так будет выглядеть рендер с выбранным пресетом")
        self.style_preview_caption.setStyleSheet("font-size:10px; color:#9fb3cc;")
        self.style_preview_caption.setWordWrap(True)
        right_layout.addWidget(self.style_preview_caption)
        crow = QHBoxLayout(); self.pick_text_btn = QPushButton(tr.get("text_color", "Text color")); self.pick_text_btn.clicked.connect(self.on_pick_text)
        self.pick_bg_btn = QPushButton(tr.get("bg_color", "BG color")); self.pick_bg_btn.clicked.connect(self.on_pick_bg)
        for b in (self.pick_text_btn, self.pick_bg_btn): b.setStyleSheet(self._glass_btn_css()); b.setCursor(Qt.PointingHandCursor)
        crow.addWidget(self.pick_text_btn); crow.addWidget(self.pick_bg_btn); right_layout.addLayout(crow)
        self.width_label = QLabel(tr.get("width", "Width (chars)"))
        self._add_labeled_row(
            right_layout, self.width_label, tr.get("width", "Width (chars)"),
            self._i3("РЁРёСЂРёРЅР° (СЃРёРјРІ.)", "Width (chars)", "е®Ѕеє¦пј€е­—з¬¦пј‰"),
            self._i3("Р§РµРј Р±РѕР»СЊС€Рµ, С‚РµРј РґРµС‚Р°Р»СЊРЅРµРµ, РЅРѕ РјРµРґР»РµРЅРЅРµРµ.", "Higher = more detail, but slower.", "и¶Ље¤§з»†иЉ‚и¶Ље¤љпјЊдЅ†ж›ґж…ўгЂ‚")
        )
        wrow = QHBoxLayout(); self.width_slider = QSlider(Qt.Horizontal); self.width_slider.setMinimum(16); self.width_slider.setMaximum(900)
        self.width_slider.setValue(self.width_chars); self.width_slider.valueChanged.connect(self.on_width_changed)
        self.width_val_label = QLabel(str(self.width_chars)); wrow.addWidget(self.width_slider); wrow.addWidget(self.width_val_label); right_layout.addLayout(wrow)
        self.font_label = QLabel(tr.get("font", "Font size"))
        self._add_labeled_row(
            right_layout, self.font_label, tr.get("font", "Font size"),
            self._i3("Р Р°Р·РјРµСЂ С€СЂРёС„С‚Р°", "Font size", "е­—дЅ“е¤§е°Џ"),
            self._i3("Р Р°Р·РјРµСЂ СЃРёРјРІРѕР»РѕРІ ASCII РїСЂРё СЂРµРЅРґРµСЂРµ.", "ASCII glyph size in render.", "жёІжџ“ж—¶ ASCII е­—з¬¦е¤§е°ЏгЂ‚")
        )
        frow = QHBoxLayout(); self.font_slider = QSlider(Qt.Horizontal); self.font_slider.setRange(6, 48); self.font_slider.setValue(self.font_size)
        self.font_slider.valueChanged.connect(self.on_font_changed); self.font_val_label = QLabel(str(self.font_size)); frow.addWidget(self.font_slider); frow.addWidget(self.font_val_label); right_layout.addLayout(frow)
        self.fps_label = QLabel(tr.get("fps", "FPS"))
        self._add_labeled_row(
            right_layout, self.fps_label, tr.get("fps", "FPS"),
            "FPS", self._i3("Р§Р°СЃС‚РѕС‚Р° РєР°РґСЂРѕРІ. РћР±С‹С‡РЅРѕ 24вЂ“30.", "Frame rate. Usually 24вЂ“30.", "её§зЋ‡пјЊйЂљеёё 24вЂ“30гЂ‚")
        )
        fps_row = QHBoxLayout()
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(int(self.render_fps))
        self.fps_spin.valueChanged.connect(lambda v: setattr(self, "render_fps", int(v)))
        fps_row.addWidget(self.fps_spin)
        right_layout.addLayout(fps_row)
        self.scale_label = QLabel("Scale")
        self._add_labeled_row(
            right_layout, self.scale_label, tr.get("scale", "Scale"),
            self._i3("РњР°СЃС€С‚Р°Р±", "Scale", "зј©ж”ѕ"),
            self._i3("РЈРІРµР»РёС‡РёРІР°РµС‚ РёС‚РѕРіРѕРІС‹Р№ СЂР°Р·РјРµСЂ Р±РµР· РёР·РјРµРЅРµРЅРёСЏ РїСЂРѕРїРѕСЂС†РёР№.", "Upscales output without changing aspect.", "ж”ѕе¤§иѕ“е‡єдё”дёЌж”№еЏжЇ”дѕ‹гЂ‚")
        )
        scale_row = QHBoxLayout()
        self.scale_x1 = QPushButton("x1")
        self.scale_x2 = QPushButton("x2")
        self.scale_x3 = QPushButton("x3")
        for b in (self.scale_x1, self.scale_x2, self.scale_x3):
            b.setStyleSheet(self._glass_btn_css())
        self.scale_x1.clicked.connect(lambda: self._set_scale(1))
        self.scale_x2.clicked.connect(lambda: self._set_scale(2))
        self.scale_x3.clicked.connect(lambda: self._set_scale(3))
        scale_row.addWidget(self.scale_x1)
        scale_row.addWidget(self.scale_x2)
        scale_row.addWidget(self.scale_x3)
        right_layout.addLayout(scale_row)
        self.out_label = QLabel("Output (W x H)")
        self._add_labeled_row(
            right_layout, self.out_label, tr.get("output_size", "Output (W x H)"),
            self._i3("Р Р°Р·РјРµСЂ РІС‹РІРѕРґР°", "Output size", "иѕ“е‡єе°єеЇё"),
            self._i3("РўРѕС‡РЅС‹Р№ СЂР°Р·РјРµСЂ СЂРµР·СѓР»СЊС‚Р°С‚Р°. РџСѓСЃС‚Рѕ вЂ” РІР·СЏС‚СЊ РёСЃС…РѕРґРЅС‹Р№.", "Exact output size. Empty = use original.", "зІѕзЎ®иѕ“е‡єе°єеЇёпј›дёєз©єе€™з”ЁеЋџе§‹е°єеЇёгЂ‚")
        )
        out_row = QHBoxLayout()
        self.out_w = QSpinBox(); self.out_w.setRange(0, 8192); self.out_w.setValue(int(self.render_out_w))
        self.out_h = QSpinBox(); self.out_h.setRange(0, 8192); self.out_h.setValue(int(self.render_out_h))
        self.out_w.valueChanged.connect(self._on_out_w_changed)
        self.out_h.valueChanged.connect(self._on_out_h_changed)
        out_row.addWidget(self.out_w)
        out_row.addWidget(self.out_h)
        right_layout.addLayout(out_row)
        self.defaults_btn = QPushButton(tr.get("defaults", "Defaults"))
        self.defaults_btn.setStyleSheet(self._glass_btn_css())
        self.defaults_btn.clicked.connect(lambda: (self._push_undo_state(), self._apply_style_defaults()))
        try:
            self.defaults_btn.setIcon(self._load_svg_icon("reset", "#9fb3cc"))
        except Exception:
            pass
        right_layout.addWidget(self.defaults_btn)
        self.auto_size_chk = QCheckBox(tr.get("auto_size", "Auto size"))
        self.auto_size_chk.setChecked(True)
        right_layout.addWidget(self.auto_size_chk)
        self._section_anchor_fx = section("section_fx", "section_fx_desc", "IMAGE FX", "Contrast, gamma and filters")[0]
        # charset and controls
        self.charset_label = QLabel(tr.get("charset", "Charset"))
        self._add_labeled_row(
            right_layout, self.charset_label, tr.get("charset", "Charset"),
            self._i3("РќР°Р±РѕСЂ СЃРёРјРІРѕР»РѕРІ", "Charset", "е­—з¬¦й›†"),
            self._i3("РќР°Р±РѕСЂ СЃРёРјРІРѕР»РѕРІ ASCII РґР»СЏ РїСЂРµРѕР±СЂР°Р·РѕРІР°РЅРёСЏ.", "ASCII character set used for conversion.", "з”ЁдєЋиЅ¬жЌўзљ„ ASCII е­—з¬¦й›†еђ€гЂ‚")
        )
        crow = QHBoxLayout(); self.charset_input = QComboBox(); self.charset_input.setEditable(True); self.charset_input.addItem(self.ascii_chars)
        self.charset_input.setFixedHeight(28); crow.addWidget(self.charset_input)
        right_layout.addLayout(crow)
        # tooltips moved to end of _build_ui after all widgets exist
        # contrast and invert
        self.contrast_label = QLabel(tr.get("contrast", "Contrast (%)"))
        self._add_labeled_row(
            right_layout, self.contrast_label, tr.get("contrast", "Contrast (%)"),
            self._i3("РљРѕРЅС‚СЂР°СЃС‚", "Contrast", "еЇ№жЇ”еє¦"),
            self._i3("РЈСЃРёР»РёРІР°РµС‚ РёР»Рё РѕСЃР»Р°Р±Р»СЏРµС‚ СЂР°Р·Р»РёС‡РёРµ СЃРІРµС‚Р»С‹С… Рё С‚С‘РјРЅС‹С… Р·РѕРЅ.", "Increase or decrease light/dark separation.", "еўћејєж€–е‡Џеј±жЋжљ—е·®еј‚гЂ‚")
        )
        contr_row = QHBoxLayout(); self.contrast_slider = QSlider(Qt.Horizontal); self.contrast_slider.setRange(20,200); self.contrast_slider.setValue(self.contrast)
        self.contrast_val_label = QLabel(str(self.contrast))
        self.contrast_slider.valueChanged.connect(self.on_contrast_changed); contr_row.addWidget(self.contrast_slider); contr_row.addWidget(self.contrast_val_label)
        right_layout.addLayout(contr_row)
        self.gamma_label = QLabel(tr.get("gamma", "Gamma (%)"))
        self._add_labeled_row(
            right_layout, self.gamma_label, tr.get("gamma", "Gamma (%)"),
            self._i3("Р“Р°РјРјР°", "Gamma", "дјЅй©¬"),
            self._i3("РЎРґРІРёРіР°РµС‚ СЏСЂРєРѕСЃС‚СЊ СЃСЂРµРґРЅРёС… С‚РѕРЅРѕРІ.", "Adjusts midвЂ‘tone brightness.", "и°ѓж•ґдё­й—ґдє®еє¦гЂ‚")
        )
        g_row = QHBoxLayout()
        self.gamma_slider = QSlider(Qt.Horizontal)
        self.gamma_slider.setRange(50, 200)
        self.gamma_slider.setValue(self.gamma_pct)
        self.gamma_val_label = QLabel(str(self.gamma_pct))
        self.gamma_slider.valueChanged.connect(self.on_gamma_changed)
        g_row.addWidget(self.gamma_slider)
        g_row.addWidget(self.gamma_val_label)
        right_layout.addLayout(g_row)
        inv_row = QHBoxLayout()
        self.invert_chk = QCheckBox(tr.get('invert','Invert'))
        self.invert_chk.setChecked(self.invert)
        inv_row.addWidget(self.invert_chk)
        right_layout.addLayout(inv_row)
        keep_row = QHBoxLayout()
        self.keep_size_chk = QCheckBox(tr.get('keep_size','Keep original output size'))
        self.keep_size_chk.setChecked(self.keep_size)
        keep_row.addWidget(self.keep_size_chk)
        right_layout.addLayout(keep_row)
        fx_row1 = QHBoxLayout()
        self.denoise_chk = QCheckBox(tr.get("denoise", "Denoise"))
        self.denoise_chk.setChecked(self.denoise)
        self.sharpen_chk = QCheckBox(tr.get("sharpen", "Sharpen"))
        self.sharpen_chk.setChecked(self.sharpen)
        fx_row1.addWidget(self.denoise_chk)
        fx_row1.addWidget(self.sharpen_chk)
        right_layout.addLayout(fx_row1)
        fx_row2 = QHBoxLayout()
        self.edge_chk = QCheckBox(tr.get("edge_boost", "Edge boost"))
        self.edge_chk.setChecked(self.edge_boost)
        fx_row2.addWidget(self.edge_chk)
        right_layout.addLayout(fx_row2)
        # keep internal state in sync when user toggles
        try:
            self.invert_chk.stateChanged.connect(lambda s: setattr(self, 'invert', bool(s)))
        except Exception:
            pass
        self.keep_size_chk.stateChanged.connect(self._on_keep_size_changed)
        self.trail_label = QLabel(tr.get("trail", "Trail intensity"))
        right_layout.addWidget(self.trail_label)
        self.trail_combo = QComboBox()
        # fill with translated labels
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS['en'])
        self.trail_combo.addItems([tr["off"], tr["low"], tr["med"], tr["high"]])
        # map current trail_level key to label
        key_to_label = {"off": tr["off"], "low": tr["low"], "med": tr["med"], "high": tr["high"]}
        self.trail_combo.setCurrentText(key_to_label.get(self.trail_level, tr["med"]))
        self.trail_combo.currentTextChanged.connect(self._trail_combo_changed)
        right_layout.addWidget(self.trail_combo)
        # theme selector
        self.theme_combo = QComboBox(); self.theme_combo.addItems(THEME_NAMES)
        self.theme_combo.setCurrentText(self.theme if self.theme in THEME_NAMES else "dark")
        self.theme_label = QLabel(tr.get("theme", "Theme"))
        right_layout.addWidget(self.theme_label)
        right_layout.addWidget(self.theme_combo)

        # connect theme changes to apply style
        try:
            self.theme_combo.currentTextChanged.connect(self._apply_theme)
        except Exception:
            pass
        # Theme/trail are configured in Settings now.
        self.trail_label.hide()
        self.trail_combo.hide()
        self.theme_label.hide()
        self.theme_combo.hide()

        # device selection moved to settings dialog
        self.watermark_chk = QCheckBox(tr.get('watermark','Watermark')); self.watermark_chk.setChecked(self.show_watermark); right_layout.addWidget(self.watermark_chk)
        self.watermark_text_edit = QLineEdit(str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK))
        self.watermark_text_edit.setPlaceholderText(tr.get("watermark_text", "Watermark text"))
        self.watermark_text_edit.textChanged.connect(lambda v: setattr(self, "watermark_text", str(v or "")))
        self.watermark_text_edit.textChanged.connect(lambda *_: self._schedule_live_preview())
        right_layout.addWidget(self.watermark_text_edit)
        self.fx_defaults_btn = QPushButton(tr.get("defaults", "Defaults"))
        self.fx_defaults_btn.setStyleSheet(self._glass_btn_css())
        self.fx_defaults_btn.setCursor(Qt.PointingHandCursor)
        self.fx_defaults_btn.clicked.connect(lambda: (self._push_undo_state(), self._apply_fx_defaults()))
        right_layout.addWidget(self.fx_defaults_btn)
        self._pro_section_widgets = section("section_pro", "section_pro_desc", "PRO TOOLS", "Advanced filters and stylization")
        self._section_anchor_pro = self._pro_section_widgets[0] if isinstance(self._pro_section_widgets, (list, tuple)) else None
        self.pro_tools_frame = QFrame()
        self.pro_tools_frame.setObjectName('pro_tools_frame')
        pfl = QHBoxLayout(self.pro_tools_frame); pfl.setContentsMargins(0,0,0,0)
        try:
            batch_btn = QPushButton(tr.get('batch','Batch'))
            pal_btn = QPushButton(tr.get('palette','Palette'))
            dither_btn = QPushButton(tr.get('dither','Dither'))
            batch_btn.clicked.connect(lambda: self._batch_ascii_render())
            pal_btn.clicked.connect(lambda: self._apply_tool_to_selected("posterize"))
            dither_btn.clicked.connect(lambda: self._apply_tool_to_selected("edges"))
            for b,name in ((batch_btn,'batch'),(pal_btn,'palette'),(dither_btn,'dither')):
                try:
                    b.setIcon(make_icon('#88c0ff','circle'))
                except Exception:
                    pass
                b.setStyleSheet(self._glass_btn_css()); b.setCursor(Qt.PointingHandCursor)
                pfl.addWidget(b)
            self._pro_tool_buttons = {'batch': batch_btn, 'palette': pal_btn, 'dither': dither_btn}
        except Exception:
            pass
        right_layout.addWidget(self.pro_tools_frame)

        self.pro_options_frame = QFrame()
        pof = QVBoxLayout(self.pro_options_frame)
        pof.setContentsMargins(0, 0, 0, 0)
        pof.setSpacing(6)
        self.pro_preset_label = QLabel("Pro preset")
        self._add_labeled_row(
            pof, self.pro_preset_label, "Pro preset",
            self._i3("РџСЂРµСЃРµС‚ Pro Tools", "Pro preset", "Pro йў„и®ѕ"),
            self._i3("Р‘С‹СЃС‚СЂРѕ РїСЂРёРјРµРЅСЏРµС‚ РЅР°Р±РѕСЂ РїР°СЂР°РјРµС‚СЂРѕРІ Pro Tools.", "Quickly applies a Pro Tools look.", "еї«йЂџеє”з”ЁдёЂз»„ Pro Tools еЏ‚ж•°гЂ‚")
        )
        self.pro_preset_combo = QComboBox()
        self.pro_preset_combo.addItems(["none", "soft", "cyber", "cinematic", "sketch", "retro", "vhs", "clean"])
        self.pro_preset_combo.currentTextChanged.connect(self._on_pro_preset_combo_changed)
        self.pro_preset_combo.currentTextChanged.connect(lambda *_: self._update_pro_preset_help())
        pof.addWidget(self.pro_preset_combo)
        self.pro_preset_help = QLabel("")
        self.pro_preset_help.setWordWrap(True)
        self.pro_preset_help.setObjectName("codec_help")
        self.pro_preset_help.setStyleSheet(self._codec_help_css())
        pof.addWidget(self.pro_preset_help)
        self._update_pro_preset_help()
        self.pro_preview_label = QLabel()
        self.pro_preview_label.setAlignment(Qt.AlignCenter)
        self.pro_preview_label.setMinimumHeight(120)
        self.pro_preview_label.setMaximumHeight(142)
        self.pro_preview_label.setStyleSheet(
            "background: rgba(8,12,16,0.72); border:1px solid rgba(120,168,230,0.24); border-radius:10px;"
        )
        pof.addWidget(self.pro_preview_label)
        self.pro_preview_caption = QLabel("Так будет выглядеть рендер с выбранным пресетом")
        self.pro_preview_caption.setStyleSheet("font-size:10px; color:#9fb3cc;")
        self.pro_preview_caption.setWordWrap(True)
        pof.addWidget(self.pro_preview_caption)
        self.pro_scanlines_chk = QCheckBox(tr.get("pro_scanlines", "Scanlines"))
        self.pro_scanlines_chk.setChecked(bool(self.pro_scanlines))
        self.pro_scanlines_chk.stateChanged.connect(lambda *_: self._sync_pro_menu_state())
        pof.addWidget(self.pro_scanlines_chk)
        self.pro_scan_strength_label = QLabel(tr.get("pro_scan_strength", "Scanline strength (%)"))
        self._add_labeled_row(
            pof, self.pro_scan_strength_label, tr.get("pro_scan_strength", "Scanline strength (%)"),
            self._i3("Сила скан-линий", "Scanline strength", "扫描线强度"),
            self._i3("Регулирует заметность горизонтальных линий.", "Controls visibility of horizontal scanlines.", "调整扫描线可见强度。")
        )
        psl = QHBoxLayout()
        self.pro_scan_strength_slider = QSlider(Qt.Horizontal)
        self.pro_scan_strength_slider.setRange(0, 100)
        self.pro_scan_strength_slider.setValue(int(getattr(self, "pro_scan_strength", 28)))
        self.pro_scan_strength_val = QLabel(str(int(getattr(self, "pro_scan_strength", 28))))
        self.pro_scan_strength_slider.valueChanged.connect(lambda v: (setattr(self, "pro_scan_strength", int(v)), self.pro_scan_strength_val.setText(str(int(v)))))
        psl.addWidget(self.pro_scan_strength_slider)
        psl.addWidget(self.pro_scan_strength_val)
        pof.addLayout(psl)
        self.pro_scan_step_label = QLabel(tr.get("pro_scan_step", "Scanline spacing (px)"))
        self._add_labeled_row(
            pof, self.pro_scan_step_label, tr.get("pro_scan_step", "Scanline spacing (px)"),
            self._i3("Шаг скан-линий", "Scanline spacing", "扫描线间距"),
            self._i3("Определяет расстояние между линиями.", "Distance between scanlines.", "设置扫描线之间的间距。")
        )
        self.pro_scan_step_spin = QSpinBox()
        self.pro_scan_step_spin.setRange(1, 8)
        self.pro_scan_step_spin.setValue(int(getattr(self, "pro_scan_step", 3)))
        self.pro_scan_step_spin.valueChanged.connect(lambda v: setattr(self, "pro_scan_step", int(v)))
        pof.addWidget(self.pro_scan_step_spin)
        self.pro_curvature_label = QLabel(tr.get("pro_curvature", "CRT curvature (%)"))
        self._add_labeled_row(
            pof, self.pro_curvature_label, tr.get("pro_curvature", "CRT curvature (%)"),
            self._i3("Выпуклость CRT", "CRT curvature", "CRT 曲面"),
            self._i3("Имитирует выпуклость старого кинескопного монитора.", "Simulates curved CRT monitor geometry.", "模拟老式 CRT 显示器的弧面效果。")
        )
        pcl = QHBoxLayout()
        self.pro_curvature_slider = QSlider(Qt.Horizontal)
        self.pro_curvature_slider.setRange(0, 100)
        self.pro_curvature_slider.setValue(int(getattr(self, "pro_curvature", 0)))
        self.pro_curvature_val = QLabel(str(int(getattr(self, "pro_curvature", 0))))
        self.pro_curvature_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_curvature", int(v)), self.pro_curvature_val.setText(str(int(v))))
        )
        pcl.addWidget(self.pro_curvature_slider)
        pcl.addWidget(self.pro_curvature_val)
        pof.addLayout(pcl)
        self.pro_concavity_label = QLabel("Concavity (%)")
        self._add_labeled_row(
            pof, self.pro_concavity_label, "Concavity (%)",
            self._i3("Вогнутость", "Concavity", "凹面"),
            self._i3("Вогнутая деформация экрана.", "Concave lens deformation.", "凹面镜头变形效果。")
        )
        pcc = QHBoxLayout()
        self.pro_concavity_slider = QSlider(Qt.Horizontal)
        self.pro_concavity_slider.setRange(0, 100)
        self.pro_concavity_slider.setValue(int(getattr(self, "pro_concavity", 0)))
        self.pro_concavity_val = QLabel(str(int(getattr(self, "pro_concavity", 0))))
        self.pro_concavity_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_concavity", int(v)), self.pro_concavity_val.setText(str(int(v))))
        )
        pcc.addWidget(self.pro_concavity_slider)
        pcc.addWidget(self.pro_concavity_val)
        pof.addLayout(pcc)
        self.pro_curvature_center_x_label = QLabel("Center offset X (%)")
        self._add_labeled_row(
            pof, self.pro_curvature_center_x_label, "Center offset X (%)",
            self._i3("Смещение центра X", "Center X offset", "中心 X 偏移"),
            self._i3("Сдвигает центр выпуклости/вогнутости по горизонтали.", "Shifts lens center horizontally.", "水平移动镜头中心。")
        )
        pcx = QHBoxLayout()
        self.pro_curvature_center_x_slider = QSlider(Qt.Horizontal)
        self.pro_curvature_center_x_slider.setRange(-100, 100)
        self.pro_curvature_center_x_slider.setValue(int(getattr(self, "pro_curvature_center_x", 0)))
        self.pro_curvature_center_x_val = QLabel(str(int(getattr(self, "pro_curvature_center_x", 0))))
        self.pro_curvature_center_x_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_curvature_center_x", int(v)), self.pro_curvature_center_x_val.setText(str(int(v))))
        )
        pcx.addWidget(self.pro_curvature_center_x_slider)
        pcx.addWidget(self.pro_curvature_center_x_val)
        pof.addLayout(pcx)
        self.pro_curvature_expand_label = QLabel("Expand to fill (%)")
        self._add_labeled_row(
            pof, self.pro_curvature_expand_label, "Expand to fill (%)",
            self._i3("Расширение без черных краев", "Expand to fill", "填充扩展"),
            self._i3("Приближает кадр после деформации, чтобы убрать черные поля.", "Zooms to hide black borders after warp.", "变形后缩放填充，避免黑边。")
        )
        pce = QHBoxLayout()
        self.pro_curvature_expand_slider = QSlider(Qt.Horizontal)
        self.pro_curvature_expand_slider.setRange(0, 100)
        self.pro_curvature_expand_slider.setValue(int(getattr(self, "pro_curvature_expand", 0)))
        self.pro_curvature_expand_val = QLabel(str(int(getattr(self, "pro_curvature_expand", 0))))
        self.pro_curvature_expand_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_curvature_expand", int(v)), self.pro_curvature_expand_val.setText(str(int(v))))
        )
        pce.addWidget(self.pro_curvature_expand_slider)
        pce.addWidget(self.pro_curvature_expand_val)
        pof.addLayout(pce)
        self.pro_curvature_type_label = QLabel("Lens type")
        self._add_labeled_row(
            pof, self.pro_curvature_type_label, "Lens type",
            self._i3("Тип деформации", "Lens type", "镜头类型"),
            self._i3("Выберите тип геометрической деформации.", "Select geometric warp model.", "选择几何变形类型。")
        )
        self.pro_curvature_type_combo = QComboBox()
        self.pro_curvature_type_combo.addItems(["spherical", "barrel", "pincushion", "horizontal", "vertical"])
        try:
            cur_t = str(getattr(self, "pro_curvature_type", "spherical") or "spherical")
            j = self.pro_curvature_type_combo.findText(cur_t)
            self.pro_curvature_type_combo.setCurrentIndex(j if j >= 0 else 0)
        except Exception:
            self.pro_curvature_type_combo.setCurrentIndex(0)
        self.pro_curvature_type_combo.currentTextChanged.connect(lambda v: setattr(self, "pro_curvature_type", str(v or "spherical")))
        pof.addWidget(self.pro_curvature_type_combo)
        self.pro_ribbing_label = QLabel(tr.get("pro_ribbing", "TV ribbing (%)"))
        self._add_labeled_row(
            pof, self.pro_ribbing_label, tr.get("pro_ribbing", "TV ribbing (%)"),
            self._i3("Ребристость экрана", "TV ribbing", "屏幕条纹"),
            self._i3("Добавляет старую ТВ-ребристость и маску пикселей.", "Adds old TV ribbing and mask texture.", "增加老电视条纹与像素掩膜质感。")
        )
        prb = QHBoxLayout()
        self.pro_ribbing_slider = QSlider(Qt.Horizontal)
        self.pro_ribbing_slider.setRange(0, 100)
        self.pro_ribbing_slider.setValue(int(getattr(self, "pro_ribbing", 0)))
        self.pro_ribbing_val = QLabel(str(int(getattr(self, "pro_ribbing", 0))))
        self.pro_ribbing_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_ribbing", int(v)), self.pro_ribbing_val.setText(str(int(v))))
        )
        prb.addWidget(self.pro_ribbing_slider)
        prb.addWidget(self.pro_ribbing_val)
        pof.addLayout(prb)
        self.pro_bloom_label = QLabel(tr.get("pro_bloom", "Bloom (%)"))
        self._add_labeled_row(
            pof, self.pro_bloom_label, tr.get("pro_bloom", "Bloom (%)"),
            self._i3("РЎРІРµС‡РµРЅРёРµ", "Bloom", "иѕ‰е…‰"),
            self._i3("РЎРјРµС€РёРІР°РµС‚ РјСЏРіРєРѕРµ СЂР°Р·РјС‹С‚РёРµ СЃ РёСЃС…РѕРґРЅС‹Рј РєР°РґСЂРѕРј.", "Mixes soft glow over the source frame.", "е°†жџ”е’Њиѕ‰е…‰ж··еђ€е€°жєђз”»йќўгЂ‚")
        )
        pbr = QHBoxLayout()
        self.pro_bloom_slider = QSlider(Qt.Horizontal)
        self.pro_bloom_slider.setRange(0, 100)
        self.pro_bloom_slider.setValue(int(self.pro_bloom))
        self.pro_bloom_val = QLabel(str(int(self.pro_bloom)))
        self.pro_bloom_slider.valueChanged.connect(lambda v: (setattr(self, "pro_bloom", int(v)), self.pro_bloom_val.setText(str(int(v))), self._sync_pro_menu_state()))
        pbr.addWidget(self.pro_bloom_slider)
        pbr.addWidget(self.pro_bloom_val)
        pof.addLayout(pbr)
        self.pro_vignette_label = QLabel(tr.get("pro_vignette", "Vignette (%)"))
        self._add_labeled_row(
            pof, self.pro_vignette_label, tr.get("pro_vignette", "Vignette (%)"),
            self._i3("Р’РёРЅСЊРµС‚РєР°", "Vignette", "жљ—и§’"),
            self._i3("Р—Р°С‚РµРјРЅСЏРµС‚ РєСЂР°СЏ Рё Р°РєС†РµРЅС‚РёСЂСѓРµС‚ С†РµРЅС‚СЂ.", "Darkens edges and focuses the center.", "еЋ‹жљ—иѕ№зје№¶зЄЃе‡єдё­еїѓгЂ‚")
        )
        pvr = QHBoxLayout()
        self.pro_vignette_slider = QSlider(Qt.Horizontal)
        self.pro_vignette_slider.setRange(0, 100)
        self.pro_vignette_slider.setValue(int(self.pro_vignette))
        self.pro_vignette_val = QLabel(str(int(self.pro_vignette)))
        self.pro_vignette_slider.valueChanged.connect(lambda v: (setattr(self, "pro_vignette", int(v)), self.pro_vignette_val.setText(str(int(v))), self._sync_pro_menu_state()))
        pvr.addWidget(self.pro_vignette_slider)
        pvr.addWidget(self.pro_vignette_val)
        pof.addLayout(pvr)
        self.pro_poster_label = QLabel(tr.get("pro_poster_bits", "Posterize bits"))
        self._add_labeled_row(
            pof, self.pro_poster_label, tr.get("pro_poster_bits", "Posterize bits"),
            self._i3("Р‘РёС‚С‹ РїРѕСЃС‚РµСЂРёР·Р°С†РёРё", "Posterize bits", "и‰Ій¶дЅЌж•°"),
            self._i3("РњРµРЅСЊС€Рµ Р±РёС‚РѕРІ вЂ” Р±РѕР»РµРµ РіСЂР°С„РёС‡РЅС‹Р№ РІРёРґ.", "Lower bits produce a graphic look.", "дЅЌж•°и¶ЉдЅЋпјЊе›ѕеѓЏи¶Ље›ѕеЅўеЊ–гЂ‚")
        )
        self.pro_poster_spin = QSpinBox()
        self.pro_poster_spin.setRange(0, 8)
        self.pro_poster_spin.setValue(int(self.pro_poster_bits))
        self.pro_poster_spin.valueChanged.connect(lambda v: setattr(self, "pro_poster_bits", int(v)))
        pof.addWidget(self.pro_poster_spin)
        self.pro_grain_label = QLabel(tr.get("pro_grain", "Film grain (%)"))
        self._add_labeled_row(
            pof, self.pro_grain_label, tr.get("pro_grain", "Film grain (%)"),
            self._i3("Р—РµСЂРЅРѕ", "Film grain", "胶片颗粒"),
            self._i3("Р”РѕР±Р°РІР»СЏРµС‚ РїР»С‘РЅРѕС‡РЅСѓСЋ Р·РµСЂРЅРёСЃС‚РѕСЃС‚СЊ.", "Adds analog-style film grain.", "添加胶片颗粒噪点风格。")
        )
        pgr = QHBoxLayout()
        self.pro_grain_slider = QSlider(Qt.Horizontal)
        self.pro_grain_slider.setRange(0, 100)
        self.pro_grain_slider.setValue(int(getattr(self, "pro_grain", 0)))
        self.pro_grain_val = QLabel(str(int(getattr(self, "pro_grain", 0))))
        self.pro_grain_slider.valueChanged.connect(lambda v: (setattr(self, "pro_grain", int(v)), self.pro_grain_val.setText(str(int(v)))))
        pgr.addWidget(self.pro_grain_slider)
        pgr.addWidget(self.pro_grain_val)
        pof.addLayout(pgr)
        self.pro_chroma_label = QLabel(tr.get("pro_chroma", "Chroma shift (px)"))
        self._add_labeled_row(
            pof, self.pro_chroma_label, tr.get("pro_chroma", "Chroma shift (px)"),
            self._i3("РЎРґРІРёРі РєР°РЅР°Р»РѕРІ", "Chroma shift", "色偏位移"),
            self._i3("Р›С‘РіРєРёР№ RGB-СЃРґРІРёРі РґР»СЏ РєРёРЅРµРјР°С‚РѕРіСЂР°С„РёС‡РЅРѕРіРѕ СЌС„С„РµРєС‚Р°.", "Subtle RGB channel split for stylization.", "轻微 RGB 通道位移，增加风格化效果。")
        )
        self.pro_chroma_spin = QSpinBox()
        self.pro_chroma_spin.setRange(0, 16)
        self.pro_chroma_spin.setValue(int(getattr(self, "pro_chroma", 0)))
        self.pro_chroma_spin.valueChanged.connect(lambda v: setattr(self, "pro_chroma", int(v)))
        pof.addWidget(self.pro_chroma_spin)
        self.pro_color_boost_label = QLabel("Color boost (%)")
        self._add_labeled_row(
            pof, self.pro_color_boost_label, "Color boost (%)",
            self._i3("Насыщенность+", "Color boost", "色彩增强"),
            self._i3("Усиливает насыщенность и глубину цвета.", "Boosts saturation and color depth.", "提升饱和度与色彩层次。")
        )
        pcb = QHBoxLayout()
        self.pro_color_boost_slider = QSlider(Qt.Horizontal)
        self.pro_color_boost_slider.setRange(0, 100)
        self.pro_color_boost_slider.setValue(int(getattr(self, "pro_color_boost", 0)))
        self.pro_color_boost_val = QLabel(str(int(getattr(self, "pro_color_boost", 0))))
        self.pro_color_boost_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_color_boost", int(v)), self.pro_color_boost_val.setText(str(int(v))))
        )
        pcb.addWidget(self.pro_color_boost_slider)
        pcb.addWidget(self.pro_color_boost_val)
        pof.addLayout(pcb)
        self.pro_clarity_label = QLabel("Clarity (%)")
        self._add_labeled_row(
            pof, self.pro_clarity_label, "Clarity (%)",
            self._i3("Локальная четкость", "Clarity", "清晰度"),
            self._i3("Повышает локальный контраст деталей.", "Enhances local detail contrast.", "增强细节局部对比度。")
        )
        pclr = QHBoxLayout()
        self.pro_clarity_slider = QSlider(Qt.Horizontal)
        self.pro_clarity_slider.setRange(0, 100)
        self.pro_clarity_slider.setValue(int(getattr(self, "pro_clarity", 0)))
        self.pro_clarity_val = QLabel(str(int(getattr(self, "pro_clarity", 0))))
        self.pro_clarity_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_clarity", int(v)), self.pro_clarity_val.setText(str(int(v))))
        )
        pclr.addWidget(self.pro_clarity_slider)
        pclr.addWidget(self.pro_clarity_val)
        pof.addLayout(pclr)
        self.pro_motion_blur_label = QLabel("Motion blur (%)")
        self._add_labeled_row(
            pof, self.pro_motion_blur_label, "Motion blur (%)",
            self._i3("Motion Blur", "Motion blur", "运动模糊"),
            self._i3("Добавляет мягкий кинематографичный шлейф.", "Adds a cinematic directional blur.", "增加电影感方向模糊。")
        )
        pmb = QHBoxLayout()
        self.pro_motion_blur_slider = QSlider(Qt.Horizontal)
        self.pro_motion_blur_slider.setRange(0, 100)
        self.pro_motion_blur_slider.setValue(int(getattr(self, "pro_motion_blur", 0)))
        self.pro_motion_blur_val = QLabel(str(int(getattr(self, "pro_motion_blur", 0))))
        self.pro_motion_blur_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_motion_blur", int(v)), self.pro_motion_blur_val.setText(str(int(v))))
        )
        pmb.addWidget(self.pro_motion_blur_slider)
        pmb.addWidget(self.pro_motion_blur_val)
        pof.addLayout(pmb)
        self.pro_glitch_label = QLabel(tr.get("pro_glitch", "Glitch (%)"))
        self._add_labeled_row(
            pof, self.pro_glitch_label, tr.get("pro_glitch", "Glitch (%)"),
            self._i3("Глитч", "Glitch", "故障效果"),
            self._i3("Добавляет кратковременные сдвиги строк, имитируя VHS/CRT.", "Adds horizontal row shifts for VHS/CRT look.", "添加行位移，模拟 VHS/CRT 故障效果。")
        )
        pgl = QHBoxLayout()
        self.pro_glitch_slider = QSlider(Qt.Horizontal)
        self.pro_glitch_slider.setRange(0, 100)
        self.pro_glitch_slider.setValue(int(getattr(self, "pro_glitch", 0)))
        self.pro_glitch_val = QLabel(str(int(getattr(self, "pro_glitch", 0))))
        self.pro_glitch_slider.valueChanged.connect(lambda v: (setattr(self, "pro_glitch", int(v)), self.pro_glitch_val.setText(str(int(v)))))
        pgl.addWidget(self.pro_glitch_slider)
        pgl.addWidget(self.pro_glitch_val)
        pof.addLayout(pgl)
        self.pro_glitch_density_label = QLabel(tr.get("pro_glitch_density", "Glitch density (%)"))
        self._add_labeled_row(
            pof, self.pro_glitch_density_label, tr.get("pro_glitch_density", "Glitch density (%)"),
            self._i3("Плотность глитча", "Glitch density", "故障密度"),
            self._i3("Сколько полос/участков участвует в глитче.", "How many row bands are affected by glitch.", "控制有多少行带参与故障扰动。")
        )
        pgd = QHBoxLayout()
        self.pro_glitch_density_slider = QSlider(Qt.Horizontal)
        self.pro_glitch_density_slider.setRange(0, 100)
        self.pro_glitch_density_slider.setValue(int(getattr(self, "pro_glitch_density", 35)))
        self.pro_glitch_density_val = QLabel(str(int(getattr(self, "pro_glitch_density", 35))))
        self.pro_glitch_density_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_glitch_density", int(v)), self.pro_glitch_density_val.setText(str(int(v))))
        )
        pgd.addWidget(self.pro_glitch_density_slider)
        pgd.addWidget(self.pro_glitch_density_val)
        pof.addLayout(pgd)
        self.pro_glitch_shift_label = QLabel(tr.get("pro_glitch_shift", "Glitch shift (%)"))
        self._add_labeled_row(
            pof, self.pro_glitch_shift_label, tr.get("pro_glitch_shift", "Glitch shift (%)"),
            self._i3("Сила сдвига глитча", "Glitch horizontal shift", "故障位移强度"),
            self._i3("Максимальный горизонтальный сдвиг для полос.", "Maximum horizontal shift for affected bands.", "故障条带的最大水平位移。")
        )
        pgs = QHBoxLayout()
        self.pro_glitch_shift_slider = QSlider(Qt.Horizontal)
        self.pro_glitch_shift_slider.setRange(0, 100)
        self.pro_glitch_shift_slider.setValue(int(getattr(self, "pro_glitch_shift", 42)))
        self.pro_glitch_shift_val = QLabel(str(int(getattr(self, "pro_glitch_shift", 42))))
        self.pro_glitch_shift_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_glitch_shift", int(v)), self.pro_glitch_shift_val.setText(str(int(v))))
        )
        pgs.addWidget(self.pro_glitch_shift_slider)
        pgs.addWidget(self.pro_glitch_shift_val)
        pof.addLayout(pgs)
        self.pro_glitch_rgb_label = QLabel(tr.get("pro_glitch_rgb", "RGB split (px)"))
        self._add_labeled_row(
            pof, self.pro_glitch_rgb_label, tr.get("pro_glitch_rgb", "RGB split (px)"),
            self._i3("RGB-смещение", "RGB split", "RGB 偏移"),
            self._i3("Сдвиг красного/синего каналов при глитче.", "Offsets red/blue channels during glitch.", "故障时偏移红蓝通道。")
        )
        self.pro_glitch_rgb_spin = QSpinBox()
        self.pro_glitch_rgb_spin.setRange(0, 16)
        self.pro_glitch_rgb_spin.setValue(int(getattr(self, "pro_glitch_rgb", 1)))
        self.pro_glitch_rgb_spin.valueChanged.connect(lambda v: setattr(self, "pro_glitch_rgb", int(v)))
        pof.addWidget(self.pro_glitch_rgb_spin)
        self.pro_glitch_block_label = QLabel(tr.get("pro_glitch_block", "Block tear size (px)"))
        self._add_labeled_row(
            pof, self.pro_glitch_block_label, tr.get("pro_glitch_block", "Block tear size (px)"),
            self._i3("Размер блочного разрыва", "Block tear size", "块撕裂尺寸"),
            self._i3("Размер случайных блоков, которые «ломаются».", "Size of random block tears.", "随机块撕裂区域大小。")
        )
        self.pro_glitch_block_spin = QSpinBox()
        self.pro_glitch_block_spin.setRange(0, 64)
        self.pro_glitch_block_spin.setValue(int(getattr(self, "pro_glitch_block", 10)))
        self.pro_glitch_block_spin.valueChanged.connect(lambda v: setattr(self, "pro_glitch_block", int(v)))
        pof.addWidget(self.pro_glitch_block_spin)
        self.pro_glitch_jitter_label = QLabel(tr.get("pro_glitch_jitter", "Vertical jitter (px)"))
        self._add_labeled_row(
            pof, self.pro_glitch_jitter_label, tr.get("pro_glitch_jitter", "Vertical jitter (px)"),
            self._i3("Вертикальный джиттер", "Vertical jitter", "垂直抖动"),
            self._i3("Небольшие вертикальные подёргивания кадра.", "Adds slight vertical frame jitters.", "加入轻微垂直抖动。")
        )
        self.pro_glitch_jitter_spin = QSpinBox()
        self.pro_glitch_jitter_spin.setRange(0, 24)
        self.pro_glitch_jitter_spin.setValue(int(getattr(self, "pro_glitch_jitter", 1)))
        self.pro_glitch_jitter_spin.valueChanged.connect(lambda v: setattr(self, "pro_glitch_jitter", int(v)))
        pof.addWidget(self.pro_glitch_jitter_spin)
        self.pro_glitch_noise_label = QLabel(tr.get("pro_glitch_noise", "Static noise (%)"))
        self._add_labeled_row(
            pof, self.pro_glitch_noise_label, tr.get("pro_glitch_noise", "Static noise (%)"),
            self._i3("Шум статики", "Static noise", "静态噪点"),
            self._i3("Добавляет VHS-статик во время глитча.", "Adds VHS-like static noise during glitch.", "在故障时添加 VHS 静态噪点。")
        )
        pgn = QHBoxLayout()
        self.pro_glitch_noise_slider = QSlider(Qt.Horizontal)
        self.pro_glitch_noise_slider.setRange(0, 100)
        self.pro_glitch_noise_slider.setValue(int(getattr(self, "pro_glitch_noise", 12)))
        self.pro_glitch_noise_val = QLabel(str(int(getattr(self, "pro_glitch_noise", 12))))
        self.pro_glitch_noise_slider.valueChanged.connect(
            lambda v: (setattr(self, "pro_glitch_noise", int(v)), self.pro_glitch_noise_val.setText(str(int(v))))
        )
        pgn.addWidget(self.pro_glitch_noise_slider)
        pgn.addWidget(self.pro_glitch_noise_val)
        pof.addLayout(pgn)
        right_layout.addWidget(self.pro_options_frame)
        self.pro_defaults_btn = QPushButton(tr.get("defaults", "Defaults"))
        self.pro_defaults_btn.setStyleSheet(self._glass_btn_css())
        self.pro_defaults_btn.setCursor(Qt.PointingHandCursor)
        self.pro_defaults_btn.clicked.connect(lambda: (self._push_undo_state(), self._apply_pro_defaults()))
        right_layout.addWidget(self.pro_defaults_btn)

        self._section_anchor_render = section("section_render", "section_render_desc", "RENDER", "Codec and export parameters")[0]
        row2 = QHBoxLayout(); self.render_btn = QPushButton("Render"); self.render_btn.clicked.connect(self.on_render)
        self.export_btn = QPushButton("Export"); self.export_btn.clicked.connect(self.on_export)
        for b in (self.render_btn, self.export_btn): b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(38); b.setStyleSheet(self._glass_btn_css())
        row2.addWidget(self.render_btn); row2.addWidget(self.export_btn)
        self.codec_label = QLabel("Codec")
        self._add_labeled_row(
            right_layout, self.codec_label, "Codec",
            self._i3("РљРѕРґРµРє", "Codec", "зј–з Ѓе™Ё"),
            self._i3("РЎР°РјС‹Р№ СЂР°СЃРїСЂРѕСЃС‚СЂР°РЅС‘РЅРЅС‹Р№: libx264 (MP4).", "Most common: libx264 (MP4).", "жњЂеёёи§Ѓпјљlibx264 (MP4)гЂ‚")
        )
        self.codec_combo = QComboBox()
        self.codec_combo.addItems(["libx264", "mpeg4", "libvpx", "h264"])
        self.codec_combo.setCurrentText(self.render_codec)
        self.codec_combo.currentTextChanged.connect(lambda v: setattr(self, "render_codec", v))
        self.codec_combo.currentTextChanged.connect(lambda _: self._update_codec_help())
        right_layout.addWidget(self.codec_combo)
        self.codec_help = QLabel("")
        self.codec_help.setWordWrap(True)
        self.codec_help.setObjectName("codec_help")
        self.codec_help.setStyleSheet(self._codec_help_css())
        right_layout.addWidget(self.codec_help)
        self._update_codec_help()
        self.keep_audio_chk = QCheckBox(tr.get("keep_source_audio", "Keep source audio"))
        self.keep_audio_chk.setChecked(bool(self.keep_source_audio))
        self.keep_audio_chk.setToolTip(tr.get("keep_source_audio_desc", "Use original source audio"))
        self.keep_audio_chk.stateChanged.connect(lambda s: setattr(self, "keep_source_audio", bool(s)))
        right_layout.addWidget(self.keep_audio_chk)
        self.bitrate_label = QLabel(tr.get("bitrate", "Bitrate"))
        self._add_labeled_row(
            right_layout, self.bitrate_label, tr.get("bitrate", "Bitrate"),
            self._i3("Р‘РёС‚СЂРµР№С‚", "Bitrate", "з ЃзЋ‡"),
            self._i3("РљР°С‡РµСЃС‚РІРѕ/СЂР°Р·РјРµСЂ С„Р°Р№Р»Р°. РћР±С‹С‡РЅРѕ 2M-6M.", "Quality/size. Usually 2M-6M.", "иґЁй‡Џ/дЅ“з§ЇпјЊйЂљеёё 2M-6MгЂ‚")
        )
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["500k","1M","2M","4M","6M","8M","10M"])
        if self.render_bitrate:
            self.bitrate_combo.setCurrentText(str(self.render_bitrate))
        self.bitrate_combo.currentTextChanged.connect(lambda v: setattr(self, "render_bitrate", v))
        right_layout.addWidget(self.bitrate_combo)
        self.threads_label = QLabel(tr.get("cpu_threads", "CPU threads"))
        self._add_labeled_row(
            right_layout, self.threads_label, tr.get("cpu_threads", "CPU threads"),
            self._i3("РџРѕС‚РѕРєРё CPU", "CPU threads", "CPU зєїзЁ‹"),
            self._i3("Р‘РѕР»СЊС€Рµ РїРѕС‚РѕРєРѕРІ вЂ” РІС‹С€Рµ СЃРєРѕСЂРѕСЃС‚СЊ Рё РЅР°РіСЂСѓР·РєР°.", "More threads = faster but heavier.", "зєїзЁ‹и¶Ље¤љи¶Љеї«пјЊдЅ†иґџиЅЅж›ґй«гЂ‚")
        )
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 64)
        self.threads_spin.setValue(int(self.render_threads))
        self.threads_spin.valueChanged.connect(lambda v: setattr(self, "render_threads", int(v)))
        right_layout.addWidget(self.threads_spin)
        self.preset_label = QLabel(tr.get("preset", "Preset"))
        self._add_labeled_row(
            right_layout, self.preset_label, tr.get("preset", "Preset"),
            self._i3("РџСЂРµСЃРµС‚", "Preset", "йў„и®ѕ"),
            self._i3("РЎРєРѕСЂРѕСЃС‚СЊ/РєР°С‡РµСЃС‚РІРѕ: ultrafast Р±С‹СЃС‚СЂРµРµ, slow РєР°С‡РµСЃС‚РІРµРЅРЅРµРµ.", "Speed/quality: ultrafast faster, slow better.", "йЂџеє¦/иґЁй‡Џпјљultrafast ж›ґеї«пјЊslow ж›ґеҐЅгЂ‚")
        )
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["ultrafast", "veryfast", "fast", "medium", "slow", "veryslow"])
        self.preset_combo.setCurrentText(self.render_preset if self.render_preset else "medium")
        self.preset_combo.currentTextChanged.connect(lambda v: setattr(self, "render_preset", v))
        right_layout.addWidget(self.preset_combo)
        preset_btn_row = QHBoxLayout()
        self.save_preset_btn = QPushButton(tr.get("save_preset", "Save preset"))
        self.load_preset_btn = QPushButton(tr.get("load_preset", "Load preset"))
        for b in (self.save_preset_btn, self.load_preset_btn):
            b.setStyleSheet(self._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            preset_btn_row.addWidget(b)
        self.save_preset_btn.clicked.connect(self._save_user_preset)
        self.load_preset_btn.clicked.connect(self._load_user_preset)
        right_layout.addLayout(preset_btn_row)
        self.preset_preview_label = QLabel()
        self.preset_preview_label.setAlignment(Qt.AlignCenter)
        self.preset_preview_label.setMinimumHeight(120)
        self.preset_preview_label.setMaximumHeight(142)
        self.preset_preview_label.setStyleSheet(
            "background: rgba(8,12,16,0.72); border:1px solid rgba(120,168,230,0.24); border-radius:10px;"
        )
        right_layout.addWidget(self.preset_preview_label)
        self.preset_preview_caption = QLabel("Так будет выглядеть рендер с выбранным пресетом")
        self.preset_preview_caption.setStyleSheet("font-size:10px; color:#9fb3cc;")
        self.preset_preview_caption.setWordWrap(True)
        right_layout.addWidget(self.preset_preview_caption)
        self._preset_preview_timer = QTimer(self)
        self._preset_preview_timer.setSingleShot(True)
        self._preset_preview_timer.timeout.connect(self._update_preset_preview)
        self.preset_combo.currentTextChanged.connect(lambda *_: self._schedule_preset_preview_update())
        self.style_combo.currentTextChanged.connect(lambda *_: self._schedule_preset_preview_update())
        if hasattr(self, "pro_preset_combo"):
            self.pro_preset_combo.currentTextChanged.connect(lambda *_: self._schedule_preset_preview_update())
        self.crf_label = QLabel(tr.get("crf", "CRF"))
        self._add_labeled_row(
            right_layout, self.crf_label, tr.get("crf", "CRF"),
            "CRF", self._i3("РќРёР¶Рµ вЂ” РІС‹С€Рµ РєР°С‡РµСЃС‚РІРѕ. РћР±С‹С‡РЅРѕ 18-24.", "Lower = higher quality. Usually 18-24.", "ж•°еЂји¶ЉдЅЋиґЁй‡Џи¶Љй«пјЊйЂљеёё 18-24гЂ‚")
        )
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(int(self.render_crf))
        self.crf_spin.valueChanged.connect(lambda v: setattr(self, "render_crf", int(v)))
        right_layout.addWidget(self.crf_spin)
        self.render_defaults_btn = QPushButton(tr.get("defaults", "Defaults"))
        self.render_defaults_btn.setStyleSheet(self._glass_btn_css())
        self.render_defaults_btn.setCursor(Qt.PointingHandCursor)
        self.render_defaults_btn.clicked.connect(lambda: (self._push_undo_state(), self._apply_render_defaults()))
        right_layout.addWidget(self.render_defaults_btn)
        self.settings_btn = QPushButton(tr.get("settings", "Settings..."))
        # add a simple icon to settings
        try:
            self.settings_btn.setIcon(make_icon('#88c0ff','rect'))
        except Exception:
            pass
        self.settings_btn.setStyleSheet(self._glass_btn_css()); self.settings_btn.clicked.connect(self.open_settings_dialog); right_layout.addWidget(self.settings_btn)
        self.cpu_label = QLabel(tr.get("cpu_load", "CPU load"))
        self.cpu_label.hide()
        right_layout.addWidget(self.cpu_label)
        self.cpu_bars = CPULoadBars(self)
        self.cpu_bars.hide()
        right_layout.addWidget(self.cpu_bars)
        self._ascii_widgets = [
            self.pick_text_btn, self.pick_bg_btn,
            self.width_label, self.width_slider, self.width_val_label,
            self.font_label, self.font_slider, self.font_val_label,
            self.charset_label, self.charset_input,
            self.contrast_label, self.contrast_slider, self.contrast_val_label,
            self.invert_chk,
        ]
        # right-side gallery duplicate removed: single source of truth is left gallery
        self.pro_tools_frame.setVisible(bool(self.pro_tools))
        self.pro_options_frame.setVisible(bool(self.pro_tools))
        try:
            for w in getattr(self, "_pro_section_widgets", []) or []:
                w.setVisible(bool(self.pro_tools))
        except Exception:
            pass
        right_layout.addStretch(1)
        self.right_footer = QFrame(right_frame)
        self.right_footer.setObjectName("right_footer")
        self.right_footer.setStyleSheet("QFrame#right_footer{background: rgba(14,18,30,0.55); border:1px solid rgba(150,190,255,0.22); border-radius:12px;}")
        foot = QHBoxLayout(self.right_footer)
        foot.setContentsMargins(8, 6, 8, 6)
        foot.setSpacing(8)
        foot.addLayout(row2)
        foot.addStretch(1)
        self.update_chip = QFrame(self.right_footer)
        self.update_chip.setObjectName("update_chip")
        self.update_chip.setStyleSheet(self._update_chip_css("idle"))
        uc_l = QHBoxLayout(self.update_chip)
        uc_l.setContentsMargins(8, 4, 8, 4)
        uc_l.setSpacing(6)
        self.update_status_label = QLabel("v" + str(self.app_version))
        self.update_status_label.setStyleSheet("font-size:11px; font-weight:600;")
        self.update_status_label.setCursor(Qt.PointingHandCursor)
        self.update_status_label.installEventFilter(self)
        self.update_install_btn = QPushButton(tr.get("update_install", "Install"))
        self.update_later_btn = QPushButton(tr.get("update_later", "Later"))
        self.update_install_btn.setCursor(Qt.PointingHandCursor)
        self.update_later_btn.setCursor(Qt.PointingHandCursor)
        self.update_install_btn.setFixedHeight(24)
        self.update_later_btn.setFixedHeight(24)
        self.update_install_btn.setStyleSheet(self._glass_btn_css())
        self.update_later_btn.setStyleSheet(self._glass_btn_css())
        self.update_install_btn.clicked.connect(self._install_update)
        self.update_later_btn.clicked.connect(self._hide_update_chip)
        self.update_install_btn.hide()
        self.update_later_btn.hide()
        uc_l.addWidget(self.update_status_label)
        uc_l.addWidget(self.update_install_btn)
        uc_l.addWidget(self.update_later_btn)
        foot.addWidget(self.update_chip, 0, Qt.AlignRight)
        right_outer_layout.addWidget(self.right_footer, 0)
        # tooltips (all widgets are now created)
        self._apply_tooltips(tr)
        self._index_right_sections()
        self._show_right_section("style")
        self._apply_combo_styles()
        self._schedule_preset_preview_update()
        self._register_undo_widgets()
        try:
            self.gallery_list.itemSelectionChanged.connect(self._on_gallery_select)
        except Exception:
            pass
        root.addWidget(right_frame, 0)
        root.setStretch(0, 0)
        root.setStretch(1, 1)
        root.setStretch(2, 0)
        try:
            # allow more readable windowed layout
            self.setMinimumSize(1180, 740)
            QTimer.singleShot(0, self._adapt_right_panel_width)
        except Exception:
            pass
        self._apply_window_style()
        # click on preview no longer forces fullscreen
        # overlay label for trail (transparent pixmap painted each frame)
        self.trail_overlay = QLabel(central)
        self.trail_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.trail_overlay.setStyleSheet("background: transparent;")
        # ensure overlay covers central area and sits above the static background but under UI panels
        try:
            self.trail_overlay.setGeometry(0, 0, self.width(), self.height())
            self._trail_overlay_stack_dirty = True
            self._sync_trail_overlay_stack(force=True)
        except Exception:
            pass
        try:
            self._build_embedded_editor_host(central)
        except Exception:
            pass

    def _on_gallery_select(self):
        items = self.gallery_list.selectedItems()
        if not items:
            return
        self._show_gallery_item(items[0], open_player=False)

    def _update_panel_backgrounds_from_qpix(self, bg_pix):
        # bg_pix is a QPixmap sized to window; crop for panels and apply tint/mask
        try:
            left = self.findChild(QFrame, "left_frame")
            right = self.findChild(QFrame, "right_frame")
            if not left or not right:
                return
            lx, ly = left.mapTo(self, QPoint(0,0)).x(), left.mapTo(self, QPoint(0,0)).y()
            lwid, lht = max(1, left.width()), max(1, left.height())
            rx, ry = right.mapTo(self, QPoint(0,0)).x(), right.mapTo(self, QPoint(0,0)).y()
            rwid, rht = max(1, right.width()), max(1, right.height())
            # convert QPixmap->QImage->PIL for reuse of crop_and_make logic
            img = bg_pix.toImage()
            ptr = img.bits(); ptr.setsize(img.byteCount())
            arr = np.array(ptr).reshape((img.height(), img.width(), 4))
            pil = Image.fromarray(arr[..., :3])
            # reuse existing crop routine via temporary override
            base = pil
            def crop_local(x,y,w,h,tint_alpha=110):
                x0,y0 = max(0,x), max(0,y)
                x1,y1 = min(base.width, x + w), min(base.height, y + h)
                if x1 <= x0 or y1 <= y0: return None
                crop = base.crop((x0,y0,x1,y1)).convert('RGBA')
                small = crop.resize((max(1,w//2), max(1,h//2)), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=6))
                big = small.resize((w,h), Image.Resampling.BILINEAR)
                tint = Image.new('RGBA', (w,h), (18,20,24,tint_alpha))
                out = Image.alpha_composite(big, tint)
                mask = Image.new('L', (w,h), 0); md = ImageDraw.Draw(mask)
                radius = min(24, max(6, w//14), max(6, h//14)); md.rounded_rectangle((0,0,w,h), radius=radius, fill=255)
                out.putalpha(mask); return out.convert('RGB')
            left_img = crop_local(lx, ly, lwid, lht, tint_alpha=110)
            right_img = crop_local(rx, ry, rwid, rht, tint_alpha=120)
            if left_img:
                self.left_bg_label.setPixmap(pil_to_qpixmap(left_img).scaled(lwid, lht, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                self.left_bg_label.setGeometry(lx, ly, lwid, lht)
                try:
                    self.left_bg_label.stackUnder(left)
                except Exception:
                    self.left_bg_label.lower()
            if right_img:
                self.right_bg_label.setPixmap(pil_to_qpixmap(right_img).scaled(rwid, rht, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                self.right_bg_label.setGeometry(rx, ry, rwid, rht)
                try:
                    self.right_bg_label.stackUnder(right)
                except Exception:
                    self.right_bg_label.lower()
            self._normalize_main_z_order()
        except Exception:
            pass
        # function finished

    def _glass_btn_css(self):
        t = getattr(self, "theme", "dark")
        if t == "light":
            return (
                "QPushButton{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,255,255,0.98), stop:1 rgba(240,244,251,0.98)); color: #101010; border:1px solid #cdd3df; border-radius:12px; padding:7px 14px; font-weight:600; }"
                "QPushButton:hover{ background: rgba(240,245,252,0.98); border:1px solid #a9bbd6; }"
                "QPushButton:pressed{ background: rgba(228,236,248,0.98); }"
            )
        if t == "retro":
            return (
                "QPushButton{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2f5d9b, stop:1 #234875); color:#f3f7ff; "
                "border:1px solid #9ec2f1; border-radius:12px; padding:7px 14px; font-weight:600; }"
                "QPushButton:hover{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3a6fb7, stop:1 #2b568a); border:1px solid #c0d9ff; }"
                "QPushButton:pressed{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #254d7f, stop:1 #1f3f67); border:1px solid #7ca6d9; }"
            )
        if t == "cyberpunk 2077":
            return (
                "QPushButton{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(20,8,12,0.92), stop:1 rgba(10,10,14,0.90)); color:#f7f5f6; "
                "border:1px solid rgba(234,48,72,0.58); border-radius:12px; padding:7px 14px; font-weight:600; }"
                "QPushButton:hover{ background: rgba(190,22,44,0.28); border:1px solid rgba(255,92,116,0.78); }"
                "QPushButton:pressed{ background: rgba(220,32,58,0.30); border:1px solid rgba(255,118,140,0.84); }"
            )
        if t == "aphex twin":
            return (
                "QPushButton{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(16,20,30,0.86), stop:1 rgba(11,14,20,0.90)); color:#f3f7fb; "
                "border:1px solid rgba(196,214,238,0.26); border-radius:12px; padding:7px 14px; font-weight:600; }"
                "QPushButton:hover{ background: rgba(156,180,212,0.18); border:1px solid rgba(224,236,255,0.50); }"
                "QPushButton:pressed{ background: rgba(104,126,152,0.24); border:1px solid rgba(224,236,255,0.66); }"
            )
        if t == "dedsec":
            return (
                "QPushButton{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(10,16,14,0.92), stop:1 rgba(8,10,8,0.92)); color:#dcffe6; "
                "border:1px solid rgba(88,255,138,0.52); border-radius:12px; padding:7px 14px; font-weight:600; }"
                "QPushButton:hover{ background: rgba(44,180,92,0.24); border:1px solid rgba(122,255,168,0.86); }"
                "QPushButton:pressed{ background: rgba(38,148,78,0.32); border:1px solid rgba(132,255,174,0.98); }"
            )
        if t == "custom":
            bg = str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29")
            fg = str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff")
            ac = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            return (
                f"QPushButton{{ background: {bg}; color:{fg}; border:1px solid {ac}; border-radius:12px; padding:7px 14px; font-weight:600; }}"
                f"QPushButton:hover{{ background: rgba(255,255,255,0.08); border:1px solid {ac}; }}"
                f"QPushButton:pressed{{ background: rgba(0,0,0,0.26); border:1px solid {ac}; }}"
            )
        return (
            "QPushButton{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(32,44,66,0.94), stop:1 rgba(20,28,44,0.92)); color: #f3f7ff; border:1px solid rgba(145,190,255,0.38); border-radius:12px; padding:7px 14px; font-weight:600; }"
            "QPushButton:hover{ background: rgba(120,150,210,0.24); border:1px solid rgba(145,200,255,0.56); }"
            "QPushButton:pressed{ background: rgba(98,126,186,0.32); border:1px solid rgba(145,200,255,0.66); }"
        )

    def _update_chip_css(self, state="idle"):
        st = str(state or "idle")
        if st == "ok":
            return "QFrame#update_chip{background: rgba(46,132,84,0.28); border:1px solid rgba(98,212,146,0.46); border-radius:10px;}"
        if st == "error":
            return "QFrame#update_chip{background: rgba(140,42,42,0.32); border:1px solid rgba(236,108,108,0.48); border-radius:10px;}"
        if st == "available":
            return "QFrame#update_chip{background: rgba(42,88,148,0.34); border:1px solid rgba(130,190,255,0.48); border-radius:10px;}"
        if st == "busy":
            return "QFrame#update_chip{background: rgba(70,60,148,0.34); border:1px solid rgba(170,160,255,0.52); border-radius:10px;}"
        return "QFrame#update_chip{background: rgba(24,30,44,0.36); border:1px solid rgba(130,170,220,0.30); border-radius:10px;}"

    def _ascii_title_frames(self):
        brand = "ISCII STUDIO"
        tails = ["[::]", "[##]", "[//]", "[**]", "[<>]"]
        base = [
            "  ___ ____  ____ ___ ___ ",
            " |_ _/ ___|/ ___|_ _|_ _|",
            "  | |\\___ \\| |    | | | |",
            "  | | ___) | |___ | | | |",
            " |___|____/ \\____|___|___|",
        ]
        glitch = [
            {},
            {0: "#", 6: "|", 9: ":"},
            {2: "/", 4: "\\", 11: "*"},
            {1: "=", 7: "+", 10: "~"},
            {3: "%", 8: "^", 5: ":"},
        ]
        out = []
        for i, t in enumerate(tails):
            chars = list(brand)
            for pos, ch in glitch[i % len(glitch)].items():
                if 0 <= int(pos) < len(chars) and chars[int(pos)] != " ":
                    chars[int(pos)] = str(ch)
            anim_brand = "".join(chars)
            out.append("\n".join(base + [f"   {anim_brand} {t}"]))
        return out

    def _ascii_title_text(self):
        frames = self._ascii_title_frames()
        idx = int(getattr(self, "_title_anim_idx", 0)) % max(1, len(frames))
        return frames[idx]

    def _start_title_animation(self):
        try:
            self._title_anim_timer = QTimer(self)
            self._title_anim_timer.timeout.connect(self._tick_title_animation)
            self._title_anim_timer.start(260)
        except Exception:
            pass

    def _tick_title_animation(self):
        try:
            self._title_anim_tick = int(getattr(self, "_title_anim_tick", 0)) + 1
            frames = self._ascii_title_frames()
            self._title_anim_idx = (int(getattr(self, "_title_anim_idx", 0)) + 1) % max(1, len(frames))
            if hasattr(self, "title_label"):
                self.title_label.setText(frames[self._title_anim_idx])
                # soft pulse similar to welcome logo
                pulse = 140 + int(48 * (0.5 + 0.5 * math.sin(self._title_anim_tick * 0.30)))
                theme_name = getattr(self, "theme", "dark")
                if theme_name == "light":
                    color = f"rgb({max(18, pulse - 76)}, {max(66, pulse - 26)}, {min(220, pulse)})"
                elif theme_name == "cyberpunk 2077":
                    color = f"rgb({min(255, pulse + 70)}, {max(24, pulse - 124)}, {max(34, pulse - 146)})"
                elif theme_name == "dedsec":
                    color = f"rgb({max(62, pulse - 36)}, {min(255, pulse + 94)}, {max(76, pulse - 24)})"
                elif theme_name == "custom":
                    color = str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff")
                else:
                    color = f"rgb({min(190, pulse)}, {min(230, pulse + 26)}, 255)"
                self.title_label.setStyleSheet(
                    "font-family:'Consolas'; font-size:11px; font-weight:700; "
                    f"color:{color};"
                )
        except Exception:
            pass

    def _i3(self, ru, en, zh):
        return {"ru": ru, "en": en, "zh": zh}

    def _resolve_info_text(self, obj, fallback=""):
        try:
            if isinstance(obj, dict):
                return _repair_mojibake_text(obj.get(self.lang, obj.get("en", fallback)), lang_hint=self.lang)
            if isinstance(obj, (list, tuple)) and len(obj) >= 3:
                return _repair_mojibake_text({"ru": obj[0], "en": obj[1], "zh": obj[2]}.get(self.lang, obj[1]), lang_hint=self.lang)
        except Exception:
            pass
        return _repair_mojibake_text(obj if isinstance(obj, str) else fallback, lang_hint=self.lang)

    def _find_talker_audio(self, stage_idx):
        try:
            stage_names = [
                ["one1.mp3", "one.mp3"],
                ["two2.mp3", "two.mp3"],
                ["three3.mp3", "three.mp3"],
            ]
            if stage_idx < 0 or stage_idx >= len(stage_names):
                return None
            base = Path(__file__).resolve().parent / "Easter eggs" / "talker"
            if not base.exists():
                return None
            fns = stage_names[stage_idx]
            lang = str(getattr(self, "lang", "en") or "en").lower()
            lang_aliases = {
                "ru": ["russian", "ru"],
                "en": ["en", "english"],
                "zh": ["zh", "cn", "chinese"],
            }.get(lang, [lang])
            candidates = []
            for fn in fns:
                for lg in lang_aliases:
                    candidates.extend([
                        base / lg / fn,
                        base / f"{lg}_{fn}",
                        base / f"{fn[:-4]}_{lg}.mp3",
                    ])
                candidates.append(base / fn)
            for p in candidates:
                if p.exists():
                    return str(p)
        except Exception:
            return None
        return None

    def _play_talker_audio(self, stage_idx):
        path = self._find_talker_audio(stage_idx)
        if not path:
            return False
        try:
            if self._egg_audio is None:
                self._egg_audio = QAudioOutput(self)
                self._egg_audio.setVolume(0.45)
            if not hasattr(self, "_egg_player") or self._egg_player is None:
                self._egg_player = QMediaPlayer(self)
                self._egg_player.setAudioOutput(self._egg_audio)
                self._egg_player.mediaStatusChanged.connect(self._on_egg_media_status)
            self._egg_player.stop()
            self._egg_close_on_end = bool(int(stage_idx) >= 2)
            self._egg_player.setSource(QUrl.fromLocalFile(path))
            self._egg_player.play()
            return True
        except Exception:
            return False

    def _on_egg_media_status(self, status):
        try:
            if status == QMediaPlayer.MediaStatus.EndOfMedia and bool(getattr(self, "_egg_close_on_end", False)):
                self._egg_close_on_end = False
                self._closing_by_easter = True
                self.close()
        except Exception:
            pass

    def _register_section_click_easter(self, section_name):
        try:
            sec = str(section_name or "")
            if not sec:
                return
            if self._egg_click_section == sec:
                self._egg_click_count += 1
            else:
                self._egg_click_section = sec
                self._egg_click_count = 1
            if self._egg_click_count < 5:
                return
            self._egg_click_count = 0
            stage = int(self._egg_click_stage)
            played = bool(self._play_talker_audio(stage))
            if played:
                self._egg_click_stage = min(2, stage + 1)
            if stage >= 2:
                self._egg_close_on_end = True
                QTimer.singleShot(9000, lambda: (setattr(self, "_closing_by_easter", True), self.close()) if bool(getattr(self, "_egg_close_on_end", False)) else None)
        except Exception:
            pass

    def _title_easter_double_click(self, ev):
        try:
            themes = ["dark", "midnight", "retro", "sketch", "cyberpunk 2077", "aphex twin", "dedsec", "solarized", "custom"]
            cur = str(getattr(self, "theme", "dark"))
            if cur in themes:
                i = themes.index(cur)
                nxt = themes[(i + 1) % len(themes)]
            else:
                nxt = "dark"
            self._apply_theme(nxt)
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            self._show_notice("Easter", tr.get("theme", "Theme") + f": {nxt}")
        except Exception:
            pass
        try:
            if ev is not None:
                ev.accept()
        except Exception:
            pass

    def _ensure_tutorial_target_visible(self, target):
        try:
            if not target:
                return False
            sec = self._section_for_target(target)
            if sec:
                self._show_right_section(sec)
            if not hasattr(self, "right_scroll") or self.right_scroll is None:
                return False
            right_widget = self.right_scroll.widget()
            if right_widget and right_widget.isAncestorOf(target):
                self.right_scroll.ensureWidgetVisible(target, 40, 80)
                return True
        except Exception:
            pass
        return False

    def _jump_to_right_section(self, section_name):
        try:
            self._register_section_click_easter(section_name)
            self._show_right_section(section_name)
            target = None
            if section_name == "style":
                target = getattr(self, "_section_anchor_style", None)
            elif section_name == "fx":
                target = getattr(self, "_section_anchor_fx", None)
            elif section_name == "pro":
                target = getattr(self, "_section_anchor_pro", None)
            elif section_name == "render":
                target = getattr(self, "_section_anchor_render", None)
            if target is not None and hasattr(self, "right_scroll") and self.right_scroll is not None:
                self.right_scroll.ensureWidgetVisible(target, 12, 42)
        except Exception:
            pass

    def _collect_layout_item_widgets(self, item, out_set):
        if item is None or out_set is None:
            return
        w = item.widget()
        if w is not None:
            out_set.add(w)
            return
        l = item.layout()
        if l is not None:
            for i in range(l.count()):
                self._collect_layout_item_widgets(l.itemAt(i), out_set)

    def _set_layout_item_visible(self, item, visible):
        if item is None:
            return
        w = item.widget()
        if w is not None:
            w.setVisible(bool(visible))
            return
        l = item.layout()
        if l is not None:
            for i in range(l.count()):
                self._set_layout_item_visible(l.itemAt(i), visible)

    def _index_right_sections(self):
        try:
            lay = self.right_scroll.widget().layout() if hasattr(self, "right_scroll") and self.right_scroll is not None and self.right_scroll.widget() is not None else None
            if lay is None:
                return
            anchors = {
                getattr(self, "_section_anchor_style", None): "style",
                getattr(self, "_section_anchor_fx", None): "fx",
                getattr(self, "_section_anchor_pro", None): "pro",
                getattr(self, "_section_anchor_render", None): "render",
            }
            self._right_section_indices = {"style": [], "fx": [], "pro": [], "render": []}
            self._right_section_widgets = {"style": set(), "fx": set(), "pro": set(), "render": set()}
            current = None
            for i in range(lay.count()):
                item = lay.itemAt(i)
                w = item.widget()
                if w in anchors:
                    current = anchors.get(w)
                if current in self._right_section_indices:
                    self._right_section_indices[current].append(i)
                    self._collect_layout_item_widgets(item, self._right_section_widgets[current])
        except Exception:
            pass

    def _section_for_target(self, target):
        try:
            if target is None:
                return None
            for sec, ws in getattr(self, "_right_section_widgets", {}).items():
                for w in ws:
                    try:
                        if w is target or w.isAncestorOf(target):
                            return sec
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def _show_right_section(self, section_name):
        try:
            if section_name == "pro" and not bool(getattr(self, "pro_tools", False)):
                section_name = "render"
            lay = self.right_scroll.widget().layout() if hasattr(self, "right_scroll") and self.right_scroll is not None and self.right_scroll.widget() is not None else None
            if lay is None:
                return
            if not getattr(self, "_right_section_indices", None):
                self._index_right_sections()
            for sec, idxs in getattr(self, "_right_section_indices", {}).items():
                show = (sec == section_name)
                if sec == "pro" and not bool(getattr(self, "pro_tools", False)):
                    show = False
                for i in idxs:
                    self._set_layout_item_visible(lay.itemAt(i), show)
            for sec, btn in getattr(self, "right_section_tabs", {}).items():
                try:
                    if isinstance(btn, VerticalTabButton):
                        btn.setChecked(sec == section_name)
                        btn.setVisible(not (sec == "pro" and not bool(getattr(self, "pro_tools", False))))
                    else:
                        btn.setVisible(not (sec == "pro" and not bool(getattr(self, "pro_tools", False))))
                except Exception:
                    pass
            self._active_right_section = section_name
            try:
                sb = self.right_scroll.verticalScrollBar()
                if sb is not None:
                    sb.setValue(0)
            except Exception:
                pass
        except Exception:
            pass

    def _title_css(self):
        t = getattr(self, "theme", "dark")
        if t == "light":
            return ("font-family:'Consolas'; font-size:12px; font-weight:700; "
                    "color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a3a6e, stop:1 #1b7f6b);")
        if t == "retro":
            return ("font-family:'Consolas'; font-size:12px; font-weight:700; "
                    "color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d5e9ff, stop:1 #fff6c8);")
        if t == "cyberpunk 2077":
            return ("font-family:'Consolas'; font-size:12px; font-weight:700; "
                    "color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff6a82, stop:1 #c50024);")
        if t == "aphex twin":
            return ("font-family:'Consolas'; font-size:12px; font-weight:700; "
                    "color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #c9d8ef, stop:1 #9fb8d6);")
        if t == "dedsec":
            return ("font-family:'Consolas'; font-size:12px; font-weight:700; "
                    "color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8dffb8, stop:1 #2ee870);")
        if t == "custom":
            ac = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            fg = str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff")
            return f"font-family:'Consolas'; font-size:12px; font-weight:700; color:{fg}; text-shadow: 0 0 0 {ac};"
        return ("font-family:'Consolas'; font-size:12px; font-weight:700; "
                "color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7aa7ff, stop:1 #7df7c5);")

    def _section_line_css(self):
        t = getattr(self, "theme", "dark")
        if t == "light":
            return "background: rgba(20,20,30,0.10);"
        if t == "cyberpunk 2077":
            return "background: rgba(0,246,255,0.28);"
        if t == "aphex twin":
            return "background: rgba(210,222,240,0.20);"
        if t == "dedsec":
            return "background: rgba(132,255,178,0.26);"
        if t == "custom":
            ac = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            return f"background: {ac};"
        return "background: rgba(255,255,255,0.08);"

    def _scrollbar_css(self):
        t = getattr(self, "theme", "dark")
        if t == "light":
            return ("QScrollArea{background:transparent;border:none;} "
                    "QScrollArea::viewport{background:transparent;border-radius:14px;} "
                    "QScrollBar:vertical{background:rgba(0,0,0,0.05);width:14px;margin:10px 4px;border-radius:7px;border:1px solid rgba(0,0,0,0.12);} "
                    "QScrollBar::handle:vertical{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(214,233,255,0.98), stop:1 rgba(112,157,218,0.96));border-radius:7px;min-height:78px;border:1px solid rgba(255,255,255,0.78);} "
                    "QScrollBar::handle:vertical:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(230,244,255,0.99), stop:1 rgba(106,156,222,0.97));} "
                    "QScrollBar::handle:vertical:pressed{background: rgba(87,137,206,0.98);} "
                    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;} "
                    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;width:0px;}")
        if t == "retro":
            return ("QScrollArea{background:transparent;border:none;} "
                    "QScrollArea::viewport{background:transparent;border-radius:12px;} "
                    "QScrollBar:vertical{background:rgba(24,54,90,0.55);width:14px;margin:10px 4px;border-radius:7px;border:1px solid rgba(180,208,245,0.35);} "
                    "QScrollBar::handle:vertical{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #b8d2f0, stop:0.5 #8cb3df, stop:1 #6b98cb);border-radius:7px;min-height:78px;border:1px solid rgba(235,246,255,0.78);} "
                    "QScrollBar::handle:vertical:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #c8ddf6, stop:1 #7fa9d7);} "
                    "QScrollBar::handle:vertical:pressed{background:#6e97c4;} "
                    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;} "
                    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;width:0px;}")
        if t == "cyberpunk 2077":
            return ("QScrollArea{background:transparent;border:none;} "
                    "QScrollArea::viewport{background:transparent;border-radius:14px;} "
                    "QScrollBar:vertical{background:rgba(20,8,12,0.78);width:14px;margin:10px 4px;border-radius:7px;border:1px solid rgba(234,48,72,0.36);} "
                    "QScrollBar::handle:vertical{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,106,130,0.92), stop:1 rgba(197,0,36,0.94));border-radius:7px;min-height:78px;border:1px solid rgba(255,196,206,0.36);} "
                    "QScrollBar::handle:vertical:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,138,156,0.98), stop:1 rgba(224,20,56,0.98));} "
                    "QScrollBar::handle:vertical:pressed{background: rgba(220,28,54,1.0);} "
                    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;} "
                    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;width:0px;}")
        if t == "aphex twin":
            return ("QScrollArea{background:transparent;border:none;} "
                    "QScrollArea::viewport{background:transparent;border-radius:14px;} "
                    "QScrollBar:vertical{background:rgba(18,22,30,0.62);width:14px;margin:10px 4px;border-radius:7px;border:1px solid rgba(214,228,246,0.24);} "
                    "QScrollBar::handle:vertical{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(232,241,255,0.94), stop:1 rgba(139,161,188,0.94));border-radius:7px;min-height:78px;border:1px solid rgba(255,255,255,0.62);} "
                    "QScrollBar::handle:vertical:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(246,251,255,0.98), stop:1 rgba(160,183,211,0.98));} "
                    "QScrollBar::handle:vertical:pressed{background: rgba(130,150,177,0.98);} "
                    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;} "
                    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;width:0px;}")
        if t == "dedsec":
            return ("QScrollArea{background:transparent;border:none;} "
                    "QScrollArea::viewport{background:transparent;border-radius:14px;} "
                    "QScrollBar:vertical{background:rgba(8,16,10,0.70);width:14px;margin:10px 4px;border-radius:7px;border:1px solid rgba(88,255,138,0.34);} "
                    "QScrollBar::handle:vertical{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(172,255,206,0.94), stop:1 rgba(40,196,104,0.94));border-radius:7px;min-height:78px;border:1px solid rgba(224,255,234,0.62);} "
                    "QScrollBar::handle:vertical:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(196,255,220,0.98), stop:1 rgba(52,218,116,0.98));} "
                    "QScrollBar::handle:vertical:pressed{background: rgba(34,166,88,0.98);} "
                    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;} "
                    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;width:0px;}")
        if t == "custom":
            bg = str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29")
            ac = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            return ("QScrollArea{background:transparent;border:none;} "
                    "QScrollArea::viewport{background:transparent;border-radius:14px;} "
                    f"QScrollBar:vertical{{background:{bg};width:14px;margin:10px 4px;border-radius:7px;border:1px solid {ac};}} "
                    f"QScrollBar::handle:vertical{{background:{ac};border-radius:7px;min-height:78px;border:1px solid rgba(255,255,255,0.45);}} "
                    "QScrollBar::handle:vertical:hover{background: rgba(255,255,255,0.88);} "
                    "QScrollBar::handle:vertical:pressed{background: rgba(255,255,255,0.68);} "
                    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;} "
                    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;width:0px;}")
        return ("QScrollArea{background:transparent;border:none;} "
                "QScrollArea::viewport{background:transparent;border-radius:14px;} "
                "QScrollBar:vertical{background:rgba(255,255,255,0.10);width:14px;margin:10px 4px;border-radius:7px;border:1px solid rgba(255,255,255,0.22);} "
                "QScrollBar::handle:vertical{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(244,251,255,0.98), stop:0.5 rgba(177,212,247,0.96), stop:1 rgba(102,151,212,0.95));border-radius:7px;min-height:78px;border:1px solid rgba(255,255,255,0.82);} "
                "QScrollBar::handle:vertical:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,1.0), stop:1 rgba(129,184,242,0.99));} "
                "QScrollBar::handle:vertical:pressed{background: rgba(112,170,236,1.0);} "
                "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;} "
                "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;width:0px;}")

    def _combo_css(self):
        t = getattr(self, "theme", "dark")
        if t == "light":
            return (
                "QComboBox{min-height:28px; padding:4px 28px 4px 8px; border-radius:10px; "
                "border:1px solid #c9d5e8; background: rgba(255,255,255,0.96); color:#13243d; combobox-popup:1;}"
                "QComboBox:hover{border:1px solid #95b6df;}"
                "QComboBox:focus{border:1px solid #5d97dd;}"
                "QComboBox::drop-down{subcontrol-origin:padding; subcontrol-position: top right; width:24px; border:none; background:transparent;}"
            )
        if t == "retro":
            return (
                "QComboBox{min-height:28px; padding:4px 28px 4px 8px; border-radius:10px; "
                "border:1px solid rgba(188,214,246,0.56); background: rgba(35,66,106,0.88); color:#eff6ff; combobox-popup:1;}"
                "QComboBox:hover{border:1px solid rgba(214,233,255,0.82);}"
                "QComboBox:focus{border:1px solid rgba(235,246,255,0.94);}"
                "QComboBox::drop-down{subcontrol-origin:padding; subcontrol-position: top right; width:24px; border:none; background:transparent;}"
            )
        if t == "cyberpunk 2077":
            return (
                "QComboBox{min-height:28px; padding:4px 28px 4px 8px; border-radius:10px; "
                "border:1px solid rgba(234,48,72,0.56); background: rgba(18,10,18,0.92); color:#fff2f4; combobox-popup:1;}"
                "QComboBox:hover{border:1px solid rgba(255,120,138,0.84);}"
                "QComboBox:focus{border:1px solid rgba(255,152,168,0.96);}"
                "QComboBox::drop-down{subcontrol-origin:padding; subcontrol-position: top right; width:24px; border:none; background:transparent;}"
            )
        if t == "aphex twin":
            return (
                "QComboBox{min-height:28px; padding:4px 28px 4px 8px; border-radius:10px; "
                "border:1px solid rgba(208,223,244,0.36); background: rgba(20,25,35,0.92); color:#edf3fb; combobox-popup:1;}"
                "QComboBox:hover{border:1px solid rgba(224,236,255,0.62);}"
                "QComboBox:focus{border:1px solid rgba(232,244,255,0.84);}"
                "QComboBox::drop-down{subcontrol-origin:padding; subcontrol-position: top right; width:24px; border:none; background:transparent;}"
            )
        if t == "dedsec":
            return (
                "QComboBox{min-height:28px; padding:4px 28px 4px 8px; border-radius:10px; "
                "border:1px solid rgba(88,255,138,0.52); background: rgba(10,18,12,0.94); color:#dcffe6; combobox-popup:1;}"
                "QComboBox:hover{border:1px solid rgba(132,255,176,0.86);}"
                "QComboBox:focus{border:1px solid rgba(162,255,196,0.96);}"
                "QComboBox::drop-down{subcontrol-origin:padding; subcontrol-position: top right; width:24px; border:none; background:transparent;}"
            )
        if t == "custom":
            bg = str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29")
            fg = str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff")
            ac = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            return (
                "QComboBox{min-height:28px; padding:4px 28px 4px 8px; border-radius:10px; "
                f"border:1px solid {ac}; background: {bg}; color:{fg}; combobox-popup:1;}}"
                f"QComboBox:hover{{border:1px solid {ac};}}"
                f"QComboBox:focus{{border:1px solid {ac};}}"
                "QComboBox::drop-down{subcontrol-origin:padding; subcontrol-position: top right; width:24px; border:none; background:transparent;}"
            )
        return (
            "QComboBox{min-height:28px; padding:4px 28px 4px 8px; border-radius:10px; "
            "border:1px solid rgba(145,190,255,0.24); background: rgba(18,23,34,0.86); color:#e6eef6; combobox-popup:1;}"
            "QComboBox:hover{border:1px solid rgba(145,200,255,0.44);}"
            "QComboBox:focus{border:1px solid rgba(135,205,255,0.72);}"
            "QComboBox::drop-down{subcontrol-origin:padding; subcontrol-position: top right; width:24px; border:none; background:transparent;}"
        )

    def _combo_view_css(self):
        t = getattr(self, "theme", "dark")
        if t == "light":
            return (
                "QListView{background:#f5f9ff; color:#10233d; border:1px solid #bfd0e8; border-radius:10px; padding:4px; outline:none;}"
                "QListView::item{min-height:24px; padding:4px 8px; border-radius:7px;}"
                "QListView::item:selected{background:rgba(94,150,224,0.28); color:#0c1e34;}"
                "QListView::item:hover{background:rgba(94,150,224,0.18);}"
            )
        if t == "retro":
            return (
                "QListView{background:rgba(28,55,90,0.98); color:#f0f7ff; border:1px solid rgba(188,214,246,0.56); border-radius:10px; padding:4px; outline:none;}"
                "QListView::item{min-height:24px; padding:4px 8px; border-radius:7px;}"
                "QListView::item:selected{background:rgba(188,214,246,0.34); color:#ffffff;}"
                "QListView::item:hover{background:rgba(188,214,246,0.22);}"
            )
        if t == "cyberpunk 2077":
            return (
                "QListView{background:rgba(14,8,16,0.98); color:#fff2f4; border:1px solid rgba(234,48,72,0.44); border-radius:10px; padding:4px; outline:none;}"
                "QListView::item{min-height:24px; padding:4px 8px; border-radius:7px;}"
                "QListView::item:selected{background:rgba(220,34,58,0.40); color:#ffffff;}"
                "QListView::item:hover{background:rgba(234,48,72,0.24);}"
            )
        if t == "aphex twin":
            return (
                "QListView{background:rgba(16,20,28,0.98); color:#eef3f8; border:1px solid rgba(214,228,246,0.32); border-radius:10px; padding:4px; outline:none;}"
                "QListView::item{min-height:24px; padding:4px 8px; border-radius:7px;}"
                "QListView::item:selected{background:rgba(163,184,210,0.32); color:#ffffff;}"
                "QListView::item:hover{background:rgba(163,184,210,0.18);}"
            )
        if t == "dedsec":
            return (
                "QListView{background:rgba(8,16,10,0.98); color:#dcffe6; border:1px solid rgba(88,255,138,0.40); border-radius:10px; padding:4px; outline:none;}"
                "QListView::item{min-height:24px; padding:4px 8px; border-radius:7px;}"
                "QListView::item:selected{background:rgba(44,180,92,0.40); color:#ffffff;}"
                "QListView::item:hover{background:rgba(44,180,92,0.22);}"
            )
        if t == "custom":
            bg = str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29")
            fg = str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff")
            ac = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            return (
                f"QListView{{background:{bg}; color:{fg}; border:1px solid {ac}; border-radius:10px; padding:4px; outline:none;}}"
                "QListView::item{min-height:24px; padding:4px 8px; border-radius:7px;}"
                "QListView::item:selected{background:rgba(255,255,255,0.26); color:#ffffff;}"
                "QListView::item:hover{background:rgba(255,255,255,0.14);}"
            )
        return (
            "QListView{background:rgba(14,18,28,0.98); color:#e6eef6; border:1px solid rgba(145,190,255,0.34); border-radius:10px; padding:4px; outline:none;}"
            "QListView::item{min-height:24px; padding:4px 8px; border-radius:7px;}"
                "QListView::item:selected{background:rgba(120,170,238,0.34); color:#f6fbff;}"
                "QListView::item:hover{background:rgba(120,170,238,0.22);}"
        )

    def _input_css(self):
        t = getattr(self, "theme", "dark")
        if t == "light":
            return (
                "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
                "border:1px solid #c9d5e8; background: rgba(255,255,255,0.97); color:#13243d; selection-background-color:#6a9ff0; selection-color:#ffffff;}"
                "QSpinBox:hover,QLineEdit:hover{border:1px solid #95b6df;}"
                "QSpinBox:focus,QLineEdit:focus{border:1px solid #5d97dd;}"
                "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(90,130,190,0.10); border-radius:8px; margin:2px;}"
                "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(90,130,190,0.18);}"
            )
        if t == "retro":
            return (
                "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
                "border:1px solid rgba(188,214,246,0.54); background: rgba(26,53,90,0.90); color:#eff6ff; selection-background-color:rgba(188,214,246,0.45); selection-color:#ffffff;}"
                "QSpinBox:hover,QLineEdit:hover{border:1px solid rgba(214,233,255,0.72);}"
                "QSpinBox:focus,QLineEdit:focus{border:1px solid rgba(235,246,255,0.90);}"
                "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(188,214,246,0.16); border-radius:8px; margin:2px;}"
                "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(188,214,246,0.24);}"
            )
        if t == "cyberpunk 2077":
            return (
                "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
                "border:1px solid rgba(234,48,72,0.56); background: rgba(16,8,14,0.92); color:#fff2f4; selection-background-color:rgba(220,34,58,0.44); selection-color:#ffffff;}"
                "QSpinBox:hover,QLineEdit:hover{border:1px solid rgba(255,122,142,0.82);}"
                "QSpinBox:focus,QLineEdit:focus{border:1px solid rgba(255,156,174,0.98);}"
                "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(220,34,58,0.20); border-radius:8px; margin:2px;}"
                "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(255,122,142,0.28);}"
            )
        if t == "aphex twin":
            return (
                "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
                "border:1px solid rgba(206,222,242,0.36); background: rgba(18,23,34,0.92); color:#edf3fa; selection-background-color:rgba(163,184,210,0.44); selection-color:#ffffff;}"
                "QSpinBox:hover,QLineEdit:hover{border:1px solid rgba(224,236,255,0.56);}"
                "QSpinBox:focus,QLineEdit:focus{border:1px solid rgba(233,245,255,0.80);}"
                "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(163,184,210,0.14); border-radius:8px; margin:2px;}"
                "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(163,184,210,0.24);}"
            )
        if t == "sketch":
            return (
                "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
                "border:1px solid rgba(255,255,255,0.34); background: rgba(255,255,255,0.09); color:#f6f8fb; selection-background-color:rgba(255,255,255,0.34); selection-color:#111111;}"
                "QSpinBox:hover,QLineEdit:hover{border:1px solid rgba(255,255,255,0.52);}"
                "QSpinBox:focus,QLineEdit:focus{border:1px solid rgba(255,255,255,0.72);}"
                "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(255,255,255,0.14); border-radius:8px; margin:2px;}"
                "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(255,255,255,0.24);}"
            )
        if t == "dedsec":
            return (
                "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
                "border:1px solid rgba(88,255,138,0.52); background: rgba(8,16,10,0.94); color:#dcffe6; selection-background-color:rgba(44,180,92,0.44); selection-color:#ffffff;}"
                "QSpinBox:hover,QLineEdit:hover{border:1px solid rgba(132,255,176,0.82);}"
                "QSpinBox:focus,QLineEdit:focus{border:1px solid rgba(162,255,196,0.96);}"
                "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(44,180,92,0.20); border-radius:8px; margin:2px;}"
                "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(84,220,132,0.28);}"
            )
        if t == "custom":
            bg = str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29")
            fg = str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff")
            ac = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            return (
                "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
                f"border:1px solid {ac}; background:{bg}; color:{fg}; selection-background-color:rgba(255,255,255,0.34); selection-color:#111111;}}"
                f"QSpinBox:hover,QLineEdit:hover{{border:1px solid {ac};}}"
                f"QSpinBox:focus,QLineEdit:focus{{border:1px solid {ac};}}"
                "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(255,255,255,0.12); border-radius:8px; margin:2px;}"
                "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(255,255,255,0.22);}"
            )
        return (
            "QSpinBox,QLineEdit{min-height:28px; padding:4px 8px; border-radius:10px; "
            "border:1px solid rgba(145,190,255,0.30); background: rgba(18,23,34,0.90); color:#e6eef6; selection-background-color:rgba(120,170,238,0.40); selection-color:#ffffff;}"
            "QSpinBox:hover,QLineEdit:hover{border:1px solid rgba(145,200,255,0.50);}"
            "QSpinBox:focus,QLineEdit:focus{border:1px solid rgba(135,205,255,0.72);}"
            "QSpinBox::up-button,QSpinBox::down-button{width:18px; border:none; background: rgba(145,190,255,0.10); border-radius:8px; margin:2px;}"
            "QSpinBox::up-button:hover,QSpinBox::down-button:hover{background: rgba(145,190,255,0.22);}"
        )

    def _apply_input_styles(self):
        try:
            css = self._input_css()
            for sp in self.findChildren(QSpinBox):
                sp.setStyleSheet(css)
                try:
                    le = sp.lineEdit()
                    if le is not None:
                        le.setReadOnly(False)
                except Exception:
                    pass
            for le in self.findChildren(QLineEdit):
                if isinstance(le.parent(), QComboBox):
                    continue
                le.setStyleSheet(css)
        except Exception:
            pass

    def _apply_combo_styles(self):
        try:
            combo_css = self._combo_css()
            popup_css = self._combo_view_css()
            for cb in self.findChildren(QComboBox):
                cb.setStyleSheet(combo_css)
                try:
                    cb.setMaxVisibleItems(14)
                    view = cb.view()
                    if view is not None:
                        view.setStyleSheet(popup_css)
                        view.setUniformItemSizes(True)
                        view.setAlternatingRowColors(False)
                        view.setAutoFillBackground(True)
                        view.setWindowOpacity(1.0)
                except Exception:
                    pass
        except Exception:
            pass

    def _resolve_device_choice(self, choice):
        try:
            if choice == "auto":
                if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                    return "gpu"
                return "cpu"
            if choice == "gpu":
                return "gpu" if cv2.cuda.getCudaEnabledDeviceCount() > 0 else "cpu"
        except Exception:
            return "cpu"
        return "cpu"

    def _info_btn_css(self):
        if getattr(self, "theme", "dark") == "light":
            return "QPushButton{background:transparent;border:none;} QPushButton:hover{background:rgba(0,0,0,0.06);border-radius:8px;}"
        return "QPushButton{background:transparent;border:none;} QPushButton:hover{background:rgba(255,255,255,0.08);border-radius:8px;}"

    def _style_help_css(self):
        if getattr(self, "theme", "dark") == "light":
            return "QLabel#style_help{font-size:11px; font-family:'Segoe UI','Microsoft YaHei','Noto Sans CJK SC','Arial'; color:#263246; background:rgba(240,244,250,0.95); border:1px solid #d7dee8; border-radius:8px; padding:6px 8px;}"
        return "QLabel#style_help{font-size:11px; font-family:'Segoe UI','Microsoft YaHei','Noto Sans CJK SC','Arial'; color:#9fb3cc; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:6px 8px;}"

    def _codec_help_css(self):
        if getattr(self, "theme", "dark") == "light":
            return "QLabel#codec_help{font-size:11px; font-family:'Segoe UI','Microsoft YaHei','Noto Sans CJK SC','Arial'; color:#263246; background:rgba(240,244,250,0.95); border:1px solid #d7dee8; border-radius:8px; padding:6px 8px;}"
        return "QLabel#codec_help{font-size:11px; font-family:'Segoe UI','Microsoft YaHei','Noto Sans CJK SC','Arial'; color:#9fb3cc; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:6px 8px;}"

    def _update_style_help(self):
        try:
            lang = getattr(self, "lang", "en")
            style = self.style_combo.currentText() if hasattr(self, "style_combo") else "bw"
            txt = STYLE_HELP.get(lang, STYLE_HELP["en"]).get(style, "")
            if hasattr(self, "style_help"):
                self.style_help.setText(_repair_mojibake_text(txt, lang_hint=lang))
        except Exception:
            pass

    def _update_codec_help(self):
        try:
            lang = getattr(self, "lang", "en")
            codec = self.codec_combo.currentText() if hasattr(self, "codec_combo") else "libx264"
            txt = CODEC_HELP.get(lang, CODEC_HELP["en"]).get(codec, "")
            if hasattr(self, "codec_help"):
                self.codec_help.setText(_repair_mojibake_text(txt, lang_hint=lang))
        except Exception:
            pass

    def _update_pro_preset_help(self):
        try:
            lang = getattr(self, "lang", "en")
            name = self.pro_preset_combo.currentText() if hasattr(self, "pro_preset_combo") else "none"
            txt = PRO_PRESET_HELP.get(lang, PRO_PRESET_HELP["en"]).get(name, "")
            if hasattr(self, "pro_preset_help"):
                self.pro_preset_help.setText(_repair_mojibake_text(txt, lang_hint=lang))
        except Exception:
            pass

    def _refresh_info_icons(self):
        try:
            color = "#1c2533" if getattr(self, "theme", "dark") == "light" else "#9fb3cc"
            for btn in getattr(self, "_info_buttons", []):
                icon = self._load_svg_icon("info", color)
                if icon is not None:
                    btn.setIcon(icon)
                btn.setStyleSheet(self._info_btn_css())
            if hasattr(self, "codec_help"):
                self.codec_help.setStyleSheet(self._codec_help_css())
            if hasattr(self, "pro_preset_help"):
                self.pro_preset_help.setStyleSheet(self._codec_help_css())
        except Exception:
            pass

    def _make_geom_icon(self, color, shape='rect', size=18):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor(color))
            p.setPen(Qt.NoPen)
            pad = 2
            span = size - pad * 2
            if shape == 'rect':
                p.drawRect(pad, pad, span, span)
            elif shape == 'tri':
                p.drawPolygon(QPolygon([QPoint(pad+1, size-pad), QPoint(size-pad, size//2), QPoint(pad+1, pad)]))
            elif shape == 'circle':
                p.drawEllipse(pad, pad, span, span)
        finally:
            if p.isActive():
                p.end()
        return QIcon(pm)

    def _refresh_button_icons(self):
        try:
            if self.theme == "light":
                icon_color = "#111111"
            elif self.theme == "dedsec":
                icon_color = "#bfffd5"
            elif self.theme == "custom":
                icon_color = str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff")
            else:
                icon_color = "#e5ebf5"
            def icon(name, shape):
                ico = self._load_svg_icon(name, icon_color)
                return ico if ico is not None else self._make_geom_icon(icon_color, shape)
            self.load_btn.setIcon(icon("upload", "rect"))
            if hasattr(self, "gallery_load_btn"):
                self.gallery_load_btn.setIcon(icon("upload", "rect"))
            if hasattr(self, "gallery_editor_btn"):
                self.gallery_editor_btn.setIcon(icon("sliders", "rect"))
            self.render_btn.setIcon(icon("play-fill", "tri"))
            self.export_btn.setIcon(icon("download", "circle"))
            self.settings_btn.setIcon(icon("gear", "rect"))
            self.preview_prev_btn.setIcon(icon("arrow-left-circle", "circle"))
            self.preview_next_btn.setIcon(icon("arrow-right-circle", "circle"))
            self.preview_prev_btn.setText("")
            self.preview_next_btn.setText("")
            self.preview_prev_btn.setIconSize(QSize(18, 18))
            self.preview_next_btn.setIconSize(QSize(18, 18))
            self.preview_open_btn.setIcon(icon("monitor", "rect"))
            if hasattr(self, "action_undo_menu"):
                iu = self._load_svg_icon("undo", icon_color)
                if iu is not None:
                    self.action_undo_menu.setIcon(iu)
            if hasattr(self, "action_redo_menu"):
                ir = self._load_svg_icon("redo", icon_color)
                if ir is not None:
                    self.action_redo_menu.setIcon(ir)
            if hasattr(self, "action_check_updates"):
                iu = self._load_svg_icon("update", icon_color)
                if iu is not None:
                    self.action_check_updates.setIcon(iu)
            if hasattr(self, "player_play_btn"):
                self.player_play_btn.setIcon(icon("play-fill", "tri"))
            if hasattr(self, "player_stop_btn"):
                self.player_stop_btn.setIcon(icon("stop", "rect"))
            if hasattr(self, "player_repeat_btn"):
                self.player_repeat_btn.setIcon(icon("repeat", "circle"))
            if hasattr(self, "player_fullscreen_btn"):
                self.player_fullscreen_btn.setIcon(icon("monitor", "rect"))
            if hasattr(self, "update_install_btn"):
                self.update_install_btn.setIcon(icon("download", "circle"))
            if hasattr(self, "update_later_btn"):
                self.update_later_btn.setIcon(icon("clock", "circle"))
            if hasattr(self, "save_preset_btn"):
                self.save_preset_btn.setIcon(icon("download", "rect"))
            if hasattr(self, "load_preset_btn"):
                self.load_preset_btn.setIcon(icon("upload", "rect"))
            if hasattr(self, "defaults_btn"):
                self.defaults_btn.setIcon(icon("reset", "circle"))
            if hasattr(self, "fx_defaults_btn"):
                self.fx_defaults_btn.setIcon(icon("reset", "circle"))
            if hasattr(self, "pro_defaults_btn"):
                self.pro_defaults_btn.setIcon(icon("reset", "circle"))
            if hasattr(self, "render_defaults_btn"):
                self.render_defaults_btn.setIcon(icon("reset", "circle"))
            if hasattr(self, "_embedded_editor_full_btn") and self._embedded_editor_full_btn is not None:
                self._embedded_editor_full_btn.setIcon(icon("fullscreen", "rect"))
            if hasattr(self, "_embedded_editor_close_btn") and self._embedded_editor_close_btn is not None:
                self._embedded_editor_close_btn.setIcon(icon("close", "circle"))
            for bname in (
                "load_btn",
                "gallery_load_btn",
                "gallery_editor_btn",
                "render_btn",
                "export_btn",
                "settings_btn",
                "preview_open_btn",
                "player_play_btn",
                "player_stop_btn",
                "player_repeat_btn",
                "player_fullscreen_btn",
            ):
                b = getattr(self, bname, None)
                if b is not None:
                    try:
                        b.setIconSize(QSize(16, 16))
                    except Exception:
                        pass
            pro_icon_map = {"batch": "layers", "palette": "spark", "dither": "sliders"}
            for key, b in getattr(self, "_pro_tool_buttons", {}).items():
                try:
                    b.setIcon(icon(pro_icon_map.get(str(key), "spark"), "circle"))
                    b.setIconSize(QSize(16, 16))
                except Exception:
                    b.setIcon(self._make_geom_icon(icon_color, "circle"))
            self._refresh_info_icons()
            if hasattr(self, "style_help"):
                self.style_help.setStyleSheet(self._style_help_css())
            self._sync_compact_button_sizes()
        except Exception:
            pass

    def _load_svg_icon(self, name, color):
        if QSvgRenderer is None:
            return None
        try:
            svg = None
            base_name = str(name or "").strip()
            aliases = {
                "play-fill": "play",
                "gear": "settings",
                "reset": "rotate-ccw",
                "spark": "sparkles",
                "arrow-left-circle": "circle-arrow-left",
                "arrow-right-circle": "circle-arrow-right",
                "fullscreen": "maximize-2",
                "repeat": "repeat-2",
                "refresh": "refresh-cw",
                "wave": "audio-lines",
                "node": "workflow",
            }
            name_variants = [base_name]
            alt_name = aliases.get(base_name)
            if alt_name and alt_name not in name_variants:
                name_variants.append(alt_name)
            # 0) bundled high-quality icon pack.
            try:
                bdir = _pick_resource_path("assets/icons_lucide", "icons/lucide")
                if bdir:
                    for nm in name_variants:
                        p = Path(bdir) / f"{nm}.svg"
                        if p.exists():
                            svg = p.read_text(encoding="utf-8", errors="replace")
                            break
            except Exception:
                svg = None
            # 1) local custom icon pack folder
            if not svg:
                try:
                    pdir = str(getattr(self, "icon_pack_path", "") or "").strip()
                    if pdir:
                        pdir = str(Path(pdir).expanduser().resolve())
                        for nm in name_variants:
                            p = Path(pdir) / f"{nm}.svg"
                            if p.exists():
                                svg = p.read_text(encoding="utf-8", errors="replace")
                                break
                except Exception:
                    svg = None
            # 2) remote icon pack URL with filesystem cache
            if not svg:
                try:
                    base_url = str(getattr(self, "icon_pack_url", "") or "").strip().rstrip("/")
                    if base_url:
                        cache_dir = Path(getattr(self, "_icon_cache_dir", Path.home() / ".ascii_studio_icon_cache"))
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        for nm in name_variants:
                            cache_file = cache_dir / f"{nm}.svg"
                            if cache_file.exists():
                                svg = cache_file.read_text(encoding="utf-8", errors="replace")
                                break
                            if nm in getattr(self, "_icon_remote_failed", set()):
                                continue
                            req = urllib.request.Request(f"{base_url}/{nm}.svg", headers={"User-Agent": f"ASCIIStudio/{self.app_version}"})
                            with urllib.request.urlopen(req, timeout=2.5) as resp:
                                raw = resp.read().decode("utf-8", errors="replace")
                            if "<svg" in raw.lower():
                                cache_file.write_text(raw, encoding="utf-8")
                                svg = raw
                                break
                            self._icon_remote_failed.add(nm)
                except Exception:
                    try:
                        for nm in name_variants:
                            self._icon_remote_failed.add(nm)
                    except Exception:
                        pass
            # 3) builtin fallback
            if not svg:
                svg = self._builtin_svg(base_name)
                if not svg and alt_name:
                    svg = self._builtin_svg(alt_name)
                if not svg:
                    return None
            svg = svg.replace("CURRENT_COLOR", color).replace("currentColor", color)
            renderer = QSvgRenderer(bytearray(svg, encoding="utf-8"))
            pm_size = 22
            pm = QPixmap(pm_size, pm_size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            try:
                p.setRenderHint(QPainter.Antialiasing)
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                renderer.render(p)
            finally:
                if p.isActive():
                    p.end()
            return QIcon(pm)
        except Exception:
            return None

    def _builtin_svg(self, name):
        icons = {
            "upload": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M.5 9.9v3.6c0 .6.4 1 1 1h13c.6 0 1-.4 1-1V9.9h-1.5v3.1h-11V9.9H.5z\"/><path d=\"M8 12V3.7l2.1 2.1 1.1-1.1L8 1.5 4.8 4.7l1.1 1.1L8 3.7V12h0z\"/></svg>",
            "download": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M.5 11.5v2c0 .6.4 1 1 1h13c.6 0 1-.4 1-1v-2h-1.5V13h-11v-1.5H.5z\"/><path d=\"M8 12.5l3.2-3.2-1.1-1.1L8 10.3V2H6.5v8.3L4.4 8.2 3.3 9.3 8 12.5z\"/></svg>",
            "play-fill": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M4 2.5v11l9-5.5-9-5.5z\"/></svg>",
            "pause": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M4 2h3v12H4V2zm5 0h3v12H9V2z\"/></svg>",
            "stop": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M3 3h10v10H3z\"/></svg>",
            "repeat": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M3 5h7l-1.8-1.8L9.3 2 13 5.7 9.3 9.4 8.2 8.3 10 6.5H3V5zm10 6H6l1.8 1.8-1.1 1.1L3 10.3 6.7 6.6l1.1 1.1L6 9.5h7V11z\"/></svg>",
            "fullscreen": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M2 2h5v1.5H3.5V7H2V2zm12 0v5h-1.5V3.5H9V2h5zM2 14V9h1.5v3.5H7V14H2zm12 0H9v-1.5h3.5V9H14v5z\"/></svg>",
            "undo": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M6 4V1L1.5 5.5 6 10V7c3.2 0 5.5 1 7 3-.4-3.8-2.9-6-7-6z\"/></svg>",
            "redo": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M10 4V1l4.5 4.5L10 10V7c-3.2 0-5.5 1-7 3 .4-3.8 2.9-6 7-6z\"/></svg>",
            "chevron-left": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M10.8 2.2 5 8l5.8 5.8-1.4 1.4L2.2 8l7.2-7.2z\"/></svg>",
            "chevron-right": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M5.2 13.8 11 8 5.2 2.2l1.4-1.4L13.8 8l-7.2 7.2z\"/></svg>",
            "arrow-left-circle": "<svg viewBox=\"0 0 24 24\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12 2a10 10 0 1 0 10 10A10.011 10.011 0 0 0 12 2Zm0 18a8 8 0 1 1 8-8 8.009 8.009 0 0 1-8 8Zm1.7-12.7L9 12l4.7 4.7-1.4 1.4L6.2 12l6.1-6.1Z\"/></svg>",
            "arrow-right-circle": "<svg viewBox=\"0 0 24 24\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12 2a10 10 0 1 0 10 10A10.011 10.011 0 0 0 12 2Zm0 18a8 8 0 1 1 8-8 8.009 8.009 0 0 1-8 8Zm-1.7-1.9L15 12l-4.7-4.7 1.4-1.4 6.1 6.1-6.1 6.1Z\"/></svg>",
            "monitor": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M1.5 2.5A1.5 1.5 0 0 1 3 1h10a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 13 11h-3v2h2v1.5H4V13h2v-2H3A1.5 1.5 0 0 1 1.5 9.5v-7Zm1.5 0v7h10v-7H3Z\"/></svg>",
            "gear": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M9.7 1.2l.3 1.5c.4.1.8.3 1.1.5l1.3-.8 1.3 2.3-1.3.8c.1.4.2.8.2 1.2s-.1.8-.2 1.2l1.3.8-1.3 2.3-1.3-.8c-.3.2-.7.4-1.1.5l-.3 1.5H6.3l-.3-1.5c-.4-.1-.8-.3-1.1-.5l-1.3.8-1.3-2.3 1.3-.8c-.1-.4-.2-.8-.2-1.2s.1-.8.2-1.2l-1.3-.8L3.7 2.4l1.3.8c.3-.2.7-.4 1.1-.5l.3-1.5h3.3zm-2 4.3a2 2 0 100 4 2 2 0 000-4z\"/></svg>",
            "info": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M8 1.5A6.5 6.5 0 108 14.5 6.5 6.5 0 008 1.5zm0 1.2a5.3 5.3 0 110 10.6A5.3 5.3 0 018 2.7zm0 2.1a.8.8 0 100 1.6.8.8 0 000-1.6zm-1 2.6h2v4H7v-4z\"/></svg>",
            "reset": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M8 3V1L5 4l3 3V5a4 4 0 11-4 4H2a6 6 0 106-6z\"/></svg>",
            "spark": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M8 1l1.5 3.5L13 6l-3.5 1.5L8 11 6.5 7.5 3 6l3.5-1.5L8 1zm0 9l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2z\"/></svg>",
            "close": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M3.2 2.2 8 7l4.8-4.8 1 1L9 8l4.8 4.8-1 1L8 9 3.2 13.8l-1-1L7 8 2.2 3.2z\"/></svg>",
            "clock": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M8 1.5A6.5 6.5 0 108 14.5 6.5 6.5 0 008 1.5zm0 1.2A5.3 5.3 0 118 13.3 5.3 5.3 0 018 2.7zm.7 2.3H7.3v3.5l2.8 1.7.7-1.1-2.1-1.2V5z\"/></svg>",
            "update": "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"CURRENT_COLOR\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M21 12a9 9 0 1 1-2.64-6.36\"/><polyline points=\"21 3 21 9 15 9\"/></svg>",
            "refresh-cw": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M13.5 2.5v4h-4l1.5-1.5A4.5 4.5 0 103 8H1.5a6 6 0 1110.9-3.5L13.5 2.5z\"/></svg>",
            "sliders": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M2 3h5v1H2V3zm8 0h4v1h-4V3zM6 2h3v3H6V2zM2 8h2v1H2V8zm5 0h7v1H7V8zM4 7h3v3H4V7zM2 13h7v1H2v-1zm10 0h2v1h-2v-1zm-3-1h3v3H9v-3z\"/></svg>",
            "crop": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M4 1h1v3h6v1H5v6H4V1zm3 3h8v8H7V4zm1 1v6h6V5H8zM1 11h3v1H2v2H1v-3zm11 3v-3h1v2h2v1h-3z\"/></svg>",
            "layers": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M8 1 1 4.5 8 8l7-3.5L8 1zm-7 6 7 3.5L15 7v2L8 12.5 1 9V7zm0 4 7 3.5 7-3.5v2L8 16.5 1 13v-2z\"/></svg>",
            "scissors": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M5 4a2 2 0 11-4 0 2 2 0 014 0zm0 8a2 2 0 11-4 0 2 2 0 014 0zM15 2 7.5 7.5 6.3 6.3 13.8.8 15 2zm0 12-1.2 1.2L6.3 9.7l1.2-1.2L15 14z\"/></svg>",
            "wave": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M1 8c1.3 0 1.3-4 2.6-4s1.3 8 2.6 8 1.3-8 2.6-8 1.3 8 2.6 8 1.3-4 2.6-4v2c-1.3 0-1.3 4-2.6 4s-1.3-8-2.6-8-1.3 8-2.6 8-1.3-8-2.6-8-1.3 4-2.6 4V8z\"/></svg>",
            "node": "<svg viewBox=\"0 0 16 16\" fill=\"CURRENT_COLOR\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M2 2h3v3H2V2zm9 0h3v3h-3V2zM2 11h3v3H2v-3zm9 0h3v3h-3v-3zM5 3.2h6v1.6H5V3.2zm1 4h4v1.6H6V7.2zm-1 4h6v1.6H5v-1.6z\"/></svg>",
        }
        return icons.get(name)

    def _add_labeled_row(self, layout, label, tooltip, info_title=None, info_body=None):
        try:
            container = QWidget()
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            container.setLayout(row)
            row.addWidget(label)
            icon_color = "#1c2533" if getattr(self, "theme", "dark") == "light" else "#9fb3cc"
            icon = self._load_svg_icon("info", icon_color)
            if icon is not None:
                btn = QPushButton()
                btn.setFixedSize(16, 16)
                btn.setIcon(icon)
                btn.setIconSize(QSize(12, 12))
                btn.setStyleSheet(self._info_btn_css())
                btn.setToolTip(tooltip)
                if info_title or info_body:
                    def _show():
                        t = self._resolve_info_text(info_title, label.text()) if info_title else label.text()
                        b = self._resolve_info_text(info_body, tooltip) if info_body else tooltip
                        self._show_info(t, b)
                    btn.clicked.connect(_show)
                row.addWidget(btn)
                try:
                    label._info_btn = btn
                except Exception:
                    pass
                try:
                    self._info_buttons.append(btn)
                except Exception:
                    pass
            row.addStretch(1)
            try:
                label._row_container = container
            except Exception:
                pass
            layout.addWidget(container)
        except Exception:
            layout.addWidget(label)

    def _show_info(self, title, body):
        try:
            self._prepare_modal_ui()
            dlg = OverlayDialog(self, self.theme, title)
            dlg.set_panel_size(380, 220)
            dlg.set_body_text(body)
            dlg.exec()
        except Exception:
            pass
        finally:
            self._restore_modal_ui()

    def _show_notice(self, title, body):
        self._show_info(title, body)

    def _prepare_modal_ui(self):
        self._modal_prev_state = None
        self._modal_prev_focus = bool(getattr(self, "_preview_focus_mode", False))
        try:
            if self._modal_prev_focus:
                self._toggle_player_focus_mode()
        except Exception:
            self._modal_prev_focus = False
        try:
            mode = getattr(self, "_preview_mode", "image")
            path = getattr(self, "current_path", None)
            if mode == "video" and self._preview_player is not None and path:
                st = self._preview_player.playbackState()
                self._modal_prev_state = {
                    "mode": "video",
                    "path": str(path),
                    "position": int(self._preview_player.position() or 0),
                    "playing": st == QMediaPlayer.PlaybackState.PlayingState,
                    "loop": bool(self._preview_loop),
                    "rate": float(getattr(self, "_preview_rate", 1.0)),
                }
                try:
                    self._preview_player.pause()
                except Exception:
                    pass
            elif mode == "gif" and self._preview_gif_movie is not None and path:
                self._modal_prev_state = {
                    "mode": "gif",
                    "path": str(path),
                    "frame": int(self._preview_gif_movie.currentFrameNumber() or 0),
                    "playing": self._preview_gif_movie.state() == QMovie.Running,
                    "loop": bool(self._preview_loop),
                    "rate": float(getattr(self, "_preview_rate", 1.0)),
                }
                try:
                    self._preview_gif_movie.setPaused(True)
                except Exception:
                    pass
        except Exception:
            self._modal_prev_state = None

    def _restore_modal_ui(self):
        try:
            state = self._modal_prev_state if isinstance(self._modal_prev_state, dict) else None
            if state:
                mode = state.get("mode")
                path = state.get("path")
                if path and os.path.exists(path):
                    if mode == "video":
                        self._start_preview_video(path)
                        if self._preview_player is not None:
                            try:
                                self._preview_player.setPlaybackRate(float(state.get("rate", 1.0)))
                            except Exception:
                                pass
                            try:
                                pos = int(state.get("position", 0))
                                if pos > 0:
                                    self._preview_player.setPosition(pos)
                            except Exception:
                                pass
                            if not bool(state.get("playing", False)):
                                try:
                                    self._preview_player.pause()
                                except Exception:
                                    pass
                    elif mode == "gif":
                        self._start_preview_gif(path)
                        try:
                            if self._preview_gif_movie is not None:
                                idx = int(state.get("frame", 0))
                                self._preview_gif_movie.jumpToFrame(max(0, idx))
                                if not bool(state.get("playing", False)):
                                    self._preview_gif_movie.setPaused(True)
                        except Exception:
                            pass
            if bool(getattr(self, "_modal_prev_focus", False)) and not bool(getattr(self, "_preview_focus_mode", False)):
                try:
                    self._toggle_player_focus_mode()
                except Exception:
                    pass
        except Exception:
            pass
        self._modal_prev_state = None
        self._modal_prev_focus = False
        self._force_clear_blur_effects()
        try:
            if not bool(getattr(self, "_embedded_editor_active", False)) and not bool(getattr(self, "_preview_focus_mode", False)):
                if hasattr(self, "gallery_frame") and self.gallery_frame is not None:
                    self.gallery_frame.setVisible(True)
                if hasattr(self, "left_frame") and self.left_frame is not None:
                    self.left_frame.setVisible(True)
                if hasattr(self, "right_frame") and self.right_frame is not None:
                    self.right_frame.setVisible(True)
                self._trail_overlay_stack_dirty = True
                self._sync_trail_overlay_stack(force=True)
                self._normalize_main_z_order()
        except Exception:
            pass

    def _force_clear_blur_effects(self):
        """Safety cleanup for rare cases when modal blur remains attached."""
        try:
            targets = []
            try:
                mb = self.menuBar()
                if mb is not None:
                    targets.append(mb)
            except Exception:
                pass
            try:
                cw = self.centralWidget()
                if cw is not None:
                    targets.append(cw)
                    targets.extend(cw.findChildren(QWidget))
            except Exception:
                pass
            for attr in (
                "gallery_frame",
                "left_frame",
                "right_frame",
                "right_tabs_rail",
                "right_footer",
                "player_controls",
            ):
                try:
                    w = getattr(self, attr, None)
                    if w is not None:
                        targets.append(w)
                except Exception:
                    pass
            seen = set()
            for w in targets:
                try:
                    if w is None:
                        continue
                    wid = id(w)
                    if wid in seen:
                        continue
                    seen.add(wid)
                    eff = w.graphicsEffect()
                    if isinstance(eff, QGraphicsBlurEffect):
                        w.setGraphicsEffect(None)
                except Exception:
                    pass
        except Exception:
            pass

    def _schedule_blur_cleanup(self):
        try:
            self._force_clear_blur_effects()
            QTimer.singleShot(40, self._force_clear_blur_effects)
            QTimer.singleShot(160, self._force_clear_blur_effects)
            QTimer.singleShot(360, self._force_clear_blur_effects)
        except Exception:
            pass

    def _confirm_overlay(self, title, body):
        try:
            self._prepare_modal_ui()
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            dlg = OverlayDialog(self, self.theme, title)
            dlg.set_panel_size(420, 220)
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(body)
            lbl.setWordWrap(True)
            lay.addWidget(lbl, 1)
            row = QHBoxLayout()
            row.addStretch(1)
            yes_btn = QPushButton(tr.get("yes", "Yes"))
            no_btn = QPushButton(tr.get("no", "No"))
            yes_btn.setStyleSheet(self._glass_btn_css())
            no_btn.setStyleSheet(self._glass_btn_css())
            yes_btn.clicked.connect(dlg.accept)
            no_btn.clicked.connect(dlg.reject)
            row.addWidget(yes_btn)
            row.addWidget(no_btn)
            lay.addLayout(row)
            dlg.set_body_widget(box)
            try:
                self._attach_sounds(dlg)
            except Exception:
                pass
            ok = dlg.exec() == QDialog.Accepted
            self._restore_modal_ui()
            return ok
        except Exception:
            self._restore_modal_ui()
            return False

    def _apply_tooltips(self, tr):
        try:
            self.load_btn.setToolTip(tr.get("load", "Load"))
            if hasattr(self, "gallery_load_btn"):
                self.gallery_load_btn.setToolTip(tr.get("load", "Load"))
            if hasattr(self, "gallery_editor_btn"):
                self.gallery_editor_btn.setToolTip(tr.get("editor", "Editor"))
            self.render_btn.setToolTip(tr.get("render", "Render"))
            self.export_btn.setToolTip(tr.get("export", "Export"))
            self.preview_prev_btn.setToolTip(tr.get("preview_prev", "Previous file"))
            self.preview_next_btn.setToolTip(tr.get("preview_next", "Next file"))
            self.preview_open_btn.setToolTip(tr.get("player_focus", "Focus mode"))
            if hasattr(self, "player_play_btn"):
                self.player_play_btn.setToolTip(tr.get("play", "Play"))
            if hasattr(self, "player_stop_btn"):
                self.player_stop_btn.setToolTip(tr.get("stop", "Stop"))
            if hasattr(self, "player_repeat_btn"):
                self.player_repeat_btn.setToolTip(tr.get("player_repeat", "Repeat"))
            if hasattr(self, "player_seek_slider"):
                self.player_seek_slider.setToolTip(tr.get("player_seek", "Seek"))
            if hasattr(self, "player_speed_combo"):
                self.player_speed_combo.setToolTip(tr.get("player_speed", "Speed"))
            if hasattr(self, "player_volume_slider"):
                self.player_volume_slider.setToolTip(tr.get("volume", "Volume"))
            if hasattr(self, "player_fullscreen_btn"):
                self.player_fullscreen_btn.setToolTip(tr.get("player_focus", "Focus mode"))
            self.style_combo.setToolTip(tr.get("style", "Style"))
            self.width_slider.setToolTip(tr.get("width", "Width"))
            self.font_slider.setToolTip(tr.get("font", "Font size"))
            self.fps_spin.setToolTip(tr.get("fps", "FPS"))
            self.scale_x1.setToolTip(tr.get("scale", "Scale") + " x1")
            self.scale_x2.setToolTip(tr.get("scale", "Scale") + " x2")
            self.scale_x3.setToolTip(tr.get("scale", "Scale") + " x3")
            self.out_w.setToolTip(tr.get("output_size", "Output size"))
            self.out_h.setToolTip(tr.get("output_size", "Output size"))
            self.defaults_btn.setToolTip(tr.get("defaults", "Defaults"))
            if hasattr(self, "fx_defaults_btn"):
                self.fx_defaults_btn.setToolTip(tr.get("defaults", "Defaults"))
            if hasattr(self, "pro_defaults_btn"):
                self.pro_defaults_btn.setToolTip(tr.get("defaults", "Defaults"))
            if hasattr(self, "render_defaults_btn"):
                self.render_defaults_btn.setToolTip(tr.get("defaults", "Defaults"))
            self.auto_size_chk.setToolTip(tr.get("auto_size", "Auto size"))
            self.charset_input.setToolTip(tr.get("charset", "Charset"))
            self.contrast_slider.setToolTip(tr.get("contrast", "Contrast"))
            self.gamma_slider.setToolTip(tr.get("gamma", "Gamma"))
            self.invert_chk.setToolTip(tr.get("invert", "Invert"))
            self.keep_size_chk.setToolTip(tr.get("keep_size", "Keep size"))
            self.denoise_chk.setToolTip(tr.get("denoise", "Denoise"))
            self.sharpen_chk.setToolTip(tr.get("sharpen", "Sharpen"))
            self.edge_chk.setToolTip(tr.get("edge_boost", "Edge boost"))
            self.pick_text_btn.setToolTip(tr.get("text_color", "Text color"))
            self.pick_bg_btn.setToolTip(tr.get("bg_color", "BG color"))
            self.settings_btn.setToolTip(tr.get("settings", "Settings"))
            self.codec_combo.setToolTip(tr.get("codec", "Codec"))
            if hasattr(self, "bitrate_combo"):
                self.bitrate_combo.setToolTip(tr.get("bitrate", "Bitrate"))
            if hasattr(self, "threads_spin"):
                self.threads_spin.setToolTip(tr.get("cpu_threads", "CPU threads"))
            if hasattr(self, "preset_combo"):
                self.preset_combo.setToolTip(tr.get("preset", "Preset"))
            if hasattr(self, "save_preset_btn"):
                self.save_preset_btn.setToolTip(tr.get("save_preset", "Save preset"))
            if hasattr(self, "load_preset_btn"):
                self.load_preset_btn.setToolTip(tr.get("load_preset", "Load preset"))
            if hasattr(self, "crf_spin"):
                self.crf_spin.setToolTip(tr.get("crf", "CRF"))
            if hasattr(self, "keep_audio_chk"):
                self.keep_audio_chk.setToolTip(tr.get("keep_source_audio_desc", "Use original source audio"))
            if hasattr(self, "pro_scanlines_chk"):
                self.pro_scanlines_chk.setToolTip(tr.get("pro_scanlines", "Scanlines"))
            if hasattr(self, "pro_bloom_slider"):
                self.pro_bloom_slider.setToolTip(tr.get("pro_bloom", "Bloom (%)"))
            if hasattr(self, "pro_vignette_slider"):
                self.pro_vignette_slider.setToolTip(tr.get("pro_vignette", "Vignette (%)"))
            if hasattr(self, "pro_poster_spin"):
                self.pro_poster_spin.setToolTip(tr.get("pro_poster_bits", "Posterize bits"))
            if hasattr(self, "pro_grain_slider"):
                self.pro_grain_slider.setToolTip(tr.get("pro_grain", "Film grain (%)"))
            if hasattr(self, "pro_chroma_spin"):
                self.pro_chroma_spin.setToolTip(tr.get("pro_chroma", "Chroma shift (px)"))
            if hasattr(self, "pro_color_boost_slider"):
                self.pro_color_boost_slider.setToolTip("Color boost (%)")
            if hasattr(self, "pro_clarity_slider"):
                self.pro_clarity_slider.setToolTip("Clarity (%)")
            if hasattr(self, "pro_motion_blur_slider"):
                self.pro_motion_blur_slider.setToolTip("Motion blur (%)")
            if hasattr(self, "pro_scan_strength_slider"):
                self.pro_scan_strength_slider.setToolTip(tr.get("pro_scan_strength", "Scanline strength (%)"))
            if hasattr(self, "pro_scan_step_spin"):
                self.pro_scan_step_spin.setToolTip(tr.get("pro_scan_step", "Scanline spacing (px)"))
            if hasattr(self, "pro_curvature_slider"):
                self.pro_curvature_slider.setToolTip(tr.get("pro_curvature", "CRT curvature (%)"))
            if hasattr(self, "pro_concavity_slider"):
                self.pro_concavity_slider.setToolTip("Concavity (%)")
            if hasattr(self, "pro_curvature_center_x_slider"):
                self.pro_curvature_center_x_slider.setToolTip("Center offset X (%)")
            if hasattr(self, "pro_curvature_expand_slider"):
                self.pro_curvature_expand_slider.setToolTip("Expand to fill (%)")
            if hasattr(self, "pro_curvature_type_combo"):
                self.pro_curvature_type_combo.setToolTip("Lens type")
            if hasattr(self, "pro_ribbing_slider"):
                self.pro_ribbing_slider.setToolTip(tr.get("pro_ribbing", "TV ribbing (%)"))
            if hasattr(self, "pro_glitch_slider"):
                self.pro_glitch_slider.setToolTip(tr.get("pro_glitch", "Glitch (%)"))
            if hasattr(self, "pro_glitch_density_slider"):
                self.pro_glitch_density_slider.setToolTip(tr.get("pro_glitch_density", "Glitch density (%)"))
            if hasattr(self, "pro_glitch_shift_slider"):
                self.pro_glitch_shift_slider.setToolTip(tr.get("pro_glitch_shift", "Glitch shift (%)"))
            if hasattr(self, "pro_glitch_rgb_spin"):
                self.pro_glitch_rgb_spin.setToolTip(tr.get("pro_glitch_rgb", "RGB split (px)"))
            if hasattr(self, "pro_glitch_block_spin"):
                self.pro_glitch_block_spin.setToolTip(tr.get("pro_glitch_block", "Block tear size (px)"))
            if hasattr(self, "pro_glitch_jitter_spin"):
                self.pro_glitch_jitter_spin.setToolTip(tr.get("pro_glitch_jitter", "Vertical jitter (px)"))
            if hasattr(self, "pro_glitch_noise_slider"):
                self.pro_glitch_noise_slider.setToolTip(tr.get("pro_glitch_noise", "Static noise (%)"))
            if hasattr(self, "pro_preset_combo"):
                self.pro_preset_combo.setToolTip(tr.get("preset", "Preset"))
            if hasattr(self, "_pro_tool_buttons"):
                if "batch" in self._pro_tool_buttons:
                    self._pro_tool_buttons["batch"].setToolTip(
                        self._resolve_info_text(self._i3(
                            "Пакетно: обработка нескольких файлов одним набором параметров.",
                            "Batch: render multiple files with current settings.",
                            "批处理：按当前参数批量渲染多个文件。"
                        ), tr.get("batch", "Batch"))
                    )
                if "palette" in self._pro_tool_buttons:
                    self._pro_tool_buttons["palette"].setToolTip(
                        self._resolve_info_text(self._i3(
                            "Палитра: уменьшает число цветов и стилизует изображение.",
                            "Palette: reduces colors for a stylized look.",
                            "调色板：减少颜色数量并进行风格化。"
                        ), tr.get("palette", "Palette"))
                    )
                if "dither" in self._pro_tool_buttons:
                    self._pro_tool_buttons["dither"].setToolTip(
                        self._resolve_info_text(self._i3(
                            "Растеризация: подчёркивает контуры и добавляет зернистый рисунок.",
                            "Dither: emphasizes edges with a raster/noise pattern.",
                            "抖动：强化边缘并叠加栅格噪点效果。"
                        ), tr.get("dither", "Dither"))
                    )
        except Exception:
            pass

    def _apply_window_style(self):
        self._apply_theme(self.theme if getattr(self, "theme", None) else "dark")
        # timers are started after UI build where timers are created

    def _apply_theme(self, name):
        try:
            self.theme = name if name in THEME_NAMES else "dark"
            if self.theme == "light":
                css = """
                QMainWindow { background: #f7f9fc; }
                QLabel { color: #0f172a; }
                QFrame#gallery_frame { background: rgba(255,255,255,0.94); border: 1px solid #d8dde6; border-radius:14px; }
                QFrame#left_frame { background: rgba(255,255,255,0.94); border: 1px solid #d8dde6; border-radius:14px; }
                QFrame#right_frame { background: rgba(250,250,250,0.98); border: 1px solid #d8dde6; border-radius:14px; padding:8px; }
                QListWidget { background: rgba(255,255,255,0.95); border: 1px solid #d8dde6; border-radius:8px; color: #1b2430; }
                QComboBox, QSpinBox, QLineEdit, QSlider, QCheckBox, QMenuBar, QMenu { color: #0f172a; background: #ffffff; }
                QComboBox, QSpinBox, QLineEdit { border:1px solid #d7dee8; border-radius:6px; padding:4px 6px; }
                QSlider::groove:horizontal { height:6px; background:#dbe3ee; border-radius:3px; }
                QSlider::handle:horizontal { background:#3b82f6; border:1px solid #1d4ed8; width:14px; margin:-6px 0; border-radius:7px; }
                QCheckBox { color: #111; }
                QCheckBox::indicator { width: 14px; height: 14px; }
                QCheckBox::indicator:unchecked { border:1px solid #b9c3d3; background:#fff; }
                QCheckBox::indicator:checked { border:1px solid #3b82f6; background:#3b82f6; }
                QToolTip { color: #111; background: #f3f6fb; border: 1px solid #ccd5e4; }
                QMenuBar { background: rgba(238,242,248,0.56); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid #d7dee8; border-radius:12px; margin:4px 6px; }
                QMenuBar::item { padding:5px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(0,0,0,0.10); }
                QMenu { background: #f7f9fc; border:1px solid #d7dee8; }
                """
            elif self.theme == "solarized":
                css = """
                QMainWindow { background: #002b36; }
                QLabel { color: #fdf6e3; }
                QFrame#gallery_frame { background: rgba(7,54,66,0.55); border-radius:14px; border:1px solid rgba(238,232,213,0.18); }
                QFrame#left_frame { background: rgba(7,54,66,0.55); border-radius:14px; border:1px solid rgba(238,232,213,0.18); }
                QFrame#right_frame { background: rgba(0,31,39,0.60); border-radius:14px; padding:8px; border:1px solid rgba(238,232,213,0.18); }
                QListWidget { background: rgba(7,54,66,0.45); border-radius:8px; color: #eee8d5; border:1px solid rgba(238,232,213,0.18); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #eee8d5; }
                QMenuBar { background: rgba(7,54,66,0.56); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(238,232,213,0.22); border-radius:12px; margin:4px 6px; }
                QMenuBar::item { padding:5px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(255,255,255,0.12); }
                QMenu { background: rgba(7,54,66,0.96); border:1px solid rgba(238,232,213,0.20); }
                """
            elif self.theme == "midnight":
                css = """
                QMainWindow { background: #0a0e19; }
                QLabel { color: #e6eef6; }
                QFrame#gallery_frame { background: rgba(12,14,24,0.55); border-radius:14px; border:1px solid rgba(255,255,255,0.08); }
                QFrame#left_frame { background: rgba(12,14,24,0.55); border-radius:14px; border:1px solid rgba(255,255,255,0.08); }
                QFrame#right_frame { background: rgba(12,14,26,0.58); border-radius:14px; padding:8px; border:1px solid rgba(255,255,255,0.08); }
                QListWidget { background: rgba(19,22,35,0.45); border-radius:8px; color: #dfe8f2; border:1px solid rgba(255,255,255,0.06); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #e6eef6; }
                QMenuBar { background: rgba(10,14,25,0.48); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(255,255,255,0.14); border-radius:12px; margin:4px 6px; }
                QMenuBar::item { padding:5px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(115,165,255,0.18); }
                QMenu { background: rgba(14,18,30,0.98); border:1px solid rgba(255,255,255,0.14); }
                """
            elif self.theme == "retro":
                css = """
                QMainWindow { background: #0f1a2d; }
                QLabel { color: #ecf4ff; }
                QFrame#gallery_frame { background: rgba(34,67,108,0.48); border-radius:16px; border:1px solid rgba(194,220,249,0.38); }
                QFrame#left_frame { background: rgba(30,60,98,0.50); border-radius:16px; border:1px solid rgba(194,220,249,0.34); }
                QFrame#right_frame { background: rgba(36,70,110,0.52); border-radius:16px; padding:8px; border:1px solid rgba(194,220,249,0.34); }
                QListWidget { background: rgba(26,52,86,0.62); border-radius:10px; color: #ecf4ff; border:1px solid rgba(194,220,249,0.30); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #ecf4ff; }
                QMenuBar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(51,104,164,0.86), stop:1 rgba(34,72,118,0.84)); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(207,228,252,0.46); border-radius:14px; margin:4px 6px; }
                QMenuBar::item { padding:6px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(194,220,249,0.22); }
                QMenu { background: rgba(31,61,98,0.97); border:1px solid rgba(194,220,249,0.40); border-radius:10px; padding:6px; }
                QMenu::item { border-radius:8px; padding:6px 12px; }
                QMenu::item:selected { background: rgba(194,220,249,0.24); }
                """
            elif self.theme == "cyberpunk 2077":
                css = """
                QMainWindow { background: #08080c; }
                QLabel { color: #fff2f4; }
                QFrame#gallery_frame { background: rgba(20,8,12,0.64); border-radius:16px; border:1px solid rgba(234,48,72,0.36); }
                QFrame#left_frame { background: rgba(16,8,12,0.66); border-radius:16px; border:1px solid rgba(234,48,72,0.30); }
                QFrame#right_frame { background: rgba(18,8,12,0.68); border-radius:16px; padding:8px; border:1px solid rgba(234,48,72,0.30); }
                QListWidget { background: rgba(12,8,12,0.76); border-radius:10px; color: #fff2f4; border:1px solid rgba(234,48,72,0.28); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #fff2f4; }
                QMenuBar { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(30,10,14,0.86), stop:1 rgba(92,16,24,0.86)); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(234,48,72,0.46); border-radius:14px; margin:4px 6px; }
                QMenuBar::item { padding:6px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(220,34,58,0.28); }
                QMenu { background: rgba(14,8,12,0.98); border:1px solid rgba(234,48,72,0.42); border-radius:10px; padding:6px; }
                QMenu::item { border-radius:8px; padding:6px 12px; }
                QMenu::item:selected { background: rgba(220,34,58,0.28); }
                """
            elif self.theme == "aphex twin":
                css = """
                QMainWindow { background: #090d12; }
                QLabel { color: #e9f0f7; }
                QFrame#gallery_frame { background: rgba(18,24,34,0.58); border-radius:16px; border:1px solid rgba(202,217,238,0.24); }
                QFrame#left_frame { background: rgba(14,20,30,0.60); border-radius:16px; border:1px solid rgba(202,217,238,0.20); }
                QFrame#right_frame { background: rgba(20,26,36,0.62); border-radius:16px; padding:8px; border:1px solid rgba(202,217,238,0.20); }
                QListWidget { background: rgba(12,18,27,0.72); border-radius:10px; color: #e9f0f7; border:1px solid rgba(202,217,238,0.18); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #e9f0f7; }
                QMenuBar { background: rgba(18,24,34,0.64); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(202,217,238,0.26); border-radius:14px; margin:4px 6px; }
                QMenuBar::item { padding:6px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(202,217,238,0.20); }
                QMenu { background: rgba(14,18,26,0.98); border:1px solid rgba(202,217,238,0.26); border-radius:10px; padding:6px; }
                QMenu::item { border-radius:8px; padding:6px 12px; }
                QMenu::item:selected { background: rgba(202,217,238,0.20); }
                """
            elif self.theme == "sketch":
                css = """
                QMainWindow { background: #0b0c0e; }
                QLabel { color: #f4f6f8; }
                QFrame#gallery_frame { background: rgba(245,245,245,0.08); border-radius:16px; border:1px solid rgba(255,255,255,0.22); }
                QFrame#left_frame { background: rgba(245,245,245,0.06); border-radius:16px; border:1px solid rgba(255,255,255,0.18); }
                QFrame#right_frame { background: rgba(245,245,245,0.08); border-radius:16px; padding:8px; border:1px solid rgba(255,255,255,0.20); }
                QListWidget { background: rgba(255,255,255,0.06); border-radius:10px; color: #f6f6f6; border:1px solid rgba(255,255,255,0.18); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #f4f4f4; }
                QMenuBar { background: rgba(255,255,255,0.08); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(255,255,255,0.22); border-radius:14px; margin:4px 6px; }
                QMenuBar::item { padding:6px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(255,255,255,0.16); }
                QMenu { background: rgba(10,10,10,0.96); border:1px solid rgba(255,255,255,0.24); border-radius:10px; padding:6px; }
                QMenu::item { border-radius:8px; padding:6px 12px; }
                QMenu::item:selected { background: rgba(255,255,255,0.16); }
                """
            elif self.theme == "dedsec":
                css = """
                QMainWindow { background: #060a08; }
                QLabel { color: #dcffe6; }
                QFrame#gallery_frame { background: rgba(8,16,10,0.70); border-radius:16px; border:1px solid rgba(88,255,138,0.36); }
                QFrame#left_frame { background: rgba(8,14,10,0.72); border-radius:16px; border:1px solid rgba(88,255,138,0.34); }
                QFrame#right_frame { background: rgba(6,12,8,0.78); border-radius:16px; padding:8px; border:1px solid rgba(88,255,138,0.34); }
                QListWidget { background: rgba(6,14,8,0.84); border-radius:10px; color: #dcffe6; border:1px solid rgba(88,255,138,0.34); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #dcffe6; }
                QMenuBar { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(8,16,10,0.86), stop:1 rgba(10,26,14,0.88)); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(88,255,138,0.44); border-radius:14px; margin:4px 6px; }
                QMenuBar::item { padding:6px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(44,180,92,0.28); }
                QMenu { background: rgba(6,12,8,0.98); border:1px solid rgba(88,255,138,0.42); border-radius:10px; padding:6px; }
                QMenu::item { border-radius:8px; padding:6px 12px; }
                QMenu::item:selected { background: rgba(44,180,92,0.30); }
                """
            elif self.theme == "custom":
                def _safe_hex(v, fb):
                    s = str(v or "").strip()
                    if len(s) == 7 and s.startswith("#"):
                        ok = True
                        for ch in s[1:]:
                            if ch not in "0123456789abcdefABCDEF":
                                ok = False
                                break
                        if ok:
                            return s
                    return str(fb)
                c_bg = _safe_hex(getattr(self, "custom_theme_bg", "#0c1018"), "#0c1018")
                c_fg = _safe_hex(getattr(self, "custom_theme_fg", "#e8f2ff"), "#e8f2ff")
                c_ac = _safe_hex(getattr(self, "custom_theme_accent", "#5ec8ff"), "#5ec8ff")
                c_panel = _safe_hex(getattr(self, "custom_theme_panel", "#151c29"), "#151c29")
                css = f"""
                QMainWindow {{ background: {c_bg}; }}
                QLabel {{ color: {c_fg}; }}
                QFrame#gallery_frame {{ background: {c_panel}; border-radius:16px; border:1px solid {c_ac}; }}
                QFrame#left_frame {{ background: {c_panel}; border-radius:16px; border:1px solid {c_ac}; }}
                QFrame#right_frame {{ background: {c_panel}; border-radius:16px; padding:8px; border:1px solid {c_ac}; }}
                QListWidget {{ background: rgba(0,0,0,0.30); border-radius:10px; color: {c_fg}; border:1px solid {c_ac}; }}
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu {{ color: {c_fg}; }}
                QMenuBar {{ background: rgba(0,0,0,0.36); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid {c_ac}; border-radius:14px; margin:4px 6px; }}
                QMenuBar::item {{ padding:6px 12px; border-radius:10px; margin:0 3px; }}
                QMenuBar::item:selected {{ background: rgba(255,255,255,0.16); }}
                QMenu {{ background: rgba(0,0,0,0.92); border:1px solid {c_ac}; border-radius:10px; padding:6px; }}
                QMenu::item {{ border-radius:8px; padding:6px 12px; }}
                QMenu::item:selected {{ background: rgba(255,255,255,0.18); }}
                """
            else:
                css = """
                QMainWindow { background: #0b101b; }
                QLabel { color: #e6eef6; }
                QFrame#gallery_frame { background: rgba(12,16,25,0.90); border-radius:14px; border:1px solid rgba(146,188,244,0.20); }
                QFrame#left_frame { background: rgba(12,16,25,0.90); border-radius:14px; border:1px solid rgba(146,188,244,0.20); }
                QFrame#right_frame { background: rgba(12,16,25,0.92); border-radius:14px; padding:8px; border:1px solid rgba(146,188,244,0.20); }
                QListWidget { background: rgba(12,16,24,0.92); border-radius:8px; color: #dfe8f2; border:1px solid rgba(146,188,244,0.18); }
                QComboBox, QSpinBox, QSlider, QCheckBox, QMenuBar, QMenu { color: #e6eef6; }
                QMenuBar { background: rgba(8,12,20,0.46); min-height:26px; font-size:12px; padding:3px 8px; border-bottom:1px solid rgba(255,255,255,0.12); border-radius:12px; margin:4px 6px; }
                QMenuBar::item { padding:5px 12px; border-radius:10px; margin:0 3px; }
                QMenuBar::item:selected { background: rgba(115,165,255,0.18); }
                QMenu { background: rgba(14,18,30,0.98); border:1px solid rgba(255,255,255,0.14); }
                """
            css += """
            QMenu { border-radius: 12px; padding: 6px; }
            QMenu::item { border-radius: 8px; padding: 6px 12px; margin: 2px 2px; }
            """
            self.setStyleSheet(css)
            btn_css = self._glass_btn_css()
            for b in self.findChildren(QPushButton):
                try:
                    if isinstance(b, VerticalTabButton):
                        continue
                    if b in getattr(self, "_info_buttons", []):
                        continue
                    b.setStyleSheet(btn_css)
                except Exception:
                    continue
            for b in getattr(self, "right_section_tabs", {}).values():
                try:
                    if isinstance(b, VerticalTabButton):
                        b.set_theme(self.theme)
                    else:
                        b.setStyleSheet(btn_css)
                except Exception:
                    pass
            self._refresh_button_icons()
            self._update_color_buttons_state()
            try:
                self.title_label.setStyleSheet(self._title_css())
            except Exception:
                pass
            try:
                self._title_brand = "ISCII STUDIO"
                if hasattr(self, "title_label"):
                    self.title_label.setText(self._ascii_title_text())
            except Exception:
                pass
            try:
                if hasattr(self, "right_scroll"):
                    self.right_scroll.setStyleSheet(self._scrollbar_css())
            except Exception:
                pass
            try:
                self._apply_combo_styles()
            except Exception:
                pass
            try:
                self._apply_input_styles()
            except Exception:
                pass
            try:
                self._show_right_section(getattr(self, "_active_right_section", "style"))
            except Exception:
                pass
            try:
                for line in self.findChildren(QFrame, "section_line"):
                    line.setStyleSheet(self._section_line_css())
            except Exception:
                pass
            try:
                if hasattr(self, "right_content"):
                    if self.theme == "light":
                        self.right_content.setStyleSheet("background: rgba(255,255,255,0.88); border-radius:16px;")
                    elif self.theme == "retro":
                        self.right_content.setStyleSheet("background: rgba(35,68,108,0.50); border-radius:16px;")
                    elif self.theme == "cyberpunk 2077":
                        self.right_content.setStyleSheet("background: rgba(18,8,12,0.60); border-radius:16px;")
                    elif self.theme == "aphex twin":
                        self.right_content.setStyleSheet("background: rgba(20,26,36,0.52); border-radius:16px;")
                    elif self.theme == "sketch":
                        self.right_content.setStyleSheet("background: rgba(255,255,255,0.06); border-radius:16px;")
                    elif self.theme == "dedsec":
                        self.right_content.setStyleSheet("background: rgba(8,16,10,0.66); border-radius:16px;")
                    elif self.theme == "custom":
                        self.right_content.setStyleSheet(f"background: {self.custom_theme_panel}; border-radius:16px;")
                    else:
                        self.right_content.setStyleSheet("background: rgba(20,20,20,0.28); border-radius:16px;")
                if hasattr(self, "right_tabs_rail"):
                    if self.theme == "light":
                        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(255,255,255,0.84); border:1px solid rgba(90,120,160,0.26); border-radius:14px;}")
                    elif self.theme == "retro":
                        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(42,80,125,0.62); border:1px solid rgba(194,220,249,0.42); border-radius:14px;}")
                    elif self.theme == "cyberpunk 2077":
                        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(18,8,12,0.68); border:1px solid rgba(234,48,72,0.38); border-radius:14px;}")
                    elif self.theme == "aphex twin":
                        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(18,24,34,0.56); border:1px solid rgba(202,217,238,0.32); border-radius:14px;}")
                    elif self.theme == "sketch":
                        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.24); border-radius:14px;}")
                    elif self.theme == "dedsec":
                        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(6,14,8,0.80); border:1px solid rgba(88,255,138,0.42); border-radius:14px;}")
                    elif self.theme == "custom":
                        self.right_tabs_rail.setStyleSheet(f"QFrame#right_tabs_rail{{background: {self.custom_theme_panel}; border:1px solid {self.custom_theme_accent}; border-radius:14px;}}")
                    else:
                        self.right_tabs_rail.setStyleSheet("QFrame#right_tabs_rail{background: rgba(18,24,38,0.42); border:1px solid rgba(150,200,255,0.20); border-radius:14px;}")
            except Exception:
                pass
            try:
                if hasattr(self, "right_footer") and self.right_footer is not None:
                    if self.theme == "light":
                        self.right_footer.setStyleSheet("QFrame#right_footer{background: rgba(255,255,255,0.92); border:1px solid #d8dde6; border-radius:12px;}")
                    elif self.theme == "retro":
                        self.right_footer.setStyleSheet("QFrame#right_footer{background: rgba(44,82,128,0.66); border:1px solid rgba(194,220,249,0.44); border-radius:12px;}")
                    elif self.theme == "cyberpunk 2077":
                        self.right_footer.setStyleSheet("QFrame#right_footer{background: rgba(18,8,12,0.74); border:1px solid rgba(234,48,72,0.36); border-radius:12px;}")
                    elif self.theme == "aphex twin":
                        self.right_footer.setStyleSheet("QFrame#right_footer{background: rgba(20,24,34,0.64); border:1px solid rgba(202,217,238,0.30); border-radius:12px;}")
                    elif self.theme == "dedsec":
                        self.right_footer.setStyleSheet("QFrame#right_footer{background: rgba(6,14,8,0.84); border:1px solid rgba(88,255,138,0.36); border-radius:12px;}")
                    elif self.theme == "custom":
                        self.right_footer.setStyleSheet(f"QFrame#right_footer{{background: {self.custom_theme_panel}; border:1px solid {self.custom_theme_accent}; border-radius:12px;}}")
                    else:
                        self.right_footer.setStyleSheet("QFrame#right_footer{background: rgba(14,18,30,0.55); border:1px solid rgba(150,190,255,0.22); border-radius:12px;}")
                if hasattr(self, "update_chip"):
                    if getattr(self, "update_available_info", None):
                        self.update_chip.setStyleSheet(self._update_chip_css("available"))
                    else:
                        self.update_chip.setStyleSheet(self._update_chip_css("idle"))
            except Exception:
                pass
            try:
                self._style_embedded_editor_host()
            except Exception:
                pass
        except Exception:
            pass
        try:
            if hasattr(self, "theme_combo"):
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentText(self.theme)
                self.theme_combo.blockSignals(False)
        except Exception:
            pass
        try:
            s = load_settings()
            s["theme"] = self.theme
            save_settings(s)
        except Exception:
            pass
        try:
            self._sync_perf_mode()
        except Exception:
            pass

    def _start_ui_animations(self):
        try:
            # Keep startup stable: avoid panel opacity effects that can leave UI transparent on some GPUs.
            QTimer.singleShot(80, self._ensure_main_panels_visible)
            QTimer.singleShot(340, self._ensure_main_panels_visible)
        except Exception:
            pass

    def _normalize_main_z_order(self):
        try:
            wg = getattr(self, "window_bg_label", None)
            lbg = getattr(self, "left_bg_label", None)
            rbg = getattr(self, "right_bg_label", None)
            to = getattr(self, "trail_overlay", None)
            gf = getattr(self, "gallery_frame", None)
            lf = getattr(self, "left_frame", None)
            rf = getattr(self, "right_frame", None)
            if wg is not None:
                wg.lower()
            if lbg is not None:
                lbg.lower()
            if rbg is not None:
                rbg.lower()
            if to is not None and not bool(getattr(self, "_embedded_editor_active", False)):
                try:
                    to.raise_()
                    if gf is not None:
                        to.stackUnder(gf)
                    if lf is not None:
                        to.stackUnder(lf)
                    if rf is not None:
                        to.stackUnder(rf)
                except Exception:
                    pass
            if gf is not None:
                gf.raise_()
            if lf is not None:
                lf.raise_()
            if rf is not None:
                rf.raise_()
        except Exception:
            pass

    def _ensure_main_panels_visible(self):
        try:
            if bool(getattr(self, "_embedded_editor_active", False)) or bool(getattr(self, "_preview_focus_mode", False)):
                return
            changed = False
            for wname in ("gallery_frame", "left_frame", "right_frame", "preview_label"):
                w = getattr(self, wname, None)
                if w is None:
                    continue
                try:
                    if not w.isVisible():
                        w.show()
                        changed = True
                except Exception:
                    pass
            try:
                pi = getattr(self, "preview_image", None)
                pv = getattr(self, "preview_video", None)
                if pi is not None and pv is not None and not pi.isVisible() and not pv.isVisible():
                    if str(getattr(self, "_preview_mode", "image") or "image").strip().lower() == "video" and bool(getattr(self, "current_path", None)):
                        pv.show()
                    else:
                        pi.show()
                    changed = True
            except Exception:
                pass
            try:
                if getattr(self, "trail_level", "med") != "off" and hasattr(self, "trail_overlay") and self.trail_overlay is not None and not self.trail_overlay.isVisible():
                    self.trail_overlay.show()
                    changed = True
            except Exception:
                pass
            if changed:
                self._trail_overlay_stack_dirty = True
                self._sync_trail_overlay_stack(force=True)
            self._normalize_main_z_order()
        except Exception:
            pass

    def _guard_main_visibility(self):
        try:
            if self.isHidden():
                return
            self._ensure_editor_state_consistency()
            if bool(getattr(self, "_embedded_editor_active", False)) or bool(getattr(self, "_preview_focus_mode", False)):
                return
            self._ensure_main_panels_visible()
        except Exception:
            pass

    def _track_ui_anim(self, anim):
        try:
            if anim is None:
                return
            self._ui_anims.append(anim)
            if len(self._ui_anims) > 24:
                del self._ui_anims[:-24]
            anim.finished.connect(lambda a=anim: self._ui_anims.remove(a) if a in self._ui_anims else None)
        except Exception:
            pass

    def _animate_button_click(self, btn):
        try:
            if btn is None:
                return
            eff = QGraphicsOpacityEffect(btn)
            btn.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(130)
            anim.setStartValue(0.90)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda b=btn: b.setGraphicsEffect(None))
            self._track_ui_anim(anim)
            anim.start()
        except Exception:
            pass

    def _attach_sounds(self, root):
        try:
            if not getattr(self, "_sound_mgr", None):
                return
            for b in root.findChildren(QAbstractButton):
                if getattr(b, "_sound_hooked", False):
                    continue
                b.clicked.connect(self._sound_mgr.play_click)
                b.clicked.connect(lambda *_ , w=b: self._animate_button_click(w))
                b._sound_hooked = True
            for cb in root.findChildren(QComboBox):
                if getattr(cb, "_sound_hooked", False):
                    continue
                cb.currentIndexChanged.connect(lambda *_: self._sound_mgr.play_click())
                cb._sound_hooked = True
            for sp in root.findChildren(QSpinBox):
                if getattr(sp, "_sound_hooked", False):
                    continue
                sp.valueChanged.connect(lambda *_: self._sound_mgr.play_click())
                sp._sound_hooked = True
            for s in root.findChildren(QSlider):
                if getattr(s, "_sound_hooked", False):
                    continue
                s.sliderPressed.connect(lambda s=s: self._sound_mgr.slider_press(s))
                s.sliderReleased.connect(lambda s=s: self._sound_mgr.slider_release(s))
                s.valueChanged.connect(lambda _, s=s: self._sound_mgr.slider_move(s))
                s._sound_hooked = True
        except Exception:
            pass

    def _init_ui_sounds(self):
        try:
            base = Path(__file__).parent / "sounds"
            click_dir = base / "clicks"
            open_dir = base / "open a window"
            close_dir = base / "close the window"
            zip_dir = base / "zipper"
            norm_root = base / "_normalized"

            def _normalize_wav(src: Path) -> str:
                try:
                    rel = src.relative_to(base)
                    out = norm_root / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
                        return str(out)
                    import wave
                    with wave.open(str(src), 'rb') as w:
                        params = w.getparams()
                        frames = w.readframes(w.getnframes())
                        sampwidth = int(w.getsampwidth())
                        channels = int(w.getnchannels())
                    if not frames:
                        return str(src)
                    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth)
                    if dtype is None:
                        return str(src)
                    arr = np.frombuffer(frames, dtype=dtype).astype(np.float32)
                    if arr.size == 0:
                        return str(src)
                    max_amp = float(np.max(np.abs(arr)))
                    if max_amp <= 0.0:
                        return str(src)
                    peak = float(np.iinfo(dtype).max)
                    target = peak * 0.80
                    gain = min(8.0, target / max_amp)
                    arr = np.clip(arr * gain, np.iinfo(dtype).min, np.iinfo(dtype).max).astype(dtype)
                    frames2 = arr.tobytes()
                    with wave.open(str(out), 'wb') as o:
                        o.setparams(params)
                        o.writeframes(frames2)
                    return str(out)
                except Exception:
                    return str(src)

            def _collect(dir_path: Path):
                if not dir_path.exists():
                    return []
                return [str(_normalize_wav(p)) for p in sorted(dir_path.glob("*.wav"))]

            click_files = _collect(click_dir)
            open_files = _collect(open_dir)
            close_files = _collect(close_dir)
            slider_files = _collect(zip_dir)
            slider_path = slider_files[0] if slider_files else None
            self._sound_mgr = UISoundManager(self, click_files, slider_path, open_files, close_files)
            self._attach_sounds(self)
        except Exception:
            self._sound_mgr = None

    def _apply_translations(self):
        t = TRANSLATIONS[self.lang]
        try:
            self._title_brand = "ISCII STUDIO"
            if hasattr(self, "title_label"):
                self.title_label.setText(self._ascii_title_text())
            self.load_btn.setText(t["load"])
            if hasattr(self, "gallery_load_btn"):
                self.gallery_load_btn.setText(t["load"])
            if hasattr(self, "gallery_editor_btn"):
                self.gallery_editor_btn.setText(t.get("editor", "Editor"))
            self._sync_compact_button_sizes()
            self.render_btn.setText(t["render"])
            self.export_btn.setText(t["export"])
            self.pick_text_btn.setText(t["text_color"])
            self.pick_bg_btn.setText(t["bg_color"])
            self.invert_chk.setText(t.get("invert", self.invert_chk.text()))
            self.keep_size_chk.setText(t.get("keep_size", self.keep_size_chk.text()))
            self.fps_label.setText(t.get("fps", self.fps_label.text()))
            self.gamma_label.setText(t.get("gamma", self.gamma_label.text()))
            self.denoise_chk.setText(t.get("denoise", self.denoise_chk.text()))
            self.sharpen_chk.setText(t.get("sharpen", self.sharpen_chk.text()))
            self.edge_chk.setText(t.get("edge_boost", self.edge_chk.text()))
            self.gallery_title.setText(t.get("gallery", self.gallery_title.text()))
            self.gallery_empty.setText(t.get("gallery_empty", self.gallery_empty.text()))
            self.preview_title.setText(t.get("preview", self.preview_title.text()))
            self.cpu_label.setText(t.get("cpu_load", self.cpu_label.text()))
            self.scale_label.setText(t.get("scale", self.scale_label.text()) if hasattr(self, "scale_label") else "Scale")
            self.out_label.setText(t.get("output_size", self.out_label.text()) if hasattr(self, "out_label") else "Output (W x H)")
            self.defaults_btn.setText(t.get("defaults", self.defaults_btn.text()))
            if hasattr(self, "fx_defaults_btn"):
                self.fx_defaults_btn.setText(t.get("defaults", self.fx_defaults_btn.text()))
            if hasattr(self, "pro_defaults_btn"):
                self.pro_defaults_btn.setText(t.get("defaults", self.pro_defaults_btn.text()))
            if hasattr(self, "render_defaults_btn"):
                self.render_defaults_btn.setText(t.get("defaults", self.render_defaults_btn.text()))
            self.auto_size_chk.setText(t.get("auto_size", self.auto_size_chk.text()))
            self.preview_open_btn.setText(t.get("player_focus_exit", "Exit focus") if self._preview_focus_mode else t.get("player_focus", "Focus mode"))
            self.defaults_btn.setToolTip(t.get("defaults", self.defaults_btn.toolTip()))
            self.auto_size_chk.setToolTip(t.get("auto_size", self.auto_size_chk.toolTip()))
            self._apply_tooltips(t)
        except Exception:
            pass
        # update other labels
        try:
            self.style_label.setText(t.get("style", self.style_label.text()))
            self.width_label.setText(t.get("width", self.width_label.text()))
            self.font_label.setText(t.get("font", self.font_label.text()))
            if hasattr(self, "charset_label"):
                self.charset_label.setText(t.get("charset", self.charset_label.text()))
            if hasattr(self, "contrast_label"):
                self.contrast_label.setText(t.get("contrast", self.contrast_label.text()))
            self.trail_label.setText(t.get("trail", self.trail_label.text()))
            try:
                for h, d, k1, k2, f1, f2 in getattr(self, "_section_labels", []):
                    h.setText(t.get(k1, f1))
                    d.setText(t.get(k2, f2))
            except Exception:
                pass
            try:
                if hasattr(self, "right_section_tabs"):
                    if "style" in self.right_section_tabs:
                        self.right_section_tabs["style"].setText(t.get("section_style", "STYLE"))
                    if "fx" in self.right_section_tabs:
                        self.right_section_tabs["fx"].setText(t.get("section_fx", "IMAGE FX"))
                    if "pro" in self.right_section_tabs:
                        self.right_section_tabs["pro"].setText(t.get("section_pro", "PRO TOOLS"))
                    if "render" in self.right_section_tabs:
                        self.right_section_tabs["render"].setText(t.get("section_render", "RENDER"))
            except Exception:
                pass
            try:
                self.bitrate_label.setText(t.get("bitrate", self.bitrate_label.text()))
                self.threads_label.setText(t.get("cpu_threads", self.threads_label.text()))
                self.preset_label.setText(t.get("preset", self.preset_label.text()))
                self.crf_label.setText(t.get("crf", self.crf_label.text()))
                if hasattr(self, "keep_audio_chk"):
                    self.keep_audio_chk.setText(t.get("keep_source_audio", self.keep_audio_chk.text()))
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setText(t.get("pro_scanlines", self.pro_scanlines_chk.text()))
                if hasattr(self, "pro_bloom_label"):
                    self.pro_bloom_label.setText(t.get("pro_bloom", self.pro_bloom_label.text()))
                if hasattr(self, "pro_vignette_label"):
                    self.pro_vignette_label.setText(t.get("pro_vignette", self.pro_vignette_label.text()))
                if hasattr(self, "pro_poster_label"):
                    self.pro_poster_label.setText(t.get("pro_poster_bits", self.pro_poster_label.text()))
                if hasattr(self, "pro_grain_label"):
                    self.pro_grain_label.setText(t.get("pro_grain", self.pro_grain_label.text()))
                if hasattr(self, "pro_chroma_label"):
                    self.pro_chroma_label.setText(t.get("pro_chroma", self.pro_chroma_label.text()))
                if hasattr(self, "pro_color_boost_label"):
                    self.pro_color_boost_label.setText(t.get("pro_color_boost", self.pro_color_boost_label.text()))
                if hasattr(self, "pro_clarity_label"):
                    self.pro_clarity_label.setText(t.get("pro_clarity", self.pro_clarity_label.text()))
                if hasattr(self, "pro_motion_blur_label"):
                    self.pro_motion_blur_label.setText(t.get("pro_motion_blur", self.pro_motion_blur_label.text()))
                if hasattr(self, "pro_scan_strength_label"):
                    self.pro_scan_strength_label.setText(t.get("pro_scan_strength", self.pro_scan_strength_label.text()))
                if hasattr(self, "pro_scan_step_label"):
                    self.pro_scan_step_label.setText(t.get("pro_scan_step", self.pro_scan_step_label.text()))
                if hasattr(self, "pro_curvature_label"):
                    self.pro_curvature_label.setText(t.get("pro_curvature", self.pro_curvature_label.text()))
                if hasattr(self, "pro_concavity_label"):
                    self.pro_concavity_label.setText(t.get("pro_concavity", self.pro_concavity_label.text()))
                if hasattr(self, "pro_curvature_center_x_label"):
                    self.pro_curvature_center_x_label.setText(t.get("pro_curvature_center_x", self.pro_curvature_center_x_label.text()))
                if hasattr(self, "pro_curvature_expand_label"):
                    self.pro_curvature_expand_label.setText(t.get("pro_curvature_expand", self.pro_curvature_expand_label.text()))
                if hasattr(self, "pro_curvature_type_label"):
                    self.pro_curvature_type_label.setText(t.get("pro_curvature_type", self.pro_curvature_type_label.text()))
                if hasattr(self, "pro_ribbing_label"):
                    self.pro_ribbing_label.setText(t.get("pro_ribbing", self.pro_ribbing_label.text()))
                if hasattr(self, "pro_glitch_label"):
                    self.pro_glitch_label.setText(t.get("pro_glitch", self.pro_glitch_label.text()))
                if hasattr(self, "pro_glitch_density_label"):
                    self.pro_glitch_density_label.setText(t.get("pro_glitch_density", self.pro_glitch_density_label.text()))
                if hasattr(self, "pro_glitch_shift_label"):
                    self.pro_glitch_shift_label.setText(t.get("pro_glitch_shift", self.pro_glitch_shift_label.text()))
                if hasattr(self, "pro_glitch_rgb_label"):
                    self.pro_glitch_rgb_label.setText(t.get("pro_glitch_rgb", self.pro_glitch_rgb_label.text()))
                if hasattr(self, "pro_glitch_block_label"):
                    self.pro_glitch_block_label.setText(t.get("pro_glitch_block", self.pro_glitch_block_label.text()))
                if hasattr(self, "pro_glitch_jitter_label"):
                    self.pro_glitch_jitter_label.setText(t.get("pro_glitch_jitter", self.pro_glitch_jitter_label.text()))
                if hasattr(self, "pro_glitch_noise_label"):
                    self.pro_glitch_noise_label.setText(t.get("pro_glitch_noise", self.pro_glitch_noise_label.text()))
                if hasattr(self, "pro_preset_label"):
                    self.pro_preset_label.setText(t.get("preset", self.pro_preset_label.text()))
                if hasattr(self, "player_play_btn"):
                    self.player_play_btn.setText(t.get("play", self.player_play_btn.text()))
                if hasattr(self, "player_stop_btn"):
                    self.player_stop_btn.setText(t.get("stop", self.player_stop_btn.text()))
                if hasattr(self, "player_repeat_btn"):
                    self.player_repeat_btn.setText(t.get("repeat_loop", self.player_repeat_btn.text()) if self._preview_loop else t.get("repeat_once", self.player_repeat_btn.text()))
                if hasattr(self, "player_fullscreen_btn"):
                    self.player_fullscreen_btn.setText(t.get("player_focus_exit", "Exit focus") if self._preview_focus_mode else t.get("player_focus", "Focus mode"))
                if hasattr(self, "player_volume_label"):
                    self.player_volume_label.setText(t.get("volume", self.player_volume_label.text()))
                if hasattr(self, "player_speed_label"):
                    self.player_speed_label.setText(t.get("player_speed", self.player_speed_label.text()))
            except Exception:
                pass
            # device label may be located in settings dialog; guard
            try:
                self.device_label.setText(t.get("device", self.device_label.text()))
            except Exception:
                pass
            # theme label
            try:
                self.theme_label.setText(t.get('theme', self.theme_label.text()))
            except Exception:
                pass
            try:
                if hasattr(self, "watermark_chk"):
                    self.watermark_chk.setText(t.get("watermark", self.watermark_chk.text()))
                if hasattr(self, "watermark_text_edit"):
                    self.watermark_text_edit.setPlaceholderText(t.get("watermark_text", "Watermark text"))
                if hasattr(self, "save_preset_btn"):
                    self.save_preset_btn.setText(t.get("save_preset", self.save_preset_btn.text()))
                if hasattr(self, "load_preset_btn"):
                    self.load_preset_btn.setText(t.get("load_preset", self.load_preset_btn.text()))
            except Exception:
                pass
            try:
                if hasattr(self, "_embedded_editor_header") and self._embedded_editor_header is not None:
                    self._embedded_editor_header.setText(t.get("editor", "Editor"))
                if hasattr(self, "_embedded_editor_full_btn") and self._embedded_editor_full_btn is not None:
                    self._embedded_editor_full_btn.setText(
                        t.get("editor_fullscreen_exit", "Exit fullscreen editor")
                        if bool(getattr(self, "_embedded_editor_full", False))
                        else t.get("editor_fullscreen", "Fullscreen editor")
                    )
            except Exception:
                pass
            self.settings_btn.setText(t.get("settings", self.settings_btn.text()))
            if hasattr(self, "theme_label"):
                self.theme_label.setText(t.get("theme", self.theme_label.text()))
            # update trail combo labels and selection
            current_key = self.trail_level
            self.trail_combo.blockSignals(True)
            self.trail_combo.clear()
            self.trail_combo.addItems([t["off"], t["low"], t["med"], t["high"]])
            map_key = {"off": t["off"], "low": t["low"], "med": t["med"], "high": t["high"]}
            self.trail_combo.setCurrentText(map_key.get(current_key, t["med"]))
            self.trail_combo.blockSignals(False)
            self._schedule_preset_preview_update()
        except Exception:
            pass
        try:
            self._update_style_help()
            self._update_codec_help()
            self._update_pro_preset_help()
            self._update_ascii_controls_visibility()
        except Exception:
            pass
        # update menu texts if built
        try:
            if hasattr(self, 'file_menu'):
                self.file_menu.setTitle(TRANSLATIONS[self.lang].get("file", "File"))
                self.action_load.setText(TRANSLATIONS[self.lang].get("load", "Load"))
                self.action_export.setText(TRANSLATIONS[self.lang].get("export", "Export"))
                self.action_settings.setText(TRANSLATIONS[self.lang].get("settings", "Settings"))
                if hasattr(self, "action_check_updates"):
                    self.action_check_updates.setText(TRANSLATIONS[self.lang].get("menu_check_updates", "Check for updates"))
            if hasattr(self, "edit_menu"):
                self.edit_menu.setTitle(TRANSLATIONS[self.lang].get("edit", "Edit"))
                self.action_undo_menu.setText(TRANSLATIONS[self.lang].get("undo", "Undo"))
                self.action_redo_menu.setText(TRANSLATIONS[self.lang].get("redo", "Redo"))
            if hasattr(self, "help_menu"):
                self.help_menu.setTitle(TRANSLATIONS[self.lang].get("help", "Help"))
                self.action_help.setText(TRANSLATIONS[self.lang].get("help_open", "Open help"))
            if hasattr(self, "tools_menu"):
                self.tools_menu.setTitle(TRANSLATIONS[self.lang].get("tools", "Tools"))
                self.tools_invert.setText(TRANSLATIONS[self.lang].get("tool_invert", self.tools_invert.text()))
                self.tools_edges.setText(TRANSLATIONS[self.lang].get("tool_edges", self.tools_edges.text()))
                self.tools_sharp.setText(TRANSLATIONS[self.lang].get("tool_sharpen", self.tools_sharp.text()))
                if hasattr(self, "tools_hybrid_runtime"):
                    self.tools_hybrid_runtime.setText(self._i3("Гибридный UI (QML/C++)", "Hybrid UI (QML/C++)", "混合 UI (QML/C++)"))
            if hasattr(self, "pro_menu"):
                self.pro_menu.menuAction().setVisible(bool(self.pro_tools))
                self.pro_menu.setTitle(TRANSLATIONS[self.lang].get("pro_menu", "Pro Tools"))
                self.pro_action_posterize.setText(TRANSLATIONS[self.lang].get("tool_posterize", self.pro_action_posterize.text()))
                self.pro_action_mirror.setText(TRANSLATIONS[self.lang].get("tool_mirror", self.pro_action_mirror.text()))
                if hasattr(self, "pro_action_bloom"):
                    self.pro_action_bloom.setText(TRANSLATIONS[self.lang].get("tool_bloom", self.pro_action_bloom.text()))
                if hasattr(self, "pro_action_vignette"):
                    self.pro_action_vignette.setText(TRANSLATIONS[self.lang].get("tool_vignette", self.pro_action_vignette.text()))
                if hasattr(self, "pro_action_scan"):
                    self.pro_action_scan.setText(TRANSLATIONS[self.lang].get("tool_scanlines", self.pro_action_scan.text()))
                if hasattr(self, "pro_action_grain"):
                    self.pro_action_grain.setText(TRANSLATIONS[self.lang].get("tool_grain", self.pro_action_grain.text()))
                if hasattr(self, "pro_action_chroma"):
                    self.pro_action_chroma.setText(TRANSLATIONS[self.lang].get("tool_chroma", self.pro_action_chroma.text()))
                if hasattr(self, "pro_action_glitch"):
                    self.pro_action_glitch.setText(TRANSLATIONS[self.lang].get("tool_glitch", self.pro_action_glitch.text()))
                if hasattr(self, "pro_toggle_scan"):
                    self.pro_toggle_scan.setText(TRANSLATIONS[self.lang].get("pro_scanlines", self.pro_toggle_scan.text()))
                if hasattr(self, "pro_toggle_bloom"):
                    self.pro_toggle_bloom.setText(TRANSLATIONS[self.lang].get("tool_bloom", self.pro_toggle_bloom.text()))
                if hasattr(self, "pro_toggle_vignette"):
                    self.pro_toggle_vignette.setText(TRANSLATIONS[self.lang].get("tool_vignette", self.pro_toggle_vignette.text()))
                if hasattr(self, "pro_preset_soft"):
                    self.pro_preset_soft.setText("Preset: Soft")
                if hasattr(self, "pro_preset_cyber"):
                    self.pro_preset_cyber.setText("Preset: Cyber")
                if hasattr(self, "pro_preset_retro"):
                    self.pro_preset_retro.setText("Preset: Retro")
                if hasattr(self, "pro_preset_vhs"):
                    self.pro_preset_vhs.setText("Preset: VHS")
                if hasattr(self, "pro_reset"):
                    self.pro_reset.setText("Reset Pro Tools")
            if hasattr(self, "pro_options_frame"):
                self.pro_options_frame.setVisible(bool(self.pro_tools))
            for w in getattr(self, "_pro_section_widgets", []) or []:
                w.setVisible(bool(self.pro_tools))
            if hasattr(self, "_pro_tool_buttons"):
                for k, b in self._pro_tool_buttons.items():
                    b.setText(TRANSLATIONS[self.lang].get(k, b.text()))
            self._sync_pro_menu_state()
            self._show_right_section(getattr(self, "_active_right_section", "style"))
            self._apply_combo_styles()
            if hasattr(self, "update_install_btn"):
                self.update_install_btn.setText(t.get("update_install", "Install"))
            if hasattr(self, "update_later_btn"):
                self.update_later_btn.setText(t.get("update_later", "Later"))
        except Exception:
            pass

    def _start_background_animation(self):
        w = max(1200, self.width()); h = max(800, self.height())
        self.bg_base = Image.new("RGB", (w,h), "#0e1117")
        self._update_background()

    def _fit_button_text(self, btn, min_w=86, pad=30, max_w=None):
        try:
            if btn is None:
                return
            txt = str(btn.text() or "").strip()
            fm = btn.fontMetrics()
            width = int(fm.horizontalAdvance((txt + "  ") if txt else "  ")) + int(pad)
            try:
                ico = btn.icon()
                if ico is not None and (not ico.isNull()):
                    width += 18
            except Exception:
                pass
            width = max(int(min_w), int(width))
            if max_w is not None:
                width = min(int(width), int(max_w))
            btn.setMinimumWidth(int(width))
            if max_w is not None:
                btn.setMaximumWidth(int(max_w))
        except Exception:
            pass

    def _sync_compact_button_sizes(self):
        try:
            gl = getattr(self, "gallery_load_btn", None)
            ge = getattr(self, "gallery_editor_btn", None)
            if gl is not None and ge is not None:
                gl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                ge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                compact_css = self._glass_btn_css() + "QPushButton{padding:4px 8px; border-radius:10px; font-weight:600;}"
                gl.setStyleSheet(compact_css)
                ge.setStyleSheet(compact_css)
                self._fit_button_text(gl, min_w=74, pad=18, max_w=112)
                self._fit_button_text(ge, min_w=74, pad=18, max_w=112)
                gf = getattr(self, "gallery_frame", None)
                gw = int(gf.width() if gf is not None else 250)
                title_w = int(getattr(self, "gallery_title", None).sizeHint().width()) if getattr(self, "gallery_title", None) is not None else 42
                avail = max(112, int(gw - title_w - 34))
                target_each = max(66, min(108, int((avail - 6) // 2)))
                w1 = min(int(gl.minimumWidth()), int(target_each))
                w2 = min(int(ge.minimumWidth()), int(target_each))
                gl.setMinimumWidth(int(w1)); gl.setMaximumWidth(int(w1))
                ge.setMinimumWidth(int(w2)); ge.setMaximumWidth(int(w2))
            self._fit_button_text(getattr(self, "load_btn", None), min_w=94, pad=26, max_w=148)
        except Exception:
            pass

    def _adapt_right_panel_width(self):
        try:
            rf = getattr(self, "right_frame", None)
            if rf is None:
                return
            cw = self.centralWidget()
            ww = int((cw.width() if cw is not None else self.width()) or self.width() or 980)
            gallery_w = int(getattr(self, "gallery_frame", None).width()) if getattr(self, "gallery_frame", None) is not None else 240
            left_floor = 300
            lf = getattr(self, "left_frame", None)
            if lf is not None:
                left_floor = max(260, min(420, int(lf.minimumWidth() or lf.width() or 320)))
            chrome = 38
            max_by_layout = int(ww - gallery_w - left_floor - chrome)
            target = int(round(ww * 0.42))
            target = max(320, min(1220, target))
            if target > max_by_layout:
                target = max(280, int(max_by_layout))
            if int(rf.width()) != int(target):
                rf.setFixedWidth(int(target))
            self._sync_compact_button_sizes()
        except Exception:
            pass

    def _ensure_editor_state_consistency(self):
        try:
            if not bool(getattr(self, "_embedded_editor_active", False)):
                return
            fr = getattr(self, "_embedded_editor_frame", None)
            ed = getattr(self, "_embedded_editor_widget", None)
            frame_visible = bool(fr is not None and fr.isVisible())
            if frame_visible and ed is not None:
                return
            self._embedded_editor_active = False
            self._embedded_editor_opening = False
            for wname in ("gallery_frame", "left_frame", "right_frame"):
                w = getattr(self, wname, None)
                if w is not None:
                    w.setVisible(True)
            if hasattr(self, "trail_overlay") and self.trail_overlay is not None:
                self.trail_overlay.show()
            self._trail_overlay_stack_dirty = True
            self._sync_trail_overlay_stack(force=True)
        except Exception:
            pass

    def resizeEvent(self, ev):
        # ensure overlay covers whole window and panel backgrounds update on resize
        try:
            self._ensure_editor_state_consistency()
            self._sync_perf_mode()
            self._adapt_right_panel_width()
            self._sync_compact_button_sizes()
            if hasattr(self, 'trail_overlay') and self.trail_overlay is not None:
                self.trail_overlay.setGeometry(0, 0, self.width(), self.height())
                self._trail_overlay_stack_dirty = True
            # ensure bg label covers central area
            try:
                cw = self.centralWidget()
                if hasattr(self, 'window_bg_label') and self.window_bg_label is not None and cw is not None:
                    self.window_bg_label.setGeometry(cw.rect())
            except Exception:
                pass
            # update panel crops less often but keep them consistent
            self._update_panel_backgrounds()
            if hasattr(self, "_preview_base_pil") and self._preview_base_pil is not None:
                self._render_preview_scaled()
            try:
                if self._preview_mode in ("video", "gif"):
                    self._schedule_preview_media_transform(0)
                self._layout_preview_controls()
            except Exception:
                pass
            try:
                if hasattr(self, "right_content") and self.right_content is not None:
                    rf = self.findChild(QFrame, "right_frame")
                    if rf:
                        self.right_content.setGeometry(6, 6, rf.width() - 12, rf.height() - 12)
                self._layout_preview_controls()
            except Exception:
                pass
            try:
                if hasattr(self, "_tour_overlay") and self._tour_overlay is not None:
                    self._tour_overlay.setGeometry(self.rect())
                    self._tour_overlay._render()
                if hasattr(self, "_tour_panel") and self._tour_panel is not None:
                    self._tour_panel._render()
            except Exception:
                pass
            try:
                self._schedule_preset_preview_update()
            except Exception:
                pass
            try:
                if self._embedded_editor_frame is not None and self._embedded_editor_frame.isVisible():
                    self._layout_embedded_editor_host()
            except Exception:
                pass
            try:
                if self._embedded_editor_frame is not None and self._embedded_editor_frame.isVisible():
                    self._embedded_editor_frame.raise_()
                else:
                    self._sync_trail_overlay_stack()
                    self._normalize_main_z_order()
            except Exception:
                pass
        except Exception:
            pass
        return super().resizeEvent(ev)

    def showEvent(self, ev):
        # force a layout refresh on first show to avoid broken windowed layout
        try:
            self._ensure_editor_state_consistency()
            self._adapt_right_panel_width()
            self._apply_theme(self.theme)
            self._update_panel_backgrounds()
            self._render_preview_scaled()
            self._layout_preview_controls()
            QTimer.singleShot(120, self._ensure_main_panels_visible)
            QTimer.singleShot(240, self._guard_main_visibility)
            QTimer.singleShot(520, self._guard_main_visibility)
            QTimer.singleShot(160, self._normalize_main_z_order)
            if not self._welcome_checked:
                self._welcome_checked = True
                QTimer.singleShot(120, self._maybe_show_welcome)
        except Exception:
            pass
        return super().showEvent(ev)

    def changeEvent(self, ev):
        try:
            if ev.type() == QEvent.Type.WindowStateChange:
                QTimer.singleShot(0, self._post_layout_fix)
        except Exception:
            pass
        return super().changeEvent(ev)

    def _post_layout_fix(self):
        try:
            self._update_panel_backgrounds()
            if hasattr(self, "_preview_base_pil") and self._preview_base_pil is not None:
                self._render_preview_scaled()
            elif self._preview_mode in ("video", "gif"):
                self._schedule_preview_media_transform(0)
            try:
                if hasattr(self, "right_scroll") and self.right_scroll:
                    self.right_scroll.updateGeometry()
            except Exception:
                pass
            try:
                self._trail_overlay_stack_dirty = True
                self._sync_trail_overlay_stack()
            except Exception:
                pass
        except Exception:
            pass

    def _sync_perf_mode(self):
        try:
            eco = bool(getattr(self, "_eco_background", True))
            if bool(getattr(self, "_embedded_editor_active", False)):
                self.bg_anim_timer.setInterval(1900 if eco else 1300)
                self.trail_timer.setInterval(340 if eco else 260)
                self.cursor_sample_timer.setInterval(220 if eco else 170)
                return
            full = bool(self.isFullScreen())
            if full == self._last_win_state_full:
                # still allow theme-based cadence updates
                pass
            self._last_win_state_full = full
            sketch = getattr(self, "theme", "dark") == "sketch"
            if full:
                if eco:
                    self.bg_anim_timer.setInterval(1700 if sketch else 1500)
                    self.trail_timer.setInterval(300 if sketch else 260)
                    self.cursor_sample_timer.setInterval(160 if sketch else 140)
                else:
                    self.bg_anim_timer.setInterval(1100 if sketch else 980)
                    self.trail_timer.setInterval(156 if sketch else 138)
                    self.cursor_sample_timer.setInterval(92 if sketch else 84)
            else:
                if eco:
                    self.bg_anim_timer.setInterval(1200 if sketch else 1000)
                    self.trail_timer.setInterval(190 if sketch else 170)
                    self.cursor_sample_timer.setInterval(120 if sketch else 105)
                else:
                    self.bg_anim_timer.setInterval(520 if sketch else 460)
                    self.trail_timer.setInterval(98 if sketch else 86)
                    self.cursor_sample_timer.setInterval(62 if sketch else 56)
            try:
                bg_mode, _ = self._custom_bg_mode() if str(getattr(self, "theme", "") or "").strip().lower() == "custom" else ("", "")
                if bg_mode in ("video", "gif"):
                    self.bg_anim_timer.setInterval(42 if full else 34)
                elif bg_mode == "image":
                    self.bg_anim_timer.setInterval(min(int(self.bg_anim_timer.interval() or 1000), 260 if full else 180))
            except Exception:
                pass
            if str(getattr(self, "trail_level", "med")) == "off":
                if hasattr(self, "trail_timer") and self.trail_timer.isActive():
                    self.trail_timer.stop()
                if hasattr(self, "cursor_sample_timer") and self.cursor_sample_timer.isActive():
                    self.cursor_sample_timer.stop()
            else:
                if hasattr(self, "trail_timer") and not self.trail_timer.isActive():
                    self.trail_timer.start()
                if hasattr(self, "cursor_sample_timer") and not self.cursor_sample_timer.isActive():
                    self.cursor_sample_timer.start()
        except Exception:
            pass

    def _hex_to_rgb(self, value, fallback=(24, 30, 44)):
        try:
            s = str(value or "").strip()
            if s.startswith("#") and len(s) == 7:
                return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))
        except Exception:
            pass
        return tuple(int(x) for x in fallback)

    def _fit_cover(self, pil, w, h):
        try:
            sw, sh = pil.size
            if sw <= 0 or sh <= 0:
                return pil.resize((w, h), Image.Resampling.LANCZOS)
            k = max(float(w) / float(sw), float(h) / float(sh))
            nw = max(1, int(sw * k))
            nh = max(1, int(sh * k))
            im = pil.resize((nw, nh), Image.Resampling.LANCZOS)
            x = max(0, (nw - w) // 2)
            y = max(0, (nh - h) // 2)
            return im.crop((x, y, x + w, y + h))
        except Exception:
            return pil.resize((w, h), Image.Resampling.LANCZOS)

    def _apply_theme_pattern(self, im, theme_name):
        try:
            w, h = im.size
            if w < 16 or h < 16:
                return im
            dr = ImageDraw.Draw(im, "RGBA")
            t = str(theme_name or "").strip().lower()
            if t == "retro":
                step = max(2, int(h / 44))
                for y in range(0, h, step):
                    dr.line((0, y, w, y), fill=(14, 24, 26, 24), width=1)
            elif t == "cyberpunk 2077":
                step = max(18, int(w / 14))
                for x in range(-h, w + h, step):
                    dr.line((x, 0, x + h, h), fill=(255, 56, 98, 24), width=1)
                for y in range(0, h, max(26, int(h / 11))):
                    dr.line((0, y, w, y), fill=(62, 18, 24, 18), width=1)
            elif t == "aphex twin":
                step = max(14, int(min(w, h) / 10))
                cx, cy = w // 2, h // 2
                for r in range(step, int(min(w, h) * 0.6), step):
                    dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(112, 146, 188, 16), width=1)
            elif t == "dedsec":
                gx = max(16, int(w / 16))
                gy = max(14, int(h / 14))
                for x in range(0, w, gx):
                    dr.line((x, 0, x, h), fill=(78, 224, 130, 16), width=1)
                for y in range(0, h, gy):
                    dr.line((0, y, w, y), fill=(58, 166, 98, 14), width=1)
            elif t == "midnight":
                for i in range(max(10, int((w * h) / 18000))):
                    x = int((i * 97 + 53) % w)
                    y = int((i * 61 + 31) % h)
                    dr.point((x, y), fill=(186, 210, 255, 22))
            elif t == "solarized":
                for y in range(0, h, max(20, int(h / 10))):
                    dr.line((0, y, w, y), fill=(132, 128, 74, 10), width=1)
            elif t == "light":
                for x in range(0, w, max(20, int(w / 12))):
                    dr.line((x, 0, x, h), fill=(124, 140, 168, 10), width=1)
        except Exception:
            return im
        return im

    def _custom_bg_mode(self):
        path = str(getattr(self, "custom_theme_background", "") or "").strip()
        if not path or (not os.path.exists(path)):
            return "", ""
        low = path.lower()
        if low.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
            return "image", path
        if low.endswith(".gif"):
            return "gif", path
        if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            return "video", path
        return "", path

    def _custom_background_frame(self, w, h):
        mode, path = self._custom_bg_mode()
        if not mode or not path:
            return None
        try:
            if mode == "image":
                with Image.open(path) as im:
                    return self._fit_cover(im.convert("RGB"), w, h)
            if mode == "gif":
                now = time.time()
                if str(getattr(self, "_custom_bg_gif_path", "")) != path:
                    self._custom_bg_gif_path = path
                    self._custom_bg_gif_start_ts = now
                    self._custom_bg_gif_bucket = -1
                    self._custom_bg_gif_frame = None
                bucket = int(max(0.0, (now - float(getattr(self, "_custom_bg_gif_start_ts", now))) * 1000.0) // 70)
                if int(getattr(self, "_custom_bg_gif_bucket", -2)) == int(bucket):
                    fr = getattr(self, "_custom_bg_gif_frame", None)
                    if isinstance(fr, Image.Image):
                        return self._fit_cover(fr.copy(), w, h)
                with Image.open(path) as im:
                    n = max(1, int(getattr(im, "n_frames", 1) or 1))
                    idx = int(bucket % n)
                    im.seek(idx)
                    fr = im.convert("RGB")
                    self._custom_bg_gif_bucket = int(bucket)
                    self._custom_bg_gif_frame = fr.copy()
                    return self._fit_cover(fr, w, h)
            if mode == "video":
                cap = getattr(self, "_custom_bg_video_cap", None)
                if cap is None or str(getattr(self, "_custom_bg_video_path", "")) != path:
                    try:
                        if cap is not None:
                            cap.release()
                    except Exception:
                        pass
                    cap = cv2.VideoCapture(path)
                    self._custom_bg_video_cap = cap
                    self._custom_bg_video_path = path
                    self._custom_bg_video_start_ts = float(time.time())
                    self._custom_bg_video_cur_idx = -1
                    self._custom_bg_video_last_pil = None
                    try:
                        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                    except Exception:
                        fps = 0.0
                    self._custom_bg_video_fps = max(1.0, min(60.0, fps if fps > 0 else 24.0))
                    try:
                        self._custom_bg_video_frames = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
                    except Exception:
                        self._custom_bg_video_frames = 0
                if cap is None or (not cap.isOpened()):
                    fr = getattr(self, "_custom_bg_video_last_pil", None)
                    return self._fit_cover(fr.copy(), w, h) if isinstance(fr, Image.Image) else None
                fps = float(getattr(self, "_custom_bg_video_fps", 24.0) or 24.0)
                frames = int(getattr(self, "_custom_bg_video_frames", 0) or 0)
                elapsed = max(0.0, float(time.time() - float(getattr(self, "_custom_bg_video_start_ts", time.time()))))
                target_idx = int(elapsed * fps)
                if frames > 0:
                    target_idx = int(target_idx % max(1, frames))
                cur_idx = int(getattr(self, "_custom_bg_video_cur_idx", -1))
                fr = getattr(self, "_custom_bg_video_last_pil", None)
                if cur_idx == target_idx and isinstance(fr, Image.Image):
                    return self._fit_cover(fr.copy(), w, h)
                ok = False
                frame = None
                try:
                    if cur_idx < 0 or int(target_idx) <= int(cur_idx) or abs(int(target_idx - cur_idx)) > 8:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, float(max(0, target_idx)))
                        ok, frame = cap.read()
                    else:
                        steps = max(1, int(target_idx - cur_idx))
                        for _ in range(steps):
                            ok, frame = cap.read()
                            if not ok:
                                break
                    if not ok or frame is None:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0.0)
                        ok, frame = cap.read()
                        target_idx = 0
                    if ok and frame is not None:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        fr = Image.fromarray(frame)
                        self._custom_bg_video_last_pil = fr.copy()
                        self._custom_bg_video_cur_idx = int(target_idx)
                except Exception:
                    pass
                if isinstance(fr, Image.Image):
                    return self._fit_cover(fr.copy(), w, h)
        except Exception:
            return None
        return None

    def _update_background(self):
        if bool(getattr(self, "_embedded_editor_active", False)):
            return
        self._bg_tick += 1
        theme_name = str(getattr(self, "theme", "dark") or "dark")
        bg_mode, _ = self._custom_bg_mode() if theme_name == "custom" else ("", "")
        bg_anim_custom = bg_mode in ("video", "gif")
        if self.isFullScreen() and (self._bg_tick % 2 != 0) and (not bg_anim_custom):
            return
        w = max(600, self.width()); h = max(400, self.height())
        self.bg_t += 0.03
        if self.isFullScreen():
            sw, sh = max(180, w//5), max(120, h//5)
        else:
            sw, sh = max(200, w//3), max(120, h//3)
        im = Image.new("RGB", (sw, sh), "#0b0d10")
        if not (theme_name == "custom" and bool(getattr(self, "_eco_background", True)) and bg_mode in ("video", "gif", "image")):
            draw = ImageDraw.Draw(im)
            for y in range(sh):
                a = y / max(1, sh-1)
                r = int(10*(1-a) + 24*a); g = int(12*(1-a) + 30*a); b = int(20*(1-a) + 40*a)
                draw.line([(0,y),(sw,y)], fill=(r,g,b))
        if bool(getattr(self, "_eco_background", True)):
            # Lightweight background path: keeps style identity with much lower CPU/GPU usage.
            used_custom_frame = False
            try:
                if theme_name == "custom":
                    c_frame = self._custom_background_frame(sw, sh)
                    if isinstance(c_frame, Image.Image):
                        im = c_frame.convert("RGB")
                        used_custom_frame = True
                        try:
                            tint = self._hex_to_rgb(getattr(self, "custom_theme_panel", "#151c29"), fallback=(21, 28, 41))
                            over = Image.new("RGBA", im.size, (int(tint[0]), int(tint[1]), int(tint[2]), 34))
                            im = Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")
                        except Exception:
                            pass
                if not used_custom_frame:
                    palette = {
                        "retro": ((84, 132, 196), (40, 78, 124), (172, 210, 246)),
                        "cyberpunk 2077": ((44, 10, 18), (16, 8, 12), (220, 46, 70)),
                        "aphex twin": ((34, 42, 58), (16, 22, 34), (176, 196, 222)),
                        "dedsec": ((10, 30, 18), (8, 16, 12), (88, 255, 138)),
                        "light": ((226, 234, 245), (188, 206, 226), (120, 160, 214)),
                        "custom": (
                            self._hex_to_rgb(getattr(self, "custom_theme_bg", "#0c1018"), fallback=(12, 16, 24)),
                            self._hex_to_rgb(getattr(self, "custom_theme_panel", "#151c29"), fallback=(21, 28, 41)),
                            self._hex_to_rgb(getattr(self, "custom_theme_accent", "#5ec8ff"), fallback=(94, 200, 255)),
                        ),
                    }
                    top, bot, blob_col = palette.get(theme_name, ((12, 18, 32), (14, 24, 42), (96, 150, 240)))
                    yy = np.linspace(0.0, 1.0, sh, dtype=np.float32)[:, None]
                    xx = np.linspace(0.0, 1.0, sw, dtype=np.float32)[None, :]
                    wav = 0.04 * np.sin((xx * 7.6) + (self.bg_t * 0.85))
                    gy = np.clip(yy + wav, 0.0, 1.0)
                    rr = np.clip((top[0] * (1.0 - gy) + bot[0] * gy), 0, 255).astype(np.uint8)
                    gg = np.clip((top[1] * (1.0 - gy) + bot[1] * gy), 0, 255).astype(np.uint8)
                    bb = np.clip((top[2] * (1.0 - gy) + bot[2] * gy), 0, 255).astype(np.uint8)
                    arr = np.dstack((rr, gg, bb))
                    im = Image.fromarray(arr, mode="RGB")
                    cx = int((0.5 + 0.26 * math.sin(self.bg_t * 0.38)) * sw)
                    cy = int((0.5 + 0.22 * math.cos(self.bg_t * 0.33)) * sh)
                    rad = int(min(sw, sh) * 0.22)
                    blob = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
                    bd = ImageDraw.Draw(blob)
                    bd.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=(int(blob_col[0]), int(blob_col[1]), int(blob_col[2]), 44))
                    blob = blob.filter(ImageFilter.GaussianBlur(radius=max(8, rad // 2)))
                    im = Image.alpha_composite(im.convert("RGBA"), blob).convert("RGB")
            except Exception:
                pass
            try:
                if not used_custom_frame:
                    im = self._apply_theme_pattern(im, theme_name)
                elif theme_name == "custom":
                    # Add subtle motion-safe grain for custom media backgrounds.
                    im = self._apply_theme_pattern(im, "midnight")
            except Exception:
                pass
            try:
                blur = 0 if used_custom_frame else (3 if self.isFullScreen() else 4)
                im = im.resize((w, h), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=blur))
            except Exception:
                im = im.resize((w, h), Image.Resampling.BILINEAR)
            self.bg_qpix = pil_to_qpixmap(im)
            tr_mode = Qt.FastTransformation if self.isFullScreen() else Qt.SmoothTransformation
            pix = self.bg_qpix.scaled(self.size(), Qt.IgnoreAspectRatio, tr_mode)
            try:
                self.window_bg_label.setPixmap(pix)
                self.window_bg_label.setGeometry(0, 0, self.centralWidget().width(), self.centralWidget().height())
                self._normalize_main_z_order()
            except Exception:
                self.setAutoFillBackground(True)
                palette = self.palette()
                palette.setBrush(self.backgroundRole(), pix)
                self.setPalette(palette)
            self.bg_base = im
            try:
                # Update panel crops less frequently in eco mode.
                if self._bg_tick % (6 if self.isFullScreen() else 4) == 0:
                    self._update_panel_backgrounds()
            except Exception:
                pass
            return
        if theme_name == "custom":
            try:
                c_bg = self._hex_to_rgb(getattr(self, "custom_theme_bg", "#0c1018"), fallback=(12, 16, 24))
                c_panel = self._hex_to_rgb(getattr(self, "custom_theme_panel", "#151c29"), fallback=(21, 28, 41))
                for y in range(sh):
                    t = y / max(1, sh - 1)
                    rr = int(c_bg[0] * (1.0 - t) + c_panel[0] * t)
                    gg = int(c_bg[1] * (1.0 - t) + c_panel[1] * t)
                    bb = int(c_bg[2] * (1.0 - t) + c_panel[2] * t)
                    draw.line([(0, y), (sw, y)], fill=(rr, gg, bb))
            except Exception:
                pass
            c_frame = self._custom_background_frame(sw, sh)
            if isinstance(c_frame, Image.Image):
                try:
                    overlay = Image.new("RGBA", c_frame.size, (0, 0, 0, 62))
                    im = Image.alpha_composite(c_frame.convert("RGBA"), overlay).convert("RGB")
                except Exception:
                    im = c_frame.convert("RGB")
        if theme_name == "retro":
            # Windows-98-inspired "bliss" sky/field + VHS/CRT artifacts.
            sky_top = np.array([124, 186, 255], dtype=np.float32)
            sky_mid = np.array([108, 170, 242], dtype=np.float32)
            field_top = np.array([66, 152, 74], dtype=np.float32)
            field_bot = np.array([32, 96, 42], dtype=np.float32)
            horizon = int(sh * 0.58)
            for y in range(sh):
                if y <= horizon:
                    t = y / max(1, horizon)
                    col = (1.0 - t) * sky_top + t * sky_mid
                else:
                    t = (y - horizon) / max(1, sh - horizon)
                    col = (1.0 - t) * field_top + t * field_bot
                draw.line([(0, y), (sw, y)], fill=(int(col[0]), int(col[1]), int(col[2])))
            # hills
            hill = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            hd = ImageDraw.Draw(hill)
            hd.ellipse((-sw // 8, horizon - sh // 5, sw // 2, sh + sh // 5), fill=(84, 176, 82, 180))
            hd.ellipse((sw // 4, horizon - sh // 4, sw + sw // 6, sh + sh // 4), fill=(58, 148, 66, 188))
            im = Image.alpha_composite(im.convert("RGBA"), hill).convert("RGB")
            # cloud puffs
            cloud = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            cd = ImageDraw.Draw(cloud)
            cy = int(sh * 0.24)
            for cx, r in ((sw // 6, sw // 14), (sw // 3, sw // 12), (sw // 2, sw // 14), (sw * 3 // 4, sw // 11)):
                cd.ellipse((cx - r, cy - r // 2, cx + r, cy + r // 2), fill=(250, 255, 255, 72))
            cloud = cloud.filter(ImageFilter.GaussianBlur(radius=max(1, sw // 120)))
            im = Image.alpha_composite(im.convert("RGBA"), cloud).convert("RGB")
            arr = np.array(im, dtype=np.int16)
            # scanlines
            arr[::2, :, :] = np.clip(arr[::2, :, :] - 9, 0, 255)
            # static noise
            noise = np.random.normal(0.0, 7.5, arr.shape).astype(np.int16)
            arr = np.clip(arr + noise, 0, 255)
            # occasional horizontal tear / jitter
            if (self._bg_tick % 14) == 0:
                y0 = random.randint(0, max(0, sh - 8))
                y1 = min(sh, y0 + random.randint(2, 7))
                dx = random.choice([-4, -3, -2, 2, 3, 4])
                arr[y0:y1, :, :] = np.roll(arr[y0:y1, :, :], dx, axis=1)
            # tiny chroma misalignment
            if (self._bg_tick % 9) == 0:
                arr[:, :, 0] = np.roll(arr[:, :, 0], 1, axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -1, axis=1)
            im = Image.fromarray(arr.astype(np.uint8), mode="RGB").filter(ImageFilter.GaussianBlur(radius=0.6))
        elif theme_name == "cyberpunk 2077":
            # Arasaka-inspired black/red corporate cityscape.
            arr = np.array(im, dtype=np.int16)
            grad = np.linspace(0.0, 1.0, sh, dtype=np.float32)[:, None]
            arr[:, :, 0] = np.clip(arr[:, :, 0] + (grad * 98).astype(np.int16), 0, 255)
            arr[:, :, 1] = np.clip(arr[:, :, 1] - 22, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] - 34, 0, 255)
            im = Image.fromarray(arr.astype(np.uint8), mode="RGB")
            horizon = int(sh * 0.58)
            city = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            cd = ImageDraw.Draw(city)
            x = 0
            i = 0
            while x < sw:
                bw = max(6, int(sw * (0.028 + 0.004 * ((i % 5) + 1))))
                pulse = (math.sin(self.bg_t * 0.9 + i * 0.63) + 1.0) * 0.5
                bh = int(sh * (0.14 + 0.28 * pulse))
                y0 = max(0, horizon - bh)
                tint = int(16 + 24 * pulse)
                cd.rounded_rectangle((x, y0, min(sw, x + bw), horizon), radius=2, fill=(10 + tint, 6 + tint // 3, 8 + tint // 6, 226))
                win_step_x = max(3, bw // 4)
                for wx in range(x + 2, min(sw - 1, x + bw - 1), win_step_x):
                    for wy in range(y0 + 3, horizon - 2, 6):
                        flick = (math.sin(self.bg_t * 5.2 + wx * 0.11 + wy * 0.07) + 1.0) * 0.5
                        if flick > 0.55:
                            c = (255, 72, 94, int(58 + 86 * flick)) if ((wx + wy) % 2 == 0) else (228, 26, 48, int(44 + 64 * flick))
                            cd.rectangle((wx, wy, wx + 1, wy + 1), fill=c)
                x += bw + max(2, int(sw * 0.006))
                i += 1
            neon = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            nd = ImageDraw.Draw(neon)
            nd.line((0, int(sh * 0.16), sw, int(sh * 0.16)), fill=(255, 72, 94, 66), width=max(1, sh // 95))
            nd.line((0, int(sh * 0.78), sw, int(sh * 0.78)), fill=(198, 18, 36, 82), width=max(1, sh // 80))
            cx = sw // 2
            for k in range(1, 14):
                t = k / 14.0
                x2 = int(t * sw)
                alpha = int(48 * (1.0 - t) + 10)
                nd.line((cx, horizon + 4, x2, sh), fill=(220, 24, 46, alpha), width=1)
            rain_off = int((self.bg_t * 120) % 18)
            for rx in range(-20, sw + 20, 18):
                x0 = rx + rain_off
                nd.line((x0, 0, x0 - 10, sh), fill=(255, 78, 102, 20), width=1)
            # ARASAKA header mark
            try:
                nd.text((16, 14), "ARASAKA", fill=(255, 104, 126, 168))
            except Exception:
                pass
            im = Image.alpha_composite(im.convert("RGBA"), city)
            im = Image.alpha_composite(im, neon).convert("RGB")
            arr = np.array(im, dtype=np.int16)
            if (self._bg_tick % 9) == 0:
                y0 = random.randint(0, max(0, sh - 10))
                y1 = min(sh, y0 + random.randint(2, 7))
                dx = random.choice([-7, -5, -3, 3, 5, 7])
                arr[y0:y1, :, :] = np.roll(arr[y0:y1, :, :], dx, axis=1)
            arr = np.clip(arr + np.random.normal(0.0, 4.2, arr.shape).astype(np.int16), 0, 255)
            im = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        elif theme_name == "aphex twin":
            # Monochrome ambience + rotating lambda symbol.
            arr = np.array(im, dtype=np.int16)
            gray = (0.30 * arr[:, :, 0] + 0.59 * arr[:, :, 1] + 0.11 * arr[:, :, 2]).astype(np.int16)
            tint = np.zeros_like(arr)
            tint[:, :, 0] = np.clip(gray + 10, 0, 255)
            tint[:, :, 1] = np.clip(gray + 14, 0, 255)
            tint[:, :, 2] = np.clip(gray + 26, 0, 255)
            arr = tint
            arr[::3, :, :] = np.clip(arr[::3, :, :] - 10, 0, 255)
            arr = np.clip(arr + np.random.normal(0.0, 7.0, arr.shape).astype(np.int16), 0, 255)
            base = Image.fromarray(arr.astype(np.uint8), mode="RGB").convert("RGBA")
            sym = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            sd = ImageDraw.Draw(sym)
            cx = int(sw * (0.52 + 0.06 * math.sin(self.bg_t * 0.45)))
            cy = int(sh * (0.46 + 0.04 * math.cos(self.bg_t * 0.38)))
            size = int(min(sw, sh) * 0.28)
            th = max(2, size // 11)
            lam = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
            ld = ImageDraw.Draw(lam)
            c1 = (226, 236, 252, 224)
            c2 = (184, 204, 232, 188)
            ld.line([(int(size * 0.34), int(size * 0.20)), (int(size * 0.58), int(size * 1.66))], fill=c1, width=th)
            ld.line([(int(size * 0.58), int(size * 1.66)), (int(size * 1.42), int(size * 0.56))], fill=c1, width=th)
            ld.line([(int(size * 0.90), int(size * 1.15)), (int(size * 1.48), int(size * 1.15))], fill=c2, width=max(1, th // 2))
            lam = lam.filter(ImageFilter.GaussianBlur(radius=max(1, th // 3)))
            angle = (self.bg_t * 36.0) % 360.0
            rot = lam.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
            try:
                sym.alpha_composite(rot, (cx - rot.width // 2, cy - rot.height // 2))
            except Exception:
                sym.paste(rot, (cx - rot.width // 2, cy - rot.height // 2), rot)
            pulse_r = int(size * (0.68 + 0.08 * math.sin(self.bg_t * 1.8)))
            sd.ellipse((cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r), outline=(210, 224, 243, 46), width=max(1, th // 3))
            base = Image.alpha_composite(base, sym).convert("RGB")
            arr = np.array(base, dtype=np.int16)
            if (self._bg_tick % 11) == 0:
                arr[:, :, 0] = np.roll(arr[:, :, 0], 1, axis=1)
            im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB").filter(ImageFilter.GaussianBlur(radius=0.8))
        elif theme_name == "dedsec":
            arr = np.array(im, dtype=np.int16)
            arr[:, :, 1] = np.clip(arr[:, :, 1] + 22, 0, 255)
            arr[:, :, 0] = np.clip(arr[:, :, 0] - 6, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] - 12, 0, 255)
            im = Image.fromarray(arr.astype(np.uint8), mode="RGB")
            over = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            od = ImageDraw.Draw(over)
            step = max(10, sw // 24)
            off = int((self.bg_t * 120) % step)
            for x in range(-step, sw + step, step):
                od.line((x + off, 0, x + off, sh), fill=(74, 220, 122, 18), width=1)
            for y in range(0, sh, 3):
                od.line((0, y, sw, y), fill=(0, 0, 0, 22), width=1)
            for _ in range(max(8, sw // 40)):
                x = random.randint(0, max(1, sw - 1))
                y = random.randint(0, max(1, sh - 1))
                od.text((x, y), random.choice("01#/\\<>[]"), fill=(134, 255, 184, random.randint(44, 118)))
            im = Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")
            arr = np.array(im, dtype=np.int16)
            if (self._bg_tick % 13) == 0:
                y0 = random.randint(0, max(0, sh - 8))
                y1 = min(sh, y0 + random.randint(2, 6))
                arr[y0:y1, :, :] = np.roll(arr[y0:y1, :, :], random.choice([-6, -4, 4, 6]), axis=1)
            arr = np.clip(arr + np.random.normal(0.0, 4.0, arr.shape).astype(np.int16), 0, 255)
            im = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        if theme_name == "retro":
            colors = [(250, 220, 152), (128, 182, 255)]
            blob_alpha = 56
        elif theme_name == "cyberpunk 2077":
            colors = [(232, 24, 46), (156, 14, 28), (255, 86, 106)]
            blob_alpha = 62
        elif theme_name == "aphex twin":
            colors = [(196, 210, 232), (118, 134, 160), (88, 103, 124)]
            blob_alpha = 44
        elif theme_name == "dedsec":
            colors = [(88, 255, 138), (34, 170, 92), (178, 255, 214)]
            blob_alpha = 40
        elif theme_name == "custom":
            colors = [
                self._hex_to_rgb(getattr(self, "custom_theme_accent", "#5ec8ff"), fallback=(94, 200, 255)),
                self._hex_to_rgb(getattr(self, "custom_theme_fg", "#e8f2ff"), fallback=(232, 242, 255)),
                self._hex_to_rgb(getattr(self, "custom_theme_panel", "#151c29"), fallback=(21, 28, 41)),
            ]
            blob_alpha = 34
        else:
            colors = [(60, 160, 255), (120, 60, 220), (30, 200, 120)]
            blob_alpha = 100
        for i,c in enumerate(colors):
            cx = int((math.sin(self.bg_t*0.6 + i*1.2)+1)/2 * sw)
            cy = int((math.cos(self.bg_t*0.55 + i*0.9)+1)/2 * sh)
            rad = int(min(sw,sh) * (0.25 + 0.08*i))
            blob = Image.new("RGBA", (sw,sh), (0,0,0,0))
            bd = ImageDraw.Draw(blob)
            bd.ellipse([cx-rad, cy-rad, cx+rad, cy+rad], fill=(c[0],c[1],c[2],blob_alpha))
            blob = blob.filter(ImageFilter.GaussianBlur(radius=rad//2))
            im = Image.alpha_composite(im.convert("RGBA"), blob).convert("RGB")
        if theme_name == "retro":
            blur = 4 if self.isFullScreen() else 5
        elif theme_name == "cyberpunk 2077":
            blur = 5 if self.isFullScreen() else 7
        elif theme_name == "aphex twin":
            blur = 5 if self.isFullScreen() else 6
        elif theme_name == "dedsec":
            blur = 4 if self.isFullScreen() else 5
        elif theme_name == "custom":
            blur = 4 if self.isFullScreen() else 5
        else:
            blur = 6 if self.isFullScreen() else 8
        im = im.resize((w,h), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=blur))
        self.bg_qpix = pil_to_qpixmap(im)
        tr_mode = Qt.FastTransformation if self.isFullScreen() else Qt.SmoothTransformation
        pix = self.bg_qpix.scaled(self.size(), Qt.IgnoreAspectRatio, tr_mode)
        # set as window background label pixmap so trail can be composed onto it
        try:
            self.window_bg_label.setPixmap(pix)
            self.window_bg_label.setGeometry(0,0,self.centralWidget().width(), self.centralWidget().height())
            self._normalize_main_z_order()
        except Exception:
            # fallback to palette
            self.setAutoFillBackground(True)
            palette = self.palette(); palette.setBrush(self.backgroundRole(), pix); self.setPalette(palette)
        self.bg_base = im
        # update background pixmaps for panel crops
        try:
            if (not self.isFullScreen()) or (self._bg_tick % 2 == 0):
                self._update_panel_backgrounds()
        except Exception:
            pass

    def mouseMoveEvent(self, evt):
        # normalize to main window coordinates (map global -> window) so overlay aligns
        try:
            try:
                gp = evt.globalPosition()
            except Exception:
                gp = evt.globalPos()
            x = int(gp.x()); y = int(gp.y())
            local = self.mapFromGlobal(QPoint(x, y))
            lx = int(local.x()); ly = int(local.y())
            try:
                now = time.time()
                if getattr(self, "trail_level", "med") != "off":
                    can_push = (now - float(getattr(self, "_trail_last_sample_ts", 0.0))) >= 0.028
                    if can_push:
                        if len(self.trail) > 0:
                            px, py, _ = self.trail[-1]
                            if abs(px - lx) > 0 or abs(py - ly) > 0:
                                self.trail.append((lx, ly, now))
                                self._trail_last_sample_ts = now
                        else:
                            self.trail.append((lx, ly, now))
                            self._trail_last_sample_ts = now
                        if hasattr(self, "trail_timer") and self.trail_timer is not None and not self.trail_timer.isActive():
                            self.trail_timer.start()
            except Exception:
                pass
            # detect if cursor is positioned over preview_label area -> enable preview spotlight
            try:
                pl = self.preview_label
                glo = self.mapToGlobal(pl.pos())
                rel = pl.geometry()
                if pl.isVisible():
                    # compute preview rect in main window coordinates
                    top_left = pl.mapTo(self, QPoint(0,0))
                    pr = QRect(top_left, pl.size())
                    if pr.contains(QPoint(lx, ly)):
                        # show spotlight on preview to improve contrast around cursor
                        self._show_preview_spotlight(pl, lx - pr.x(), ly - pr.y())
                    else:
                        if getattr(self, '_suppress_trail', False):
                            # hide spotlight when leaving preview
                            try:
                                self.preview_overlay.clear(); self.preview_overlay.hide()
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception:
            pass
        return super().mouseMoveEvent(evt)

    def _sample_cursor(self):
        # called by timer to sample cursor even when mouse isn't moving (keeps trail smooth)
        try:
            if bool(getattr(self, "_embedded_editor_active", False)):
                return
            if str(getattr(self, "trail_level", "med")) == "off":
                return
            gp = QCursor.pos()
            local = self.mapFromGlobal(gp)
            x = int(local.x()); y = int(local.y())
            if 0 <= x <= self.width() and 0 <= y <= self.height():
                now = time.time()
                # Do not append duplicates while cursor is static - lets trail fade naturally.
                if len(self.trail) > 0:
                    lx, ly, _ = self.trail[-1]
                    if abs(lx - x) < 1 and abs(ly - y) < 1:
                        return
                self.trail.append((x, y, now))
                self._trail_last_sample_ts = now
                if hasattr(self, "trail_timer") and self.trail_timer is not None and not self.trail_timer.isActive():
                    self.trail_timer.start()
        except Exception:
            pass

    def _sync_trail_overlay_stack(self, force=False):
        try:
            if not hasattr(self, "trail_overlay") or self.trail_overlay is None:
                return
            if not force and not bool(getattr(self, "_trail_overlay_stack_dirty", False)):
                return
            gf = getattr(self, "gallery_frame", None)
            lf = self.findChild(QFrame, "left_frame")
            rf = self.findChild(QFrame, "right_frame")
            # Delay stack sync until core panels are available.
            if gf is None and lf is None and rf is None:
                self._trail_overlay_stack_dirty = True
                return
            self.trail_overlay.raise_()
            stacked = False
            if gf:
                self.trail_overlay.stackUnder(gf)
                stacked = True
            if lf:
                self.trail_overlay.stackUnder(lf)
                stacked = True
            if rf:
                self.trail_overlay.stackUnder(rf)
                stacked = True
            if not stacked:
                self._trail_overlay_stack_dirty = True
                return
            # keep main panels stable without per-frame raise storms
            if not bool(getattr(self, "_embedded_editor_active", False)):
                if gf:
                    gf.raise_()
                if lf:
                    lf.raise_()
                if rf:
                    rf.raise_()
            self._trail_overlay_stack_dirty = False
        except Exception:
            pass

    def _update_trail_overlay(self):
        # Draw trail into a transparent overlay; always render so smoke shows under translucent panels
        if bool(getattr(self, "_embedded_editor_active", False)):
            try:
                self.trail_overlay.clear()
                self.trail_overlay.hide()
            except Exception:
                pass
            return
        if self.trail_level == "off":
            try:
                self.trail_overlay.clear()
                self.trail_overlay.hide()
            except Exception:
                pass
            return
        try:
            self.trail_overlay.show()
        except Exception:
            pass
        # Note: trail is always rendered; preview spotlight only improves readability but
        # does not suppress the trail entirely.
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        now = time.time()
        try:
            ttl = 2.3 if self.isFullScreen() else 2.0
            while self.trail and (now - float(self.trail[0][2])) > ttl:
                self.trail.popleft()
        except Exception:
            pass
        pts = list(self.trail)
        if not pts:
            try:
                self.trail_overlay.clear()
                self.trail_overlay.hide()
            except Exception:
                pass
            try:
                if (now - float(getattr(self, "_trail_last_sample_ts", 0.0))) > 1.1 and hasattr(self, "trail_timer") and self.trail_timer.isActive():
                    self.trail_timer.stop()
            except Exception:
                pass
            return
        full_w = max(1, int(size.width()))
        full_h = max(1, int(size.height()))
        ds = 0.45 if self.isFullScreen() else 0.58
        ow = max(1, int(full_w * ds))
        oh = max(1, int(full_h * ds))
        overlay = QPixmap(ow, oh)
        overlay.fill(Qt.transparent)
        painter = QPainter(overlay)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            max_pts = 46 if self.isFullScreen() else 70
            pts_to_draw = pts[-max_pts:] if len(pts) > max_pts else pts
            # reduce trail intensity for readability but keep it visible under panels
            alpha_scale = 0.27
            for i, (x,y,tval) in enumerate(pts_to_draw):
                age = now - tval
                if age > 2.3:
                    continue
                rel = max(0.0, 1.0 - age/2.3)
                idx_rel = (i+1) / max(1, len(pts_to_draw))
                if self.trail_level == 'high': base_r = 80
                elif self.trail_level == 'med': base_r = 48
                else: base_r = 28
                r = int(2 + rel * base_r * (0.4 + 0.6*idx_rel) * (0.80 if ds < 1.0 else 1.0))
                px = int(x * ds)
                py = int(y * ds)
                alpha = int(180 * (0.3 + 0.7*rel) * idx_rel * alpha_scale)
                qr = max(2, int(round(r / 2.0) * 2))
                qa = max(6, min(255, int(round(alpha / 12.0) * 12)))
                key = (qr, qa)
                if key in self._circle_cache:
                    cpx = self._circle_cache[key]
                else:
                    cpx = QPixmap(qr*2, qr*2)
                    cpx.fill(Qt.transparent)
                    cp = QPainter(cpx)
                    try:
                        grad = QRadialGradient(qr, qr, qr)
                        # smoky gradient: soft white center, cool mid, transparent edge
                        grad.setColorAt(0.0, QColor(240,240,240, max(8, int(qa*0.45))))
                        grad.setColorAt(0.45, QColor(180,200,220, max(6, int(qa*0.30))))
                        grad.setColorAt(1.0, QColor(0,0,0,0))
                        cp.setBrush(QBrush(grad)); cp.setPen(Qt.NoPen)
                        cp.drawEllipse(0,0,qr*2,qr*2)
                    finally:
                        if cp.isActive():
                            cp.end()
                    self._circle_cache[key] = cpx
                    if len(self._circle_cache) > int(getattr(self, "_circle_cache_limit", 320)):
                        self._circle_cache.clear()
                # draw primary spot
                painter.drawPixmap(int(px-qr), int(py-qr), cpx)
                # draw a softer larger halo for smoke feel
                halo_r = int(qr * 1.6)
                halo_alpha = max(6, int(qa*0.28))
                hrr = max(2, int(round(halo_r / 2.0) * 2))
                haa = max(6, min(255, int(round(halo_alpha / 12.0) * 12)))
                hkey = (hrr, haa)
                if hkey in self._circle_cache:
                    hpx = self._circle_cache[hkey]
                else:
                    hpx = QPixmap(hrr*2, hrr*2)
                    hpx.fill(Qt.transparent)
                    hcp = QPainter(hpx)
                    try:
                        hgrad = QRadialGradient(hrr, hrr, hrr)
                        hgrad.setColorAt(0.0, QColor(220,220,220, int(haa)))
                        hgrad.setColorAt(1.0, QColor(0,0,0,0))
                        hcp.setBrush(QBrush(hgrad)); hcp.setPen(Qt.NoPen)
                        hcp.drawEllipse(0,0,hrr*2,hrr*2)
                    finally:
                        if hcp.isActive():
                            hcp.end()
                    self._circle_cache[hkey] = hpx
                    if len(self._circle_cache) > int(getattr(self, "_circle_cache_limit", 320)):
                        self._circle_cache.clear()
                painter.drawPixmap(int(px-hrr), int(py-hrr), hpx)
                # interpolate to next point to avoid gaps
                if i+1 < len(pts_to_draw):
                    nx, ny, _ = pts_to_draw[i+1]
                    nx = int(nx * ds)
                    ny = int(ny * ds)
                    x = px
                    y = py
                    dx = nx - x; dy = ny - y
                    dist = math.hypot(dx, dy)
                    steps = int(min(5, max(0, dist//10)))
                    for s in range(1, steps+1):
                        fx = x + dx * (s/ (steps+1))
                        fy = y + dy * (s/ (steps+1))
                        painter.drawPixmap(int(fx-qr), int(fy-qr), cpx)
        finally:
            painter.end()
        try:
            if ds < 1.0:
                qmode = Qt.FastTransformation
                out = overlay.scaled(full_w, full_h, Qt.IgnoreAspectRatio, qmode)
            else:
                out = overlay
            self.trail_overlay.setPixmap(out)
            self.trail_overlay.setGeometry(0,0,self.width(), self.height())
            self._sync_trail_overlay_stack()
        except Exception:
            pass

    def _show_preview_spotlight(self, preview_widget, local_x, local_y):
        """Draw a radial spotlight on preview_overlay to improve text readability when cursor hovers preview."""
        try:
            w = preview_widget.width(); h = preview_widget.height()
            if w <= 0 or h <= 0:
                return
            overlay = QPixmap(w, h)
            overlay.fill(Qt.transparent)
            p = QPainter(overlay)
            try:
                p.setRenderHint(QPainter.Antialiasing)
                radius = max(60, int(min(w,h) * 0.18))
                grad = QRadialGradient(local_x, local_y, radius)
                grad.setColorAt(0.0, QColor(255,255,255, 220))
                grad.setColorAt(0.35, QColor(255,255,255, 80))
                grad.setColorAt(1.0, QColor(0,0,0,0))
                p.setBrush(QBrush(grad)); p.setPen(Qt.NoPen)
                p.drawRect(0,0,w,h)
            finally:
                p.end()
            # set overlay on preview_label
            try:
                self.preview_overlay.setPixmap(overlay); self.preview_overlay.resize(w,h); self.preview_overlay.show()
            except Exception:
                pass
            try:
                # refresh localized help strings after language change
                self._update_style_help()
                self._update_codec_help()
                self._update_pro_preset_help()
            except Exception:
                pass
        except Exception:
            pass

    def on_load(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            if self._sound_mgr:
                self._sound_mgr.play_open()
        except Exception:
            pass
        fn, _ = QFileDialog.getOpenFileName(self, tr.get("load", "Load"), os.getcwd(),
                                            "Images & Videos (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.avi)")
        try:
            if self._sound_mgr:
                self._sound_mgr.play_close()
        except Exception:
            pass
        if not fn:
            return
        self._load_media_from_path(fn)

    def _load_media_from_path(self, fn):
        fn = str(fn or "").strip()
        if not fn or not os.path.exists(fn):
            return False
        self.current_path = fn
        self.original_source_path = fn
        self.processing_source_path = fn
        self.preview_label.setText("")
        try:
            low = fn.lower()
            if low.endswith((".mp4", ".avi", ".mov", ".mkv")):
                cap = cv2.VideoCapture(fn)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(frame)
                    self.current_media_size = pil.size
                    self._live_preview_source_pil = pil.copy()
                    if self.auto_size_chk.isChecked():
                        self.out_w.setValue(int(pil.size[0]))
                        self.out_h.setValue(int(pil.size[1]))
                    self._add_gallery_item(pil, path=fn, media_type="video")
                    idx = max(0, self.gallery_list.count() - 1)
                    self.gallery_list.setCurrentRow(idx)
                    return True
                return False
            if low.endswith(".gif"):
                try:
                    reader = imageio.get_reader(fn)
                    arr = reader.get_data(0)
                    pil = Image.fromarray(np.array(arr))
                    self.current_media_size = pil.size
                    self._live_preview_source_pil = pil.copy()
                    if self.auto_size_chk.isChecked():
                        self.out_w.setValue(int(pil.size[0]))
                        self.out_h.setValue(int(pil.size[1]))
                    self._add_gallery_item(pil, path=fn, media_type="gif")
                    idx = max(0, self.gallery_list.count() - 1)
                    self.gallery_list.setCurrentRow(idx)
                    return True
                except Exception:
                    return False
            pil = Image.open(fn).convert("RGB")
            self._show_preview_pil(pil)
            self._live_preview_source_pil = pil.copy()
            self.current_media_size = pil.size
            if self.auto_size_chk.isChecked():
                self.out_w.setValue(int(pil.size[0]))
                self.out_h.setValue(int(pil.size[1]))
            self._add_gallery_item(pil, path=fn, media_type="image")
            idx = max(0, self.gallery_list.count() - 1)
            self.gallery_list.setCurrentRow(idx)
            return True
        except Exception as e:
            print("Load preview error:", e)
            return False

    def _prompt_render_action(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            self._prepare_modal_ui()
            dlg = OverlayDialog(self, self.theme, tr.get("render_prompt_title", "Render mode"))
            dlg.set_panel_size(500, 240)
            body = QWidget()
            lay = QVBoxLayout(body)
            lay.setContentsMargins(0, 0, 0, 0)
            info = QLabel(tr.get("render_prompt_body", "Choose action"))
            info.setWordWrap(True)
            lay.addWidget(info)
            row = QHBoxLayout()
            btn_render = QPushButton(tr.get("render_prompt_do_render", "Render media"))
            btn_txt = QPushButton(tr.get("render_prompt_do_txt", "Export TXT"))
            btn_cancel = QPushButton(tr.get("cancel", "Cancel"))
            for b in (btn_render, btn_txt, btn_cancel):
                b.setStyleSheet(self._glass_btn_css())
                b.setCursor(Qt.PointingHandCursor)
            choice = {"v": "cancel"}
            btn_render.clicked.connect(lambda: (choice.__setitem__("v", "render"), dlg.accept()))
            btn_txt.clicked.connect(lambda: (choice.__setitem__("v", "txt"), dlg.accept()))
            btn_cancel.clicked.connect(lambda: (choice.__setitem__("v", "cancel"), dlg.reject()))
            row.addWidget(btn_render)
            row.addWidget(btn_txt)
            row.addWidget(btn_cancel)
            lay.addLayout(row)
            dlg.set_body_widget(body)
            try:
                self._attach_sounds(dlg)
            except Exception:
                pass
            dlg.exec()
            self._restore_modal_ui()
            return choice.get("v", "cancel")
        except Exception:
            self._restore_modal_ui()
            return "render"

    def _export_txt_from_current(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        if not getattr(self, "current_path", None) and getattr(self, "_live_preview_source_pil", None) is None and getattr(self, "current_output", None) is None:
            self._show_notice(tr.get("info", "Info"), tr.get("txt_export_empty", "No media for TXT export."))
            return
        try:
            if self._sound_mgr:
                self._sound_mgr.play_open()
        except Exception:
            pass
        fn, _ = QFileDialog.getSaveFileName(self, tr.get("export", "Export"), os.getcwd(), "TXT (*.txt)")
        try:
            if self._sound_mgr:
                self._sound_mgr.play_close()
        except Exception:
            pass
        if not fn:
            return
        try:
            if not fn.lower().endswith(".txt"):
                fn += ".txt"
            pil = None
            if self._preview_mode == "image" and getattr(self, "_preview_base_pil", None) is not None:
                pil = self._preview_base_pil.copy()
            if pil is None:
                p = str(getattr(self, "current_path", "") or "")
                ext = os.path.splitext(p)[1].lower() if p else ""
                if p and ext in (".png", ".jpg", ".jpeg", ".bmp") and os.path.exists(p):
                    pil = Image.open(p).convert("RGB")
                elif p and os.path.exists(p):
                    pil = self._get_first_frame(p)
                elif isinstance(getattr(self, "_live_preview_source_pil", None), Image.Image):
                    pil = self._live_preview_source_pil.copy()
                elif isinstance(getattr(self, "current_output", None), Image.Image):
                    pil = self.current_output.copy()
            if pil is None:
                self._show_notice(tr.get("info", "Info"), tr.get("txt_export_empty", "No media for TXT export."))
                return
            pil = self._preprocess_pil(pil)
            ascii_chars = self.charset_input.currentText() or DEFAULT_ASCII
            invert = self.invert_chk.isChecked()
            contrast = self.contrast_slider.value() if hasattr(self, "contrast_slider") else 100
            data = image_to_ascii_data(pil, self.width_chars, ascii_chars=ascii_chars, invert=invert, contrast_pct=contrast)
            txt = "\\n".join("".join(ch for ch, _ in row) for row in data)
            Path(fn).write_text(txt, encoding="utf-8")
            self._show_notice(tr.get("info", "Info"), tr.get("txt_export_done", "TXT exported successfully."))
        except Exception as e:
            self._show_notice(tr.get("info", "Info"), str(e))

    def on_render(self):
        src_path = self._effective_source_path()
        if not src_path:
            try:
                item = self._selected_gallery_item()
                data = item.data(Qt.UserRole) if item is not None else {}
                cand = str((data or {}).get("path", "") or "")
                if cand and os.path.exists(cand):
                    src_path = cand
                    self.current_path = cand
                    self.original_source_path = cand
                    self.processing_source_path = cand
            except Exception:
                pass
        if not src_path and getattr(self, "_live_preview_source_pil", None) is None and getattr(self, "current_output", None) is None:
            return
        if src_path:
            self.processing_source_path = src_path
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        ext = os.path.splitext(src_path)[1].lower() if src_path else ".png"
        action = "render"
        if ext in (".png", ".jpg", ".jpeg", ".bmp") and src_path:
            action = self._prompt_render_action()
            if action == "cancel":
                return
            if action == "txt":
                self._export_txt_from_current()
                return
        try:
            if self._preview_focus_mode:
                self._toggle_player_focus_mode()
            if self._preview_mode in ("video", "gif"):
                self._stop_preview_media()
        except Exception:
            pass
        self.render_btn.setEnabled(False)
        self._start_cpu_load()
        ascii_chars = self.charset_input.currentText() or DEFAULT_ASCII
        invert = self.invert_chk.isChecked()
        contrast = self.contrast_slider.value() if hasattr(self, 'contrast_slider') else 100
        keep_size = self.keep_size_chk.isChecked()
        try:
            if src_path and ext in [".mp4", ".avi", ".mov", ".mkv", ".gif"]:
                out_ext = ".gif" if ext == ".gif" else ".mp4"
                tmp = tempfile.NamedTemporaryFile(suffix=out_ext, delete=False)
                tmp.close()
                self.render_worker = RenderWorker(
                    src_path, tmp.name,
                    fps=max(1, int(self.render_fps)),
                    width_chars=self.width_chars,
                    ascii_chars=ascii_chars,
                    invert=invert,
                    contrast_pct=contrast,
                    font_size=self.font_size,
                    style=self.style,
                    fg_hex=self.fg_hex,
                    bg_hex=self.bg_hex,
                    watermark=self.watermark_chk.isChecked()
                )
                self.render_worker.watermark_text = str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK)
                self.render_worker.render_device = self.render_device
                self.render_worker.codec = self.render_codec
                self.render_worker.bitrate = self.render_bitrate
                self.render_worker.threads = int(self.render_threads)
                self.render_worker.preset = getattr(self, "render_preset", "medium")
                self.render_worker.crf = int(getattr(self, "render_crf", 20))
                self.render_worker.gamma_pct = int(self.gamma_pct)
                self.render_worker.denoise = self.denoise_chk.isChecked()
                self.render_worker.sharpen = self.sharpen_chk.isChecked()
                self.render_worker.edge_boost = self.edge_chk.isChecked()
                self.render_worker.pro_scanlines = bool(self.pro_scanlines_chk.isChecked()) if hasattr(self, "pro_scanlines_chk") else bool(self.pro_scanlines)
                self.render_worker.pro_bloom = int(getattr(self, "pro_bloom", 0))
                self.render_worker.pro_vignette = int(getattr(self, "pro_vignette", 0))
                self.render_worker.pro_poster_bits = int(getattr(self, "pro_poster_bits", 0))
                self.render_worker.pro_grain = int(getattr(self, "pro_grain", 0))
                self.render_worker.pro_chroma = int(getattr(self, "pro_chroma", 0))
                self.render_worker.pro_scan_strength = int(getattr(self, "pro_scan_strength", 28))
                self.render_worker.pro_scan_step = int(getattr(self, "pro_scan_step", 3))
                self.render_worker.pro_curvature = int(getattr(self, "pro_curvature", 0))
                self.render_worker.pro_concavity = int(getattr(self, "pro_concavity", 0))
                self.render_worker.pro_curvature_center_x = int(getattr(self, "pro_curvature_center_x", 0))
                self.render_worker.pro_curvature_expand = int(getattr(self, "pro_curvature_expand", 0))
                self.render_worker.pro_curvature_type = str(getattr(self, "pro_curvature_type", "spherical") or "spherical")
                self.render_worker.pro_ribbing = int(getattr(self, "pro_ribbing", 0))
                self.render_worker.pro_clarity = int(getattr(self, "pro_clarity", 0))
                self.render_worker.pro_motion_blur = int(getattr(self, "pro_motion_blur", 0))
                self.render_worker.pro_color_boost = int(getattr(self, "pro_color_boost", 0))
                self.render_worker.pro_glitch = int(getattr(self, "pro_glitch", 0))
                self.render_worker.pro_glitch_density = int(getattr(self, "pro_glitch_density", 35))
                self.render_worker.pro_glitch_shift = int(getattr(self, "pro_glitch_shift", 42))
                self.render_worker.pro_glitch_rgb = int(getattr(self, "pro_glitch_rgb", 1))
                self.render_worker.pro_glitch_block = int(getattr(self, "pro_glitch_block", 10))
                self.render_worker.pro_glitch_jitter = int(getattr(self, "pro_glitch_jitter", 1))
                self.render_worker.pro_glitch_noise = int(getattr(self, "pro_glitch_noise", 12))
                self.render_worker.keep_size = self.keep_size_chk.isChecked()
                if int(self.render_out_w) > 0 and int(self.render_out_h) > 0:
                    self.render_worker.target_size = (int(self.render_out_w), int(self.render_out_h))
                self.render_worker.scale_mult = int(self.render_scale)
                try:
                    self.render_worker.editor_state = copy.deepcopy(getattr(self, "editor_state", {}) or {})
                    self.render_worker.trim_start_ms = int(self.editor_state.get("trim_start_ms", 0)) if bool(self.editor_state.get("trim_enabled", False)) else 0
                    self.render_worker.trim_end_ms = int(self.editor_state.get("trim_end_ms", 0)) if bool(self.editor_state.get("trim_enabled", False)) else 0
                except Exception:
                    self.render_worker.editor_state = None
                    self.render_worker.trim_start_ms = 0
                    self.render_worker.trim_end_ms = 0
                self.render_worker.keep_source_audio = bool(self.keep_audio_chk.isChecked()) if hasattr(self, "keep_audio_chk") else True
                audio_src = None
                if getattr(self.render_worker, "keep_source_audio", False):
                    try:
                        ext_audio = str((self.editor_state or {}).get("audio_path", "") or "").strip()
                        if ext_audio and os.path.exists(ext_audio):
                            audio_src = ext_audio
                    except Exception:
                        audio_src = None
                    try:
                        cand1 = getattr(self, "original_source_path", None)
                        if audio_src is None and cand1 and os.path.exists(cand1):
                            audio_src = cand1
                    except Exception:
                        audio_src = None
                    if audio_src is None:
                        try:
                            cand2 = src_path
                            if cand2 and os.path.exists(cand2):
                                audio_src = cand2
                        except Exception:
                            audio_src = None
                self.render_worker.audio_source_path = audio_src
                self.render_worker.audio_gain_db = float((self.editor_state or {}).get("audio_gain_db", 0.0) or 0.0)
                self.render_worker.audio_lowpass_hz = int((self.editor_state or {}).get("audio_lowpass_hz", 0) or 0)
                dlg = ExportProgressDialog(self, self.render_worker, theme=self.theme, tr=tr)
                self.render_worker.start()
                dlg.exec()
                self._schedule_blur_cleanup()
                self._clear_render_worker()
                if os.path.exists(tmp.name):
                    if out_ext == ".gif":
                        try:
                            reader = imageio.get_reader(tmp.name)
                            first = Image.fromarray(np.array(reader.get_data(0))).convert("RGB")
                        except Exception:
                            first = None
                        if first is not None:
                            self._show_preview_pil(first)
                            self.current_output = first
                            self._add_gallery_item(first, path=tmp.name, media_type="gif")
                    else:
                        cap = cv2.VideoCapture(tmp.name)
                        ret, frame = cap.read()
                        cap.release()
                        if ret:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            first = Image.fromarray(frame)
                            self._show_preview_pil(first)
                            self.current_output = first
                            self._add_gallery_item(first, path=tmp.name, media_type="video")
                    self.current_path = tmp.name
                return

            pil = None
            if src_path and os.path.exists(src_path):
                pil = Image.open(src_path).convert('RGB')
            elif isinstance(getattr(self, "_live_preview_source_pil", None), Image.Image):
                pil = self._live_preview_source_pil.copy()
            elif isinstance(getattr(self, "current_output", None), Image.Image):
                pil = self.current_output.copy()
            if pil is None:
                return
            pil = self._preprocess_pil(pil)
            orig_size = pil.size
            target = None
            if int(self.render_out_w) > 0 and int(self.render_out_h) > 0:
                target = (int(self.render_out_w), int(self.render_out_h))
            elif keep_size or int(self.render_scale) > 1:
                target = orig_size
            if target and int(self.render_scale) > 1:
                target = (int(target[0] * int(self.render_scale)), int(target[1] * int(self.render_scale)))
            out = self._render_with_style(pil, output_size=target)
            self.current_output = out
            self._show_preview_pil(out, update_live_source=False)
            self._add_gallery_item(out, path=None, media_type='image')
        except Exception as e:
            print("Render error:", e)
            try:
                self._show_notice(tr.get("info", "Info"), f"{tr.get('render', 'Render')} error: {e}")
            except Exception:
                pass
        finally:
            self._stop_cpu_load()
            self.render_btn.setEnabled(True)
            self._schedule_blur_cleanup()

    def _on_render_finished(self, pil_img):
        # legacy hook kept
        self.render_btn.setEnabled(True)
        if pil_img is None: print("Render failed"); return
        self.current_output = pil_img; self._show_preview_pil(pil_img, update_live_source=False); self._add_gallery_item(pil_img)

    def _clear_render_worker(self, *_):
        try:
            if self.render_worker is not None:
                # ensure thread cleaned up
                self.render_worker.wait(50)
        except Exception:
            pass
        self.render_worker = None

    def on_export(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            if self._preview_focus_mode:
                self._toggle_player_focus_mode()
            if self._preview_mode in ("video", "gif"):
                self._stop_preview_media()
        except Exception:
            pass
        src_path = self._effective_source_path()
        media_ext = ""
        if src_path:
            media_ext = os.path.splitext(src_path)[1].lower()
        # For media source export full animation/video first.
        if media_ext in (".mp4", ".mov", ".avi", ".mkv", ".gif"):
            try:
                if self._sound_mgr:
                    self._sound_mgr.play_open()
            except Exception:
                pass
            outfn, _ = QFileDialog.getSaveFileName(self, tr.get("export", "Export"), os.getcwd(), "MP4 Video (*.mp4);;MOV Video (*.mov);;GIF (*.gif)")
            try:
                if self._sound_mgr:
                    self._sound_mgr.play_close()
            except Exception:
                pass
            if not outfn:
                return
            fps = max(1, int(getattr(self, "render_fps", 24)))
            width_chars = self.width_chars
            ascii_chars = self.charset_input.currentText() or DEFAULT_ASCII
            invert = self.invert_chk.isChecked()
            contrast = self.contrast_slider.value() if hasattr(self, 'contrast_slider') else 100
            font_size = self.font_size
            style = self.style
            fg = self.fg_hex
            bg = self.bg_hex
            watermark = self.watermark_chk.isChecked()
            try:
                self._start_cpu_load()
                self.render_worker = RenderWorker(src_path, outfn, fps=fps, width_chars=width_chars, ascii_chars=ascii_chars, invert=invert, contrast_pct=contrast, font_size=font_size, style=style, fg_hex=fg, bg_hex=bg, watermark=watermark)
                self.render_worker.watermark_text = str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK)
                self.render_worker.render_device = self.render_device
                self.render_worker.codec = self.render_codec
                self.render_worker.bitrate = self.render_bitrate
                self.render_worker.threads = int(self.render_threads)
                self.render_worker.preset = getattr(self, "render_preset", "medium")
                self.render_worker.crf = int(getattr(self, "render_crf", 20))
                self.render_worker.gamma_pct = int(self.gamma_pct)
                self.render_worker.denoise = self.denoise_chk.isChecked()
                self.render_worker.sharpen = self.sharpen_chk.isChecked()
                self.render_worker.edge_boost = self.edge_chk.isChecked()
                self.render_worker.pro_scanlines = bool(self.pro_scanlines_chk.isChecked()) if hasattr(self, "pro_scanlines_chk") else bool(self.pro_scanlines)
                self.render_worker.pro_bloom = int(getattr(self, "pro_bloom", 0))
                self.render_worker.pro_vignette = int(getattr(self, "pro_vignette", 0))
                self.render_worker.pro_poster_bits = int(getattr(self, "pro_poster_bits", 0))
                self.render_worker.pro_grain = int(getattr(self, "pro_grain", 0))
                self.render_worker.pro_chroma = int(getattr(self, "pro_chroma", 0))
                self.render_worker.pro_scan_strength = int(getattr(self, "pro_scan_strength", 28))
                self.render_worker.pro_scan_step = int(getattr(self, "pro_scan_step", 3))
                self.render_worker.pro_curvature = int(getattr(self, "pro_curvature", 0))
                self.render_worker.pro_concavity = int(getattr(self, "pro_concavity", 0))
                self.render_worker.pro_curvature_center_x = int(getattr(self, "pro_curvature_center_x", 0))
                self.render_worker.pro_curvature_expand = int(getattr(self, "pro_curvature_expand", 0))
                self.render_worker.pro_curvature_type = str(getattr(self, "pro_curvature_type", "spherical") or "spherical")
                self.render_worker.pro_ribbing = int(getattr(self, "pro_ribbing", 0))
                self.render_worker.pro_clarity = int(getattr(self, "pro_clarity", 0))
                self.render_worker.pro_motion_blur = int(getattr(self, "pro_motion_blur", 0))
                self.render_worker.pro_color_boost = int(getattr(self, "pro_color_boost", 0))
                self.render_worker.pro_glitch = int(getattr(self, "pro_glitch", 0))
                self.render_worker.pro_glitch_density = int(getattr(self, "pro_glitch_density", 35))
                self.render_worker.pro_glitch_shift = int(getattr(self, "pro_glitch_shift", 42))
                self.render_worker.pro_glitch_rgb = int(getattr(self, "pro_glitch_rgb", 1))
                self.render_worker.pro_glitch_block = int(getattr(self, "pro_glitch_block", 10))
                self.render_worker.pro_glitch_jitter = int(getattr(self, "pro_glitch_jitter", 1))
                self.render_worker.pro_glitch_noise = int(getattr(self, "pro_glitch_noise", 12))
                self.render_worker.keep_size = self.keep_size_chk.isChecked()
                if int(self.render_out_w) > 0 and int(self.render_out_h) > 0:
                    self.render_worker.target_size = (int(self.render_out_w), int(self.render_out_h))
                self.render_worker.scale_mult = int(self.render_scale)
                try:
                    self.render_worker.editor_state = copy.deepcopy(getattr(self, "editor_state", {}) or {})
                    self.render_worker.trim_start_ms = int(self.editor_state.get("trim_start_ms", 0)) if bool(self.editor_state.get("trim_enabled", False)) else 0
                    self.render_worker.trim_end_ms = int(self.editor_state.get("trim_end_ms", 0)) if bool(self.editor_state.get("trim_enabled", False)) else 0
                except Exception:
                    self.render_worker.editor_state = None
                    self.render_worker.trim_start_ms = 0
                    self.render_worker.trim_end_ms = 0
                self.render_worker.keep_source_audio = bool(self.keep_audio_chk.isChecked()) if hasattr(self, "keep_audio_chk") else True
                audio_src = None
                if getattr(self.render_worker, "keep_source_audio", False):
                    try:
                        ext_audio = str((self.editor_state or {}).get("audio_path", "") or "").strip()
                        if ext_audio and os.path.exists(ext_audio):
                            audio_src = ext_audio
                    except Exception:
                        audio_src = None
                    try:
                        cand1 = getattr(self, "original_source_path", None)
                        if audio_src is None and cand1 and os.path.exists(cand1):
                            audio_src = cand1
                    except Exception:
                        audio_src = None
                    if audio_src is None:
                        try:
                            cand2 = src_path
                            if cand2 and os.path.exists(cand2):
                                audio_src = cand2
                        except Exception:
                            audio_src = None
                self.render_worker.audio_source_path = audio_src
                self.render_worker.audio_gain_db = float((self.editor_state or {}).get("audio_gain_db", 0.0) or 0.0)
                self.render_worker.audio_lowpass_hz = int((self.editor_state or {}).get("audio_lowpass_hz", 0) or 0)
                dlg = ExportProgressDialog(self, self.render_worker, theme=self.theme, tr=tr)
                self.render_worker.start()
                dlg.exec()
                self._schedule_blur_cleanup()
                self._clear_render_worker()
                if os.path.exists(outfn):
                    first = self._get_first_frame(outfn)
                    if first is not None:
                        mtype = "gif" if outfn.lower().endswith(".gif") else "video"
                        self._add_gallery_item(first, path=outfn, media_type=mtype)
                    self._open_output_folder(outfn)
            except Exception as e:
                print('Export failed to start:', e)
            finally:
                self._stop_cpu_load()
                self._schedule_blur_cleanup()
            return
        # Static export path for current rendered image.
        if hasattr(self, "current_output") and self.current_output is not None:
            # allow selecting image or animation containers
            try:
                if self._sound_mgr:
                    self._sound_mgr.play_open()
            except Exception:
                pass
            fn, flt = QFileDialog.getSaveFileName(self, tr.get("export", "Export"), os.getcwd(), "PNG Image (*.png);;GIF (*.gif);;MP4 Video (*.mp4)")
            try:
                if self._sound_mgr:
                    self._sound_mgr.play_close()
            except Exception:
                pass
            if not fn: return
            try:
                self._start_cpu_load()
                ext = fn.split('.')[-1].lower()
                if ext == 'png':
                    self.current_output.save(fn)
                elif ext in ('gif','mp4'):
                    # use worker to avoid blocking UI when writing animations
                    saver = SaveImageWorker(self.current_output, fn, fps=10)
                    dlg = ExportProgressDialog(self, saver, theme=self.theme, tr=tr)
                    saver.start()
                    dlg.exec()
                    self._schedule_blur_cleanup()
                else:
                    self.current_output.save(fn)
                self._open_output_folder(fn)
            except Exception as e:
                print("Export save failed:", e)
            finally:
                self._stop_cpu_load()
                self._schedule_blur_cleanup()

    def on_style_changed(self, v):
        self.style = v
        # toggle color pickers
        self._update_color_buttons_state()
        self._update_ascii_controls_visibility()
        self._update_style_help()

    def _trail_combo_changed(self, label):
        """Map translated trail label back to internal key and set trail_level."""
        try:
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            rev = {tr["off"]: "off", tr["low"]: "low", tr["med"]: "med", tr["high"]: "high"}
            key = rev.get(label, "med")
            self.trail_level = key
        except Exception:
            self.trail_level = "med"
        try:
            if str(self.trail_level) == "off":
                if hasattr(self, "trail_timer") and self.trail_timer.isActive():
                    self.trail_timer.stop()
                if hasattr(self, "cursor_sample_timer") and self.cursor_sample_timer.isActive():
                    self.cursor_sample_timer.stop()
                if hasattr(self, "trail_overlay") and self.trail_overlay is not None:
                    self.trail_overlay.clear()
                    self.trail_overlay.hide()
            else:
                if hasattr(self, "trail_timer") and not self.trail_timer.isActive():
                    self.trail_timer.start()
                if hasattr(self, "cursor_sample_timer") and not self.cursor_sample_timer.isActive():
                    self.cursor_sample_timer.start()
        except Exception:
            pass

    def on_width_changed(self, v):
        self.width_chars = int(v)
        self.width_val_label.setText(str(self.width_chars))

    def on_font_changed(self, v):
        self.font_size = int(v)
        self.font_val_label.setText(str(self.font_size))

    def on_contrast_changed(self, v):
        self.contrast = int(v)
        try:
            self.contrast_val_label.setText(str(self.contrast))
        except Exception:
            pass

    def on_gamma_changed(self, v):
        self.gamma_pct = int(v)
        try:
            self.gamma_val_label.setText(str(self.gamma_pct))
        except Exception:
            pass

    def _schedule_live_preview(self, force=False):
        try:
            if not bool(getattr(self, "live_preview", False)):
                return
            if getattr(self, "_live_preview_inflight", False):
                self._live_preview_pending = True
                if bool(force):
                    self._live_preview_force = True
                return
            now = time.time()
            if (not bool(force)) and (now - float(getattr(self, "_live_preview_req_ts", 0.0))) < 0.03:
                return
            self._live_preview_req_ts = now
            delay = 0 if bool(force) else (120 if self.isFullScreen() else 90)
            self._live_preview_timer.start(delay)
        except Exception:
            pass

    def _effective_source_path(self):
        try:
            for cand in (
                getattr(self, "processing_source_path", None),
                getattr(self, "original_source_path", None),
                getattr(self, "current_path", None),
            ):
                p = str(cand or "").strip()
                if p and os.path.exists(p):
                    return p
        except Exception:
            pass
        return ""

    def _apply_live_preview_now(self):
        try:
            if not bool(getattr(self, "live_preview", False)):
                return
            if getattr(self, "_live_preview_inflight", False):
                self._live_preview_pending = True
                return
            src_path = self._effective_source_path()
            if not src_path and getattr(self, "_live_preview_source_pil", None) is None and getattr(self, "_preview_base_pil", None) is None:
                return
            self._live_preview_inflight = True
            force_now = bool(getattr(self, "_live_preview_force", False))
            self._live_preview_force = False
            src = None
            mode = getattr(self, "_preview_mode", "image")
            base_src = getattr(self, "_live_preview_source_pil", None)
            video_ext = (".mp4", ".mov", ".avi", ".mkv", ".webm")
            image_ext = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
            ext = os.path.splitext(src_path)[1].lower() if src_path else ""
            pos = int(getattr(self, "_preview_last_pos_ms", 0) or 0)
            try:
                if mode == "video" and self._preview_player is not None:
                    pos = int(self._preview_player.position() or pos)
            except Exception:
                pass
            try:
                state_sig = (
                    str(getattr(self, "style", "")),
                    int(getattr(self, "width_chars", 120) or 120),
                    int(getattr(self, "font_size", 10) or 10),
                    int(getattr(self, "contrast", 100) or 100),
                    int(getattr(self, "gamma_pct", 100) or 100),
                    bool(getattr(self, "invert", False)),
                    str(getattr(self, "ascii_chars", "")),
                    str(getattr(self, "fg_hex", "#ffffff")),
                    str(getattr(self, "bg_hex", "#000000")),
                    bool(getattr(self, "pro_tools", False)),
                    int(getattr(self, "pro_bloom", 0) or 0),
                    int(getattr(self, "pro_vignette", 0) or 0),
                    int(getattr(self, "pro_poster_bits", 0) or 0),
                    int(getattr(self, "pro_grain", 0) or 0),
                    int(getattr(self, "pro_chroma", 0) or 0),
                    int(getattr(self, "pro_glitch", 0) or 0),
                    int(getattr(self, "pro_glitch_density", 0) or 0),
                    int(getattr(self, "pro_glitch_shift", 0) or 0),
                    int(getattr(self, "render_scale", 1) or 1),
                    int(pos // (80 if mode == "video" else 500)),
                    str(mode),
                    str(src_path),
                )
            except Exception:
                state_sig = None
            now = time.time()
            if (not force_now) and state_sig is not None and state_sig == getattr(self, "_live_preview_last_sig", None):
                if (now - float(getattr(self, "_live_preview_last_ts", 0.0))) < (0.22 if self.isFullScreen() else 0.14):
                    return
            if mode == "video" or ext in video_ext:
                src = self._get_video_frame_at_ms(src_path, pos) if src_path else None
                if src is None and src_path:
                    src = self._get_first_frame(src_path)
            elif mode == "gif" or ext == ".gif":
                src = self._get_first_frame(src_path) if src_path else None
            elif src_path and ext in image_ext:
                try:
                    src = Image.open(src_path).convert("RGB")
                except Exception:
                    src = None
            if src is None and mode == "image" and getattr(self, "_preview_base_pil", None) is not None:
                try:
                    src = base_src.copy() if isinstance(base_src, Image.Image) else self._preview_base_pil.copy()
                except Exception:
                    src = None
            elif src is None and isinstance(base_src, Image.Image):
                try:
                    src = base_src.copy()
                except Exception:
                    src = None
            if src is None:
                return
            try:
                mw = 1400 if self.isFullScreen() else 1280
                if src.width > mw or src.height > mw:
                    src = src.copy()
                    src.thumbnail((mw, mw), Image.Resampling.BILINEAR)
            except Exception:
                pass
            pre = self._preprocess_pil(src, t_ms=pos if (mode == "video" or ext in video_ext) else 0)
            keep_size = self.keep_size_chk.isChecked()
            target = None
            if int(self.render_out_w) > 0 and int(self.render_out_h) > 0:
                target = (int(self.render_out_w), int(self.render_out_h))
            elif keep_size or int(self.render_scale) > 1:
                target = pre.size
            if target and int(self.render_scale) > 1:
                target = (int(target[0] * int(self.render_scale)), int(target[1] * int(self.render_scale)))
            out = self._render_with_style(pre, output_size=target)
            self.current_output = out
            # Do not overwrite preview base source, otherwise live changes can stack repeatedly.
            self._show_preview_pil(out, set_as_base=False, preserve_transform=True, update_live_source=False)
            self._live_preview_last_sig = state_sig
            self._live_preview_last_ts = now
        except Exception:
            pass
        finally:
            self._live_preview_inflight = False
            try:
                if bool(getattr(self, "_live_preview_pending", False)):
                    self._live_preview_pending = False
                    self._schedule_live_preview(force=True)
            except Exception:
                pass

    def _start_cpu_load(self):
        try:
            if hasattr(self, "cpu_bars"):
                self.cpu_bars.stop()
                self.cpu_bars.hide()
            if hasattr(self, "cpu_label"):
                self.cpu_label.hide()
        except Exception:
            pass

    def _stop_cpu_load(self):
        try:
            if hasattr(self, "cpu_bars"):
                self.cpu_bars.stop()
                self.cpu_bars.hide()
            if hasattr(self, "cpu_label"):
                self.cpu_label.hide()
        except Exception:
            pass

    def _preview_wheel_event(self, ev):
        mode = getattr(self, "_preview_mode", "image")
        if mode == "image":
            if self._preview_base_pil is None:
                return
        elif mode not in ("video", "gif"):
            return
        try:
            delta = ev.angleDelta().y()
        except Exception:
            delta = 0
        if delta == 0:
            return
        factor = 1.08 if delta > 0 else (1 / 1.08)
        max_zoom = 8.0 if mode == "image" else (4.0 if mode == "gif" else 3.0)
        self._preview_zoom_target = max(0.25, min(max_zoom, float(getattr(self, "_preview_zoom_target", self.preview_zoom)) * factor))
        if not self._preview_motion_timer.isActive():
            self._preview_motion_timer.start()
        try:
            ev.accept()
        except Exception:
            pass

    def _preview_mouse_press(self, ev):
        mode = getattr(self, "_preview_mode", "image")
        if mode == "image" and self._preview_base_pil is None:
            self._preview_drag = None
            return
        try:
            self._preview_drag = ev.globalPosition()
        except Exception:
            try:
                self._preview_drag = ev.globalPos()
            except Exception:
                self._preview_drag = None

    def _preview_mouse_move(self, ev):
        if self._preview_drag is None:
            return
        try:
            gp = ev.globalPosition()
        except Exception:
            gp = ev.globalPos()
        dx = gp.x() - self._preview_drag.x()
        dy = gp.y() - self._preview_drag.y()
        self.preview_pan[0] += dx
        self.preview_pan[1] += dy
        self._preview_pan_target[0] = float(self.preview_pan[0])
        self._preview_pan_target[1] = float(self.preview_pan[1])
        self._preview_drag = gp
        if getattr(self, "_preview_mode", "image") == "image":
            try:
                pm = self.preview_image.pixmap()
                if pm is not None and (not pm.isNull()):
                    self._position_preview_image(int(pm.width()), int(pm.height()), int(max(200, self.preview_label.width() or 800)), int(max(200, self.preview_label.height() or 500)))
                    self._layout_preview_controls()
                else:
                    self._render_preview_scaled()
            except Exception:
                self._render_preview_scaled()
        else:
            self._schedule_preview_media_transform(0)
        try:
            ev.accept()
        except Exception:
            pass

    def _preview_mouse_release(self, ev):
        self._preview_drag = None

    def _preview_leave(self, ev):
        try:
            self.preview_overlay.clear()
            self.preview_overlay.hide()
        except Exception:
            pass

    def _preview_double_click(self, ev):
        try:
            if self._preview_mode in ("video", "gif"):
                self._toggle_preview_play_pause()
            elif self._preview_base_pil is not None:
                self.open_fullscreen_viewer(self._preview_base_pil)
        except Exception:
            pass

    def _schedule_preview_media_transform(self, delay_ms=0):
        try:
            if self._preview_transform_timer.isActive():
                self._preview_transform_timer.stop()
            self._preview_transform_timer.start(max(0, int(delay_ms)))
        except Exception:
            pass

    def _tick_preview_motion(self):
        try:
            mode = str(getattr(self, "_preview_mode", "image") or "image")
            cur_z = float(getattr(self, "preview_zoom", 1.0))
            tgt_z = float(getattr(self, "_preview_zoom_target", cur_z))
            cur_px = float(self.preview_pan[0])
            cur_py = float(self.preview_pan[1])
            tgt_px = float(self._preview_pan_target[0])
            tgt_py = float(self._preview_pan_target[1])
            dz = tgt_z - cur_z
            dx = tgt_px - cur_px
            dy = tgt_py - cur_py
            done = abs(dz) < 0.002 and abs(dx) < 0.35 and abs(dy) < 0.35
            if done:
                self.preview_zoom = float(tgt_z)
                self.preview_pan[0] = int(round(tgt_px))
                self.preview_pan[1] = int(round(tgt_py))
                self._preview_motion_timer.stop()
            else:
                self.preview_zoom = cur_z + dz * 0.28
                self.preview_pan[0] = int(round(cur_px + dx * 0.28))
                self.preview_pan[1] = int(round(cur_py + dy * 0.28))
            if mode == "image":
                if abs(dz) < 0.001:
                    try:
                        pm = self.preview_image.pixmap()
                        if pm is not None and (not pm.isNull()):
                            self._position_preview_image(int(pm.width()), int(pm.height()), int(max(200, self.preview_label.width() or 800)), int(max(200, self.preview_label.height() or 500)))
                            self._layout_preview_controls()
                        else:
                            self._render_preview_scaled()
                    except Exception:
                        self._render_preview_scaled()
                else:
                    self._render_preview_scaled()
            elif mode in ("video", "gif"):
                self._schedule_preview_media_transform(0)
        except Exception:
            try:
                self._preview_motion_timer.stop()
            except Exception:
                pass

    def _set_scale(self, v):
        try:
            self.render_scale = int(v)
        except Exception:
            self.render_scale = 1
        self.scale_x1.setEnabled(self.render_scale != 1)
        self.scale_x2.setEnabled(self.render_scale != 2)
        self.scale_x3.setEnabled(self.render_scale != 3)
        for b in (self.scale_x1, self.scale_x2, self.scale_x3):
            b.setStyleSheet(self._glass_btn_css())
        active = {1: self.scale_x1, 2: self.scale_x2, 3: self.scale_x3}.get(self.render_scale)
        if active:
            active.setStyleSheet(self._glass_btn_css() + "QPushButton{ border:2px solid #6aa9ff; }")

    def _on_out_w_changed(self, v):
        self.render_out_w = int(v)
        if self.render_out_w > 0:
            self.keep_size_chk.setChecked(False)

    def _on_out_h_changed(self, v):
        self.render_out_h = int(v)
        if self.render_out_h > 0:
            self.keep_size_chk.setChecked(False)

    def _on_keep_size_changed(self, state):
        if state and (self.render_out_w > 0 or self.render_out_h > 0):
            self.out_w.setValue(0)
            self.out_h.setValue(0)

    def _apply_style_defaults(self):
        try:
            self.style_combo.setCurrentText("bw")
            self.width_slider.setValue(320)
            self.font_slider.setValue(12)
            self.fps_spin.setValue(24)
            if self.current_media_size:
                self.out_w.setValue(int(self.current_media_size[0]))
                self.out_h.setValue(int(self.current_media_size[1]))
            else:
                self.out_w.setValue(0)
                self.out_h.setValue(0)
            self._set_scale(1)
            self.auto_size_chk.setChecked(True)
        except Exception:
            pass

    def _apply_fx_defaults(self):
        try:
            self.contrast_slider.setValue(100)
            self.gamma_slider.setValue(100)
            self.invert_chk.setChecked(False)
            self.keep_size_chk.setChecked(False)
            self.denoise_chk.setChecked(False)
            self.sharpen_chk.setChecked(False)
            self.edge_chk.setChecked(False)
            self.charset_input.setCurrentText(DEFAULT_ASCII)
            self.watermark_chk.setChecked(True)
            if hasattr(self, "watermark_text_edit"):
                self.watermark_text_edit.setText(str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK))
        except Exception:
            pass

    def _apply_pro_defaults(self):
        try:
            if hasattr(self, "pro_scanlines_chk"):
                self.pro_scanlines_chk.setChecked(False)
            if hasattr(self, "pro_bloom_slider"):
                self.pro_bloom_slider.setValue(0)
            if hasattr(self, "pro_vignette_slider"):
                self.pro_vignette_slider.setValue(0)
            if hasattr(self, "pro_poster_spin"):
                self.pro_poster_spin.setValue(0)
            if hasattr(self, "pro_grain_slider"):
                self.pro_grain_slider.setValue(0)
            if hasattr(self, "pro_chroma_spin"):
                self.pro_chroma_spin.setValue(0)
            if hasattr(self, "pro_color_boost_slider"):
                self.pro_color_boost_slider.setValue(0)
            if hasattr(self, "pro_clarity_slider"):
                self.pro_clarity_slider.setValue(0)
            if hasattr(self, "pro_motion_blur_slider"):
                self.pro_motion_blur_slider.setValue(0)
            if hasattr(self, "pro_scan_strength_slider"):
                self.pro_scan_strength_slider.setValue(28)
            if hasattr(self, "pro_scan_step_spin"):
                self.pro_scan_step_spin.setValue(3)
            if hasattr(self, "pro_curvature_slider"):
                self.pro_curvature_slider.setValue(0)
            if hasattr(self, "pro_concavity_slider"):
                self.pro_concavity_slider.setValue(0)
            if hasattr(self, "pro_curvature_center_x_slider"):
                self.pro_curvature_center_x_slider.setValue(0)
            if hasattr(self, "pro_curvature_expand_slider"):
                self.pro_curvature_expand_slider.setValue(0)
            if hasattr(self, "pro_curvature_type_combo"):
                self.pro_curvature_type_combo.setCurrentText("spherical")
            if hasattr(self, "pro_ribbing_slider"):
                self.pro_ribbing_slider.setValue(0)
            if hasattr(self, "pro_glitch_slider"):
                self.pro_glitch_slider.setValue(0)
            if hasattr(self, "pro_glitch_density_slider"):
                self.pro_glitch_density_slider.setValue(35)
            if hasattr(self, "pro_glitch_shift_slider"):
                self.pro_glitch_shift_slider.setValue(42)
            if hasattr(self, "pro_glitch_rgb_spin"):
                self.pro_glitch_rgb_spin.setValue(1)
            if hasattr(self, "pro_glitch_block_spin"):
                self.pro_glitch_block_spin.setValue(10)
            if hasattr(self, "pro_glitch_jitter_spin"):
                self.pro_glitch_jitter_spin.setValue(1)
            if hasattr(self, "pro_glitch_noise_slider"):
                self.pro_glitch_noise_slider.setValue(12)
            if hasattr(self, "pro_preset_combo"):
                self.pro_preset_combo.setCurrentText("none")
        except Exception:
            pass

    def _apply_render_defaults(self):
        try:
            if hasattr(self, "keep_audio_chk"):
                self.keep_audio_chk.setChecked(True)
            if hasattr(self, "codec_combo"):
                self.codec_combo.setCurrentText("libx264")
            if hasattr(self, "bitrate_combo"):
                self.bitrate_combo.setCurrentText("2M")
            if hasattr(self, "threads_spin"):
                self.threads_spin.setValue(4)
            if hasattr(self, "preset_combo"):
                self.preset_combo.setCurrentText("medium")
            if hasattr(self, "crf_spin"):
                self.crf_spin.setValue(20)
            if hasattr(self, "fps_spin"):
                self.fps_spin.setValue(24)
        except Exception:
            pass

    def _apply_right_defaults(self):
        # reset right-panel controls to defaults
        try:
            self._push_undo_state()
            self._apply_style_defaults()
            self._apply_fx_defaults()
            self._apply_pro_defaults()
            self._apply_render_defaults()
        except Exception:
            pass

    def _layout_preview_controls(self):
        try:
            count = self.gallery_list.count() if hasattr(self, "gallery_list") else 0
            cur = self.gallery_list.currentRow() if hasattr(self, "gallery_list") else -1
            self.preview_prev_btn.setEnabled(count > 1 and cur > 0)
            self.preview_next_btn.setEnabled(count > 1 and cur >= 0 and cur < count - 1)
            self.preview_open_btn.setEnabled(count > 0 and cur >= 0)
            # Keep nav controls visible for video mode: place relative to preview area,
            # and in focus mode move arrows slightly outside preview bounds.
            pr = self.preview_label.geometry()
            w = pr.width()
            h = pr.height()
            y = max(8, pr.y() + (h - self.preview_prev_btn.height()) // 2)
            side = 42 if self._preview_focus_mode else 36
            self.preview_prev_btn.setFixedWidth(side)
            self.preview_next_btn.setFixedWidth(side)
            if self._preview_focus_mode:
                lx = max(10, pr.x() - side - 12)
                rx = min(max(10, self.left_frame.width() - side - 10), pr.x() + w + 12)
            else:
                lx = pr.x() + 10
                rx = max(pr.x() + 10, pr.x() + w - side - 10)
            self.preview_prev_btn.move(lx, y)
            self.preview_next_btn.move(rx, y)
            self.preview_open_btn.move(max(pr.x() + 10, pr.x() + w - self.preview_open_btn.width() - 10), pr.y() + 10)
            try:
                mode = getattr(self, "_preview_mode", "image")
                if mode == "video":
                    self.preview_image.hide()
                    self.preview_video.show()
                    self.preview_video.raise_()
                elif mode == "gif":
                    self.preview_video.hide()
                    self.preview_image.show()
                    self.preview_image.raise_()
                else:
                    self.preview_video.hide()
                    self.preview_image.show()
                    self.preview_image.raise_()
            except Exception:
                pass
            for b in (self.preview_prev_btn, self.preview_next_btn):
                b.show()
                b.raise_()
            self.preview_open_btn.hide()
            if hasattr(self, "timeline_hover_thumb"):
                self.timeline_hover_thumb.raise_()
        except Exception:
            pass

    def _init_shortcuts(self):
        self._main_shortcuts = []

        def _mk(seq, fn):
            try:
                sc = QShortcut(QKeySequence(seq), self)
                sc.setContext(Qt.WidgetWithChildrenShortcut)
                sc.activated.connect(fn)
                self._main_shortcuts.append(sc)
            except Exception:
                pass

        _mk("Ctrl+N", self._new_project_shortcut)
        _mk("Ctrl+O", self._open_project_shortcut)
        _mk("Ctrl+S", self._save_project_shortcut)
        _mk("Ctrl+Shift+S", self._save_project_as_shortcut)
        _mk("Ctrl+Z", self._undo_action)
        _mk("Ctrl+Y", self._redo_action)
        _mk("Ctrl+Shift+Z", self._redo_action)
        _mk("Ctrl+Q", self.close)
        _mk("Ctrl+I", self.on_load)
        _mk("Ctrl+E", self.on_export)
        _mk("F11", self._toggle_window_fullscreen)

        _mk("Space", self._toggle_preview_play_pause)
        _mk("Left", lambda: self._shortcut_seek_relative(-1))
        _mk("Right", lambda: self._shortcut_seek_relative(1))
        _mk("Shift+Left", lambda: self._shortcut_seek_relative(-5))
        _mk("Shift+Right", lambda: self._shortcut_seek_relative(5))
        _mk("Home", self._shortcut_seek_home)
        _mk("End", self._shortcut_seek_end)
        _mk("M", self._toggle_preview_mute)

        _mk("Ctrl+B", self._shortcut_split_clip)
        _mk("Delete", self._shortcut_delete_selection)
        _mk("Ctrl+D", self._shortcut_duplicate_selection)
        _mk("Ctrl+R", self._shortcut_change_speed)
        _mk("Ctrl+G", self._shortcut_group_selection)
        _mk("Ctrl+Shift+G", self._shortcut_ungroup_selection)

        _mk("Ctrl++", lambda: self._shortcut_timeline_zoom(True))
        _mk("Ctrl+=", lambda: self._shortcut_timeline_zoom(True))
        _mk("Ctrl+-", lambda: self._shortcut_timeline_zoom(False))

    def _dispatch_editor_action(self, method_name, *args, **kwargs):
        try:
            if not bool(getattr(self, "_embedded_editor_active", False)):
                return False
            ed = getattr(self, "_embedded_editor_widget", None)
            if ed is None:
                return False
            fn = getattr(ed, str(method_name), None)
            if fn is None:
                return False
            fn(*args, **kwargs)
            return True
        except Exception:
            return False

    def _editor_frame_step_ms(self):
        try:
            fps = int(getattr(self, "render_fps", 24) or 24)
        except Exception:
            fps = 24
        fps = max(1, min(240, fps))
        return max(1, int(round(1000.0 / float(fps))))

    def _shortcut_seek_relative(self, frame_steps):
        if self._dispatch_editor_action("_timeline_seek_relative", int(frame_steps) * self._editor_frame_step_ms()):
            return
        self._seek_preview_relative(int(frame_steps) * max(80, self._editor_frame_step_ms()))

    def _shortcut_seek_home(self):
        if self._dispatch_editor_action("_timeline_seek_home"):
            return
        try:
            if self._preview_mode == "video" and self._preview_player is not None:
                self._preview_player.setPosition(0)
                return
            if self._preview_mode == "gif" and self._preview_gif_movie is not None:
                self._preview_gif_movie.jumpToFrame(0)
        except Exception:
            pass

    def _shortcut_seek_end(self):
        if self._dispatch_editor_action("_timeline_seek_end"):
            return
        try:
            if self._preview_mode == "video" and self._preview_player is not None:
                dur = int(self._preview_duration_ms or self._preview_player.duration() or 0)
                self._preview_player.setPosition(max(0, dur))
                return
            if self._preview_mode == "gif" and self._preview_gif_movie is not None:
                total = max(1, int(getattr(self, "_preview_gif_frames", 1) or 1))
                self._preview_gif_movie.jumpToFrame(max(0, total - 1))
        except Exception:
            pass

    def _shortcut_split_clip(self):
        ed = getattr(self, "_embedded_editor_widget", None)
        if ed is not None and bool(getattr(self, "_embedded_editor_active", False)):
            try:
                t_ms = int(ed.time_slider.value()) if hasattr(ed, "time_slider") else 0
                ed._split_selected_clip_at_time(t_ms)
            except Exception:
                pass

    def _shortcut_delete_selection(self):
        if self._dispatch_editor_action("_delete_selected_entity"):
            return
        try:
            item = self._selected_gallery_item()
            if item is None:
                return
            row = int(self.gallery_list.row(item))
            if row < 0:
                return
            self.gallery_list.takeItem(row)
            self.gallery_empty.setVisible(self.gallery_list.count() == 0)
            if self.gallery_list.count() > 0:
                self.gallery_list.setCurrentRow(max(0, min(row, self.gallery_list.count() - 1)))
            else:
                self.current_path = None
                self.current_output = None
                self._preview_base_pil = None
                if hasattr(self, "preview_image"):
                    self.preview_image.clear()
        except Exception:
            pass

    def _shortcut_duplicate_selection(self):
        if self._dispatch_editor_action("_duplicate_selected_clip"):
            return
        try:
            item = self._selected_gallery_item()
            if item is None:
                return
            data = item.data(Qt.UserRole) if item is not None else None
            if not isinstance(data, dict):
                return
            pil = data.get("pil", None)
            if pil is None:
                try:
                    p = str(data.get("path", "") or "").strip()
                    mt = str(data.get("type", "image") or "image")
                    if p and os.path.exists(p):
                        if mt in ("video", "gif"):
                            pil = self._get_first_frame(p)
                        else:
                            pil = Image.open(p).convert("RGB")
                except Exception:
                    pil = None
            if pil is None:
                return
            media_type = str(data.get("type", data.get("media_type", "image")) or "image")
            path = str(data.get("path", "") or "") or None
            self._add_gallery_item(pil.copy() if hasattr(pil, "copy") else pil, path=path, media_type=media_type)
            self.gallery_list.setCurrentRow(max(0, self.gallery_list.count() - 1))
        except Exception:
            pass

    def _shortcut_change_speed(self):
        if self._dispatch_editor_action("_change_selected_clip_speed"):
            return
        try:
            opts = ["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"]
            cur = str(self.player_speed_combo.currentText() if hasattr(self, "player_speed_combo") else "1.0x")
            if cur in opts:
                i = opts.index(cur)
                nxt = opts[(i + 1) % len(opts)]
            else:
                nxt = "1.0x"
            if hasattr(self, "player_speed_combo"):
                self.player_speed_combo.setCurrentText(nxt)
        except Exception:
            pass

    def _shortcut_group_selection(self):
        self._dispatch_editor_action("_group_selected_clip")

    def _shortcut_ungroup_selection(self):
        self._dispatch_editor_action("_ungroup_selected_clip")

    def _shortcut_timeline_zoom(self, zoom_in):
        if self._dispatch_editor_action("_timeline_zoom_in" if bool(zoom_in) else "_timeline_zoom_out"):
            return
        try:
            factor = 1.08 if bool(zoom_in) else (1.0 / 1.08)
            mode = str(getattr(self, "_preview_mode", "image") or "image")
            max_zoom = 8.0 if mode == "image" else (4.0 if mode == "gif" else 3.0)
            self._preview_zoom_target = max(0.2, min(max_zoom, float(getattr(self, "_preview_zoom_target", self.preview_zoom)) * factor))
            if not self._preview_motion_timer.isActive():
                self._preview_motion_timer.start()
        except Exception:
            pass

    def _register_undo_widget(self, widget):
        try:
            if widget is None:
                return
            self._undo_widgets.add(widget)
            widget.installEventFilter(self)
            try:
                if isinstance(widget, QSlider):
                    widget.valueChanged.connect(lambda *_: self._schedule_live_preview())
                elif isinstance(widget, QSpinBox):
                    widget.valueChanged.connect(lambda *_: self._schedule_live_preview())
                elif isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(lambda *_: self._schedule_live_preview())
                elif isinstance(widget, QCheckBox):
                    widget.stateChanged.connect(lambda *_: self._schedule_live_preview())
                elif isinstance(widget, QLineEdit):
                    widget.textChanged.connect(lambda *_: self._schedule_live_preview())
            except Exception:
                pass
        except Exception:
            pass

    def _register_undo_widgets(self):
        names = [
            "style_combo", "width_slider", "font_slider", "fps_spin", "charset_input",
            "contrast_slider", "gamma_slider", "invert_chk", "keep_size_chk",
            "denoise_chk", "sharpen_chk", "edge_chk", "watermark_chk", "watermark_text_edit",
            "out_w", "out_h", "auto_size_chk",
            "codec_combo", "bitrate_combo", "threads_spin", "preset_combo", "crf_spin",
            "keep_audio_chk", "pro_scanlines_chk", "pro_bloom_slider", "pro_vignette_slider", "pro_poster_spin", "pro_preset_combo", "pro_grain_slider", "pro_chroma_spin",
            "pro_color_boost_slider", "pro_clarity_slider", "pro_motion_blur_slider",
            "pro_scan_strength_slider", "pro_scan_step_spin", "pro_curvature_slider", "pro_concavity_slider",
            "pro_curvature_center_x_slider", "pro_curvature_expand_slider", "pro_curvature_type_combo",
            "pro_ribbing_slider", "pro_glitch_slider",
            "pro_glitch_density_slider", "pro_glitch_shift_slider", "pro_glitch_rgb_spin",
            "pro_glitch_block_spin", "pro_glitch_jitter_spin", "pro_glitch_noise_slider",
            "theme_combo", "trail_combo",
        ]
        for n in names:
            self._register_undo_widget(getattr(self, n, None))

    def _seek_preview_relative(self, delta_ms):
        try:
            if self._preview_mode == "video" and self._preview_player is not None:
                dur = int(self._preview_duration_ms or self._preview_player.duration() or 0)
                cur = int(self._preview_player.position() or 0)
                nxt = max(0, min(max(0, dur), cur + int(delta_ms)))
                self._preview_player.setPosition(nxt)
                return
            if self._preview_mode == "gif" and self._preview_gif_movie is not None:
                total = max(1, int(self._preview_gif_frames or 1))
                cur = int(self._preview_gif_movie.currentFrameNumber() or 0)
                step = 1 if delta_ms > 0 else -1
                idx = max(0, min(total - 1, cur + step))
                self._preview_gif_movie.jumpToFrame(idx)
        except Exception:
            pass

    def _toggle_preview_mute(self):
        try:
            if self._preview_audio is None:
                return
            new_muted = not bool(self._preview_audio.isMuted())
            self._preview_audio.setMuted(new_muted)
        except Exception:
            pass

    def _capture_state_snapshot(self):
        snap = {}
        try:
            snap = {
                "style": self.style_combo.currentText() if hasattr(self, "style_combo") else self.style,
                "width": int(self.width_slider.value()) if hasattr(self, "width_slider") else int(self.width_chars),
                "font": int(self.font_slider.value()) if hasattr(self, "font_slider") else int(self.font_size),
                "fps": int(self.fps_spin.value()) if hasattr(self, "fps_spin") else int(self.render_fps),
                "contrast": int(self.contrast_slider.value()) if hasattr(self, "contrast_slider") else int(self.contrast),
                "gamma": int(self.gamma_slider.value()) if hasattr(self, "gamma_slider") else int(self.gamma_pct),
                "invert": bool(self.invert_chk.isChecked()) if hasattr(self, "invert_chk") else bool(self.invert),
                "keep_size": bool(self.keep_size_chk.isChecked()) if hasattr(self, "keep_size_chk") else bool(self.keep_size),
                "denoise": bool(self.denoise_chk.isChecked()) if hasattr(self, "denoise_chk") else bool(self.denoise),
                "sharpen": bool(self.sharpen_chk.isChecked()) if hasattr(self, "sharpen_chk") else bool(self.sharpen),
                "edge": bool(self.edge_chk.isChecked()) if hasattr(self, "edge_chk") else bool(self.edge_boost),
                "charset": self.charset_input.currentText() if hasattr(self, "charset_input") else self.ascii_chars,
                "scale": int(self.render_scale),
                "out_w": int(self.out_w.value()) if hasattr(self, "out_w") else int(self.render_out_w),
                "out_h": int(self.out_h.value()) if hasattr(self, "out_h") else int(self.render_out_h),
                "auto_size": bool(self.auto_size_chk.isChecked()) if hasattr(self, "auto_size_chk") else True,
                "fg_hex": self.fg_hex,
                "bg_hex": self.bg_hex,
                "pro_scanlines": bool(self.pro_scanlines_chk.isChecked()) if hasattr(self, "pro_scanlines_chk") else bool(self.pro_scanlines),
                "pro_bloom": int(self.pro_bloom_slider.value()) if hasattr(self, "pro_bloom_slider") else int(self.pro_bloom),
                "pro_vignette": int(self.pro_vignette_slider.value()) if hasattr(self, "pro_vignette_slider") else int(self.pro_vignette),
                "pro_poster_bits": int(self.pro_poster_spin.value()) if hasattr(self, "pro_poster_spin") else int(self.pro_poster_bits),
                "pro_grain": int(self.pro_grain_slider.value()) if hasattr(self, "pro_grain_slider") else int(getattr(self, "pro_grain", 0)),
                "pro_chroma": int(self.pro_chroma_spin.value()) if hasattr(self, "pro_chroma_spin") else int(getattr(self, "pro_chroma", 0)),
                "pro_color_boost": int(self.pro_color_boost_slider.value()) if hasattr(self, "pro_color_boost_slider") else int(getattr(self, "pro_color_boost", 0)),
                "pro_clarity": int(self.pro_clarity_slider.value()) if hasattr(self, "pro_clarity_slider") else int(getattr(self, "pro_clarity", 0)),
                "pro_motion_blur": int(self.pro_motion_blur_slider.value()) if hasattr(self, "pro_motion_blur_slider") else int(getattr(self, "pro_motion_blur", 0)),
                "pro_scan_strength": int(self.pro_scan_strength_slider.value()) if hasattr(self, "pro_scan_strength_slider") else int(getattr(self, "pro_scan_strength", 28)),
                "pro_scan_step": int(self.pro_scan_step_spin.value()) if hasattr(self, "pro_scan_step_spin") else int(getattr(self, "pro_scan_step", 3)),
                "pro_curvature": int(self.pro_curvature_slider.value()) if hasattr(self, "pro_curvature_slider") else int(getattr(self, "pro_curvature", 0)),
                "pro_concavity": int(self.pro_concavity_slider.value()) if hasattr(self, "pro_concavity_slider") else int(getattr(self, "pro_concavity", 0)),
                "pro_curvature_center_x": int(self.pro_curvature_center_x_slider.value()) if hasattr(self, "pro_curvature_center_x_slider") else int(getattr(self, "pro_curvature_center_x", 0)),
                "pro_curvature_expand": int(self.pro_curvature_expand_slider.value()) if hasattr(self, "pro_curvature_expand_slider") else int(getattr(self, "pro_curvature_expand", 0)),
                "pro_curvature_type": str(self.pro_curvature_type_combo.currentText()) if hasattr(self, "pro_curvature_type_combo") else str(getattr(self, "pro_curvature_type", "spherical") or "spherical"),
                "pro_ribbing": int(self.pro_ribbing_slider.value()) if hasattr(self, "pro_ribbing_slider") else int(getattr(self, "pro_ribbing", 0)),
                "pro_glitch": int(self.pro_glitch_slider.value()) if hasattr(self, "pro_glitch_slider") else int(getattr(self, "pro_glitch", 0)),
                "pro_glitch_density": int(self.pro_glitch_density_slider.value()) if hasattr(self, "pro_glitch_density_slider") else int(getattr(self, "pro_glitch_density", 35)),
                "pro_glitch_shift": int(self.pro_glitch_shift_slider.value()) if hasattr(self, "pro_glitch_shift_slider") else int(getattr(self, "pro_glitch_shift", 42)),
                "pro_glitch_rgb": int(self.pro_glitch_rgb_spin.value()) if hasattr(self, "pro_glitch_rgb_spin") else int(getattr(self, "pro_glitch_rgb", 1)),
                "pro_glitch_block": int(self.pro_glitch_block_spin.value()) if hasattr(self, "pro_glitch_block_spin") else int(getattr(self, "pro_glitch_block", 10)),
                "pro_glitch_jitter": int(self.pro_glitch_jitter_spin.value()) if hasattr(self, "pro_glitch_jitter_spin") else int(getattr(self, "pro_glitch_jitter", 1)),
                "pro_glitch_noise": int(self.pro_glitch_noise_slider.value()) if hasattr(self, "pro_glitch_noise_slider") else int(getattr(self, "pro_glitch_noise", 12)),
                "watermark": bool(self.watermark_chk.isChecked()) if hasattr(self, "watermark_chk") else bool(getattr(self, "show_watermark", True)),
                "watermark_text": str(self.watermark_text_edit.text()) if hasattr(self, "watermark_text_edit") else str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK),
                "theme": self.theme_combo.currentText() if hasattr(self, "theme_combo") else str(getattr(self, "theme", "dark")),
                "trail_level_text": self.trail_combo.currentText() if hasattr(self, "trail_combo") else str(getattr(self, "trail_level", "med")),
                "custom_theme_background": str(getattr(self, "custom_theme_background", "") or ""),
                "custom_theme_bg": str(getattr(self, "custom_theme_bg", "#0c1018") or "#0c1018"),
                "custom_theme_fg": str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff"),
                "custom_theme_accent": str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff"),
                "custom_theme_panel": str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29"),
                "icon_pack_path": str(getattr(self, "icon_pack_path", "") or ""),
                "icon_pack_url": str(getattr(self, "icon_pack_url", "") or ""),
                "row": int(self.gallery_list.currentRow()) if hasattr(self, "gallery_list") else -1,
                "gallery_scroll": int(self.gallery_list.verticalScrollBar().value()) if hasattr(self, "gallery_list") and self.gallery_list.verticalScrollBar() is not None else 0,
            }
        except Exception:
            pass
        return snap

    def _apply_state_snapshot(self, snap):
        if not isinstance(snap, dict):
            return
        self._state_restore_lock = True
        try:
            if hasattr(self, "style_combo") and "style" in snap:
                self.style_combo.setCurrentText(str(snap.get("style", self.style_combo.currentText())))
            if hasattr(self, "width_slider") and "width" in snap:
                self.width_slider.setValue(int(snap.get("width", self.width_slider.value())))
            if hasattr(self, "font_slider") and "font" in snap:
                self.font_slider.setValue(int(snap.get("font", self.font_slider.value())))
            if hasattr(self, "fps_spin") and "fps" in snap:
                self.fps_spin.setValue(int(snap.get("fps", self.fps_spin.value())))
            if hasattr(self, "contrast_slider") and "contrast" in snap:
                self.contrast_slider.setValue(int(snap.get("contrast", self.contrast_slider.value())))
            if hasattr(self, "gamma_slider") and "gamma" in snap:
                self.gamma_slider.setValue(int(snap.get("gamma", self.gamma_slider.value())))
            if hasattr(self, "invert_chk"):
                self.invert_chk.setChecked(bool(snap.get("invert", self.invert_chk.isChecked())))
            if hasattr(self, "keep_size_chk"):
                self.keep_size_chk.setChecked(bool(snap.get("keep_size", self.keep_size_chk.isChecked())))
            if hasattr(self, "denoise_chk"):
                self.denoise_chk.setChecked(bool(snap.get("denoise", self.denoise_chk.isChecked())))
            if hasattr(self, "sharpen_chk"):
                self.sharpen_chk.setChecked(bool(snap.get("sharpen", self.sharpen_chk.isChecked())))
            if hasattr(self, "edge_chk"):
                self.edge_chk.setChecked(bool(snap.get("edge", self.edge_chk.isChecked())))
            if hasattr(self, "charset_input"):
                self.charset_input.setCurrentText(str(snap.get("charset", self.charset_input.currentText())))
            if "scale" in snap:
                self._set_scale(int(snap.get("scale", self.render_scale)))
            if hasattr(self, "out_w"):
                self.out_w.setValue(int(snap.get("out_w", self.out_w.value())))
            if hasattr(self, "out_h"):
                self.out_h.setValue(int(snap.get("out_h", self.out_h.value())))
            if hasattr(self, "auto_size_chk"):
                self.auto_size_chk.setChecked(bool(snap.get("auto_size", self.auto_size_chk.isChecked())))
            self.fg_hex = str(snap.get("fg_hex", self.fg_hex))
            self.bg_hex = str(snap.get("bg_hex", self.bg_hex))
            if hasattr(self, "pro_scanlines_chk"):
                self.pro_scanlines_chk.setChecked(bool(snap.get("pro_scanlines", self.pro_scanlines_chk.isChecked())))
            if hasattr(self, "pro_bloom_slider"):
                self.pro_bloom_slider.setValue(int(snap.get("pro_bloom", self.pro_bloom_slider.value())))
            if hasattr(self, "pro_vignette_slider"):
                self.pro_vignette_slider.setValue(int(snap.get("pro_vignette", self.pro_vignette_slider.value())))
            if hasattr(self, "pro_poster_spin"):
                self.pro_poster_spin.setValue(int(snap.get("pro_poster_bits", self.pro_poster_spin.value())))
            if hasattr(self, "pro_grain_slider"):
                self.pro_grain_slider.setValue(int(snap.get("pro_grain", self.pro_grain_slider.value())))
            if hasattr(self, "pro_chroma_spin"):
                self.pro_chroma_spin.setValue(int(snap.get("pro_chroma", self.pro_chroma_spin.value())))
            if hasattr(self, "pro_color_boost_slider"):
                self.pro_color_boost_slider.setValue(int(snap.get("pro_color_boost", self.pro_color_boost_slider.value())))
            if hasattr(self, "pro_clarity_slider"):
                self.pro_clarity_slider.setValue(int(snap.get("pro_clarity", self.pro_clarity_slider.value())))
            if hasattr(self, "pro_motion_blur_slider"):
                self.pro_motion_blur_slider.setValue(int(snap.get("pro_motion_blur", self.pro_motion_blur_slider.value())))
            if hasattr(self, "pro_scan_strength_slider"):
                self.pro_scan_strength_slider.setValue(int(snap.get("pro_scan_strength", self.pro_scan_strength_slider.value())))
            if hasattr(self, "pro_scan_step_spin"):
                self.pro_scan_step_spin.setValue(int(snap.get("pro_scan_step", self.pro_scan_step_spin.value())))
            if hasattr(self, "pro_curvature_slider"):
                self.pro_curvature_slider.setValue(int(snap.get("pro_curvature", self.pro_curvature_slider.value())))
            if hasattr(self, "pro_concavity_slider"):
                self.pro_concavity_slider.setValue(int(snap.get("pro_concavity", self.pro_concavity_slider.value())))
            if hasattr(self, "pro_curvature_center_x_slider"):
                self.pro_curvature_center_x_slider.setValue(int(snap.get("pro_curvature_center_x", self.pro_curvature_center_x_slider.value())))
            if hasattr(self, "pro_curvature_expand_slider"):
                self.pro_curvature_expand_slider.setValue(int(snap.get("pro_curvature_expand", self.pro_curvature_expand_slider.value())))
            if hasattr(self, "pro_curvature_type_combo"):
                self.pro_curvature_type_combo.setCurrentText(str(snap.get("pro_curvature_type", self.pro_curvature_type_combo.currentText()) or self.pro_curvature_type_combo.currentText()))
            if hasattr(self, "pro_ribbing_slider"):
                self.pro_ribbing_slider.setValue(int(snap.get("pro_ribbing", self.pro_ribbing_slider.value())))
            if hasattr(self, "pro_glitch_slider"):
                self.pro_glitch_slider.setValue(int(snap.get("pro_glitch", self.pro_glitch_slider.value())))
            if hasattr(self, "pro_glitch_density_slider"):
                self.pro_glitch_density_slider.setValue(int(snap.get("pro_glitch_density", self.pro_glitch_density_slider.value())))
            if hasattr(self, "pro_glitch_shift_slider"):
                self.pro_glitch_shift_slider.setValue(int(snap.get("pro_glitch_shift", self.pro_glitch_shift_slider.value())))
            if hasattr(self, "pro_glitch_rgb_spin"):
                self.pro_glitch_rgb_spin.setValue(int(snap.get("pro_glitch_rgb", self.pro_glitch_rgb_spin.value())))
            if hasattr(self, "pro_glitch_block_spin"):
                self.pro_glitch_block_spin.setValue(int(snap.get("pro_glitch_block", self.pro_glitch_block_spin.value())))
            if hasattr(self, "pro_glitch_jitter_spin"):
                self.pro_glitch_jitter_spin.setValue(int(snap.get("pro_glitch_jitter", self.pro_glitch_jitter_spin.value())))
            if hasattr(self, "pro_glitch_noise_slider"):
                self.pro_glitch_noise_slider.setValue(int(snap.get("pro_glitch_noise", self.pro_glitch_noise_slider.value())))
            if hasattr(self, "watermark_chk"):
                self.watermark_chk.setChecked(bool(snap.get("watermark", self.watermark_chk.isChecked())))
            if "watermark_text" in snap:
                txt = str(snap.get("watermark_text", getattr(self, "watermark_text", CORE_WATERMARK)) or CORE_WATERMARK)
                self.watermark_text = txt
                if hasattr(self, "watermark_text_edit"):
                    self.watermark_text_edit.setText(txt)
            if "theme" in snap:
                self.theme = str(snap.get("theme", getattr(self, "theme", "dark")) or getattr(self, "theme", "dark"))
                if self.theme not in THEME_NAMES:
                    self.theme = "dark"
                self._apply_theme(self.theme)
            if hasattr(self, "trail_combo") and "trail_level_text" in snap:
                self.trail_combo.setCurrentText(str(snap.get("trail_level_text", self.trail_combo.currentText())))
            self.custom_theme_background = str(snap.get("custom_theme_background", getattr(self, "custom_theme_background", "")) or "")
            self.custom_theme_bg = str(snap.get("custom_theme_bg", getattr(self, "custom_theme_bg", "#0c1018")) or "#0c1018")
            self.custom_theme_fg = str(snap.get("custom_theme_fg", getattr(self, "custom_theme_fg", "#e8f2ff")) or "#e8f2ff")
            self.custom_theme_accent = str(snap.get("custom_theme_accent", getattr(self, "custom_theme_accent", "#5ec8ff")) or "#5ec8ff")
            self.custom_theme_panel = str(snap.get("custom_theme_panel", getattr(self, "custom_theme_panel", "#151c29")) or "#151c29")
            self.icon_pack_path = str(snap.get("icon_pack_path", getattr(self, "icon_pack_path", "")) or "")
            self.icon_pack_url = str(snap.get("icon_pack_url", getattr(self, "icon_pack_url", "")) or "")
            try:
                if str(getattr(self, "theme", "dark")) == "custom":
                    self._apply_theme("custom")
                self._icon_remote_failed = set()
                self._refresh_button_icons()
            except Exception:
                pass
            row = int(snap.get("row", -1))
            old_scroll = None
            try:
                if hasattr(self, "gallery_list") and self.gallery_list.verticalScrollBar() is not None:
                    old_scroll = int(self.gallery_list.verticalScrollBar().value())
            except Exception:
                old_scroll = None
            if row >= 0 and row < self.gallery_list.count():
                self.gallery_list.setCurrentRow(row)
                item = self.gallery_list.item(row)
                self._show_gallery_item(item, open_player=False)
            try:
                sb = self.gallery_list.verticalScrollBar()
                if sb is not None:
                    sb.setValue(int(snap.get("gallery_scroll", old_scroll if old_scroll is not None else sb.value())))
            except Exception:
                pass
            self._schedule_live_preview()
        except Exception:
            pass
        finally:
            self._state_restore_lock = False

    def _push_undo_state(self):
        if self._state_restore_lock:
            return
        try:
            self._undo_stack.append(self._capture_state_snapshot())
            if len(self._undo_stack) > 60:
                self._undo_stack = self._undo_stack[-60:]
            self._redo_stack.clear()
        except Exception:
            pass

    def _undo_action(self):
        try:
            if not self._undo_stack:
                return
            cur = self._capture_state_snapshot()
            snap = self._undo_stack.pop()
            self._redo_stack.append(cur)
            self._apply_state_snapshot(snap)
        except Exception:
            pass

    def _redo_action(self):
        try:
            if not self._redo_stack:
                return
            cur = self._capture_state_snapshot()
            snap = self._redo_stack.pop()
            self._undo_stack.append(cur)
            self._apply_state_snapshot(snap)
        except Exception:
            pass

    def _toggle_player_focus_mode(self):
        try:
            if bool(getattr(self, "_embedded_editor_active", False)):
                return
            self._preview_focus_mode = not bool(self._preview_focus_mode)
            on = self._preview_focus_mode
            if on:
                self.gallery_frame.hide()
                if hasattr(self, "right_frame"):
                    self.right_frame.hide()
            else:
                self.gallery_frame.show()
                if hasattr(self, "right_frame"):
                    self.right_frame.show()
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            self.preview_open_btn.setText(tr.get("player_focus_exit", "Exit focus") if on else tr.get("player_focus", "Focus mode"))
            if hasattr(self, "player_fullscreen_btn"):
                self.player_fullscreen_btn.setText(tr.get("player_focus_exit", "Exit focus") if on else tr.get("player_focus", "Focus mode"))
            self.preview_prev_btn.show()
            self.preview_next_btn.show()
            self.preview_open_btn.show()
            self._trail_overlay_stack_dirty = True
            self._sync_trail_overlay_stack()
            try:
                lay = self.centralWidget().layout()
                if lay is not None:
                    lay.activate()
                QApplication.processEvents()
            except Exception:
                pass
            QTimer.singleShot(0, self._layout_preview_controls)
            QTimer.singleShot(60, self._layout_preview_controls)
            QTimer.singleShot(140, self._layout_preview_controls)
            if self._preview_mode == "image" and self._preview_base_pil is not None:
                QTimer.singleShot(0, self._render_preview_scaled)
                QTimer.singleShot(90, self._render_preview_scaled)
            elif self._preview_mode in ("video", "gif"):
                QTimer.singleShot(0, self._apply_preview_media_transform)
                QTimer.singleShot(90, self._apply_preview_media_transform)
        except Exception:
            pass

    def _toggle_window_fullscreen(self):
        try:
            for w in QApplication.topLevelWidgets():
                if isinstance(w, WelcomeDialog) and w.isVisible():
                    return
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        except Exception:
            pass

    def _set_preview_mode(self, mode):
        self._preview_mode = mode
        self._preview_zoom_target = float(self.preview_zoom)
        self._preview_pan_target = [float(self.preview_pan[0]), float(self.preview_pan[1])]
        is_media = mode in ("video", "gif")
        try:
            self.player_play_btn.setEnabled(is_media)
            self.player_stop_btn.setEnabled(is_media)
            self.player_repeat_btn.setEnabled(is_media)
            self.player_seek_slider.setEnabled(is_media)
            self.player_speed_combo.setEnabled(is_media)
            self.player_volume_slider.setEnabled(mode == "video")
            self._update_player_labels(0, 0)
            self._update_player_buttons()
        except Exception:
            pass

    def _update_player_labels(self, cur_ms, dur_ms):
        try:
            def fmt(ms):
                s = max(0, int(ms // 1000))
                return f"{s//60:02d}:{s%60:02d}"
            self.player_time_label.setText(f"{fmt(cur_ms)} / {fmt(dur_ms)}")
        except Exception:
            pass

    def _update_player_buttons(self):
        try:
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            playing = False
            if self._preview_mode == "video" and self._preview_player is not None:
                playing = self._preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            elif self._preview_mode == "gif" and self._preview_gif_movie is not None:
                playing = self._preview_gif_movie.state() == QMovie.Running
            self.player_play_btn.setText(tr.get("pause", "Pause") if playing else tr.get("play", "Play"))
            self.player_repeat_btn.setText(tr.get("repeat_loop", "Loop") if self._preview_loop else tr.get("repeat_once", "Once"))
        except Exception:
            pass

    def _init_preview_video_backend(self):
        if self._preview_player is not None:
            return
        self._preview_player = QMediaPlayer(self)
        self._preview_audio = QAudioOutput(self)
        self._preview_player.setAudioOutput(self._preview_audio)
        self._preview_player.setVideoOutput(self.preview_video)
        self._preview_player.positionChanged.connect(self._on_preview_position_changed)
        self._preview_player.durationChanged.connect(self._on_preview_duration_changed)
        self._preview_player.playbackStateChanged.connect(lambda *_: self._update_player_buttons())
        self._preview_player.mediaStatusChanged.connect(self._on_preview_media_status_changed)

    def _start_preview_video(self, path):
        try:
            self._preview_base_pil = None
            self.preview_zoom = 1.0
            self.preview_pan = [0, 0]
            self._preview_zoom_target = 1.0
            self._preview_pan_target = [0.0, 0.0]
            self._preview_native_size = None
            self._stop_preview_gif()
            self._init_preview_video_backend()
            self._preview_duration_ms = 0
            self._preview_player_seeking = False
            self._preview_last_pos_ms = 0
            self._preview_audio.setVolume(max(0.0, min(1.0, float(self.player_volume_slider.value()) / 100.0)))
            try:
                cap = cv2.VideoCapture(path)
                if cap is not None and cap.isOpened():
                    vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                    if vw > 0 and vh > 0:
                        self._preview_native_size = (vw, vh)
                if cap is not None:
                    cap.release()
            except Exception:
                self._preview_native_size = None
            try:
                self.preview_video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
            except Exception:
                try:
                    self.preview_video.setAspectRatioMode(Qt.KeepAspectRatio)
                except Exception:
                    pass
            self.preview_video.show()
            self.preview_image.hide()
            try:
                self.preview_video.clearMask()
                self.preview_image.clearMask()
            except Exception:
                pass
            self.preview_overlay.hide()
            self.preview_label.setText("")
            self._preview_player.setPlaybackRate(float(self._preview_rate))
            self._preview_player.setSource(QUrl.fromLocalFile(path))
            self._preview_player.play()
            self._set_preview_mode("video")
            self._schedule_preview_media_transform(0)
            self._update_player_labels(0, 0)
            self._layout_preview_controls()
            QTimer.singleShot(0, self._layout_preview_controls)
            QTimer.singleShot(80, self._layout_preview_controls)
        except Exception:
            pass

    def _probe_gif_timing(self, path):
        frames = 0
        total_ms = 0
        try:
            with Image.open(path) as im:
                while True:
                    frames += 1
                    total_ms += int(im.info.get("duration", 80) or 80)
                    try:
                        im.seek(im.tell() + 1)
                    except EOFError:
                        break
        except Exception:
            pass
        return max(0, frames), max(0, total_ms)

    def _start_preview_gif(self, path):
        try:
            self._preview_base_pil = None
            self.preview_zoom = 1.0
            self.preview_pan = [0, 0]
            self._preview_zoom_target = 1.0
            self._preview_pan_target = [0.0, 0.0]
            self._preview_native_size = None
            self._stop_preview_video()
            if self._preview_gif_movie is not None:
                try:
                    self._preview_gif_movie.stop()
                except Exception:
                    pass
            try:
                with Image.open(path) as _gif_im:
                    self._preview_native_size = _gif_im.size
            except Exception:
                self._preview_native_size = None
            mv = QMovie(path)
            mv.setCacheMode(QMovie.CacheNone)
            self._preview_gif_frames, self._preview_gif_total_ms = self._probe_gif_timing(path)
            self._preview_duration_ms = int(self._preview_gif_total_ms)
            self.preview_image.setMovie(mv)
            self._preview_gif_movie = mv
            self.preview_video.hide()
            self.preview_image.show()
            self.preview_overlay.hide()
            mv.frameChanged.connect(self._on_preview_gif_frame_changed)
            try:
                mv.finished.connect(self._on_preview_gif_finished)
                mv.setLoopCount(-1 if self._preview_loop else 1)
            except Exception:
                pass
            try:
                mv.setSpeed(max(10, int(float(self._preview_rate) * 100)))
            except Exception:
                pass
            mv.start()
            self.preview_label.setText("")
            self._set_preview_mode("gif")
            self._schedule_preview_media_transform(0)
            self._update_player_labels(0, self._preview_duration_ms)
            self._layout_preview_controls()
            QTimer.singleShot(0, self._layout_preview_controls)
            QTimer.singleShot(80, self._layout_preview_controls)
        except Exception:
            pass

    def _stop_preview_video(self):
        try:
            if self._preview_player is not None:
                self._preview_player.stop()
            self.preview_video.hide()
        except Exception:
            pass

    def _stop_preview_gif(self):
        try:
            if self._preview_gif_movie is not None:
                self._preview_gif_movie.stop()
            self._preview_gif_movie = None
            self._preview_gif_frames = 0
            self._preview_gif_total_ms = 0
            try:
                self.preview_image.setMovie(None)
            except Exception:
                pass
        except Exception:
            pass

    def _hide_timeline_hover(self):
        try:
            self.timeline_hover_thumb.hide()
            self.timeline_hover_thumb.clear()
        except Exception:
            pass

    def _stop_preview_media(self):
        try:
            self._stop_preview_video()
            self._stop_preview_gif()
            self._preview_native_size = None
            self._preview_zoom_target = float(self.preview_zoom)
            self._preview_pan_target = [float(self.preview_pan[0]), float(self.preview_pan[1])]
            self._hide_timeline_hover()
            try:
                self.preview_image.clearMask()
                self.preview_video.clearMask()
            except Exception:
                pass
            self.preview_image.show()
            self._set_preview_mode("image")
        except Exception:
            pass

    def _on_preview_position_changed(self, pos):
        if self._preview_player_seeking:
            return
        try:
            self._preview_last_pos_ms = int(pos or 0)
            dur = max(1, int(self._preview_duration_ms or (self._preview_player.duration() if self._preview_player else 0) or 1))
            self.player_seek_slider.setValue(int(max(0, min(1000, pos * 1000 / dur))))
            self._update_player_labels(int(pos), int(dur))
            if self._preview_mode == "video":
                try:
                    if (float(self.preview_zoom) > 1.001) or (abs(int(self.preview_pan[0])) > 0) or (abs(int(self.preview_pan[1])) > 0):
                        now = time.time()
                        if now - float(getattr(self, "_soft_video_refresh_ts", 0.0)) > 0.04:
                            self._soft_video_refresh_ts = now
                            self._schedule_preview_media_transform(0)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_preview_duration_changed(self, dur):
        try:
            self._preview_duration_ms = int(dur or 0)
            self._update_player_labels(0, self._preview_duration_ms)
            if self._preview_mode == "video":
                self._schedule_preview_media_transform(0)
        except Exception:
            pass

    def _on_preview_media_status_changed(self, status):
        try:
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                if self._preview_loop and self._preview_player is not None:
                    self._preview_player.setPosition(0)
                    self._preview_player.play()
                else:
                    self._update_player_buttons()
        except Exception:
            pass

    def _on_preview_gif_frame_changed(self, idx):
        if self._preview_player_seeking:
            return
        try:
            total_frames = max(1, int(self._preview_gif_frames or 1))
            self.player_seek_slider.setValue(int(max(0, min(1000, idx * 1000 / total_frames))))
            cur_ms = int((idx / total_frames) * max(1, int(self._preview_duration_ms)))
            self._update_player_labels(cur_ms, int(self._preview_duration_ms))
        except Exception:
            pass

    def _on_preview_gif_finished(self):
        try:
            if self._preview_loop and self._preview_gif_movie is not None:
                self._preview_gif_movie.start()
            else:
                self._update_player_buttons()
        except Exception:
            pass

    def _toggle_preview_play_pause(self):
        try:
            if self._preview_mode == "video" and self._preview_player is not None:
                st = self._preview_player.playbackState()
                if st == QMediaPlayer.PlaybackState.PlayingState:
                    self._preview_player.pause()
                else:
                    self._preview_player.play()
            elif self._preview_mode == "gif" and self._preview_gif_movie is not None:
                st = self._preview_gif_movie.state()
                if st == QMovie.Running:
                    self._preview_gif_movie.setPaused(True)
                else:
                    if st == QMovie.NotRunning:
                        self._preview_gif_movie.start()
                    else:
                        self._preview_gif_movie.setPaused(False)
            self._update_player_buttons()
        except Exception:
            pass

    def _stop_preview_playback(self):
        try:
            if self._preview_mode == "video" and self._preview_player is not None:
                self._preview_player.pause()
                self._preview_player.setPosition(0)
                self.player_seek_slider.setValue(0)
                self._update_player_labels(0, self._preview_duration_ms)
            elif self._preview_mode == "gif" and self._preview_gif_movie is not None:
                self._preview_gif_movie.stop()
                try:
                    self._preview_gif_movie.jumpToFrame(0)
                except Exception:
                    pass
                self.player_seek_slider.setValue(0)
                self._update_player_labels(0, self._preview_duration_ms)
            self._update_player_buttons()
        except Exception:
            pass

    def _toggle_preview_repeat(self):
        self._preview_loop = not bool(self._preview_loop)
        try:
            if self._preview_gif_movie is not None:
                self._preview_gif_movie.setLoopCount(-1 if self._preview_loop else 1)
        except Exception:
            pass
        self._update_player_buttons()

    def _on_preview_seek_release(self):
        try:
            v = int(self.player_seek_slider.value())
            if self._preview_mode == "video" and self._preview_player is not None:
                dur = max(1, int(self._preview_duration_ms or self._preview_player.duration() or 1))
                self._preview_player.setPosition(int(v * dur / 1000))
            elif self._preview_mode == "gif" and self._preview_gif_movie is not None:
                total = max(1, int(self._preview_gif_frames or 1))
                idx = int(v * total / 1000)
                try:
                    self._preview_gif_movie.jumpToFrame(max(0, min(total - 1, idx)))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._preview_player_seeking = False

    def _on_preview_volume_changed(self, v):
        try:
            if self._preview_audio is not None:
                self._preview_audio.setVolume(max(0.0, min(1.0, float(v) / 100.0)))
        except Exception:
            pass

    def _on_preview_speed_changed(self, txt):
        try:
            val = float(str(txt).replace("x", ""))
        except Exception:
            val = 1.0
        self._preview_rate = max(0.25, min(4.0, float(val)))
        try:
            if self._preview_mode == "video" and self._preview_player is not None:
                self._preview_player.setPlaybackRate(self._preview_rate)
            elif self._preview_mode == "gif" and self._preview_gif_movie is not None:
                self._preview_gif_movie.setSpeed(max(10, int(self._preview_rate * 100)))
        except Exception:
            pass

    def _timeline_thumb_at_ratio(self, ratio):
        path = getattr(self, "current_path", None)
        if not path or not os.path.exists(path):
            return None
        low = path.lower()
        if not low.endswith((".mp4", ".avi", ".mov", ".mkv")):
            return None
        ratio = max(0.0, min(1.0, float(ratio)))
        bucket = int(ratio * 80)
        if self._timeline_hover_path != path:
            self._timeline_hover_cache = {}
            self._timeline_hover_path = path
        if bucket in self._timeline_hover_cache:
            return self._timeline_hover_cache[bucket]
        cap = cv2.VideoCapture(path)
        if not cap or not cap.isOpened():
            return None
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            idx = int(max(0, min(max(0, total - 1), bucket * max(1, total) / 80))) if total > 0 else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                return None
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(frame)
            pil.thumbnail((180, 100), Image.Resampling.LANCZOS)
            pm = pil_to_qpixmap(pil)
            self._timeline_hover_cache[bucket] = pm
            return pm
        except Exception:
            return None
        finally:
            try:
                cap.release()
            except Exception:
                pass

    def _show_timeline_hover(self, ratio):
        try:
            pm = self._timeline_thumb_at_ratio(ratio)
            if pm is None:
                self._hide_timeline_hover()
                return
            lbl = self.timeline_hover_thumb
            dur = max(1, int(self._preview_duration_ms))
            cur = int(dur * max(0.0, min(1.0, float(ratio))))
            s = max(0, cur // 1000)
            txt = f"{s//60:02d}:{s%60:02d}"
            # QLabel cannot show text and pixmap simultaneously; compose a single bubble pixmap.
            pad = 6
            text_h = 18
            bubble = QPixmap(pm.width() + pad * 2, pm.height() + pad * 2 + text_h)
            bubble.fill(Qt.transparent)
            qp = QPainter(bubble)
            try:
                qp.setRenderHint(QPainter.Antialiasing)
                rr = bubble.rect().adjusted(0, 0, -1, -1)
                qp.setPen(QPen(QColor(130, 180, 255, 120), 1))
                qp.setBrush(QColor(18, 22, 32, 242))
                qp.drawRoundedRect(rr, 8, 8)
                qp.drawPixmap(pad, pad, pm)
                qp.setPen(QColor(232, 237, 247))
                qp.drawText(QRect(pad, pm.height() + pad, pm.width(), text_h), Qt.AlignCenter, txt)
            finally:
                qp.end()
            lbl.setPixmap(bubble)
            lbl.resize(bubble.size())
            slider = self.player_seek_slider
            slw = max(1, slider.width())
            px = int(slw * max(0.0, min(1.0, float(ratio))))
            g = slider.mapTo(self, QPoint(0, 0))
            x = g.x() + px - lbl.width() // 2
            x = max(8, min(self.width() - lbl.width() - 8, x))
            # Prefer below the slider to avoid overlap with video widget.
            y = g.y() + slider.height() + 8
            if y + lbl.height() > self.height() - 8:
                y = g.y() - lbl.height() - 10
            lbl.move(int(x), int(y))
            lbl.raise_()
            lbl.show()
        except Exception:
            pass

    def _animate_preview_transition(self):
        try:
            target = self.preview_video if self.preview_video.isVisible() else self.preview_image
            if target is None:
                return
            try:
                prev_eff = target.graphicsEffect()
                if isinstance(prev_eff, QGraphicsOpacityEffect):
                    target.setGraphicsEffect(None)
            except Exception:
                pass
            eff = QGraphicsOpacityEffect(target)
            target.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(220)
            anim.setStartValue(0.86)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda t=target: t.setGraphicsEffect(None))
            self._track_ui_anim(anim)
            anim.start()
        except Exception:
            pass

    def _apply_preview_media_transform(self):
        try:
            mode = getattr(self, "_preview_mode", "image")
            if mode not in ("video", "gif"):
                return
            target = self.preview_video if mode == "video" else self.preview_image
            if mode == "video":
                # Keep hardware video path for smooth zoom/pan.
                self.preview_image.hide()
                self.preview_video.show()
            if target is None:
                return
            try:
                if target.parent() is not self.preview_label:
                    target.setParent(self.preview_label)
            except Exception:
                pass
            lbl_w = max(200, self.preview_label.width() or 800)
            lbl_h = max(200, self.preview_label.height() or 500)
            try:
                iw, ih = self._preview_native_size if self._preview_native_size else (lbl_w, lbl_h)
            except Exception:
                iw, ih = lbl_w, lbl_h
            iw = max(1, int(iw))
            ih = max(1, int(ih))
            base_scale = min(lbl_w / iw, lbl_h / ih)
            max_zoom = 4.0 if mode == "gif" else 3.0
            scale = max(0.05, base_scale * min(max_zoom, float(self.preview_zoom)))
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            if nw <= lbl_w:
                cx = (lbl_w - nw) // 2
                self.preview_pan[0] = 0
            else:
                base_x = (lbl_w - nw) // 2
                cx = base_x + int(self.preview_pan[0])
                cx = min(0, max(lbl_w - nw, cx))
                self.preview_pan[0] = cx - base_x
            if nh <= lbl_h:
                cy = (lbl_h - nh) // 2
                self.preview_pan[1] = 0
            else:
                base_y = (lbl_h - nh) // 2
                cy = base_y + int(self.preview_pan[1])
                cy = min(0, max(lbl_h - nh, cy))
                self.preview_pan[1] = cy - base_y
            target.setGeometry(int(cx), int(cy), int(nw), int(nh))
            try:
                if mode == "video":
                    target.raise_()
            except Exception:
                pass
            if mode == "gif" and self._preview_gif_movie is not None:
                try:
                    self._preview_gif_movie.setScaledSize(QSize(int(nw), int(nh)))
                except Exception:
                    pass
            # Clamp drawn area for both video and GIF/image-backed preview widgets.
            try:
                visible = QRect(0, 0, int(lbl_w), int(lbl_h)).intersected(QRect(int(cx), int(cy), int(nw), int(nh)))
                if not visible.isNull() and visible.width() > 0 and visible.height() > 0:
                    local_visible = visible.translated(-int(cx), -int(cy))
                    target.setMask(QRegion(local_visible))
                else:
                    target.clearMask()
            except Exception:
                try:
                    target.clearMask()
                except Exception:
                    pass
            target.show()
            self.preview_label.setText("")
            self._preview_pan_target = [float(self.preview_pan[0]), float(self.preview_pan[1])]
            self._layout_preview_controls()
        except Exception:
            pass

    def _position_preview_image(self, pix_w, pix_h, lbl_w, lbl_h):
        try:
            if pix_w <= 0 or pix_h <= 0:
                return
            if pix_w <= lbl_w:
                cx = (lbl_w - pix_w) // 2
                self.preview_pan[0] = 0
            else:
                base = (lbl_w - pix_w) // 2
                cx = base + int(self.preview_pan[0])
                cx = min(0, max(lbl_w - pix_w, cx))
                self.preview_pan[0] = cx - base
            if pix_h <= lbl_h:
                cy = (lbl_h - pix_h) // 2
                self.preview_pan[1] = 0
            else:
                basey = (lbl_h - pix_h) // 2
                cy = basey + int(self.preview_pan[1])
                cy = min(0, max(lbl_h - pix_h, cy))
                self.preview_pan[1] = cy - basey
            self.preview_image.move(int(cx), int(cy))
            try:
                visible = QRect(0, 0, int(lbl_w), int(lbl_h)).intersected(QRect(int(cx), int(cy), int(pix_w), int(pix_h)))
                if not visible.isNull() and visible.width() > 0 and visible.height() > 0:
                    local_visible = visible.translated(-int(cx), -int(cy))
                    self.preview_image.setMask(QRegion(local_visible))
                else:
                    self.preview_image.clearMask()
            except Exception:
                try:
                    self.preview_image.clearMask()
                except Exception:
                    pass
            self._preview_pan_target = [float(self.preview_pan[0]), float(self.preview_pan[1])]
        except Exception:
            pass

    def _render_preview_scaled(self):
        pil = self._preview_display_pil if isinstance(getattr(self, "_preview_display_pil", None), Image.Image) else self._preview_base_pil
        if pil is None:
            return
        try:
            self.preview_video.hide()
        except Exception:
            pass
        lbl_w = max(200, self.preview_label.width() or 800)
        lbl_h = max(200, self.preview_label.height() or 500)
        iw, ih = pil.size
        base_scale = min(lbl_w / iw, lbl_h / ih)
        scale = max(0.05, base_scale * self.preview_zoom)
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        cache_key = (
            int(getattr(self, "_preview_base_stamp", 0)),
            int(getattr(self, "_preview_display_stamp", 0)),
            int(lbl_w),
            int(lbl_h),
            int(round(float(self.preview_zoom) * 1000.0)),
        )
        reuse_only_pan = cache_key == getattr(self, "_preview_scaled_cache_key", None) and tuple(getattr(self, "_preview_scaled_cache_size", (0, 0))) == (int(nw), int(nh))
        if not reuse_only_pan:
            rs = Image.Resampling.BILINEAR if (self.isFullScreen() or self._preview_motion_timer.isActive()) else Image.Resampling.LANCZOS
            res = pil.resize((nw, nh), rs)
            qpix = pil_to_qpixmap(res)
            self._preview_native_size = (iw, ih)
            self.preview_image.setPixmap(qpix)
            self.preview_image.resize(qpix.width(), qpix.height())
            self._preview_scaled_cache_key = cache_key
            self._preview_scaled_cache_size = (int(qpix.width()), int(qpix.height()))
        self._position_preview_image(int(nw), int(nh), int(lbl_w), int(lbl_h))
        self.preview_image.show()
        self.preview_image.raise_()
        self.preview_label.repaint()
        self.preview_label.setText("")
        self._layout_preview_controls()

    def _apply_glitch_effect(self, img, amount_override=None):
        try:
            amount = int(getattr(self, "pro_glitch", 0) if amount_override is None else amount_override)
            if amount <= 0:
                return img
            arr = np.array(img.convert("RGB"), dtype=np.uint8)
            h, w = arr.shape[:2]
            density = max(0, min(100, int(getattr(self, "pro_glitch_density", 35))))
            shift_strength = max(0, min(100, int(getattr(self, "pro_glitch_shift", 42))))
            rgb_split = max(0, int(getattr(self, "pro_glitch_rgb", 1)))
            block_sz = max(0, int(getattr(self, "pro_glitch_block", 10)))
            jitter = max(0, int(getattr(self, "pro_glitch_jitter", 1)))
            static_noise = max(0, min(100, int(getattr(self, "pro_glitch_noise", 12))))
            rows = max(1, int(h * (0.004 + (density / 100.0) * (0.04 + amount / 2600.0))))
            band_base = max(1, int(h / 180))
            max_shift = max(1, int(w * (0.003 + (shift_strength / 100.0) * (0.11 + amount / 700.0))))
            for _ in range(rows):
                y = np.random.randint(0, max(1, h - 1))
                band = np.random.randint(1, max(2, band_base + amount // 24 + 2))
                shift = np.random.randint(-max_shift, max_shift + 1)
                y2 = min(h, y + band)
                arr[y:y2, :, :] = np.roll(arr[y:y2, :, :], shift, axis=1)
            if rgb_split > 0:
                split = max(1, int(rgb_split + amount / 34.0))
                arr[:, :, 0] = np.roll(arr[:, :, 0], split, axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -split, axis=1)
            if block_sz > 0 and w > 4 and h > 4:
                blocks = max(1, int(1 + amount / 24 + density / 36))
                max_side = min(max(4, block_sz * 2), max(6, min(w, h) // 3))
                for _ in range(blocks):
                    bw = np.random.randint(max(4, block_sz), max(max(5, block_sz + 1), max_side + 1))
                    bh = np.random.randint(max(3, block_sz // 2 + 1), max(max(4, block_sz // 2 + 2), max_side // 2 + 2))
                    x = np.random.randint(0, max(1, w - bw))
                    y = np.random.randint(0, max(1, h - bh))
                    dx = np.random.randint(-max_shift, max_shift + 1)
                    src = arr[y:y + bh, x:x + bw, :].copy()
                    tx = max(0, min(w - bw, x + dx))
                    arr[y:y + bh, tx:tx + bw, :] = src
            if jitter > 0:
                dy = np.random.randint(-jitter, jitter + 1)
                if dy != 0:
                    arr = np.roll(arr, dy, axis=0)
            if static_noise > 0:
                sigma = max(1.0, static_noise * 0.20 + amount * 0.08)
                noise = np.random.normal(0.0, sigma, arr.shape).astype(np.int16)
                arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            if amount > 60 and h > 4:
                y = np.random.randint(0, h - 1)
                line = np.random.randint(120, 255, (1, w, 3), dtype=np.uint8)
                arr[y:y + 1, :, :] = line
            return Image.fromarray(arr, mode="RGB")
        except Exception:
            return img

    def _apply_curvature_effect(self, img, convex_amount, concave_amount=0, center_x=0, expand=0, lens_type="spherical"):
        try:
            convex = max(0, min(100, int(convex_amount)))
            concave = max(0, min(100, int(concave_amount)))
            signed = float(convex - concave)
            cx_shift = max(-100, min(100, int(center_x)))
            expand_val = max(0, min(100, int(expand)))
            if abs(signed) <= 0.01 and expand_val <= 0 and cx_shift == 0:
                return img
            arr = np.array(img.convert("RGB"), dtype=np.uint8)
            h, w = arr.shape[:2]
            if w < 8 or h < 8:
                return img
            lens = str(lens_type or "spherical").strip().lower()
            if lens not in ("spherical", "barrel", "pincushion", "horizontal", "vertical"):
                lens = "spherical"
            cx_off = (float(cx_shift) / 100.0) * 0.45
            zoom = 1.0 + (float(expand_val) / 100.0) * 0.85 + (abs(signed) / 100.0) * 0.28
            x = np.linspace(-1.0, 1.0, w, dtype=np.float32) - np.float32(cx_off)
            y = np.linspace(-1.0, 1.0, h, dtype=np.float32)
            xv, yv = np.meshgrid(x, y)
            xv /= np.float32(max(0.2, zoom))
            yv /= np.float32(max(0.2, zoom))
            r2 = np.clip(xv * xv + yv * yv, 0.0, 8.0)
            k = np.float32((signed / 100.0) * 0.52)
            if lens == "horizontal":
                fx = 1.0 + k * (xv * xv)
                fy = np.ones_like(fx, dtype=np.float32)
                src_x = xv * fx + np.float32(cx_off)
                src_y = yv * fy
            elif lens == "vertical":
                fy = 1.0 + k * (yv * yv)
                fx = np.ones_like(fy, dtype=np.float32)
                src_x = xv * fx + np.float32(cx_off)
                src_y = yv * fy
            else:
                if lens == "barrel":
                    q = r2 + 0.35 * (r2 * r2)
                elif lens == "pincushion":
                    q = 0.55 * r2 + 0.75 * np.sqrt(r2 + 1e-8) * r2
                else:
                    q = r2
                factor = 1.0 + k * q
                src_x = xv * factor + np.float32(cx_off)
                src_y = yv * factor
            map_x = ((src_x + 1.0) * 0.5 * (w - 1)).astype(np.float32)
            map_y = ((src_y + 1.0) * 0.5 * (h - 1)).astype(np.float32)
            warped = cv2.remap(
                arr,
                map_x,
                map_y,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT101,
            )
            return Image.fromarray(warped, mode="RGB")
        except Exception:
            return img

    def _apply_ribbing_effect(self, img, amount):
        try:
            amt = max(0, min(100, int(amount)))
            if amt <= 0:
                return img
            arr = np.array(img.convert("RGB"), dtype=np.int16)
            h, w = arr.shape[:2]
            if w < 6 or h < 6:
                return img
            step = max(2, int(10 - amt / 14.0))
            dark = int(3 + amt * 0.14)
            side = max(1, dark // 3)
            for x in range(0, w, step):
                arr[:, x:x + 1, :] = np.clip(arr[:, x:x + 1, :] - dark, 0, 255)
                if x > 0:
                    arr[:, x - 1:x, :] = np.clip(arr[:, x - 1:x, :] + side, 0, 255)
                if x + 1 < w:
                    arr[:, x + 1:x + 2, :] = np.clip(arr[:, x + 1:x + 2, :] + side, 0, 255)
            if amt >= 12:
                arr[::2, :, :] = np.clip(arr[::2, :, :] - int(1 + amt * 0.05), 0, 255)
            return Image.fromarray(arr.astype(np.uint8), mode="RGB")
        except Exception:
            return img

    def _preprocess_pil(self, pil, t_ms=0):
        img = self._apply_editor_state(pil, t_ms=t_ms).convert("RGB")
        gp = float(getattr(self, "gamma_pct", 100))
        if gp != 100.0:
            gamma = max(0.2, min(4.0, gp / 100.0))
            inv = 1.0 / gamma
            lut = [int(((i / 255.0) ** inv) * 255.0) for i in range(256)]
            img = img.point(lut * 3)
        if self.denoise_chk.isChecked():
            img = img.filter(ImageFilter.MedianFilter(size=3))
        if self.sharpen_chk.isChecked():
            img = img.filter(ImageFilter.SHARPEN)
        if self.edge_chk.isChecked():
            img = ImageEnhance.Contrast(img).enhance(1.18)
        return img

    def _apply_postprocess_fx(self, pil):
        img = pil.convert("RGB")
        # Pro FX are applied after style render, so they are visible on final ASCII frame.
        # Pro filters
        try:
            bits = int(getattr(self, "pro_poster_bits", 0))
            if bits > 0:
                bits = max(1, min(8, bits))
                img = ImageOps.posterize(img, bits)
        except Exception:
            pass
        try:
            bloom = int(getattr(self, "pro_bloom", 0))
            if bloom > 0:
                blur = img.filter(ImageFilter.GaussianBlur(radius=max(1.0, 4.0 * bloom / 100.0)))
                img = Image.blend(img, blur, min(0.6, bloom / 180.0))
        except Exception:
            pass
        try:
            clarity = int(getattr(self, "pro_clarity", 0))
            if clarity > 0:
                arr = np.array(img.convert("RGB"), dtype=np.float32)
                sigma = max(0.6, 0.55 + clarity / 32.0)
                blur = cv2.GaussianBlur(arr, (0, 0), sigmaX=sigma, sigmaY=sigma)
                amt = min(1.7, clarity / 68.0)
                arr = np.clip(arr + (arr - blur) * amt, 0, 255).astype(np.uint8)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            vig = int(getattr(self, "pro_vignette", 0))
            if vig > 0:
                w, h = img.size
                mask = Image.new("L", (w, h), 255)
                md = ImageDraw.Draw(mask)
                border = int(min(w, h) * min(0.45, vig / 140.0))
                md.rectangle((0, 0, w, h), fill=255)
                md.rectangle((border, border, w - border, h - border), fill=0)
                mask = mask.filter(ImageFilter.GaussianBlur(radius=max(8, int(min(w, h) * 0.08))))
                dark = Image.new("RGB", (w, h), (0, 0, 0))
                img = Image.composite(dark, img, mask)
        except Exception:
            pass
        try:
            chroma = int(getattr(self, "pro_chroma", 0))
            if chroma > 0:
                arr = np.array(img.convert("RGB"), dtype=np.uint8)
                arr[:, :, 0] = np.roll(arr[:, :, 0], int(chroma), axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -int(chroma), axis=1)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            color_boost = int(getattr(self, "pro_color_boost", 0))
            if color_boost > 0:
                img = ImageEnhance.Color(img).enhance(1.0 + min(2.0, color_boost / 62.0))
        except Exception:
            pass
        try:
            grain = int(getattr(self, "pro_grain", 0))
            if grain > 0:
                arr = np.array(img.convert("RGB"), dtype=np.int16)
                sigma = max(1.0, float(grain) * 0.8)
                noise = np.random.normal(0.0, sigma, arr.shape).astype(np.int16)
                arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            motion_blur = int(getattr(self, "pro_motion_blur", 0))
            if motion_blur > 0:
                arr = np.array(img.convert("RGB"), dtype=np.uint8)
                k = max(3, int(3 + motion_blur * 0.34))
                if k % 2 == 0:
                    k += 1
                kernel = np.zeros((k, k), dtype=np.float32)
                kernel[k // 2, :] = 1.0 / float(k)
                arr = cv2.filter2D(arr, -1, kernel, borderType=cv2.BORDER_REFLECT101)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            if hasattr(self, "pro_scanlines_chk") and self.pro_scanlines_chk.isChecked():
                w, h = img.size
                over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                od = ImageDraw.Draw(over)
                step = max(1, int(getattr(self, "pro_scan_step", 3)))
                strength = max(0, min(100, int(getattr(self, "pro_scan_strength", 28))))
                alpha = int(8 + strength * 1.1)
                for y in range(0, h, step):
                    od.line((0, y, w, y), fill=(0, 0, 0, alpha), width=1)
                img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
        except Exception:
            pass
        try:
            glitch = int(getattr(self, "pro_glitch", 0))
            if glitch > 0:
                img = self._apply_glitch_effect(img, glitch)
        except Exception:
            pass
        try:
            curvature = int(getattr(self, "pro_curvature", 0))
            concavity = int(getattr(self, "pro_concavity", 0))
            if curvature > 0 or concavity > 0:
                img = self._apply_curvature_effect(
                    img,
                    curvature,
                    concavity,
                    int(getattr(self, "pro_curvature_center_x", 0)),
                    int(getattr(self, "pro_curvature_expand", 0)),
                    str(getattr(self, "pro_curvature_type", "spherical") or "spherical"),
                )
        except Exception:
            pass
        try:
            ribbing = int(getattr(self, "pro_ribbing", 0))
            if ribbing > 0:
                img = self._apply_ribbing_effect(img, ribbing)
        except Exception:
            pass
        return img

    def _render_with_style(self, pil, output_size=None):
        src = pil.convert("RGB")
        if self.style == "none":
            out = src
            if output_size and isinstance(output_size, tuple):
                try:
                    out = out.resize((max(1, int(output_size[0])), max(1, int(output_size[1]))), Image.Resampling.LANCZOS)
                except Exception:
                    pass
            if self.watermark_chk.isChecked():
                try:
                    wtxt = str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK).strip()
                    if not wtxt:
                        wtxt = CORE_WATERMARK
                    d = ImageDraw.Draw(out)
                    d.text((10, max(2, out.height - 20)), wtxt, fill=(130, 130, 130))
                except Exception:
                    pass
            return self._apply_postprocess_fx(out)
        ascii_chars = self.charset_input.currentText() or DEFAULT_ASCII
        invert = self.invert_chk.isChecked()
        contrast = self.contrast_slider.value() if hasattr(self, "contrast_slider") else 100
        data = image_to_ascii_data(src, self.width_chars, ascii_chars=ascii_chars, invert=invert, contrast_pct=contrast)
        out = render_ascii_pil(
            data, self.font_size, self.style, self.fg_hex, self.bg_hex,
            output_size=output_size,
            watermark=self.watermark_chk.isChecked(),
            watermark_text=str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK),
        )
        return self._apply_postprocess_fx(out)

    def _schedule_preset_preview_update(self):
        try:
            if hasattr(self, "_preset_preview_timer") and self._preset_preview_timer is not None:
                self._preset_preview_timer.start(120)
        except Exception:
            pass

    def _set_rounded_preview(self, label, pil_img, radius=9):
        if label is None or pil_img is None:
            return
        w = max(36, int(label.width() or 36))
        h = max(36, int(label.height() or 36))
        pm = pil_to_qpixmap(pil_img).scaled(w - 2, h - 2, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        out = QPixmap(w, h)
        out.fill(Qt.transparent)
        p = QPainter(out)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRect(0, 0, w, h), int(radius), int(radius))
            p.setClipPath(path)
            p.fillRect(QRect(0, 0, w, h), QColor(10, 14, 20, 230))
            p.drawPixmap(0, 0, pm)
        finally:
            if p.isActive():
                p.end()
        label.setPixmap(out)

    def _update_preset_preview(self):
        try:
            sample = _pick_resource_path(
                PRESET_PREVIEW_SAMPLE,
                f"assets/{PRESET_PREVIEW_SAMPLE}",
                f"_internal/{PRESET_PREVIEW_SAMPLE}",
            )
            src = None
            if sample is not None and Path(sample).exists():
                with Image.open(sample) as im:
                    src = im.convert("RGB")
            elif hasattr(self, "_preview_base_pil") and self._preview_base_pil is not None:
                src = self._preview_base_pil.convert("RGB")
            elif getattr(self, "current_path", None):
                try:
                    with Image.open(self.current_path) as im:
                        src = im.convert("RGB")
                except Exception:
                    src = None
            if src is None:
                for nm in ("style_preview_label", "pro_preview_label", "preset_preview_label"):
                    lb = getattr(self, nm, None)
                    if lb is not None:
                        lb.setText("Preset preview unavailable")
                return
            targets = []
            for nm in ("style_preview_label", "pro_preview_label", "preset_preview_label"):
                lb = getattr(self, nm, None)
                if lb is not None:
                    targets.append(lb)
            if not targets:
                return
            for lb in targets:
                ow = max(120, int(lb.width() or 120))
                oh = max(72, int(lb.height() or 72))
                tw = max(220, ow - 8)
                th = max(120, oh - 8)
                base = ImageOps.fit(src, (tw, th), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                out = self._render_with_style(base, output_size=(tw, th)).convert("RGB")
                self._set_rounded_preview(lb, out, radius=10)
                sample_name = Path(sample).name if sample is not None else "current source"
                lb.setToolTip(
                    f"{sample_name}\n{TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get('preset', 'Preset')}: {self.preset_combo.currentText()}"
                )
            caption = self._resolve_info_text(self._i3(
                "Так будет выглядеть рендер с выбранным пресетом",
                "Preview of render with the selected preset",
                "这是所选预设的渲染预览效果",
            ))
            if hasattr(self, "style_preview_caption"):
                self.style_preview_caption.setText(caption)
            if hasattr(self, "pro_preview_caption"):
                self.pro_preview_caption.setText(caption)
            if hasattr(self, "preset_preview_caption"):
                self.preset_preview_caption.setText(caption)
        except Exception:
            for nm in ("style_preview_label", "pro_preview_label", "preset_preview_label"):
                lb = getattr(self, nm, None)
                if lb is not None:
                    lb.setText("Preset preview unavailable")

    def _collect_user_preset(self):
        return {
            "style": self.style_combo.currentText() if hasattr(self, "style_combo") else self.style,
            "width_chars": int(self.width_slider.value()) if hasattr(self, "width_slider") else int(self.width_chars),
            "font_size": int(self.font_slider.value()) if hasattr(self, "font_slider") else int(self.font_size),
            "contrast": int(self.contrast_slider.value()) if hasattr(self, "contrast_slider") else int(self.contrast),
            "gamma_pct": int(getattr(self, "gamma_pct", 100)),
            "invert": bool(self.invert_chk.isChecked()) if hasattr(self, "invert_chk") else bool(self.invert),
            "keep_size": bool(self.keep_size_chk.isChecked()) if hasattr(self, "keep_size_chk") else bool(self.keep_size),
            "fg_hex": str(getattr(self, "fg_hex", "#FFFFFF")),
            "bg_hex": str(getattr(self, "bg_hex", "#0F1013")),
            "ascii_chars": self.charset_input.currentText() if hasattr(self, "charset_input") else str(getattr(self, "ascii_chars", DEFAULT_ASCII)),
            "watermark": bool(self.watermark_chk.isChecked()) if hasattr(self, "watermark_chk") else bool(self.show_watermark),
            "watermark_text": str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK),
            "theme": str(getattr(self, "theme", "dark") or "dark"),
            "render_fps": int(self.fps_spin.value()) if hasattr(self, "fps_spin") else int(getattr(self, "render_fps", 24)),
            "render_scale": int(getattr(self, "render_scale", 1)),
            "render_out_w": int(getattr(self, "render_out_w", 0)),
            "render_out_h": int(getattr(self, "render_out_h", 0)),
            "render_codec": str(getattr(self, "render_codec", "libx264")),
            "render_bitrate": str(getattr(self, "render_bitrate", "2M")),
            "render_threads": int(getattr(self, "render_threads", 4)),
            "render_preset": str(getattr(self, "render_preset", "medium")),
            "render_crf": int(getattr(self, "render_crf", 20)),
            "pro_tools": bool(getattr(self, "pro_tools", False)),
            "pro_scanlines": bool(self.pro_scanlines_chk.isChecked()) if hasattr(self, "pro_scanlines_chk") else bool(getattr(self, "pro_scanlines", False)),
            "pro_bloom": int(getattr(self, "pro_bloom", 0)),
            "pro_vignette": int(getattr(self, "pro_vignette", 0)),
            "pro_poster_bits": int(getattr(self, "pro_poster_bits", 0)),
            "pro_grain": int(getattr(self, "pro_grain", 0)),
            "pro_chroma": int(getattr(self, "pro_chroma", 0)),
            "pro_color_boost": int(getattr(self, "pro_color_boost", 0)),
            "pro_clarity": int(getattr(self, "pro_clarity", 0)),
            "pro_motion_blur": int(getattr(self, "pro_motion_blur", 0)),
            "pro_curvature": int(getattr(self, "pro_curvature", 0)),
            "pro_concavity": int(getattr(self, "pro_concavity", 0)),
            "pro_curvature_center_x": int(getattr(self, "pro_curvature_center_x", 0)),
            "pro_curvature_expand": int(getattr(self, "pro_curvature_expand", 0)),
            "pro_curvature_type": str(getattr(self, "pro_curvature_type", "spherical") or "spherical"),
            "pro_ribbing": int(getattr(self, "pro_ribbing", 0)),
            "editor_state": copy.deepcopy(getattr(self, "editor_state", {}) or {}),
        }

    def _apply_user_preset(self, data):
        if not isinstance(data, dict):
            return
        self._push_undo_state()
        try:
            style = str(data.get("style", self.style))
            if hasattr(self, "style_combo"):
                self.style_combo.setCurrentText(style)
            self.width_chars = int(data.get("width_chars", self.width_chars))
            self.font_size = int(data.get("font_size", self.font_size))
            self.contrast = int(data.get("contrast", self.contrast))
            self.gamma_pct = int(data.get("gamma_pct", self.gamma_pct))
            self.fg_hex = str(data.get("fg_hex", self.fg_hex))
            self.bg_hex = str(data.get("bg_hex", self.bg_hex))
            self.ascii_chars = str(data.get("ascii_chars", self.ascii_chars))
            self.render_fps = int(data.get("render_fps", self.render_fps))
            self.render_scale = int(data.get("render_scale", self.render_scale))
            self.render_out_w = int(data.get("render_out_w", self.render_out_w))
            self.render_out_h = int(data.get("render_out_h", self.render_out_h))
            self.render_codec = str(data.get("render_codec", self.render_codec))
            self.render_bitrate = str(data.get("render_bitrate", self.render_bitrate))
            self.render_threads = int(data.get("render_threads", self.render_threads))
            self.render_preset = str(data.get("render_preset", self.render_preset))
            self.render_crf = int(data.get("render_crf", self.render_crf))
            self.pro_tools = bool(data.get("pro_tools", self.pro_tools))
            self.pro_scanlines = bool(data.get("pro_scanlines", self.pro_scanlines))
            self.pro_bloom = int(data.get("pro_bloom", self.pro_bloom))
            self.pro_vignette = int(data.get("pro_vignette", self.pro_vignette))
            self.pro_poster_bits = int(data.get("pro_poster_bits", self.pro_poster_bits))
            self.pro_grain = int(data.get("pro_grain", self.pro_grain))
            self.pro_chroma = int(data.get("pro_chroma", self.pro_chroma))
            self.pro_color_boost = int(data.get("pro_color_boost", getattr(self, "pro_color_boost", 0)))
            self.pro_clarity = int(data.get("pro_clarity", getattr(self, "pro_clarity", 0)))
            self.pro_motion_blur = int(data.get("pro_motion_blur", getattr(self, "pro_motion_blur", 0)))
            self.pro_curvature = int(data.get("pro_curvature", getattr(self, "pro_curvature", 0)))
            self.pro_concavity = int(data.get("pro_concavity", getattr(self, "pro_concavity", 0)))
            self.pro_curvature_center_x = int(data.get("pro_curvature_center_x", getattr(self, "pro_curvature_center_x", 0)))
            self.pro_curvature_expand = int(data.get("pro_curvature_expand", getattr(self, "pro_curvature_expand", 0)))
            self.pro_curvature_type = str(data.get("pro_curvature_type", getattr(self, "pro_curvature_type", "spherical")) or "spherical")
            self.pro_ribbing = int(data.get("pro_ribbing", getattr(self, "pro_ribbing", 0)))
            self.watermark_text = str(data.get("watermark_text", self.watermark_text) or self.watermark_text)
            if isinstance(data.get("editor_state"), dict):
                self.editor_state = copy.deepcopy(data.get("editor_state") or {})
            if hasattr(self, "width_slider"):
                self.width_slider.setValue(int(self.width_chars))
            if hasattr(self, "font_slider"):
                self.font_slider.setValue(int(self.font_size))
            if hasattr(self, "contrast_slider"):
                self.contrast_slider.setValue(int(self.contrast))
            if hasattr(self, "gamma_slider"):
                self.gamma_slider.setValue(int(self.gamma_pct))
            if hasattr(self, "invert_chk"):
                self.invert_chk.setChecked(bool(data.get("invert", self.invert)))
            if hasattr(self, "keep_size_chk"):
                self.keep_size_chk.setChecked(bool(data.get("keep_size", self.keep_size)))
            if hasattr(self, "charset_input"):
                self.charset_input.setCurrentText(self.ascii_chars)
            if hasattr(self, "watermark_chk"):
                self.watermark_chk.setChecked(bool(data.get("watermark", self.watermark_chk.isChecked())))
            if hasattr(self, "watermark_text_edit"):
                self.watermark_text_edit.setText(self.watermark_text)
            if hasattr(self, "fps_spin"):
                self.fps_spin.setValue(int(self.render_fps))
            if hasattr(self, "codec_combo"):
                self.codec_combo.setCurrentText(self.render_codec)
            if hasattr(self, "bitrate_combo"):
                self.bitrate_combo.setCurrentText(self.render_bitrate)
            if hasattr(self, "threads_spin"):
                self.threads_spin.setValue(int(self.render_threads))
            if hasattr(self, "preset_combo"):
                self.preset_combo.setCurrentText(self.render_preset)
            if hasattr(self, "crf_spin"):
                self.crf_spin.setValue(int(self.render_crf))
            if hasattr(self, "pro_scanlines_chk"):
                self.pro_scanlines_chk.setChecked(bool(self.pro_scanlines))
            if hasattr(self, "pro_bloom_slider"):
                self.pro_bloom_slider.setValue(int(self.pro_bloom))
            if hasattr(self, "pro_vignette_slider"):
                self.pro_vignette_slider.setValue(int(self.pro_vignette))
            if hasattr(self, "pro_poster_spin"):
                self.pro_poster_spin.setValue(int(self.pro_poster_bits))
            if hasattr(self, "pro_grain_slider"):
                self.pro_grain_slider.setValue(int(self.pro_grain))
            if hasattr(self, "pro_chroma_spin"):
                self.pro_chroma_spin.setValue(int(self.pro_chroma))
            if hasattr(self, "pro_color_boost_slider"):
                self.pro_color_boost_slider.setValue(int(self.pro_color_boost))
            if hasattr(self, "pro_clarity_slider"):
                self.pro_clarity_slider.setValue(int(self.pro_clarity))
            if hasattr(self, "pro_motion_blur_slider"):
                self.pro_motion_blur_slider.setValue(int(self.pro_motion_blur))
            if hasattr(self, "pro_curvature_slider"):
                self.pro_curvature_slider.setValue(int(self.pro_curvature))
            if hasattr(self, "pro_concavity_slider"):
                self.pro_concavity_slider.setValue(int(self.pro_concavity))
            if hasattr(self, "pro_curvature_center_x_slider"):
                self.pro_curvature_center_x_slider.setValue(int(self.pro_curvature_center_x))
            if hasattr(self, "pro_curvature_expand_slider"):
                self.pro_curvature_expand_slider.setValue(int(self.pro_curvature_expand))
            if hasattr(self, "pro_curvature_type_combo"):
                self.pro_curvature_type_combo.setCurrentText(str(self.pro_curvature_type or "spherical"))
            if hasattr(self, "pro_ribbing_slider"):
                self.pro_ribbing_slider.setValue(int(self.pro_ribbing))
            theme_name = str(data.get("theme", self.theme) or self.theme)
            if theme_name in THEME_NAMES:
                self._apply_theme(theme_name)
            self._sync_pro_menu_state()
            self._update_ascii_controls_visibility()
            self._update_color_buttons_state()
            self._schedule_live_preview()
            self._schedule_preset_preview_update()
        except Exception:
            pass

    def _default_project_path(self):
        try:
            d = Path.cwd() / "project2"
            d.mkdir(parents=True, exist_ok=True)
            return str(d / "project.asproj.json")
        except Exception:
            return str(Path.cwd() / "project.asproj.json")

    def _collect_project_payload(self):
        return {
            "format": "ultra_ascii_project",
            "version": str(APP_VERSION),
            "saved_at": int(time.time()),
            "source_path": str(self._effective_source_path() or ""),
            "editor_time_ms": int(getattr(self, "_editor_last_preview_ms", 0) or 0),
            "preset": self._collect_user_preset(),
        }

    def _apply_project_payload(self, data):
        if not isinstance(data, dict):
            return False
        preset = data.get("preset", data)
        if isinstance(preset, dict):
            self._apply_user_preset(preset)
        src = str(data.get("source_path", "") or "").strip()
        if src and os.path.exists(src):
            self._load_media_from_path(src)
        try:
            self._editor_last_preview_ms = int(data.get("editor_time_ms", self._editor_last_preview_ms) or self._editor_last_preview_ms)
        except Exception:
            pass
        try:
            self._schedule_live_preview()
        except Exception:
            pass
        return True

    def _new_project_shortcut(self):
        try:
            if bool(getattr(self, "_embedded_editor_active", False)):
                self._close_embedded_editor(apply=False, restore_modal=False)
        except Exception:
            pass
        try:
            self._push_undo_state()
        except Exception:
            pass
        try:
            if hasattr(self, "gallery_list"):
                self.gallery_list.clear()
            if hasattr(self, "gallery_empty"):
                self.gallery_empty.setVisible(True)
            self.current_path = None
            self.original_source_path = None
            self.processing_source_path = None
            self._project_file_path = ""
            self.current_output = None
            self._live_preview_source_pil = None
            self._preview_base_pil = None
            self._stop_preview_media()
            self.editor_state = {
                "enabled": False,
                "brightness": 100,
                "contrast": 100,
                "saturation": 100,
                "sharpness": 100,
                "hue": 0,
                "exposure": 0,
                "temperature": 0,
                "crop_enabled": False,
                "crop_x": 0,
                "crop_y": 0,
                "crop_w": 0,
                "crop_h": 0,
                "mask_enabled": False,
                "mask_x": 0,
                "mask_y": 0,
                "mask_w": 0,
                "mask_h": 0,
                "mask_use_image": False,
                "mask_image_path": "",
                "trim_enabled": False,
                "trim_start_ms": 0,
                "trim_end_ms": 0,
                "audio_path": "",
                "audio_gain_db": 0.0,
                "audio_lowpass_hz": 0,
                "nodes_enabled": False,
                "nodes_preview": False,
                "nodes_code": "",
                "node_chain": [],
                "node_links": [],
                "node_params": [],
                "node_io": [],
                "photo_paint_enabled": False,
                "photo_paint_opacity": 100,
                "photo_paint_png_b64": "",
                "photo_paint_hash": "",
                "photo_brush_size": 26,
                "photo_brush_opacity": 92,
                "photo_brush_color_rgba": [236, 244, 255, 220],
                "media_layers": [],
                "text_layers": [],
            }
            if hasattr(self, "preview_image"):
                self.preview_image.clear()
                self.preview_image.setText("")
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            self._show_notice(tr.get("app", "ASCII Studio"), "New project created")
        except Exception:
            pass

    def _save_project_as_shortcut(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            fn, _ = QFileDialog.getSaveFileName(
                self,
                tr.get("save_preset", "Save preset"),
                self._default_project_path(),
                "ASCII Studio Project (*.asproj.json);;JSON (*.json)",
            )
            if not fn:
                return
            payload = self._collect_project_payload()
            Path(fn).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._project_file_path = str(fn)
            self._show_notice(tr.get("settings", "Settings"), f"Project saved: {os.path.basename(fn)}")
        except Exception as e:
            self._show_notice(tr.get("info", "Info"), f"Project save failed: {e}")

    def _save_project_shortcut(self):
        path = str(getattr(self, "_project_file_path", "") or "").strip()
        if not path:
            self._save_project_as_shortcut()
            return
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            payload = self._collect_project_payload()
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._show_notice(tr.get("settings", "Settings"), f"Project saved: {os.path.basename(path)}")
        except Exception:
            self._save_project_as_shortcut()

    def _open_project_shortcut(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            fn, _ = QFileDialog.getOpenFileName(
                self,
                tr.get("load_preset", "Load preset"),
                str(Path.cwd()),
                "ASCII Studio Project (*.asproj.json *.json)",
            )
            if not fn:
                return
            data = json.loads(Path(fn).read_text(encoding="utf-8"))
            if self._apply_project_payload(data):
                self._project_file_path = str(fn)
                self._show_notice(tr.get("settings", "Settings"), f"Project loaded: {os.path.basename(fn)}")
        except Exception as e:
            self._show_notice(tr.get("info", "Info"), f"Project load failed: {e}")

    def _save_user_preset(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            presets_dir = Path.cwd() / "presets"
            presets_dir.mkdir(parents=True, exist_ok=True)
            fn, _ = QFileDialog.getSaveFileName(
                self,
                tr.get("save_preset", "Save preset"),
                str(presets_dir / "preset.json"),
                "JSON (*.json)",
            )
            if not fn:
                return
            if not fn.lower().endswith(".json"):
                fn += ".json"
            Path(fn).write_text(json.dumps(self._collect_user_preset(), ensure_ascii=False, indent=2), encoding="utf-8")
            self._show_notice(tr.get("settings", "Settings"), f"{tr.get('preset_saved', 'Preset saved')}: {os.path.basename(fn)}")
        except Exception as e:
            self._show_notice(tr.get("settings", "Settings"), str(e))

    def _load_user_preset(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            presets_dir = Path.cwd() / "presets"
            fn, _ = QFileDialog.getOpenFileName(
                self,
                tr.get("load_preset", "Load preset"),
                str(presets_dir if presets_dir.exists() else Path.cwd()),
                "JSON (*.json)",
            )
            if not fn:
                return
            data = json.loads(Path(fn).read_text(encoding="utf-8"))
            self._apply_user_preset(data)
            self._show_notice(tr.get("settings", "Settings"), f"{tr.get('preset_loaded', 'Preset loaded')}: {os.path.basename(fn)}")
        except Exception as e:
            self._show_notice(tr.get("settings", "Settings"), str(e))

    def on_pick_text(self):
        self._push_undo_state()
        c = QColorDialog.getColor()
        if c.isValid():
            self.fg_hex = c.name()
            # update button color
            self.pick_text_btn.setStyleSheet(self._glass_btn_css() + f"QPushButton{{ background:{self.fg_hex}; color:#000; }}")

    def on_pick_bg(self):
        self._push_undo_state()
        cdlg = QColorDialog(self)
        cdlg.setOption(QColorDialog.ShowAlphaChannel, True)
        c = cdlg.getColor()
        if c.isValid():
            if c.alpha() <= 0:
                self.bg_hex = "transparent"
            else:
                # Keep alpha for PNG/GIF output when possible.
                self.bg_hex = c.name(QColor.HexArgb)
            self._update_background()
            # update button color
            btn_bg = "#2b3444" if self.bg_hex == "transparent" else self.bg_hex
            self.pick_bg_btn.setStyleSheet(self._glass_btn_css() + f"QPushButton{{ background:{btn_bg}; color:#000; }}")

    def _update_color_buttons_state(self):
        # enable color pickers only when style is custom
        enabled = (self.style_combo.currentText() == "custom")
        try:
            self.pick_text_btn.setEnabled(enabled)
            self.pick_bg_btn.setEnabled(enabled)
            self.pick_text_btn.setVisible(enabled)
            self.pick_bg_btn.setVisible(enabled)
            # visually dim when disabled
            if not enabled:
                self.pick_text_btn.setStyleSheet(self._glass_btn_css())
                self.pick_bg_btn.setStyleSheet(self._glass_btn_css())
            else:
                self.pick_text_btn.setStyleSheet(self._glass_btn_css())
                self.pick_bg_btn.setStyleSheet(self._glass_btn_css())
        except Exception:
            pass

    def _show_preview_pil(self, pil, set_as_base=True, preserve_transform=False, update_live_source=True):
        self._last_preview_pil = pil
        self._preview_display_pil = pil
        try:
            self._preview_display_stamp = int(getattr(self, "_preview_display_stamp", 0)) + 1
        except Exception:
            self._preview_display_stamp = 1
        self._preview_scaled_cache_key = None
        self._preview_scaled_cache_size = (0, 0)
        if bool(set_as_base):
            self._preview_base_pil = pil
            try:
                self._preview_base_stamp = int(getattr(self, "_preview_base_stamp", 0)) + 1
            except Exception:
                self._preview_base_stamp = 1
            if bool(update_live_source):
                try:
                    self._live_preview_source_pil = pil.copy()
                except Exception:
                    self._live_preview_source_pil = pil
        try:
            self._preview_native_size = pil.size
        except Exception:
            self._preview_native_size = None
        if not bool(preserve_transform):
            self.preview_zoom = 1.0
            self.preview_pan = [0, 0]
        self._preview_zoom_target = float(self.preview_zoom)
        self._preview_pan_target = [float(self.preview_pan[0]), float(self.preview_pan[1])]
        self._stop_preview_media()
        self._render_preview_scaled()
        # Re-run after layout settles (focus mode / section changes can update geometry async).
        QTimer.singleShot(0, self._render_preview_scaled)
        QTimer.singleShot(80, self._render_preview_scaled)

    def _get_first_frame(self, path):
        try:
            low = path.lower()
            if low.endswith(".gif"):
                reader = imageio.get_reader(path)
                return Image.fromarray(np.array(reader.get_data(0))).convert("RGB")
            if low.endswith((".mp4", ".avi", ".mov", ".mkv")):
                cap = cv2.VideoCapture(path)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if low.endswith((".png", ".jpg", ".jpeg", ".bmp")):
                return Image.open(path).convert("RGB")
        except Exception:
            return None
        return None

    def _get_video_frame_at_ms(self, path, ms):
        try:
            if not path or not os.path.exists(path):
                return None
            cap = cv2.VideoCapture(path)
            if not cap or not cap.isOpened():
                return None
            try:
                cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(ms)))
                ret, frame = cap.read()
                if not ret:
                    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                    idx = int(max(0.0, float(ms)) * (fps if fps > 0 else 24.0) / 1000.0)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ret, frame = cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    return Image.fromarray(frame)
            finally:
                cap.release()
        except Exception:
            return None
        return None

    def _safe_font(self, family, size):
        try:
            s = max(6, int(size))
        except Exception:
            s = 18
        def _norm(txt):
            return "".join(ch for ch in str(txt or "").lower() if ch.isalnum())
        candidates = []
        fam = str(family or "").strip()
        fam_norm = _norm(fam)
        fam_tokens = [
            "".join(ch for ch in str(tok).lower() if ch.isalnum())
            for tok in str(fam).replace("_", " ").replace("-", " ").split()
            if str(tok).strip()
        ]
        if fam:
            candidates.extend([
                fam,
                fam + ".ttf",
                os.path.join("C:\\Windows\\Fonts", fam + ".ttf"),
                os.path.join("C:\\Windows\\Fonts", fam.replace(" ", "") + ".ttf"),
            ])
        # Try cached family->paths map first, then build lightweight lookup from Fonts folders.
        try:
            cache = getattr(self, "_font_family_lookup", None)
            if cache is None:
                cache = {}
                setattr(self, "_font_family_lookup", cache)
            if fam_norm and fam_norm in cache:
                candidates.extend(list(cache.get(fam_norm) or []))
            elif fam_norm:
                roots = []
                win_dir = str(os.environ.get("WINDIR", "C:\\Windows") or "C:\\Windows")
                roots.append(os.path.join(win_dir, "Fonts"))
                roots.extend([
                    "/usr/share/fonts",
                    "/usr/local/share/fonts",
                    os.path.expanduser("~/.fonts"),
                ])
                hits = []
                for root in roots:
                    if not root or (not os.path.isdir(root)):
                        continue
                    try:
                        for fn in os.listdir(root):
                            low = str(fn or "").lower()
                            if not low.endswith((".ttf", ".otf", ".ttc")):
                                continue
                            nn = _norm(low)
                            ok = bool(fam_norm and fam_norm in nn)
                            if (not ok) and fam_tokens:
                                ok = any(tok in nn for tok in fam_tokens if len(tok) >= 3)
                            if ok:
                                hits.append(os.path.join(root, fn))
                                if len(hits) >= 24:
                                    break
                    except Exception:
                        continue
                    if len(hits) >= 24:
                        break
                cache[fam_norm] = list(hits)
                candidates.extend(hits)
        except Exception:
            pass
        candidates.extend([
            os.path.join("C:\\Windows\\Fonts", "arial.ttf"),
            os.path.join("C:\\Windows\\Fonts", "segoeui.ttf"),
            os.path.join("C:\\Windows\\Fonts", "consola.ttf"),
            "arial.ttf",
            "segoeui.ttf",
            "consola.ttf",
        ])
        seen = set()
        for cand in candidates:
            c = str(cand or "").strip()
            if not c or c in seen:
                continue
            seen.add(c)
            try:
                return ImageFont.truetype(c, s)
            except Exception:
                continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _apply_editor_basic_fx(self, pil):
        img = pil.convert("RGB")
        st = getattr(self, "editor_state", {}) or {}
        try:
            img = ImageEnhance.Brightness(img).enhance(max(0.0, float(st.get("brightness", 100)) / 100.0))
        except Exception:
            pass
        try:
            img = ImageEnhance.Contrast(img).enhance(max(0.0, float(st.get("contrast", 100)) / 100.0))
        except Exception:
            pass
        try:
            img = ImageEnhance.Color(img).enhance(max(0.0, float(st.get("saturation", 100)) / 100.0))
        except Exception:
            pass
        try:
            img = ImageEnhance.Sharpness(img).enhance(max(0.0, float(st.get("sharpness", 100)) / 100.0))
        except Exception:
            pass
        try:
            h = int(st.get("hue", 0))
            if h != 0:
                hsv = img.convert("HSV")
                arr = np.array(hsv, dtype=np.uint8)
                arr[:, :, 0] = ((arr[:, :, 0].astype(np.int16) + int(h / 2)) % 256).astype(np.uint8)
                img = Image.fromarray(arr, mode="HSV").convert("RGB")
        except Exception:
            pass
        try:
            ex = int(st.get("exposure", 0))
            if ex != 0:
                img = ImageEnhance.Brightness(img).enhance(max(0.05, 1.0 + (ex / 120.0)))
        except Exception:
            pass
        try:
            temp = int(st.get("temperature", 0))
            if temp != 0:
                arr = np.array(img, dtype=np.int16)
                delta = int(temp * 0.65)
                arr[:, :, 0] = np.clip(arr[:, :, 0] + delta, 0, 255)
                arr[:, :, 2] = np.clip(arr[:, :, 2] - delta, 0, 255)
                img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        except Exception:
            pass
        return img

    def _cubic_bezier_progress(self, t, x1, y1, x2, y2):
        # Solve cubic-bezier x(s)=t, then return y(s). UI-style easing curve.
        tt = max(0.0, min(1.0, float(t)))
        ax = 3.0 * x1 - 3.0 * x2 + 1.0
        bx = -6.0 * x1 + 3.0 * x2
        cx = 3.0 * x1
        ay = 3.0 * y1 - 3.0 * y2 + 1.0
        by = -6.0 * y1 + 3.0 * y2
        cy = 3.0 * y1
        s = tt
        for _ in range(7):
            xs = ((ax * s + bx) * s + cx) * s
            dx = (3.0 * ax * s + 2.0 * bx) * s + cx
            if abs(dx) < 1e-6:
                break
            s2 = s - (xs - tt) / dx
            if s2 < 0.0 or s2 > 1.0:
                break
            s = s2
        lo = 0.0
        hi = 1.0
        for _ in range(12):
            xs = ((ax * s + bx) * s + cx) * s
            if xs < tt:
                lo = s
            else:
                hi = s
            s = (lo + hi) * 0.5
        ys = ((ay * s + by) * s + cy) * s
        return max(0.0, min(1.0, float(ys)))

    def _ease_progress(self, layer, k):
        kk = max(0.0, min(1.0, float(k)))
        ease = str((layer or {}).get("anim_ease", "linear") or "linear").strip().lower()
        if ease == "ease_in":
            return kk * kk
        if ease == "ease_out":
            return 1.0 - (1.0 - kk) * (1.0 - kk)
        if ease == "ease_in_out":
            if kk < 0.5:
                return 2.0 * kk * kk
            return 1.0 - ((-2.0 * kk + 2.0) ** 2) * 0.5
        if ease == "bezier":
            bz = (layer or {}).get("anim_bezier", [0.25, 0.1, 0.25, 1.0])
            if not isinstance(bz, (list, tuple)) or len(bz) < 4:
                bz = [0.25, 0.1, 0.25, 1.0]
            try:
                x1 = max(0.0, min(1.0, float(bz[0])))
                y1 = max(0.0, min(1.0, float(bz[1])))
                x2 = max(0.0, min(1.0, float(bz[2])))
                y2 = max(0.0, min(1.0, float(bz[3])))
            except Exception:
                x1, y1, x2, y2 = 0.25, 0.1, 0.25, 1.0
            return self._cubic_bezier_progress(kk, x1, y1, x2, y2)
        return kk

    def _layer_t_xy(self, layer, t_ms):
        try:
            x0 = float(layer.get("x", 24))
            y0 = float(layer.get("y", 24))
            x1 = float(layer.get("x1", x0))
            y1 = float(layer.get("y1", y0))
            t0 = int(layer.get("anim_in_ms", layer.get("start_ms", 0)) or layer.get("start_ms", 0))
            t1 = int(layer.get("anim_out_ms", layer.get("end_ms", 0)) or layer.get("end_ms", 0))
            c0 = int(layer.get("start_ms", 0) or 0)
            c1 = int(layer.get("end_ms", t1) or t1)
            t0 = max(c0, min(c1, t0))
            t1 = max(t0, min(c1, t1))
            if t1 <= t0:
                return int(round(x0)), int(round(y0))
            if t_ms <= t0:
                k = 0.0
            elif t_ms >= t1:
                k = 1.0
            else:
                k = float(t_ms - t0) / float(max(1, t1 - t0))
            k = self._ease_progress(layer, k)
            x = x0 + (x1 - x0) * k
            y = y0 + (y1 - y0) * k
            return int(round(x)), int(round(y))
        except Exception:
            return int(layer.get("x", 24)), int(layer.get("y", 24))

    def _load_media_layer_frame(self, layer, t_ms=0):
        path = str((layer or {}).get("path", "") or "").strip()
        if not path or (not os.path.exists(path)):
            return None
        mtype = str((layer or {}).get("type", "") or "").strip().lower()
        if not mtype:
            low = path.lower()
            if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
                mtype = "video"
            elif low.endswith(".gif"):
                mtype = "gif"
            else:
                mtype = "image"
        try:
            bucket = int(int(t_ms) // 120) if mtype == "video" else int(int(t_ms) // 100)
            key = (path, mtype, bucket if mtype in ("video", "gif") else 0)
            cache = getattr(self, "_media_layer_cache", None)
            if isinstance(cache, dict) and key in cache:
                try:
                    return cache[key].copy()
                except Exception:
                    return cache[key]
            frame = None
            if mtype == "video":
                frame = self._get_video_frame_at_ms(path, int(max(0, t_ms)))
                if frame is None:
                    frame = self._get_first_frame(path)
                if frame is not None:
                    frame = frame.convert("RGBA")
            elif mtype == "gif":
                try:
                    with Image.open(path) as gim:
                        n = max(1, int(getattr(gim, "n_frames", 1) or 1))
                        if n > 1:
                            idx = int(max(0, t_ms) / 80.0) % n
                            gim.seek(idx)
                        frame = gim.convert("RGBA")
                except Exception:
                    ff = self._get_first_frame(path)
                    frame = ff.convert("RGBA") if ff is not None else None
            else:
                with Image.open(path) as im:
                    frame = im.convert("RGBA")
            if frame is None:
                return None
            if isinstance(cache, dict):
                if len(cache) > 48:
                    try:
                        for k in list(cache.keys())[:16]:
                            cache.pop(k, None)
                    except Exception:
                        cache.clear()
                cache[key] = frame.copy()
            return frame
        except Exception:
            return None

    def _draw_media_layers(self, pil, t_ms=0):
        st = getattr(self, "editor_state", {}) or {}
        layers = st.get("media_layers", []) or []
        if not layers:
            return pil
        base = pil.convert("RGBA")
        for layer in layers:
            try:
                if not bool((layer or {}).get("enabled", True)):
                    continue
                t0 = int((layer or {}).get("start_ms", 0) or 0)
                t1 = int((layer or {}).get("end_ms", 0) or 0)
                if t1 > t0 and (int(t_ms) < t0 or int(t_ms) > t1):
                    continue
                try:
                    spd = float((layer or {}).get("speed", 1.0) or 1.0)
                except Exception:
                    spd = 1.0
                spd = max(0.05, min(16.0, spd))
                local_t = int(max(0, (int(t_ms) - t0) * spd))
                ov = self._load_media_layer_frame(layer or {}, t_ms=local_t)
                if ov is None:
                    continue
                sx = max(0.1, min(8.0, float((layer or {}).get("scale_x", 1.0) or 1.0)))
                sy = max(0.1, min(8.0, float((layer or {}).get("scale_y", 1.0) or 1.0)))
                if abs(sx - 1.0) > 0.01 or abs(sy - 1.0) > 0.01:
                    ow = max(1, int(ov.width * sx))
                    oh = max(1, int(ov.height * sy))
                    ov = ov.resize((ow, oh), Image.Resampling.LANCZOS)
                alpha = max(0, min(255, int((layer or {}).get("alpha", 255) or 255)))
                if alpha < 255:
                    a = ov.split()[-1]
                    a = a.point(lambda v: int(v * alpha / 255))
                    ov.putalpha(a)
                x, y = self._layer_t_xy(layer or {}, int(t_ms))
                blend = str((layer or {}).get("blend", "normal") or "normal").strip().lower()
                if blend == "normal":
                    base.alpha_composite(ov, (int(x), int(y)))
                    continue
                bx0 = max(0, int(x))
                by0 = max(0, int(y))
                bx1 = min(base.width, int(x) + ov.width)
                by1 = min(base.height, int(y) + ov.height)
                if bx1 <= bx0 or by1 <= by0:
                    continue
                ox0 = max(0, -int(x))
                oy0 = max(0, -int(y))
                ovc = ov.crop((ox0, oy0, ox0 + (bx1 - bx0), oy0 + (by1 - by0)))
                reg = base.crop((bx0, by0, bx1, by1)).convert("RGB")
                ov_rgb = ovc.convert("RGB")
                if blend == "screen":
                    mixed = ImageChops.screen(reg, ov_rgb)
                elif blend == "multiply":
                    mixed = ImageChops.multiply(reg, ov_rgb)
                elif blend == "add":
                    mixed = ImageChops.add(reg, ov_rgb, scale=1.0, offset=0)
                else:
                    mixed = ov_rgb
                rr = reg.convert("RGBA")
                rr.paste(mixed.convert("RGBA"), (0, 0), ovc.split()[-1])
                base.paste(rr, (bx0, by0))
            except Exception:
                continue
        return base.convert("RGB")

    def _draw_text_layers(self, pil, t_ms=0):
        st = getattr(self, "editor_state", {}) or {}
        layers = st.get("text_layers", []) or []
        if not layers:
            return pil
        img = pil.convert("RGBA")
        for lyr in layers:
            try:
                if not bool(lyr.get("enabled", True)):
                    continue
                txt = str(lyr.get("text", "") or "").strip()
                if not txt:
                    continue
                t0 = int(lyr.get("start_ms", 0))
                t1 = int(lyr.get("end_ms", 0))
                if t1 > t0 and (t_ms < t0 or t_ms > t1):
                    continue
                x, y = self._layer_t_xy(lyr, t_ms)
                size = int(lyr.get("size", 28))
                font = self._safe_font(lyr.get("font", "Arial"), size)
                rgba = lyr.get("color_rgba", (255, 255, 255, 220))
                try:
                    r, g, b, a = int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])
                except Exception:
                    r, g, b, a = 255, 255, 255, 220
                sx = float(lyr.get("scale_x", 1.0))
                sy = float(lyr.get("scale_y", 1.0))
                sx = max(0.1, min(8.0, sx))
                sy = max(0.1, min(8.0, sy))
                if abs(sx - 1.0) > 0.02 or abs(sy - 1.0) > 0.02:
                    tmp = Image.new("RGBA", (max(64, img.width), max(64, img.height)), (0, 0, 0, 0))
                    td = ImageDraw.Draw(tmp, "RGBA")
                    td.text((0, 0), txt, fill=(r, g, b, a), font=font)
                    bb = tmp.getbbox()
                    if bb:
                        glyph = tmp.crop(bb)
                        gw = max(1, int(glyph.width * sx))
                        gh = max(1, int(glyph.height * sy))
                        glyph = glyph.resize((gw, gh), Image.Resampling.BICUBIC)
                        img.alpha_composite(glyph, (x, y))
                else:
                    d = ImageDraw.Draw(img, "RGBA")
                    d.text((x, y), txt, fill=(r, g, b, a), font=font)
            except Exception:
                continue
        return img.convert("RGB")

    def _apply_editor_nodes(self, pil, t_ms=0):
        st = getattr(self, "editor_state", {}) or {}
        if not bool(st.get("nodes_enabled", False)):
            return pil
        img = pil.convert("RGB")
        chain = [str(x).strip() for x in (st.get("node_chain", []) or []) if str(x).strip()]
        params = st.get("node_params", []) or []
        order = self._resolve_editor_node_chain(st)
        for idx in order:
            if idx < 0 or idx >= len(chain):
                continue
            nid = str(chain[idx] or "").strip().lower()
            prm = params[idx] if idx < len(params) and isinstance(params[idx], dict) else {}
            if not bool(prm.get("enabled", True)):
                continue
            intensity = max(0, min(100, int(prm.get("intensity", 55) or 55)))
            radius = max(0, min(32, int(prm.get("radius", 2) or 2)))
            mix = max(0.0, min(1.0, float(int(prm.get("mix", 100) or 100)) / 100.0))
            value = max(-200, min(200, int(prm.get("value", 0) or 0)))
            seed = max(0, min(9999, int(prm.get("seed", 0) or 0)))
            if nid in ("video-in", "video-out", "audio-in", "audio-gain", "audio-lowpass", "audio-analyzer", "value-node", "math-add", "switch-node", "if-node", "python-script"):
                continue
            try:
                if nid == "bypass":
                    pass
                elif nid == "blur":
                    rr = max(0.1, float(radius) * (0.35 + intensity / 120.0))
                    fx = img.filter(ImageFilter.GaussianBlur(radius=rr))
                    img = Image.blend(img, fx, mix)
                elif nid == "brightness-node":
                    factor = max(0.05, 1.0 + ((intensity - 50) / 50.0) * 0.85 + (value / 240.0))
                    fx = ImageEnhance.Brightness(img).enhance(factor)
                    img = Image.blend(img, fx, mix)
                elif nid == "contrast-node":
                    factor = max(0.05, 1.0 + ((intensity - 50) / 50.0) * 0.95 + (value / 260.0))
                    fx = ImageEnhance.Contrast(img).enhance(factor)
                    img = Image.blend(img, fx, mix)
                elif nid == "saturation-node":
                    factor = max(0.0, 1.0 + ((intensity - 50) / 50.0) * 1.2 + (value / 220.0))
                    fx = ImageEnhance.Color(img).enhance(factor)
                    img = Image.blend(img, fx, mix)
                elif nid == "hue-shift":
                    hsv = np.array(img.convert("HSV"), dtype=np.uint8)
                    shift = int(round((intensity - 50) * 0.9 + value))
                    hsv[:, :, 0] = (hsv[:, :, 0].astype(np.int16) + shift) % 255
                    fx = Image.fromarray(hsv, mode="HSV").convert("RGB")
                    img = Image.blend(img, fx, mix)
                elif nid == "gamma-node":
                    g = max(0.2, min(4.0, 1.0 + ((50 - intensity) / 80.0) + (value / 320.0)))
                    inv = 1.0 / g
                    lut = [int(((i / 255.0) ** inv) * 255.0) for i in range(256)]
                    fx = img.point(lut * 3)
                    img = Image.blend(img, fx, mix)
                elif nid == "autocontrast":
                    fx = ImageOps.autocontrast(img, cutoff=max(0, min(20, int(10 - intensity / 12))))
                    img = Image.blend(img, fx, mix)
                elif nid == "equalize":
                    fx = ImageOps.equalize(img.convert("RGB"))
                    img = Image.blend(img, fx, mix)
                elif nid == "sharpen":
                    fx = img.filter(ImageFilter.UnsharpMask(radius=max(1, radius), percent=max(60, intensity * 2), threshold=2))
                    img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                elif nid == "median-denoise":
                    ksz = max(3, min(9, int(radius) * 2 + 1))
                    fx = img.filter(ImageFilter.MedianFilter(size=ksz))
                    img = Image.blend(img, fx, mix)
                elif nid == "motion-blur":
                    arr = np.array(img.convert("RGB"), dtype=np.float32)
                    sh = max(1, int(radius + intensity / 18.0))
                    acc = arr.copy()
                    taps = max(2, min(16, int(2 + intensity / 8.0)))
                    for k in range(1, taps):
                        w = (taps - k) / float(taps)
                        acc += np.roll(arr, shift=int(k * sh / 2), axis=1) * w
                    fx = Image.fromarray(np.clip(acc / (1.0 + sum((taps - k) / float(taps) for k in range(1, taps))), 0, 255).astype(np.uint8), mode="RGB")
                    img = Image.blend(img, fx, mix)
                elif nid == "edge":
                    fx = img.filter(ImageFilter.FIND_EDGES).convert("RGB")
                    img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                elif nid == "posterize":
                    bits = max(2, min(8, 8 - int(intensity / 16)))
                    fx = ImageOps.posterize(img.convert("RGB"), bits)
                    img = Image.blend(img, fx, mix)
                elif nid == "invert":
                    fx = ImageOps.invert(img.convert("RGB"))
                    img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                elif nid == "emboss":
                    fx = img.filter(ImageFilter.EMBOSS).convert("RGB")
                    img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                elif nid == "grayscale":
                    fx = ImageOps.grayscale(img).convert("RGB")
                    img = Image.blend(img, fx, mix)
                elif nid == "solarize":
                    thr = int(max(1, min(254, 128 + value - int((intensity - 50) * 1.2))))
                    fx = ImageOps.solarize(img.convert("RGB"), threshold=thr)
                    img = Image.blend(img, fx, mix)
                elif nid == "pixelate":
                    step = max(2, int(2 + radius + intensity / 14.0))
                    w, h = img.size
                    sx = max(1, w // step)
                    sy = max(1, h // step)
                    fx = img.resize((sx, sy), Image.Resampling.NEAREST).resize((w, h), Image.Resampling.NEAREST)
                    img = Image.blend(img, fx, mix)
                elif nid == "glitch-lite":
                    fx = self._apply_glitch_effect(img, amount_override=max(8, int(intensity * 0.75)))
                    img = Image.blend(img, fx, mix)
                elif nid == "vignette":
                    arr = np.array(img.convert("RGB"), dtype=np.float32)
                    hh, ww = arr.shape[:2]
                    yy, xx = np.ogrid[:hh, :ww]
                    cx = (ww - 1) * 0.5
                    cy = (hh - 1) * 0.5
                    rx = max(1.0, ww * 0.5)
                    ry = max(1.0, hh * 0.5)
                    dist = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
                    power = max(0.4, 0.9 + radius * 0.08)
                    fade = np.clip(1.0 - (dist ** power) * (intensity / 100.0), 0.12, 1.0)
                    arr *= fade[..., None]
                    fx = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
                    img = Image.blend(img, fx, mix)
                elif nid == "bloom-lite":
                    rr = max(0.8, float(radius) * (0.25 + intensity / 160.0))
                    fx = img.filter(ImageFilter.GaussianBlur(radius=rr)).convert("RGB")
                    img = Image.blend(img, fx, max(0.0, min(0.62, (intensity / 125.0) * mix)))
                elif nid == "threshold":
                    g = img.convert("L")
                    thr = int(max(8, min(246, 255 * (0.15 + intensity / 140.0) + value)))
                    bw = g.point(lambda p, t=thr: 255 if p >= t else 0).convert("RGB")
                    img = Image.blend(img, bw, max(0.0, min(1.0, (0.25 + intensity / 120.0) * mix)))
                elif nid == "noise":
                    arr = np.array(img.convert("RGB"), dtype=np.float32)
                    amp = max(1.0, intensity * 0.9)
                    rng = np.random.default_rng(int(seed) + int(t_ms) % 100000)
                    arr += rng.normal(0.0, amp, arr.shape)
                    fx = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
                    img = Image.blend(img, fx, mix)
                elif nid == "channel-shift":
                    arr = np.array(img.convert("RGB"), dtype=np.uint8)
                    sh = max(1, int(round(radius + intensity / 24.0)))
                    mix2 = max(0.0, min(1.0, mix * (intensity / 100.0)))
                    r = np.roll(arr[:, :, 0], sh, axis=1)
                    b = np.roll(arr[:, :, 2], -sh, axis=0)
                    out = arr.copy()
                    out[:, :, 0] = np.clip((1.0 - mix2) * arr[:, :, 0] + mix2 * r, 0, 255).astype(np.uint8)
                    out[:, :, 2] = np.clip((1.0 - mix2) * arr[:, :, 2] + mix2 * b, 0, 255).astype(np.uint8)
                    img = Image.fromarray(out, mode="RGB")
            except Exception:
                continue
        code = str(st.get("nodes_code", "") or "").strip()
        if not code:
            return img
        try:
            safe_builtins = {
                "abs": abs,
                "min": min,
                "max": max,
                "round": round,
                "int": int,
                "float": float,
                "len": len,
                "range": range,
                "sum": sum,
                "enumerate": enumerate,
                "zip": zip,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "sorted": sorted,
                "print": print,
            }
            env = {
                "__builtins__": safe_builtins,
                "np": np,
                "Image": Image,
                "ImageFilter": ImageFilter,
                "ImageEnhance": ImageEnhance,
                "ImageOps": ImageOps,
                "cv2": cv2,
            }
            local = {}
            exec(code, env, local)
            fn = local.get("process", env.get("process"))
            if callable(fn):
                out = fn(img.copy(), int(t_ms), dict(st))
                if isinstance(out, Image.Image):
                    return out.convert("RGB")
                if isinstance(out, np.ndarray):
                    arr = np.array(out)
                    if arr.ndim == 2:
                        arr = np.stack([arr, arr, arr], axis=-1)
                    if arr.dtype != np.uint8:
                        arr = np.clip(arr, 0, 255).astype(np.uint8)
                    return Image.fromarray(arr[:, :, :3], mode="RGB")
        except Exception:
            pass
        return img

    def _resolve_editor_node_chain(self, st):
        chain = [str(x).strip() for x in (st.get("node_chain", []) or []) if str(x).strip()]
        if not chain:
            return []
        links = []
        for link in (st.get("node_links", []) or []):
            try:
                if isinstance(link, dict):
                    a = int(link.get("src", -1))
                    b = int(link.get("dst", -1))
                else:
                    a, b = int(link[0]), int(link[1])
            except Exception:
                continue
            if a < 0 or b < 0 or a >= len(chain) or b >= len(chain) or a == b:
                continue
            links.append((a, b))
        if not links:
            return list(range(len(chain)))
        incoming = {i: 0 for i in range(len(chain))}
        out = {i: [] for i in range(len(chain))}
        for a, b in links:
            out[a].append(b)
            incoming[b] += 1
        base = list(range(len(chain)))
        ready = [i for i in base if incoming[i] == 0]
        ordered = []
        while ready:
            n = ready.pop(0)
            ordered.append(n)
            for m in out.get(n, []):
                incoming[m] -= 1
                if incoming[m] == 0:
                    ready.append(m)
            ready.sort()
        if len(ordered) < len(chain):
            for i in base:
                if i not in ordered:
                    ordered.append(i)
        return [i for i in ordered if 0 <= i < len(chain)]

    def _editor_photo_paint_layer(self, st, target_size):
        if not isinstance(st, dict):
            return None
        payload = str(st.get("photo_paint_png_b64", "") or "").strip()
        if not payload:
            return None
        token = str(st.get("photo_paint_hash", "") or "")
        if not token:
            try:
                token = hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()
            except Exception:
                token = f"len:{len(payload)}"
        if token != getattr(self, "_photo_paint_cache_token", None):
            try:
                raw = base64.b64decode(payload.encode("ascii"), validate=False)
                layer = Image.open(io.BytesIO(raw)).convert("RGBA")
            except Exception:
                layer = None
            self._photo_paint_cache_token = token
            self._photo_paint_cache_base = layer
            self._photo_paint_cache_scaled_size = None
            self._photo_paint_cache_scaled = None
        base_layer = getattr(self, "_photo_paint_cache_base", None)
        if base_layer is None:
            return None
        tgt = (max(1, int(target_size[0])), max(1, int(target_size[1])))
        try:
            if base_layer.size == tgt:
                return base_layer.copy()
            if tgt != getattr(self, "_photo_paint_cache_scaled_size", None):
                self._photo_paint_cache_scaled = base_layer.resize(tgt, Image.Resampling.LANCZOS)
                self._photo_paint_cache_scaled_size = tgt
            scaled = getattr(self, "_photo_paint_cache_scaled", None)
            return scaled.copy() if scaled is not None else None
        except Exception:
            return None

    def _apply_editor_photo_paint(self, pil_img, st):
        if not isinstance(st, dict):
            return pil_img
        if not bool(st.get("photo_paint_enabled", False)):
            return pil_img
        opacity = max(0, min(100, int(st.get("photo_paint_opacity", 100) or 100)))
        if opacity <= 0:
            return pil_img
        layer = self._editor_photo_paint_layer(st, pil_img.size)
        if layer is None:
            return pil_img
        if opacity < 100:
            try:
                a = np.array(layer.split()[-1], dtype=np.float32)
                a *= float(opacity) / 100.0
                layer.putalpha(np.clip(a, 0, 255).astype(np.uint8))
            except Exception:
                pass
        base = pil_img.convert("RGBA")
        try:
            base.alpha_composite(layer)
            return base.convert("RGB")
        except Exception:
            return pil_img

    def _apply_editor_state(self, pil, t_ms=0):
        st = getattr(self, "editor_state", {}) or {}
        if not bool(st.get("enabled", False)):
            return pil.convert("RGB")
        img = pil.convert("RGB")
        try:
            if bool(st.get("crop_enabled", False)):
                x = max(0, int(st.get("crop_x", 0)))
                y = max(0, int(st.get("crop_y", 0)))
                w = max(1, int(st.get("crop_w", img.width)))
                h = max(1, int(st.get("crop_h", img.height)))
                x2 = min(img.width, x + w)
                y2 = min(img.height, y + h)
                if x2 > x + 1 and y2 > y + 1:
                    img = img.crop((x, y, x2, y2))
        except Exception:
            pass
        try:
            if bool(st.get("mask_enabled", False)) or bool(st.get("mask_use_image", False)):
                fx = self._apply_editor_basic_fx(img.copy())
                used_media_mask = False
                if bool(st.get("mask_use_image", False)):
                    mpath = str(st.get("mask_image_path", "") or "").strip()
                    if mpath:
                        try:
                            mtype = "image"
                            low = mpath.lower()
                            if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
                                mtype = "video"
                            elif low.endswith(".gif"):
                                mtype = "gif"
                            mlyr = {"path": mpath, "type": mtype}
                            msrc = self._load_media_layer_frame(mlyr, int(t_ms))
                            if msrc is not None:
                                mm = ImageOps.fit(msrc.convert("L"), img.size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                                img = Image.composite(fx, img, mm)
                                used_media_mask = True
                        except Exception:
                            used_media_mask = False
                if not used_media_mask:
                    mx = max(0, int(st.get("mask_x", 0)))
                    my = max(0, int(st.get("mask_y", 0)))
                    mw = max(1, int(st.get("mask_w", img.width)))
                    mh = max(1, int(st.get("mask_h", img.height)))
                    mx2 = min(img.width, mx + mw)
                    my2 = min(img.height, my + mh)
                    if mx2 > mx + 1 and my2 > my + 1:
                        m = Image.new("L", img.size, 0)
                        md = ImageDraw.Draw(m)
                        md.rectangle((mx, my, mx2, my2), fill=255)
                        img = Image.composite(fx, img, m)
                    else:
                        img = fx
            else:
                img = self._apply_editor_basic_fx(img)
        except Exception:
            pass
        img = self._apply_editor_nodes(img, t_ms=t_ms)
        img = self._draw_media_layers(img, t_ms=t_ms)
        img = self._draw_text_layers(img, t_ms=t_ms)
        img = self._apply_editor_photo_paint(img, st)
        return img

    def _build_embedded_editor_host(self, parent_widget):
        if self._embedded_editor_frame is not None:
            return
        holder = QFrame(parent_widget)
        holder.setObjectName("embedded_editor_frame")
        holder.setStyleSheet(
            "QFrame#embedded_editor_frame{"
            "background: rgba(6,10,16,0.94);"
            "border: 1px solid rgba(132,190,255,0.30);"
            "border-radius: 12px;"
            "}"
        )
        holder.hide()
        root = QVBoxLayout(holder)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)
        hdr = QFrame(holder)
        hdr.setObjectName("embedded_editor_header")
        hdr.setStyleSheet(
            "QFrame#embedded_editor_header{"
            "background: rgba(18,24,36,0.86);"
            "border:1px solid rgba(130,176,236,0.24);"
            "border-radius:10px;"
            "}"
        )
        hr = QHBoxLayout(hdr)
        hr.setContentsMargins(10, 6, 10, 6)
        hr.setSpacing(8)
        ttl = QLabel(TRANSLATIONS.get(self.lang, TRANSLATIONS["en"]).get("editor", "Editor"), hdr)
        ttl.setStyleSheet("font-weight:700; font-size:12px;")
        full_btn = QPushButton(TRANSLATIONS.get(self.lang, TRANSLATIONS["en"]).get("editor_fullscreen", "Fullscreen editor"), hdr)
        close_btn = QPushButton("x", hdr)
        full_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setCursor(Qt.PointingHandCursor)
        full_btn.setFixedHeight(30)
        close_btn.setFixedSize(30, 30)
        full_btn.setStyleSheet(self._glass_btn_css())
        close_btn.setStyleSheet(self._glass_btn_css())
        try:
            ico = self._load_svg_icon("close", "#dfe8f6")
            if ico is not None:
                close_btn.setText("")
                close_btn.setIcon(ico)
                close_btn.setIconSize(QSize(12, 12))
        except Exception:
            pass
        hr.addWidget(ttl, 1)
        hr.addWidget(full_btn, 0)
        hr.addWidget(close_btn, 0)
        root.addWidget(hdr, 0)
        body = QFrame(holder)
        body.setObjectName("embedded_editor_body")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(0)
        root.addWidget(body, 1)
        self._embedded_editor_frame = holder
        self._embedded_editor_header = ttl
        self._embedded_editor_body = body
        self._embedded_editor_body_layout = body_l
        self._embedded_editor_full_btn = full_btn
        self._embedded_editor_close_btn = close_btn
        self._embedded_editor_full_btn.clicked.connect(self._toggle_embedded_editor_fullscreen)
        self._embedded_editor_close_btn.clicked.connect(lambda: self._close_embedded_editor(apply=False))
        self._style_embedded_editor_host()
        self._layout_embedded_editor_host()

    def _style_embedded_editor_host(self):
        fr = self._embedded_editor_frame
        if fr is None:
            return
        if self.theme == "light":
            bg = "rgba(250,252,255,0.96)"
            bd = "rgba(94,128,170,0.34)"
            hb = "rgba(240,246,253,0.96)"
        elif self.theme == "cyberpunk 2077":
            bg = "rgba(14,6,10,0.95)"
            bd = "rgba(234,48,72,0.42)"
            hb = "rgba(22,8,14,0.94)"
        elif self.theme == "dedsec":
            bg = "rgba(6,12,8,0.95)"
            bd = "rgba(88,255,138,0.38)"
            hb = "rgba(8,16,10,0.92)"
        elif self.theme == "custom":
            bg = str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29")
            bd = str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff")
            hb = bg
        else:
            bg = "rgba(6,10,16,0.94)"
            bd = "rgba(132,190,255,0.30)"
            hb = "rgba(18,24,36,0.86)"
        fr.setStyleSheet(
            "QFrame#embedded_editor_frame{"
            f"background:{bg}; border:1px solid {bd}; border-radius:12px;"
            "}"
        )
        if self._embedded_editor_header is not None and self._embedded_editor_header.parent() is not None:
            try:
                self._embedded_editor_header.parent().setStyleSheet(
                    "QFrame#embedded_editor_header{"
                    f"background:{hb}; border:1px solid {bd}; border-radius:10px;"
                    "}"
                )
            except Exception:
                pass

    def _layout_embedded_editor_host(self):
        fr = self._embedded_editor_frame
        cw = self.centralWidget()
        if fr is None or cw is None:
            return
        if bool(getattr(self, "_embedded_editor_active", False)):
            try:
                for wname in ("gallery_frame", "left_frame", "right_frame"):
                    w = getattr(self, wname, None)
                    if w is not None and w.isVisible():
                        w.hide()
            except Exception:
                pass
        margin = 0 if bool(self._embedded_editor_full) else 6
        r = cw.rect().adjusted(margin, margin, -margin, -margin)
        fr.setGeometry(r)
        fr.raise_()
        try:
            if self._embedded_editor_widget is not None:
                self._embedded_editor_widget.raise_()
        except Exception:
            pass

    def _suspend_background_animations_for_editor(self):
        try:
            if bool(getattr(self, "_embedded_editor_timer_state", None)):
                return
            st = {}
            for name in ("bg_anim_timer", "trail_timer", "cursor_sample_timer"):
                timer = getattr(self, name, None)
                if timer is None:
                    continue
                st[name] = (bool(timer.isActive()), int(timer.interval()))
                if timer.isActive():
                    timer.stop()
            self._embedded_editor_timer_state = st
        except Exception:
            pass

    def _resume_background_animations_from_editor(self):
        try:
            st = self._embedded_editor_timer_state if isinstance(self._embedded_editor_timer_state, dict) else {}
            for name, meta in st.items():
                timer = getattr(self, name, None)
                if timer is None:
                    continue
                try:
                    was_active = bool(meta[0])
                    interval = int(meta[1])
                except Exception:
                    was_active = True
                    interval = int(timer.interval() or 16)
                try:
                    timer.setInterval(max(1, interval))
                except Exception:
                    pass
                if was_active and not timer.isActive():
                    timer.start()
        except Exception:
            pass
        self._embedded_editor_timer_state = None
        try:
            self._sync_perf_mode()
        except Exception:
            pass

    def _on_embedded_editor_rejected(self):
        self._close_embedded_editor(apply=False)

    def _toggle_embedded_editor_fullscreen(self):
        if self._embedded_editor_frame is None or not self._embedded_editor_frame.isVisible():
            return False
        self._embedded_editor_full = not bool(self._embedded_editor_full)
        if self._embedded_editor_full:
            self._embedded_editor_prev_fullscreen = bool(self.isFullScreen())
            if not self._embedded_editor_prev_fullscreen:
                self.showFullScreen()
        else:
            if not bool(getattr(self, "_embedded_editor_prev_fullscreen", False)) and self.isFullScreen():
                self.showNormal()
        self._layout_embedded_editor_host()
        try:
            if self._embedded_editor_widget is not None and hasattr(self._embedded_editor_widget, "set_embedded_fullscreen_state"):
                self._embedded_editor_widget.set_embedded_fullscreen_state(self._embedded_editor_full)
        except Exception:
            pass
        if hasattr(self, "_embedded_editor_full_btn") and self._embedded_editor_full_btn is not None:
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            self._embedded_editor_full_btn.setText(
                tr.get("editor_fullscreen_exit", "Exit fullscreen editor")
                if self._embedded_editor_full
                else tr.get("editor_fullscreen", "Fullscreen editor")
            )
        return bool(self._embedded_editor_full)

    def _set_main_menu_visible(self, visible):
        try:
            mb = self.menuBar()
            if mb is None:
                return
            if not bool(visible):
                self._menu_prev_visible = bool(mb.isVisible())
                mb.setVisible(False)
            else:
                restore_to = True if self._menu_prev_visible is None else bool(self._menu_prev_visible)
                mb.setVisible(bool(restore_to))
                self._menu_prev_visible = None
        except Exception:
            pass

    def _open_embedded_editor(self, src_pil, duration_ms, tr, photo_mode=False):
        self._embedded_editor_opening = True
        self._prepare_modal_ui()
        self._build_embedded_editor_host(self.centralWidget())
        self._close_embedded_editor(apply=False, restore_modal=False)
        self._set_main_menu_visible(False)
        try:
            self._embedded_prev_panel_vis = {}
            for wname in ("gallery_frame", "left_frame", "right_frame"):
                w = getattr(self, wname, None)
                if w is not None:
                    self._embedded_prev_panel_vis[wname] = bool(w.isVisible())
                    w.hide()
            if hasattr(self, "trail_overlay") and self.trail_overlay is not None:
                self.trail_overlay.hide()
                self._trail_overlay_stack_dirty = True
            self._embedded_editor_active = True
            self._embedded_editor_open_ts = float(time.time())
            self._suspend_background_animations_for_editor()
        except Exception:
            pass
        try:
            ed = AdvancedEditorDialog(
                self,
                src_pil,
                copy.deepcopy(getattr(self, "editor_state", {}) or {}),
                duration_ms=int(max(1000, int(duration_ms or 6000))),
                tr=tr,
                embedded=True,
                photo_mode=bool(photo_mode),
            )
            self._embedded_editor_widget = ed
            try:
                self._embedded_editor_source = src_pil.copy()
            except Exception:
                self._embedded_editor_source = src_pil
            try:
                self._embedded_editor_header.setText(tr.get("editor", "Editor"))
            except Exception:
                pass
            self._embedded_editor_body_layout.addWidget(ed, 1)
            ed.accepted.connect(self._on_embedded_editor_accepted)
            ed.rejected.connect(self._on_embedded_editor_rejected)
            self._embedded_editor_full = False
            if hasattr(self, "_embedded_editor_full_btn") and self._embedded_editor_full_btn is not None:
                self._embedded_editor_full_btn.setText(tr.get("editor_fullscreen", "Fullscreen editor"))
            self._embedded_editor_frame.show()
            self._layout_embedded_editor_host()
            QTimer.singleShot(0, self._layout_embedded_editor_host)
            try:
                if self._embedded_editor_raise_timer is None:
                    self._embedded_editor_raise_timer = QTimer(self)
                    self._embedded_editor_raise_timer.setInterval(120)
                    self._embedded_editor_raise_timer.timeout.connect(self._layout_embedded_editor_host)
                self._embedded_editor_raise_timer.start()
            except Exception:
                pass
            ed.show()
            ed.raise_()
            ed.setFocus()
        except Exception:
            self._close_embedded_editor(apply=False, restore_modal=True)
            raise
        finally:
            self._embedded_editor_opening = False

    def _apply_editor_ascii_bridge(self, st):
        if not isinstance(st, dict) or not bool(st.get("ascii_bridge_apply", False)):
            return
        try:
            self.style = str(st.get("ascii_style", self.style) or self.style)
            self.width_chars = int(st.get("ascii_width", self.width_chars) or self.width_chars)
            self.font_size = int(st.get("ascii_font_size", self.font_size) or self.font_size)
            self.ascii_chars = str(st.get("ascii_charset", self.ascii_chars) or self.ascii_chars)
            self.fg_hex = str(st.get("ascii_fg_hex", self.fg_hex) or self.fg_hex)
            self.bg_hex = str(st.get("ascii_bg_hex", self.bg_hex) or self.bg_hex)
            self.pro_tools = bool(st.get("ascii_pro_tools", self.pro_tools))
            self.pro_bloom = int(st.get("ascii_pro_bloom", getattr(self, "pro_bloom", 0)) or 0)
            self.pro_vignette = int(st.get("ascii_pro_vignette", getattr(self, "pro_vignette", 0)) or 0)
            self.pro_grain = int(st.get("ascii_pro_grain", getattr(self, "pro_grain", 0)) or 0)
            self.pro_chroma = int(st.get("ascii_pro_chroma", getattr(self, "pro_chroma", 0)) or 0)
            self.pro_glitch = int(st.get("ascii_pro_glitch", getattr(self, "pro_glitch", 0)) or 0)
            try:
                if hasattr(self, "style_combo"):
                    self.style_combo.setCurrentText(self.style)
                if hasattr(self, "width_slider"):
                    self.width_slider.setValue(int(self.width_chars))
                if hasattr(self, "font_slider"):
                    self.font_slider.setValue(int(self.font_size))
                if hasattr(self, "charset_input"):
                    self.charset_input.setText(str(self.ascii_chars or ""))
                if hasattr(self, "pro_tools_chk"):
                    self.pro_tools_chk.setChecked(bool(self.pro_tools))
                if hasattr(self, "pro_bloom_slider"):
                    self.pro_bloom_slider.setValue(int(self.pro_bloom))
                if hasattr(self, "pro_vignette_slider"):
                    self.pro_vignette_slider.setValue(int(self.pro_vignette))
                if hasattr(self, "pro_grain_slider"):
                    self.pro_grain_slider.setValue(int(self.pro_grain))
                if hasattr(self, "pro_chroma_spin"):
                    self.pro_chroma_spin.setValue(int(self.pro_chroma))
                if hasattr(self, "pro_glitch_slider"):
                    self.pro_glitch_slider.setValue(int(self.pro_glitch))
            except Exception:
                pass
        except Exception:
            pass

    def _on_embedded_editor_accepted(self):
        ed = self._embedded_editor_widget
        if ed is None:
            self._close_embedded_editor(apply=False)
            return
        self.editor_state = ed.result_state()
        self._apply_editor_ascii_bridge(self.editor_state)
        self._editor_last_preview_ms = int(ed.time_slider.value()) if hasattr(ed, "time_slider") else int(getattr(self, "_editor_last_preview_ms", 0))
        src_pil = self._embedded_editor_source
        src_path = str(self._effective_source_path() or "")
        low = src_path.lower()
        is_timed_media = bool(low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm", ".gif")))
        preview_src = None
        if is_timed_media and src_path:
            try:
                if low.endswith(".gif"):
                    preview_src = self._load_media_layer_frame({"path": src_path, "type": "gif"}, int(self._editor_last_preview_ms))
                else:
                    preview_src = self._get_video_frame_at_ms(src_path, int(self._editor_last_preview_ms))
            except Exception:
                preview_src = None
        if preview_src is None:
            preview_src = src_pil
        try:
            self._live_preview_source_pil = preview_src.copy()
        except Exception:
            self._live_preview_source_pil = preview_src
        try:
            pre = self._preprocess_pil(preview_src.copy(), t_ms=int(self._editor_last_preview_ms))
            keep_size = self.keep_size_chk.isChecked()
            target = None
            if int(self.render_out_w) > 0 and int(self.render_out_h) > 0:
                target = (int(self.render_out_w), int(self.render_out_h))
            elif keep_size or int(self.render_scale) > 1:
                target = pre.size
            if target and int(self.render_scale) > 1:
                target = (int(target[0] * int(self.render_scale)), int(target[1] * int(self.render_scale)))
            out = self._render_with_style(pre, output_size=target)
            self.current_output = out
            self._show_preview_pil(out, set_as_base=False, preserve_transform=True)
        except Exception:
            pass
        try:
            self._schedule_live_preview(force=True)
        except Exception:
            pass
        self._close_embedded_editor(apply=False)

    def _close_embedded_editor(self, apply=False, restore_modal=True):
        ed = self._embedded_editor_widget
        if apply and ed is not None:
            try:
                if hasattr(ed, "_request_accept"):
                    ed._request_accept()
                else:
                    ed.accept()
            except Exception:
                pass
        if self._embedded_editor_full:
            try:
                self._toggle_embedded_editor_fullscreen()
            except Exception:
                self._embedded_editor_full = False
        if ed is not None:
            try:
                if self._embedded_editor_body_layout is not None:
                    self._embedded_editor_body_layout.removeWidget(ed)
                ed.setParent(None)
                ed.deleteLater()
            except Exception:
                pass
        self._embedded_editor_widget = None
        self._embedded_editor_source = None
        try:
            if self._embedded_editor_frame is not None:
                self._embedded_editor_frame.hide()
        except Exception:
            pass
        try:
            if self._embedded_editor_raise_timer is not None:
                self._embedded_editor_raise_timer.stop()
        except Exception:
            pass
        self._embedded_editor_active = False
        self._embedded_editor_open_ts = 0.0
        self._resume_background_animations_from_editor()
        self._set_main_menu_visible(True)
        try:
            if isinstance(self._embedded_prev_panel_vis, dict):
                for wname, vis in self._embedded_prev_panel_vis.items():
                    w = getattr(self, wname, None)
                    if w is not None:
                        w.setVisible(bool(vis))
            self._embedded_prev_panel_vis = None
            if hasattr(self, "trail_overlay") and self.trail_overlay is not None:
                self.trail_overlay.show()
                self._trail_overlay_stack_dirty = True
                self._sync_trail_overlay_stack(force=True)
        except Exception:
            pass
        if restore_modal:
            self._restore_modal_ui()

    def _open_output_folder(self, out_path):
        try:
            p = Path(out_path)
            if not p.exists():
                return
            folder = p.parent
            if os.name == "nt":
                try:
                    os.startfile(str(folder))
                except Exception:
                    subprocess.Popen(["explorer", str(folder)])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception:
            pass

    def _open_in_editor(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        src_pil = None
        src_path = str(self._effective_source_path() or "")
        try:
            if self._preview_mode == "image" and self._preview_base_pil is not None:
                src_pil = self._preview_base_pil.copy()
            elif src_path:
                src_pil = self._get_first_frame(src_path)
        except Exception:
            src_pil = None
        if src_pil is None:
            self._show_notice(tr.get("info", "Info"), tr.get("gallery_empty", "No items yet"))
            return
        try:
            dur_ms = 6000
            photo_mode = bool(self._preview_mode == "image")
            if int(getattr(self, "_preview_duration_ms", 0) or 0) > 0:
                dur_ms = int(self._preview_duration_ms)
            elif src_path.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                photo_mode = False
                cap = cv2.VideoCapture(src_path)
                if cap is not None and cap.isOpened():
                    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    if fps > 0 and frames > 0:
                        dur_ms = int((frames / fps) * 1000.0)
                if cap is not None:
                    cap.release()
            if src_path.lower().endswith(".gif"):
                photo_mode = False
            self._open_embedded_editor(src_pil, dur_ms, tr, photo_mode=photo_mode)
            return
        except Exception as e:
            try:
                self._restore_modal_ui()
            except Exception:
                pass
            self._show_notice(tr.get("info", "Info"), f"Editor open error: {repr(e)}")
            return
        try:
            self._prepare_modal_ui()
            dlg = OverlayDialog(self, self.theme, tr.get("editor", "Editor"))
            dlg.set_panel_size(880, 700)
            body = QWidget()
            lay = QVBoxLayout(body)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(8)
            preview = QLabel()
            preview.setAlignment(Qt.AlignCenter)
            preview.setMinimumHeight(400)
            preview.setStyleSheet("background: rgba(0,0,0,0.12); border-radius:10px;")
            lay.addWidget(preview, 1)
            sliders = {}
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignLeft)
            params = [
                ("brightness", tr.get("brightness", "Brightness"), 100),
                ("contrast2", tr.get("contrast", "Contrast"), 100),
                ("saturation", tr.get("saturation", "Saturation"), 100),
                ("sharpness2", tr.get("sharpen", "Sharpen"), 100),
                ("hue", tr.get("hue", "Hue"), 0),
                ("exposure", tr.get("exposure", "Exposure"), 0),
                ("temperature", tr.get("temperature", "Temperature"), 0),
            ]
            for key, title, default in params:
                sl = QSlider(Qt.Horizontal)
                if key in ("hue", "exposure", "temperature"):
                    sl.setRange(-180, 180)
                else:
                    sl.setRange(0, 250)
                sl.setValue(int(default))
                sliders[key] = sl
                form.addRow(title + ":", sl)
            lay.addLayout(form)
            tools_row = QHBoxLayout()
            tools_row.setSpacing(10)
            crop_box = QFrame()
            crop_box.setStyleSheet("QFrame{background: rgba(255,255,255,0.05); border-radius:10px;}")
            crop_l = QFormLayout(crop_box)
            crop_l.setContentsMargins(8, 8, 8, 8)
            crop_l.setLabelAlignment(Qt.AlignLeft)
            crop_enable = QCheckBox(tr.get("crop", "Crop"))
            crop_enable.setChecked(False)
            crop_x = QSpinBox(); crop_x.setRange(0, max(0, src_pil.width - 1)); crop_x.setValue(0)
            crop_y = QSpinBox(); crop_y.setRange(0, max(0, src_pil.height - 1)); crop_y.setValue(0)
            crop_w = QSpinBox(); crop_w.setRange(1, max(1, src_pil.width)); crop_w.setValue(int(src_pil.width))
            crop_h = QSpinBox(); crop_h.setRange(1, max(1, src_pil.height)); crop_h.setValue(int(src_pil.height))
            crop_l.addRow(crop_enable)
            crop_l.addRow("X:", crop_x)
            crop_l.addRow("Y:", crop_y)
            crop_l.addRow("W:", crop_w)
            crop_l.addRow("H:", crop_h)
            text_box = QFrame()
            text_box.setStyleSheet("QFrame{background: rgba(255,255,255,0.05); border-radius:10px;}")
            text_l = QFormLayout(text_box)
            text_l.setContentsMargins(8, 8, 8, 8)
            text_l.setLabelAlignment(Qt.AlignLeft)
            text_input = QLineEdit()
            text_input.setPlaceholderText(tr.get("add_text", "Text overlay"))
            text_size = QSpinBox(); text_size.setRange(8, 240); text_size.setValue(28)
            text_x = QSpinBox(); text_x.setRange(0, 8000); text_x.setValue(24)
            text_y = QSpinBox(); text_y.setRange(0, 8000); text_y.setValue(24)
            text_alpha = QSlider(Qt.Horizontal); text_alpha.setRange(0, 255); text_alpha.setValue(220)
            text_color_btn = QPushButton(tr.get("text_color", "Text color"))
            text_color_btn.setStyleSheet(self._glass_btn_css())
            text_l.addRow(tr.get("add_text", "Text") + ":", text_input)
            text_l.addRow(tr.get("font_size", "Font size") + ":", text_size)
            text_l.addRow("X:", text_x)
            text_l.addRow("Y:", text_y)
            text_l.addRow("A:", text_alpha)
            text_l.addRow(text_color_btn)
            tools_row.addWidget(crop_box, 1)
            tools_row.addWidget(text_box, 1)
            lay.addLayout(tools_row)
            buttons = QHBoxLayout()
            reset_btn = QPushButton(tr.get("defaults", "Defaults"))
            apply_btn = QPushButton(tr.get("apply", "Apply"))
            cancel_btn = QPushButton(tr.get("cancel", "Cancel"))
            for b in (reset_btn, apply_btn, cancel_btn):
                b.setStyleSheet(self._glass_btn_css())
                b.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(reset_btn)
            buttons.addStretch(1)
            buttons.addWidget(apply_btn)
            buttons.addWidget(cancel_btn)
            lay.addLayout(buttons)
            edited = {"img": src_pil.copy()}
            text_color = {"rgba": (255, 255, 255, 220)}

            def _render_edit_preview():
                try:
                    img = src_pil.copy().convert("RGB")
                    if crop_enable.isChecked():
                        x = max(0, int(crop_x.value()))
                        y = max(0, int(crop_y.value()))
                        w = max(1, int(crop_w.value()))
                        h = max(1, int(crop_h.value()))
                        x2 = min(img.width, x + w)
                        y2 = min(img.height, y + h)
                        if x2 > x + 1 and y2 > y + 1:
                            img = img.crop((x, y, x2, y2))
                    b = sliders["brightness"].value() / 100.0
                    c = sliders["contrast2"].value() / 100.0
                    s = sliders["saturation"].value() / 100.0
                    sh = sliders["sharpness2"].value() / 100.0
                    h = int(sliders["hue"].value())
                    ex = int(sliders["exposure"].value())
                    temp = int(sliders["temperature"].value())
                    img = ImageEnhance.Brightness(img).enhance(max(0.0, b))
                    img = ImageEnhance.Contrast(img).enhance(max(0.0, c))
                    img = ImageEnhance.Color(img).enhance(max(0.0, s))
                    img = ImageEnhance.Sharpness(img).enhance(max(0.0, sh))
                    if h != 0:
                        hsv = img.convert("HSV")
                        arr = np.array(hsv, dtype=np.uint8)
                        arr[:, :, 0] = ((arr[:, :, 0].astype(np.int16) + int(h / 2)) % 256).astype(np.uint8)
                        img = Image.fromarray(arr, mode="HSV").convert("RGB")
                    if ex != 0:
                        img = ImageEnhance.Brightness(img).enhance(max(0.05, 1.0 + (ex / 120.0)))
                    if temp != 0:
                        arr = np.array(img, dtype=np.int16)
                        delta = int(temp * 0.65)
                        arr[:, :, 0] = np.clip(arr[:, :, 0] + delta, 0, 255)
                        arr[:, :, 2] = np.clip(arr[:, :, 2] - delta, 0, 255)
                        img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
                    txt = (text_input.text() or "").strip()
                    if txt:
                        d = ImageDraw.Draw(img, "RGBA")
                        try:
                            font = ImageFont.truetype("arial.ttf", int(text_size.value()))
                        except Exception:
                            font = ImageFont.load_default()
                        a = int(max(0, min(255, text_alpha.value())))
                        rgba = text_color["rgba"]
                        d.text((int(text_x.value()), int(text_y.value())), txt, fill=(int(rgba[0]), int(rgba[1]), int(rgba[2]), a), font=font)
                    edited["img"] = img
                    pv = img.copy()
                    pv.thumbnail((800, 400), Image.Resampling.LANCZOS)
                    preview.setPixmap(pil_to_qpixmap(pv))
                except Exception:
                    pass

            for sl in sliders.values():
                sl.valueChanged.connect(_render_edit_preview)
            for w in (crop_enable, crop_x, crop_y, crop_w, crop_h, text_input, text_size, text_x, text_y, text_alpha):
                try:
                    if isinstance(w, QCheckBox):
                        w.stateChanged.connect(_render_edit_preview)
                    elif isinstance(w, QLineEdit):
                        w.textChanged.connect(_render_edit_preview)
                    else:
                        w.valueChanged.connect(_render_edit_preview)
                except Exception:
                    pass

            def _pick_text_color():
                try:
                    cdlg = QColorDialog(self)
                    cdlg.setOption(QColorDialog.ShowAlphaChannel, True)
                    col = cdlg.getColor()
                    if col.isValid():
                        text_color["rgba"] = (col.red(), col.green(), col.blue(), col.alpha())
                        _render_edit_preview()
                except Exception:
                    pass
            text_color_btn.clicked.connect(_pick_text_color)

            def _reset():
                try:
                    sliders["brightness"].setValue(100)
                    sliders["contrast2"].setValue(100)
                    sliders["saturation"].setValue(100)
                    sliders["sharpness2"].setValue(100)
                    sliders["hue"].setValue(0)
                    sliders["exposure"].setValue(0)
                    sliders["temperature"].setValue(0)
                    crop_enable.setChecked(False)
                    crop_x.setValue(0); crop_y.setValue(0)
                    crop_w.setValue(int(src_pil.width)); crop_h.setValue(int(src_pil.height))
                    text_input.setText("")
                    text_size.setValue(28)
                    text_x.setValue(24); text_y.setValue(24)
                    text_alpha.setValue(220)
                    text_color["rgba"] = (255, 255, 255, 220)
                except Exception:
                    pass

            def _apply():
                try:
                    out = edited["img"].copy()
                    self.current_output = out
                    self._show_preview_pil(out)
                    self._add_gallery_item(out, path=None, media_type="image")
                except Exception:
                    pass
                dlg.accept()

            reset_btn.clicked.connect(_reset)
            apply_btn.clicked.connect(_apply)
            cancel_btn.clicked.connect(dlg.reject)
            _render_edit_preview()
            dlg.set_body_widget(body)
            try:
                self._attach_sounds(dlg)
            except Exception:
                pass
            dlg.exec()
        finally:
            self._restore_modal_ui()

    def _add_gallery_item(self, pil, path=None, media_type='image'):
        # media_type: 'image', 'video', 'gif'
        try:
            thumb = pil.copy(); thumb.thumbnail((140,140), Image.Resampling.LANCZOS); qicon = pil_to_qpixmap(thumb)
        except Exception:
            qicon = QPixmap(140,140)
        item = QListWidgetItem(); item.setIcon(QIcon(qicon))
        stored_pil = pil
        try:
            p = str(path or "").strip()
            # Keep memory low: do not store full-frame previews for path-backed video/GIF items.
            if p and media_type in ("video", "gif"):
                stored_pil = None
            elif p and media_type == "image" and isinstance(pil, Image.Image):
                # For path-backed images keep a limited in-memory preview.
                if pil.width > 1400 or pil.height > 1400:
                    stored_pil = pil.copy()
                    stored_pil.thumbnail((1400, 1400), Image.Resampling.BILINEAR)
            elif (not p) and isinstance(pil, Image.Image):
                # Generated images may be large; cap stored gallery preview size.
                if pil.width > 1800 or pil.height > 1800:
                    stored_pil = pil.copy()
                    stored_pil.thumbnail((1800, 1800), Image.Resampling.BILINEAR)
        except Exception:
            stored_pil = pil
        data = {'type': media_type, 'pil': stored_pil, 'path': path, 'enabled': True}
        item.setData(Qt.UserRole, data)
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
        item.setSizeHint(QSize(160, 196))
        try:
            fps = int(getattr(self, "render_fps", 24))
            codec = str(getattr(self, "render_codec", "libx264"))
            bitrate = str(getattr(self, "render_bitrate", "2M"))
            if media_type in ("video", "gif"):
                item.setText(f"{media_type.upper()}\n{fps} FPS | {codec} {bitrate}")
            else:
                item.setText("IMG")
        except Exception:
            pass
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        if path:
            item.setToolTip(path)
        # Keep only thumbnail in item roles (full-size pixmaps consume too much RAM).
        item.setData(Qt.UserRole+1, qicon)
        self.gallery_list.addItem(item)
        # Cap gallery item count to prevent memory growth on long sessions.
        try:
            max_items = 36
            while self.gallery_list.count() > max_items:
                self.gallery_list.takeItem(0)
        except Exception:
            pass
        try:
            self.gallery_empty.setVisible(self.gallery_list.count() == 0)
            self._layout_preview_controls()
        except Exception:
            pass
        # context menu for gallery
        try:
            if not bool(getattr(self, "_gallery_context_connected", False)):
                self.gallery_list.setContextMenuPolicy(Qt.CustomContextMenu)
                self.gallery_list.customContextMenuRequested.connect(self._on_gallery_context)
                self._gallery_context_connected = True
        except Exception:
            pass
        # refresh panels as gallery changed (so glass shows new blurred bg)
        try:
            self._update_panel_backgrounds()
        except Exception:
            pass

    def _show_gallery_item(self, item, open_player=False):
        data = item.data(Qt.UserRole)
        if not data:
            return
        mtype = data.get('type', 'image')
        self._layout_preview_controls()
        if mtype == 'image':
            self._stop_preview_media()
            pil = data.get("pil")
            if pil is None:
                p = str(data.get("path") or "").strip()
                if p and os.path.exists(p):
                    try:
                        pil = Image.open(p).convert("RGB")
                    except Exception:
                        pil = None
            if pil is not None:
                try:
                    self._live_preview_source_pil = pil.copy()
                except Exception:
                    self._live_preview_source_pil = pil
                self._show_preview_pil(pil)
                self.current_output = pil
                self.current_path = data.get("path")
                p = str(data.get("path") or "").strip()
                if p and os.path.exists(p):
                    self.original_source_path = p
                    self.processing_source_path = p
                else:
                    self.processing_source_path = None
        elif mtype == 'gif':
            p = data.get("path")
            if p and os.path.exists(p):
                self.current_path = p
                self.original_source_path = p
                self.processing_source_path = p
                self.current_output = data.get("pil")
                try:
                    self._live_preview_source_pil = (data.get("pil") or self._get_first_frame(p))
                except Exception:
                    self._live_preview_source_pil = None
                self._start_preview_gif(p)
        else:
            p = data.get("path")
            if p and os.path.exists(p):
                self.current_path = p
                self.original_source_path = p
                self.processing_source_path = p
                self.current_output = data.get("pil")
                try:
                    self._live_preview_source_pil = (data.get("pil") or self._get_first_frame(p))
                except Exception:
                    self._live_preview_source_pil = None
                self._start_preview_video(p)
        try:
            idx = self.gallery_list.row(item)
            name = os.path.basename(data.get("path") or f"item_{idx+1}")
            self.player_playlist_label.setText(f"{idx+1}/{max(1,self.gallery_list.count())}  {name}")
        except Exception:
            pass

    def _update_ascii_controls_visibility(self):
        try:
            none_mode = (self.style_combo.currentText() == "none")
            for w in getattr(self, "_ascii_widgets", []):
                try:
                    w.setVisible(not none_mode)
                    rowc = getattr(w, "_row_container", None)
                    if rowc is not None:
                        rowc.setVisible(not none_mode)
                except Exception:
                    pass
            if hasattr(self, "style_help"):
                self.style_help.setVisible(not none_mode)
        except Exception:
            pass
        self._animate_preview_transition()

    def on_gallery_click(self, item):
        self._show_gallery_item(item, open_player=False)

    def _open_current_in_player(self):
        self._toggle_player_focus_mode()

    def _select_gallery_relative(self, delta):
        try:
            count = self.gallery_list.count()
            if count <= 0:
                return
            cur = self.gallery_list.currentRow()
            if cur < 0:
                cur = 0
            nxt = max(0, min(count - 1, cur + int(delta)))
            if nxt == cur and count > 1:
                return
            self.gallery_list.setCurrentRow(nxt)
            item = self.gallery_list.item(nxt)
            if item is not None:
                self.gallery_list.scrollToItem(item)
        except Exception:
            pass

    def on_gallery_double_click(self, item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        if data.get('type') == 'image':
            self.open_fullscreen_viewer(data.get('pil'))
        else:
            self._toggle_player_focus_mode()

    def _on_gallery_context(self, pos):
        item = self.gallery_list.itemAt(pos)
        if not item: return
        data = item.data(Qt.UserRole)
        menu = []
        # simple remove / toggle
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        a_remove = m.addAction(tr.get("remove", "Remove"))
        a_toggle = m.addAction(tr.get("toggle", "Toggle enabled"))
        act = m.exec(self.gallery_list.mapToGlobal(pos))
        if act == a_remove:
            row = self.gallery_list.row(item); self.gallery_list.takeItem(row)
            try:
                self.gallery_empty.setVisible(self.gallery_list.count() == 0)
                self._layout_preview_controls()
            except Exception:
                pass
        elif act == a_toggle:
            try:
                data = item.data(Qt.UserRole) or {}
                enabled = bool(data.get("enabled", True))
                data["enabled"] = not enabled
                item.setData(Qt.UserRole, data)
                if data["enabled"]:
                    item.setForeground(QColor("#e6eef6"))
                else:
                    item.setForeground(QColor("#6d7484"))
            except Exception:
                pass

    def _preview_clicked(self, event):
        if hasattr(self, "current_output") and self.current_output: self.open_fullscreen_viewer(self.current_output)

    def open_fullscreen_viewer(self, pil):
        viewer = FullscreenViewer(self, pil)
        viewer.exec()
    def _update_panel_backgrounds(self):
        """Crop bg_base for left and right panels, apply local blur + tint and set to overlay labels."""
        try:
            now = time.time()
            if (now - float(getattr(self, "_last_panel_bg_ts", 0.0))) < (0.26 if self.isFullScreen() else 0.18):
                return
            self._last_panel_bg_ts = now
            left = self.findChild(QFrame, "left_frame")
            right = self.findChild(QFrame, "right_frame")
            if not left or not right or not hasattr(self, 'bg_base') or self.bg_base is None:
                return
            base = self.bg_base
            # map widget positions to main window coordinates
            lx, ly = left.mapTo(self, QPoint(0,0)).x(), left.mapTo(self, QPoint(0,0)).y()
            lwid, lht = max(1, left.width()), max(1, left.height())
            rx, ry = right.mapTo(self, QPoint(0,0)).x(), right.mapTo(self, QPoint(0,0)).y()
            rwid, rht = max(1, right.width()), max(1, right.height())

            def crop_and_make(x, y, w, h, tint_alpha=110):
                x0, y0 = max(0, x), max(0, y)
                x1, y1 = min(base.width, x + w), min(base.height, y + h)
                if x1 <= x0 or y1 <= y0:
                    return None
                crop = base.crop((x0, y0, x1, y1)).convert('RGBA')
                small = crop.resize((max(1, w//2), max(1, h//2)), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=6))
                big = small.resize((w, h), Image.Resampling.BILINEAR)
                tint = Image.new('RGBA', (w, h), (18,20,24,tint_alpha))
                out = Image.alpha_composite(big, tint)
                # rounded mask
                mask = Image.new('L', (w,h), 0)
                md = ImageDraw.Draw(mask)
                radius = min(24, max(6, w//14), max(6, h//14))
                md.rounded_rectangle((0,0,w,h), radius=radius, fill=255)
                out.putalpha(mask)
                return out.convert('RGB')

            left_img = crop_and_make(lx, ly, lwid, lht, tint_alpha=110)
            right_img = crop_and_make(rx, ry, rwid, rht, tint_alpha=120)
            if left_img:
                self.left_bg_label.setPixmap(pil_to_qpixmap(left_img).scaled(lwid, lht, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                self.left_bg_label.setGeometry(lx, ly, lwid, lht)
                try:
                    self.left_bg_label.stackUnder(left)
                except Exception:
                    self.left_bg_label.lower()
            if right_img:
                self.right_bg_label.setPixmap(pil_to_qpixmap(right_img).scaled(rwid, rht, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                self.right_bg_label.setGeometry(rx, ry, rwid, rht)
                try:
                    self.right_bg_label.stackUnder(right)
                except Exception:
                    self.right_bg_label.lower()
            self._normalize_main_z_order()
        except Exception:
            pass

    def _build_menu(self):
        menubar = self.menuBar()
        try:
            menubar.setNativeMenuBar(False)
        except Exception:
            pass
        # File menu
        self.file_menu = menubar.addMenu(TRANSLATIONS[self.lang].get("file", "File"))
        self.action_load = self.file_menu.addAction(TRANSLATIONS[self.lang].get("load", "Load"))
        self.action_load.triggered.connect(self.on_load)
        self.action_export = self.file_menu.addAction(TRANSLATIONS[self.lang].get("export", "Export"))
        self.action_export.triggered.connect(self.on_export)
        self.action_settings = self.file_menu.addAction(TRANSLATIONS[self.lang].get("settings", "Settings"))
        self.action_settings.triggered.connect(self.open_settings_dialog)
        self.action_check_updates = self.file_menu.addAction(TRANSLATIONS[self.lang].get("menu_check_updates", "Check for updates"))
        self.action_check_updates.triggered.connect(lambda: self._check_updates_async(force=True))
        self.edit_menu = menubar.addMenu(TRANSLATIONS[self.lang].get("edit", "Edit"))
        self.action_undo_menu = self.edit_menu.addAction(TRANSLATIONS[self.lang].get("undo", "Undo"))
        self.action_redo_menu = self.edit_menu.addAction(TRANSLATIONS[self.lang].get("redo", "Redo"))
        self.action_undo_menu.setShortcut(QKeySequence("Ctrl+Z"))
        self.action_redo_menu.setShortcut(QKeySequence("Ctrl+Y"))
        self.action_undo_menu.triggered.connect(self._undo_action)
        self.action_redo_menu.triggered.connect(self._redo_action)
        try:
            ico_color = "#111111" if self.theme == "light" else "#e5ebf5"
            i1 = self._load_svg_icon("undo", ico_color)
            i2 = self._load_svg_icon("redo", ico_color)
            if i1 is not None:
                self.action_undo_menu.setIcon(i1)
            if i2 is not None:
                self.action_redo_menu.setIcon(i2)
        except Exception:
            pass
        self.tools_menu = menubar.addMenu(TRANSLATIONS[self.lang].get("tools", "Tools"))
        self.tools_invert = self.tools_menu.addAction(TRANSLATIONS[self.lang].get("tool_invert", "Invert selected"))
        self.tools_invert.triggered.connect(lambda: self._apply_tool_to_selected("invert"))
        self.tools_edges = self.tools_menu.addAction(TRANSLATIONS[self.lang].get("tool_edges", "Edge detect"))
        self.tools_edges.triggered.connect(lambda: self._apply_tool_to_selected("edges"))
        self.tools_sharp = self.tools_menu.addAction(TRANSLATIONS[self.lang].get("tool_sharpen", "Sharpen"))
        self.tools_sharp.triggered.connect(lambda: self._apply_tool_to_selected("sharpen"))
        self.tools_menu.addSeparator()
        self.tools_hybrid_runtime = self.tools_menu.addAction("Hybrid UI (QML/C++)")
        self.tools_hybrid_runtime.triggered.connect(self._open_hybrid_runtime)
        self.pro_menu = menubar.addMenu(TRANSLATIONS[self.lang].get("pro_menu", "Pro Tools"))
        self.pro_menu.setVisible(True)
        self.pro_action_posterize = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_posterize", "Posterize"))
        self.pro_action_posterize.triggered.connect(lambda: self._apply_tool_to_selected("posterize"))
        self.pro_action_mirror = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_mirror", "Mirror"))
        self.pro_action_mirror.triggered.connect(lambda: self._apply_tool_to_selected("mirror"))
        self.pro_action_bloom = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_bloom", "Bloom"))
        self.pro_action_bloom.triggered.connect(lambda: self._apply_tool_to_selected("bloom"))
        self.pro_action_vignette = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_vignette", "Vignette"))
        self.pro_action_vignette.triggered.connect(lambda: self._apply_tool_to_selected("vignette"))
        self.pro_action_scan = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_scanlines", "Scanlines"))
        self.pro_action_scan.triggered.connect(lambda: self._apply_tool_to_selected("scanlines"))
        self.pro_action_grain = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_grain", "Film grain"))
        self.pro_action_grain.triggered.connect(lambda: self._apply_tool_to_selected("grain"))
        self.pro_action_chroma = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_chroma", "Chroma shift"))
        self.pro_action_chroma.triggered.connect(lambda: self._apply_tool_to_selected("chroma"))
        self.pro_action_glitch = self.pro_menu.addAction(TRANSLATIONS[self.lang].get("tool_glitch", "Glitch"))
        self.pro_action_glitch.triggered.connect(lambda: self._apply_tool_to_selected("glitch"))
        self.pro_menu.addSeparator()
        self.pro_toggle_scan = self.pro_menu.addAction("Toggle scanlines")
        self.pro_toggle_scan.setCheckable(True)
        self.pro_toggle_scan.triggered.connect(lambda v: self._set_pro_option("scanlines", bool(v)))
        self.pro_toggle_bloom = self.pro_menu.addAction("Toggle bloom")
        self.pro_toggle_bloom.setCheckable(True)
        self.pro_toggle_bloom.triggered.connect(lambda v: self._set_pro_option("bloom", bool(v)))
        self.pro_toggle_vignette = self.pro_menu.addAction("Toggle vignette")
        self.pro_toggle_vignette.setCheckable(True)
        self.pro_toggle_vignette.triggered.connect(lambda v: self._set_pro_option("vignette", bool(v)))
        self.pro_menu.addSeparator()
        self.pro_preset_soft = self.pro_menu.addAction("Preset: Soft")
        self.pro_preset_soft.triggered.connect(lambda: self._apply_pro_preset("soft"))
        self.pro_preset_cyber = self.pro_menu.addAction("Preset: Cyber")
        self.pro_preset_cyber.triggered.connect(lambda: self._apply_pro_preset("cyber"))
        self.pro_preset_retro = self.pro_menu.addAction("Preset: Retro")
        self.pro_preset_retro.triggered.connect(lambda: self._apply_pro_preset("retro"))
        self.pro_preset_vhs = self.pro_menu.addAction("Preset: VHS")
        self.pro_preset_vhs.triggered.connect(lambda: self._apply_pro_preset("vhs"))
        self.pro_reset = self.pro_menu.addAction("Reset Pro Tools")
        self.pro_reset.triggered.connect(self._reset_pro_tools)
        self.pro_menu.menuAction().setVisible(bool(self.pro_tools))
        self.help_menu = menubar.addMenu(TRANSLATIONS[self.lang].get("help", "Help"))
        self.action_help = self.help_menu.addAction(TRANSLATIONS[self.lang].get("help_open", "Open help"))
        self.action_help.triggered.connect(self._open_help)
        self._sync_pro_menu_state()

    def _info_overlay(self, title, body, w=560, h=260):
        try:
            self._prepare_modal_ui()
            dlg = OverlayDialog(self, self.theme, title)
            dlg.set_panel_size(int(w), int(h))
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(str(body))
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size:13px; line-height:1.3;")
            lay.addWidget(lbl, 1)
            row = QHBoxLayout()
            row.addStretch(1)
            ok = QPushButton("OK")
            ok.setStyleSheet(self._glass_btn_css())
            ok.clicked.connect(dlg.accept)
            row.addWidget(ok)
            lay.addLayout(row)
            dlg.set_body_widget(box)
            dlg.exec()
        except Exception:
            pass
        finally:
            self._restore_modal_ui()

    def _hybrid_bridge_path(self):
        try:
            root = Path(__file__).resolve().parent / "hybrid_nextgen" / "bridge"
            root.mkdir(parents=True, exist_ok=True)
            return root / "runtime_state.json"
        except Exception:
            return Path(tempfile.gettempdir()) / "ultra_ascii_hybrid_runtime_state.json"

    def _find_hybrid_runtime_exe(self):
        base = Path(__file__).resolve().parent / "hybrid_nextgen" / "build"
        cands = [
            base / "ultra_ascii_hybrid.exe",
            base / "Release" / "ultra_ascii_hybrid.exe",
            base / "ultra_ascii_hybrid",
            base / "Release" / "ultra_ascii_hybrid",
        ]
        for c in cands:
            if c.exists():
                return c
        return None

    def _collect_hybrid_bridge_state(self):
        st = copy.deepcopy(getattr(self, "editor_state", {}) or {})
        chain = [str(x).strip() for x in (st.get("node_chain", []) or []) if str(x).strip()]
        io = st.get("node_io", []) or []
        links = st.get("node_links", []) or []
        nodes = []
        for i, nid in enumerate(chain):
            in_t = "video"
            out_t = "video"
            try:
                if i < len(io) and isinstance(io[i], dict):
                    in_types = io[i].get("in_types", [io[i].get("input_type", "video")]) or ["video"]
                    out_types = io[i].get("out_types", [io[i].get("output_type", "video")]) or ["video"]
                    in_t = str(in_types[0]).strip().lower() if in_types else "video"
                    out_t = str(out_types[0]).strip().lower() if out_types else "video"
            except Exception:
                pass
            if in_t not in ("video", "audio", "data", "any"):
                in_t = "video"
            if out_t not in ("video", "audio", "data", "any"):
                out_t = "video"
            nodes.append({"id": nid, "inType": in_t, "outType": out_t})
        out_links = []
        for lk in (links or []):
            try:
                a = int(lk[0]); b = int(lk[1])
                op = int(lk[2]) if len(lk) >= 3 else 0
                ip = int(lk[3]) if len(lk) >= 4 else 0
            except Exception:
                continue
            if a < 0 or b < 0 or a >= len(nodes) or b >= len(nodes) or a == b:
                continue
            out_links.append({"src": a, "dst": b, "outPort": op, "inPort": ip})
        return {
            "realtime_preview": bool(getattr(self, "live_preview", True)),
            "timeline_ms": int(getattr(self, "_editor_last_preview_ms", 0) or 0),
            "duration_ms": int(max(1000, int(getattr(self, "_video_duration_ms", 6000) or 6000))),
            "nodes": nodes,
            "links": out_links,
        }

    def _apply_hybrid_bridge_state(self, bridge):
        if not isinstance(bridge, dict):
            return
        st = copy.deepcopy(getattr(self, "editor_state", {}) or {})
        nodes = bridge.get("nodes", []) if isinstance(bridge.get("nodes"), list) else []
        links = bridge.get("links", []) if isinstance(bridge.get("links"), list) else []
        chain = []
        io = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            nid = str(n.get("id", "") or "").strip()
            if not nid:
                continue
            it = str(n.get("inType", "video") or "video").strip().lower()
            ot = str(n.get("outType", "video") or "video").strip().lower()
            if it not in ("video", "audio", "data", "any"):
                it = "video"
            if ot not in ("video", "audio", "data", "any"):
                ot = "video"
            chain.append(nid)
            io.append({
                "inputs": 1,
                "outputs": 1,
                "in_types": [it],
                "out_types": [ot],
                "input_type": it,
                "output_type": ot,
            })
        out_links = []
        for lk in links:
            if not isinstance(lk, dict):
                continue
            try:
                a = int(lk.get("src", -1))
                b = int(lk.get("dst", -1))
                op = int(lk.get("outPort", 0))
                ip = int(lk.get("inPort", 0))
            except Exception:
                continue
            if a < 0 or b < 0 or a >= len(chain) or b >= len(chain) or a == b:
                continue
            out_links.append([a, b, max(0, op), max(0, ip)])
        st["node_chain"] = chain
        st["node_io"] = io
        st["node_links"] = out_links
        st["nodes_enabled"] = bool(len(chain) > 0)
        st["enabled"] = bool(st.get("enabled", False) or st["nodes_enabled"])
        self.editor_state = st
        try:
            self._editor_last_preview_ms = int(bridge.get("timeline_ms", self._editor_last_preview_ms) or self._editor_last_preview_ms)
        except Exception:
            pass
        try:
            self.live_preview = bool(bridge.get("realtime_preview", self.live_preview))
            if hasattr(self, "live_preview_chk"):
                self.live_preview_chk.setChecked(bool(self.live_preview))
        except Exception:
            pass
        try:
            self._schedule_live_preview()
        except Exception:
            pass

    def _open_hybrid_runtime(self):
        exe = self._find_hybrid_runtime_exe()
        if exe is None:
            self._info_overlay(
                "Hybrid UI",
                "Hybrid runtime is not built yet.\n\nBuild command:\ncmake -S hybrid_nextgen -B hybrid_nextgen/build -G \"Ninja\"\ncmake --build hybrid_nextgen/build --config Release\n\nThen run this action again.",
                760,
                320,
            )
            return
        bridge_path = self._hybrid_bridge_path()
        payload = {
            "bridge_state": self._collect_hybrid_bridge_state(),
            "editor_state": copy.deepcopy(getattr(self, "editor_state", {}) or {}),
            "app_version": APP_VERSION,
            "timestamp": int(time.time()),
        }
        try:
            bridge_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            self._info_overlay("Hybrid UI", f"Failed to create bridge file:\n{e}", 620, 260)
            return
        try:
            self._prepare_modal_ui()
            self.setEnabled(False)
            subprocess.run([str(exe), "--bridge-file", str(bridge_path)], cwd=str(exe.parent), check=False)
        except Exception as e:
            self._info_overlay("Hybrid UI", f"Failed to start hybrid runtime:\n{e}", 620, 260)
        finally:
            try:
                self.setEnabled(True)
            except Exception:
                pass
            self._restore_modal_ui()
        try:
            data = json.loads(bridge_path.read_text(encoding="utf-8"))
            bridge = data.get("bridge_state", data)
            self._apply_hybrid_bridge_state(bridge)
        except Exception:
            pass

    def _on_change_language(self, code):
        if code in TRANSLATIONS:
            self.lang = code
            self._apply_translations()
    def _open_help(self):
        try:
            self._prepare_modal_ui()
            title = self._resolve_info_text(self._i3("Справка", "Help", "帮助"), "Help")
            txt = self._resolve_info_text(self._i3(
                "ASCII Studio\n\nСоздатель: SNERK503\nВерсия: 1.0\n\nВозможности:\n- Конвертация фото/видео/GIF в ASCII.\n- Режим none (без ASCII-преобразования).\n- Превью, встроенный плеер и галерея.\n- Экспорт PNG/GIF/MP4/TXT.\n- Pro Tools: bloom, vignette, scanlines, posterize.",
                "ASCII Studio\n\nCreator: SNERK503\nVersion: 1.0\n\nFeatures:\n- Convert image/video/GIF to ASCII.\n- None style (no ASCII conversion).\n- Preview, embedded player and gallery.\n- Export PNG/GIF/MP4/TXT.\n- Pro Tools: bloom, vignette, scanlines, posterize.",
                "ASCII Studio\n\n作者: SNERK503\n版本: 1.0\n\n功能:\n- 将图片/视频/GIF 转为 ASCII。\n- none 模式（不做 ASCII 转换）。\n- 预览、内置播放器和画廊。\n- 导出 PNG/GIF/MP4/TXT。\n- Pro Tools: 辉光、暗角、扫描线、色阶。"
            ), "")
            dlg = OverlayDialog(self, self.theme, title)
            dlg.set_panel_size(620, 420)
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            body = QLabel(txt)
            body.setWordWrap(True)
            body.setStyleSheet("font-size:13px; line-height:1.35;")
            lay.addWidget(body, 1)
            dlg.set_body_widget(box)
            dlg.exec()
        except Exception:
            pass
        finally:
            self._restore_modal_ui()

    def _version_tuple(self, text):
        try:
            v = str(text or "").strip().lower().replace("v", "")
            nums = []
            cur = ""
            for ch in v:
                if ch.isdigit():
                    cur += ch
                else:
                    if cur:
                        nums.append(int(cur))
                        cur = ""
            if cur:
                nums.append(int(cur))
            while len(nums) < 3:
                nums.append(0)
            return tuple(nums[:3])
        except Exception:
            return (0, 0, 0)

    def _set_update_chip_state(self, text, state="idle", show_buttons=False):
        try:
            if not hasattr(self, "update_chip"):
                return
            self.update_status_label.setText(str(text or ""))
            self.update_chip.setStyleSheet(self._update_chip_css(state))
            self.update_install_btn.setVisible(bool(show_buttons))
            self.update_later_btn.setVisible(bool(show_buttons))
            self.update_chip.show()
            try:
                eff = QGraphicsOpacityEffect(self.update_chip)
                self.update_chip.setGraphicsEffect(eff)
                anim = QPropertyAnimation(eff, b"opacity", self)
                anim.setDuration(240)
                anim.setStartValue(0.35)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                self._update_chip_anim = anim
                anim.start()
            except Exception:
                pass
        except Exception:
            pass

    def _hide_update_chip(self, *_):
        try:
            if hasattr(self, "update_install_btn"):
                self.update_install_btn.hide()
            if hasattr(self, "update_later_btn"):
                self.update_later_btn.hide()
            if hasattr(self, "update_chip"):
                self.update_chip.setStyleSheet(self._update_chip_css("idle"))
        except Exception:
            pass

    def _check_updates_async(self, force=False):
        try:
            if self._update_thread is not None and self._update_thread.is_alive():
                return
            now = time.time()
            if (not force) and now - float(getattr(self, "last_update_check", 0) or 0) < 1800:
                return
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            self._set_update_chip_state(tr.get("update_status_checking", "Checking updates..."), "busy", show_buttons=False)
            self.last_update_check = now

            def _worker():
                result = None
                err = ""
                try:
                    feed = str(getattr(self, "update_feed_url", DEFAULT_UPDATE_FEED_URL) or DEFAULT_UPDATE_FEED_URL).strip()
                    if not feed:
                        raise RuntimeError("empty update feed")
                    raw = None
                    if feed.startswith("http://") or feed.startswith("https://"):
                        req = urllib.request.Request(feed, headers={"User-Agent": f"ASCIIStudio/{self.app_version}"})
                        with urllib.request.urlopen(req, timeout=7) as resp:
                            raw = resp.read().decode("utf-8", errors="replace")
                    else:
                        p = Path(feed)
                        if not p.is_absolute():
                            p = (Path(__file__).resolve().parent / p).resolve()
                        raw = p.read_text(encoding="utf-8")
                    data = json.loads(raw or "{}")
                    latest = str(data.get("latest_version", "") or "").strip()
                    if latest:
                        result = data
                    else:
                        raise RuntimeError("manifest missing latest_version")
                except Exception as e:
                    err = str(e)
                try:
                    self.update_check_done.emit(result, err)
                except Exception:
                    pass

            self._update_thread = threading.Thread(target=_worker, daemon=True)
            self._update_thread.start()
        except Exception:
            pass

    def _on_update_check_done(self, result, err):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            if err:
                self._set_update_chip_state(tr.get("update_error", "Update check failed"), "error", show_buttons=False)
                return
            if not isinstance(result, dict):
                self._set_update_chip_state(tr.get("update_none", "Latest version installed"), "ok", show_buttons=False)
                return
            latest = str(result.get("latest_version", "") or "").strip()
            cur = str(getattr(self, "app_version", APP_VERSION) or APP_VERSION)
            self.last_known_version = latest
            if self._version_tuple(latest) > self._version_tuple(cur):
                self.update_available_info = result
                self._set_update_chip_state(
                    f"{tr.get('update_available', 'Update available')}: v{latest}",
                    "available",
                    show_buttons=True,
                )
                try:
                    self.update_install_btn.setText(tr.get("update_install", "Install"))
                    self.update_later_btn.setText(tr.get("update_later", "Later"))
                except Exception:
                    pass
                return
            self.update_available_info = None
            self._set_update_chip_state(f"v{cur} • {tr.get('update_none', 'Latest version installed')}", "ok", show_buttons=False)
        except Exception:
            pass

    def _install_update(self, *_):
        if self._update_installing:
            return
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        info = self.update_available_info if isinstance(self.update_available_info, dict) else None
        if not info:
            return
        self._update_installing = True
        self._set_update_chip_state(tr.get("update_downloading", "Downloading update..."), "busy", show_buttons=False)
        try:
            url = str(info.get("installer_url", "") or info.get("url", "") or "").strip()
            if not url:
                raise RuntimeError("manifest missing installer_url")
            local_installer = None
            if url.startswith("http://") or url.startswith("https://"):
                name = os.path.basename(url.split("?")[0]) or "ASCIIStudio_Update.exe"
                if not name.lower().endswith((".exe", ".msi", ".bat", ".cmd")):
                    QDesktopServices.openUrl(QUrl(url))
                    self._set_update_chip_state(tr.get("update_ready", "Starting installer..."), "ok", show_buttons=False)
                    return
                tmp = Path(tempfile.gettempdir()) / name
                req = urllib.request.Request(url, headers={"User-Agent": f"ASCIIStudio/{self.app_version}"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                tmp.write_bytes(data)
                local_installer = str(tmp)
            else:
                p = Path(url)
                if not p.is_absolute():
                    p = (Path(__file__).resolve().parent / p).resolve()
                local_installer = str(p)
            if not local_installer or not os.path.exists(local_installer):
                raise RuntimeError("installer not found")
            self._set_update_chip_state(tr.get("update_ready", "Starting installer..."), "ok", show_buttons=False)
            try:
                if os.name == "nt":
                    subprocess.Popen([local_installer], shell=False)
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(local_installer))
            except Exception:
                QDesktopServices.openUrl(QUrl.fromLocalFile(local_installer))
            try:
                QTimer.singleShot(250, self.close)
            except Exception:
                pass
        except Exception as e:
            self._set_update_chip_state(f"{tr.get('update_error', 'Update check failed')}: {e}", "error", show_buttons=False)
        finally:
            self._update_installing = False

    def _maybe_show_welcome(self):
        try:
            app_welcome_ver = "1.2"
            cur_ver = str(load_settings().get("welcome_version", ""))
            force = bool(getattr(self, "_force_welcome", False))
            if (not force) and bool(getattr(self, "welcome_shown", False)) and cur_ver == app_welcome_ver:
                return
            dlg = WelcomeDialog(self, self.lang)
            ok = dlg.exec() == QDialog.Accepted
            if ok:
                if getattr(dlg, "selected_lang", self.lang) in TRANSLATIONS and dlg.selected_lang != self.lang:
                    self.lang = dlg.selected_lang
                    self._apply_translations()
                sel_theme = str(getattr(dlg, "selected_theme", self.theme) or self.theme)
                if sel_theme in THEME_NAMES and sel_theme != self.theme:
                    self._apply_theme(sel_theme)
            s = load_settings()
            s["welcome_shown"] = True
            s["welcome_version"] = app_welcome_ver
            save_settings(s)
            self.welcome_shown = True
            self._force_welcome = False
            if ok and bool(getattr(dlg, "start_tutorial", False)):
                QTimer.singleShot(60, lambda: self._maybe_start_tutorial(first_run=False))
        except Exception:
            pass

    def _maybe_start_tutorial(self, first_run=False):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        if not self._confirm_overlay(tr.get("tutorial", "Tutorial"), tr.get("tutorial_confirm", "Ready to start the tutorial?")):
            return
        steps = [
            (self.gallery_frame, tr.get("tutorial", "Tutorial"), self._i3(
                "1. Р“Р°Р»РµСЂРµСЏ: Р·РґРµСЃСЊ С…СЂР°РЅСЏС‚СЃСЏ РёСЃС…РѕРґРЅРёРєРё Рё СЂРµР·СѓР»СЊС‚Р°С‚С‹ СЂРµРЅРґРµСЂР°. РћРґРёРЅ РєР»РёРє вЂ” РїСЂРµРІСЊСЋ, РґРІРѕР№РЅРѕР№ РєР»РёРє вЂ” РїР»РµРµСЂ.",
                "1. Gallery: your sources and rendered results are stored here.",
                "1. з”»е»Љпјљиї™й‡Њдїќе­жєђж–‡д»¶е’ЊжёІжџ“з»“жћњгЂ‚еЌ•е‡»йў„и§€пјЊеЏЊе‡»ж‰“ејЂж’­ж”ѕе™ЁгЂ‚"
            )),
            (self.preview_label, tr.get("tutorial", "Tutorial"), self._i3(
                "2. РџСЂРµРІСЊСЋ: РєРѕР»РµСЃРѕ РјС‹С€Рё вЂ” РјР°СЃС€С‚Р°Р±, РїРµСЂРµС‚Р°СЃРєРёРІР°РЅРёРµ вЂ” РїР°РЅРѕСЂР°РјР° (РґР»СЏ РёР·РѕР±СЂР°Р¶РµРЅРёР№).",
                "2. Preview: mouse wheel zooms, drag pans (for images).",
                "2. йў„и§€пјљж»љиЅ®зј©ж”ѕпјЊж‹–ж‹Ѕе№із§»пј€д»…е›ѕз‰‡пј‰гЂ‚"
            )),
            (None, tr.get("tutorial", "Tutorial"), self._i3(
                "2.1 Подсказка: клик по пустой затемнённой области переводит к следующему шагу обучения.",
                "2.1 Tip: click empty dark area to continue to the next tutorial step.",
                "2.1 提示：点击空白暗色区域可继续下一步教程。"
            )),
            (self.player_controls, tr.get("tutorial", "Tutorial"), self._i3(
                "2.2 Видеорежим: загрузите видео/GIF, здесь будут кнопки Play/Stop/Loop и таймлайн.",
                "2.2 Video mode: load a video or GIF to use Play/Stop/Loop and timeline controls.",
                "2.2 视频模式：加载视频或 GIF 后，在这里使用播放/停止/循环和时间轴控制。"
            )),
            (self.gallery_editor_btn, tr.get("tutorial", "Tutorial"), self._i3(
                "2.3 Редактор: кнопка открывает встроенный редактор со слоями, маской, обрезкой, аудио и нодами.",
                "2.3 Editor: opens the embedded editor with layers, mask, trim, audio and nodes.",
                "2.3 编辑器：打开内置编辑器，包含图层、遮罩、剪辑、音频和节点。"
            )),
            (self.preview_label, tr.get("tutorial", "Tutorial"), self._i3(
                "2.4 Фоторежим: при выбранном изображении масштабируйте колесом и двигайте кадр мышью.",
                "2.4 Photo mode: with an image selected, zoom by wheel and move frame with mouse drag.",
                "2.4 图片模式：选择图片后可滚轮缩放，并用鼠标拖动画面。"
            )),
            (self.load_btn, tr.get("tutorial", "Tutorial"), self._i3(
                "3. Р—Р°РіСЂСѓР·РёС‚СЊ: РёРјРїРѕСЂС‚ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ, РІРёРґРµРѕ РёР»Рё GIF.",
                "3. Load: import image, video or GIF.",
                "3. еЉ иЅЅпјљеЇје…Ґе›ѕз‰‡гЂЃи§†йў‘ж€– GIFгЂ‚"
            )),
            (self.render_btn, tr.get("tutorial", "Tutorial"), self._i3(
                "4. Р РµРЅРґРµСЂ: СЃС‚СЂРѕРёС‚ ASCII-РІРµСЂСЃРёСЋ СЃ С‚РµРєСѓС‰РёРјРё РїР°СЂР°РјРµС‚СЂР°РјРё.",
                "4. Render: generates ASCII output with current parameters.",
                "4. жёІжџ“пјљжЊ‰еЅ“е‰ЌеЏ‚ж•°з”џж€ђ ASCII иѕ“е‡єгЂ‚"
            )),
            (self.export_btn, tr.get("tutorial", "Tutorial"), self._i3(
                "5. Р­РєСЃРїРѕСЂС‚: СЃРѕС…СЂР°РЅСЏРµС‚ С„РёРЅР°Р»СЊРЅС‹Р№ С„Р°Р№Р» (PNG/GIF/MP4).",
                "5. Export: save final image/video/GIF.",
                "5. еЇје‡єпјљдїќе­жњЂз»€ж–‡д»¶пј€PNG/GIF/MP4пј‰гЂ‚"
            )),
            (self.preview_prev_btn, tr.get("tutorial", "Tutorial"), self._i3(
                "6. РљРЅРѕРїРєРё < Рё >: Р±С‹СЃС‚СЂРѕРµ РїРµСЂРµРєР»СЋС‡РµРЅРёРµ РјРµР¶РґСѓ С„Р°Р№Р»Р°РјРё РІ РіР°Р»РµСЂРµРµ.",
                "6. < and > switch between gallery items.",
                "6. дЅїз”Ё < е’Њ > ењЁз”»е»ЉжќЎз›®й—ґе€‡жЌўгЂ‚"
            )),
            (self.right_tabs_rail, tr.get("tutorial", "Tutorial"), self._i3(
                "7. Вертикальные вкладки справа: STYLE / IMAGE FX / PRO TOOLS / RENDER. Выбирайте категорию и настраивайте только нужный раздел.",
                "7. Right vertical tabs: STYLE / IMAGE FX / PRO TOOLS / RENDER. Open only the section you need.",
                "7. 右侧垂直标签：STYLE / IMAGE FX / PRO TOOLS / RENDER。按类别切换，只显示当前所需设置。"
            )),
            (self.style_combo, tr.get("tutorial", "Tutorial"), self._i3(
                "8. РЎС‚РёР»СЊ: Р·Р°РґР°С‘С‚ РІРёР·СѓР°Р»СЊРЅС‹Р№ С…Р°СЂР°РєС‚РµСЂ ASCII. Р’ custom Р°РєС‚РёРІРёСЂСѓСЋС‚СЃСЏ С†РІРµС‚ С‚РµРєСЃС‚Р°/С„РѕРЅР°.",
                "6. Style: choose the visual look. Custom enables text/background colors.",
                "8. йЈЋж јпјље†іе®љ ASCII и§†и§‰йЈЋж јгЂ‚йЂ‰ж‹© custom еђЋеЏЇи®ѕзЅ®ж–‡е­—/иѓЊж™Їи‰ІгЂ‚"
            )),
            (self.charset_input, tr.get("tutorial", "Tutorial"), self._i3(
                "9. РќР°Р±РѕСЂ СЃРёРјРІРѕР»РѕРІ: С‡РµРј Р±РѕРіР°С‡Рµ РЅР°Р±РѕСЂ, С‚РµРј Р±РѕР»СЊС€Рµ РЅСЋР°РЅСЃРѕРІ РїРѕР»СѓС‚РѕРЅРѕРІ.",
                "7. Charset: characters used for ASCII. Different sets change detail and style.",
                "9. е­—з¬¦й›†пјље­—з¬¦и¶Љдё°еЇЊпјЊзЃ°еє¦з»†иЉ‚и¶Ље¤љгЂ‚"
            )),
            (self.width_slider, tr.get("tutorial", "Tutorial"), self._i3(
                "10. РЁРёСЂРёРЅР° (СЃРёРјРІ.): Р±РѕР»СЊС€Рµ Р·РЅР°С‡РµРЅРёРµ вЂ” Р±РѕР»СЊС€Рµ РґРµС‚Р°Р»РµР№, РЅРѕ РјРµРґР»РµРЅРЅРµРµ СЂРµРЅРґРµСЂ.",
                "8. Width (chars): more chars = more detail, slower render.",
                "10. е®Ѕеє¦пј€е­—з¬¦пј‰пјљеЂји¶Ље¤§з»†иЉ‚и¶Љй«пјЊдЅ†жёІжџ“ж›ґж…ўгЂ‚"
            )),
            (self.font_slider, tr.get("tutorial", "Tutorial"), self._i3(
                "11. Р Р°Р·РјРµСЂ С€СЂРёС„С‚Р°: СЂР°Р·РјРµСЂ ASCII-СЃРёРјРІРѕР»РѕРІ РІ РёС‚РѕРіРѕРІРѕРј РёР·РѕР±СЂР°Р¶РµРЅРёРё/РІРёРґРµРѕ.",
                "9. Font size: ASCII glyph size in output.",
                "11. е­—дЅ“е¤§е°ЏпјљжЋ§е€¶иѕ“е‡єдё­ ASCII е­—з¬¦е°єеЇёгЂ‚"
            )),
            (self.fps_spin, tr.get("tutorial", "Tutorial"), self._i3(
                "12. FPS: С‡Р°СЃС‚РѕС‚Р° РєР°РґСЂРѕРІ РґР»СЏ Р°РЅРёРјР°С†РёРё Рё РІРёРґРµРѕ.",
                "10. FPS: animation and video export speed.",
                "12. FPSпјљеЉЁз”»дёЋи§†йў‘её§зЋ‡гЂ‚"
            )),
            (self.scale_x2, tr.get("tutorial", "Tutorial"), self._i3(
                "13. РњР°СЃС€С‚Р°Р± x1/x2/x3: СѓРІРµР»РёС‡РёРІР°РµС‚ РёС‚РѕРіРѕРІС‹Р№ СЂР°Р·РјРµСЂ Р±РµР· Р»РѕРјРєРё РїСЂРѕРїРѕСЂС†РёР№.",
                "11. Scale: x1/x2/x3 multiplies output size.",
                "13. зј©ж”ѕ x1/x2/x3пјљж”ѕе¤§иѕ“е‡єе°єеЇёе№¶дїќжЊЃжЇ”дѕ‹гЂ‚"
            )),
            (self.out_w, tr.get("tutorial", "Tutorial"), self._i3(
                "14. Р Р°Р·РјРµСЂ (РЁ x Р’): Р·Р°РґР°С‘С‚ С‚РѕС‡РЅРѕРµ СЂР°Р·СЂРµС€РµРЅРёРµ. РќРѕР»СЊ вЂ” Р°РІС‚РѕРїРѕРґР±РѕСЂ.",
                "12. Output size: set exact width/height (0 keeps auto/aspect).",
                "14. иѕ“е‡єе°єеЇёпј€е®Ѕxй«пј‰пјљеЏЇи®ѕе®љзІѕзЎ®е€†иѕЁзЋ‡пјЊ0 дёєи‡ЄеЉЁгЂ‚"
            )),
            (self.auto_size_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "15. РђРІС‚РѕСЂР°Р·РјРµСЂ: Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РІС‹СЃС‚Р°РІР»СЏРµС‚ СЂР°Р·РјРµСЂ РїРѕ РёСЃС…РѕРґРЅРѕРјСѓ С„Р°Р№Р»Сѓ.",
                "13. Auto size: fill size from source file.",
                "15. и‡ЄеЉЁе°єеЇёпјљж №жЌ®жєђж–‡д»¶и‡ЄеЉЁи®ѕзЅ®е°єеЇёгЂ‚"
            )),
            (self.invert_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "16. РРЅРІРµСЂС‚РёСЂРѕРІР°С‚СЊ: РјРµРЅСЏРµС‚ СЃРІРµС‚Р»С‹Рµ/С‚С‘РјРЅС‹Рµ РѕР±Р»Р°СЃС‚Рё РјРµСЃС‚Р°РјРё.",
                "14. Invert: swap dark/light tones.",
                "16. еЏЌз›ёпјљдє¤жЌўжЋжљ—еЊєеџџгЂ‚"
            )),
            (self.keep_size_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "17. РЎРѕС…СЂР°РЅСЏС‚СЊ РѕСЂРёРіРёРЅР°Р»СЊРЅС‹Р№ СЂР°Р·РјРµСЂ: РѕСЃС‚Р°РІР»СЏРµС‚ РёСЃС…РѕРґРЅРѕРµ СЂР°Р·СЂРµС€РµРЅРёРµ.",
                "15. Keep size: preserve original output size.",
                "17. дїќжЊЃеЋџе°єеЇёпјљдїќз•™еЋџе§‹е€†иѕЁзЋ‡гЂ‚"
            )),
            (self.denoise_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "18. РЁСѓРјРѕРїРѕРґР°РІР»РµРЅРёРµ: СѓРјРµРЅСЊС€Р°РµС‚ С€СѓРј РїРµСЂРµРґ ASCII-РїСЂРµРѕР±СЂР°Р·РѕРІР°РЅРёРµРј.",
                "16. Denoise: reduce noise before ASCII conversion.",
                "18. й™Ќе™ЄпјљењЁ ASCII иЅ¬жЌўе‰Ќе‡Џе°‘е™Єз‚№гЂ‚"
            )),
            (self.sharpen_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "19. Р РµР·РєРѕСЃС‚СЊ: РїРѕРґС‡С‘СЂРєРёРІР°РµС‚ РґРµС‚Р°Р»Рё Рё РєСЂР°СЏ.",
                "17. Sharpen: increase edge clarity.",
                "19. й”ђеЊ–пјљеўћејєз»†иЉ‚е’Њиѕ№зјгЂ‚"
            )),
            (self.edge_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "20. РЈСЃРёР»РµРЅРёРµ РєРѕРЅС‚СѓСЂРѕРІ: РґРµР»Р°РµС‚ РіСЂР°РЅРёС†С‹ Р±РѕР»РµРµ РІС‹СЂР°Р¶РµРЅРЅС‹РјРё.",
                "18. Edge boost: emphasize contours.",
                "20. иѕ№зјеўћејєпјљи®©иЅ®е»“ж›ґжЋжѕгЂ‚"
            )),
            (self.watermark_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "21. Р’РѕРґСЏРЅРѕР№ Р·РЅР°Рє: РґРѕР±Р°РІР»СЏРµС‚ РїРѕРґРїРёСЃСЊ Р°РІС‚РѕСЂР° РІ СЂРµР·СѓР»СЊС‚Р°С‚.",
                "19. Watermark: add your mark to output.",
                "21. ж°ґеЌ°пјљењЁз»“жћњдё­ж·»еЉ дЅњиЂ…ж ‡и®°гЂ‚"
            )),
            (self.pro_tools_frame, tr.get("tutorial", "Tutorial"), self._i3(
                "22. Pro Tools: РїР°РєРµС‚РЅР°СЏ РѕР±СЂР°Р±РѕС‚РєР° Рё Р±С‹СЃС‚СЂС‹Рµ С…СѓРґРѕР¶РµСЃС‚РІРµРЅРЅС‹Рµ РёРЅСЃС‚СЂСѓРјРµРЅС‚С‹.",
                "22. Pro Tools: batch processing and quick artistic tools.",
                "22. Pro Toolsпјљж‰№е¤„зђ†е’Њеї«жЌ·йЈЋж је·Ґе…·гЂ‚"
            )),
            (self.pro_options_frame, tr.get("tutorial", "Tutorial"), self._i3(
                "23. Pro FX: scanlines, СЃРІРµС‡РµРЅРёРµ, РІРёРЅСЊРµС‚РєР° Рё РїРѕСЃС‚РµСЂРёР·Р°С†РёСЏ РґР»СЏ СЃС‚РёР»РёР·Р°С†РёРё.",
                "23. Pro FX: scanlines, bloom, vignette and posterize controls.",
                "23. Pro FXпјљж‰«жЏЏзєїгЂЃиѕ‰е…‰гЂЃжљ—и§’дёЋи‰Ій¶жЋ§е€¶гЂ‚"
            )),
            (self.codec_combo, tr.get("tutorial", "Tutorial"), self._i3(
                "24. РљРѕРґРµРє: С„РѕСЂРјР°С‚ РІРёРґРµРѕ РїСЂРё СЌРєСЃРїРѕСЂС‚Рµ. libx264 вЂ” СЃР°РјС‹Р№ СѓРЅРёРІРµСЂСЃР°Р»СЊРЅС‹Р№.",
                "20. Codec: video format for export (compatibility vs size).",
                "24. зј–з Ѓе™ЁпјљеЇје‡єи§†йў‘ж јејЏгЂ‚libx264 е…је®№жЂ§жњЂеҐЅгЂ‚"
            )),
            (self.bitrate_combo, tr.get("tutorial", "Tutorial"), self._i3(
                "25. Р‘РёС‚СЂРµР№С‚: Р±Р°Р»Р°РЅСЃ РјРµР¶РґСѓ РєР°С‡РµСЃС‚РІРѕРј Рё СЂР°Р·РјРµСЂРѕРј С„Р°Р№Р»Р°.",
                "21. Bitrate: quality and file size trade-off.",
                "25. з ЃзЋ‡пјљиґЁй‡ЏдёЋдЅ“з§Їзљ„е№іиЎЎгЂ‚"
            )),
            (self.threads_spin, tr.get("tutorial", "Tutorial"), self._i3(
                "26. РџРѕС‚РѕРєРё CPU: Р±РѕР»СЊС€Рµ РїРѕС‚РѕРєРѕРІ РѕР±С‹С‡РЅРѕ СѓСЃРєРѕСЂСЏРµС‚ СЂРµРЅРґРµСЂ.",
                "22. CPU threads: more threads = faster render (if available).",
                "26. CPU зєїзЁ‹пјљж›ґе¤љзєїзЁ‹йЂљеёёжёІжџ“ж›ґеї«гЂ‚"
            )),
            (self.preset_combo, tr.get("tutorial", "Tutorial"), self._i3(
                "27. Preset: СЃРєРѕСЂРѕСЃС‚СЊ РєРѕРґРёСЂРѕРІР°РЅРёСЏ РїСЂРѕС‚РёРІ СЌС„С„РµРєС‚РёРІРЅРѕСЃС‚Рё СЃР¶Р°С‚РёСЏ.",
                "23. Preset: speed vs quality for encoding.",
                "27. йў„и®ѕпјљзј–з ЃйЂџеє¦дёЋеЋ‹зј©ж•€зЋ‡зљ„е№іиЎЎгЂ‚"
            )),
            (self.crf_spin, tr.get("tutorial", "Tutorial"), self._i3(
                "28. CRF: РјРµРЅСЊС€Рµ Р·РЅР°С‡РµРЅРёРµ вЂ” РІС‹С€Рµ РєР°С‡РµСЃС‚РІРѕ Рё Р±РѕР»СЊС€Рµ СЂР°Р·РјРµСЂ.",
                "24. CRF: lower = higher quality, larger size.",
                "28. CRFпјљеЂји¶ЉдЅЋиґЁй‡Џи¶Љй«гЂЃдЅ“з§Їи¶Ље¤§гЂ‚"
            )),
            (self.keep_audio_chk, tr.get("tutorial", "Tutorial"), self._i3(
                "29. РЎРѕС…СЂР°РЅСЏС‚СЊ Р·РІСѓРє РёСЃС‚РѕС‡РЅРёРєР°: РїРµСЂРµРЅРѕСЃРёС‚ Р°СѓРґРёРѕ РёР· РѕСЂРёРіРёРЅР°Р»СЊРЅРѕРіРѕ РІРёРґРµРѕ РІ С„РёРЅР°Р»СЊРЅС‹Р№ СЂРѕР»РёРє.",
                "29. Keep source audio: mux audio from original source into rendered video.",
                "29. дїќз•™жєђйџійў‘пјље°†еЋџи§†йў‘йџіиЅЁж··е…ҐжёІжџ“з»“жћњгЂ‚"
            )),
            (self.settings_btn, tr.get("tutorial", "Tutorial"), self._i3(
                "30. РќР°СЃС‚СЂРѕР№РєРё: СЏР·С‹Рє, СѓСЃС‚СЂРѕР№СЃС‚РІРѕ СЂРµРЅРґРµСЂР°, СЂРµРєРѕРјРµРЅРґСѓРµРјС‹Рµ/РґРµС„РѕР»С‚РЅС‹Рµ РїР°СЂР°РјРµС‚СЂС‹ Рё Р·Р°РїСѓСЃРє РѕР±СѓС‡РµРЅРёСЏ.",
                "25. Settings: language, device, defaults and tutorial access.",
                "30. и®ѕзЅ®пјљиЇ­иЁЂгЂЃжёІжџ“и®ѕе¤‡гЂЃй»и®¤/жЋЁиЌђеЏ‚ж•°е’Њж•™зЁ‹е…ҐеЏЈгЂ‚"
            )),
            (None, tr.get("tutorial", "Tutorial"), self._i3(
                "31. Р§С‚Рѕ С‚Р°РєРѕРµ ASCII: СЌС‚Рѕ СЃРїРѕСЃРѕР± РїСЂРµРґСЃС‚Р°РІР»СЏС‚СЊ РёР·РѕР±СЂР°Р¶РµРЅРёРµ СЃРёРјРІРѕР»Р°РјРё. Р›СѓС‡С€РёР№ СЂРµР·СѓР»СЊС‚Р°С‚ РѕР±С‹С‡РЅРѕ РґР°СЋС‚ РєРѕСЂСЂРµРєС‚РЅС‹Р№ РєРѕРЅС‚СЂР°СЃС‚, РїРѕРґС…РѕРґСЏС‰РёР№ РЅР°Р±РѕСЂ СЃРёРјРІРѕР»РѕРІ Рё РІРµСЂРЅС‹Р№ СЂР°Р·РјРµСЂ.",
                "31. What is ASCII: images represented by characters. Best quality usually comes from good contrast, proper charset and output size.",
                "31. д»Ђд№€жЇ ASCIIпјљз”Ёе­—з¬¦иЎЁз¤єе›ѕеѓЏгЂ‚ж›ґеҐЅзљ„з»“жћњйЂљеёёжќҐи‡Єеђ€йЂ‚еЇ№жЇ”еє¦гЂЃе­—з¬¦й›†е’Њиѕ“е‡єе°єеЇёгЂ‚"
            )),
        ]
        self._tour_overlay = GuidedTourOverlay(self, steps, tr)
        self._tour_overlay.show()
        self._tour_panel = TourPanel(self, self._tour_overlay, tr)
        self._tour_panel._render()
        self._tour_panel.show()

    def _mark_tutorial_done(self):
        try:
            s = load_settings()
            s["tutorial_done"] = True
            save_settings(s)
            self.tutorial_done = True
        except Exception:
            pass

    def open_settings_dialog(self):
        self._prepare_modal_ui()
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        dlg = OverlayDialog(self, self.theme, tr.get("settings", "Settings"))
        dlg.set_panel_size(860, 760)
        content = QWidget()
        c_l = QVBoxLayout(content)
        c_l.setContentsMargins(0, 0, 0, 0)
        c_l.setSpacing(8)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(2, 0, 2, 0)
        top_row.addWidget(QLabel(tr.get("settings", "Settings")), 1)
        version_chip = QLabel(f"v{self.app_version}")
        version_chip.setStyleSheet(
            "font-size:11px; padding:2px 8px;"
            "background: rgba(120,160,220,0.20); border:1px solid rgba(120,160,220,0.36); border-radius:8px;"
        )
        version_chip.setCursor(Qt.PointingHandCursor)
        _vclick = {"n": 0, "ts": 0.0}
        def _version_chip_press(_ev):
            now = time.time()
            if now - float(_vclick["ts"]) > 2.2:
                _vclick["n"] = 0
            _vclick["ts"] = now
            _vclick["n"] += 1
            if _vclick["n"] >= 5:
                _vclick["n"] = 0
                self._show_notice("Easter", "я в твоей голове")
        version_chip.mousePressEvent = _version_chip_press
        top_row.addWidget(version_chip, 0, Qt.AlignRight)
        c_l.addLayout(top_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(self._scrollbar_css())
        body = QWidget()
        fl = QFormLayout(body)
        fl.setLabelAlignment(Qt.AlignLeft)
        fl.setFormAlignment(Qt.AlignTop)
        fl.setHorizontalSpacing(16)
        fl.setVerticalSpacing(7)

        def _sec(title):
            txt = self._resolve_info_text(title, "Section")
            lbl = QLabel(txt)
            lbl.setStyleSheet("font-weight:700; font-size:12px; padding-top:10px;")
            fl.addRow(lbl)
            return lbl

        def _add_row(label, widget):
            lw = QLabel(str(label))
            fl.addRow(lw, widget)
            return lw, widget

        _sec(self._i3("Общие", "General", "常规"))
        lang_combo = QComboBox()
        lang_combo.addItems(["en", "ru", "zh"])
        lang_combo.setCurrentText(self.lang)
        _add_row(tr.get("language", "Language") + ":", lang_combo)

        dev_combo = QComboBox()
        dev_combo.addItem(tr.get("device_auto", "Auto"), "auto")
        dev_combo.addItem(tr.get("device_cpu", "CPU"), "cpu")
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                dev_combo.addItem(tr.get("device_gpu", "GPU (if available)"), "gpu")
        except Exception:
            pass
        idx = dev_combo.findData(self.device_choice)
        dev_combo.setCurrentIndex(idx if idx >= 0 else 0)
        _add_row(tr.get("processor", "Processor") + ":", dev_combo)

        watermark_chk = QCheckBox(tr.get("watermark", "Watermark"))
        watermark_chk.setChecked(self.watermark_chk.isChecked())
        fl.addRow(watermark_chk)
        watermark_text_input = QLineEdit(str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK))
        watermark_text_input.setPlaceholderText(tr.get("watermark_text", "Watermark text"))
        _add_row(tr.get("watermark_text", "Watermark text") + ":", watermark_text_input)
        live_preview_chk = QCheckBox(tr.get("live_preview", "Live preview (realtime)"))
        live_preview_chk.setChecked(bool(getattr(self, "live_preview", False)))
        fl.addRow(live_preview_chk)

        _sec(self._i3("Обновления", "Updates", "更新"))
        update_feed_input = QLineEdit(str(getattr(self, "update_feed_url", DEFAULT_UPDATE_FEED_URL) or DEFAULT_UPDATE_FEED_URL))
        update_feed_input.setPlaceholderText("update_manifest.json or https://.../update_manifest.json")
        _add_row("Update feed URL:", update_feed_input)
        auto_update_chk = QCheckBox(tr.get("menu_check_updates", "Check for updates"))
        auto_update_chk.setChecked(bool(getattr(self, "auto_check_updates", True)))
        fl.addRow(auto_update_chk)
        upd_help = QLabel(tr.get("update_feed_help", "Set update_feed_url in settings file."))
        upd_help.setWordWrap(True)
        upd_help.setStyleSheet("font-size:11px; color:#9fb3cc;")
        fl.addRow(upd_help)
        upd_btn = QPushButton(tr.get("menu_check_updates", "Check for updates"))
        upd_btn.setStyleSheet(self._glass_btn_css())
        try:
            ic = self._load_svg_icon("refresh", "#9fb3cc")
            if ic is None:
                ic = self._make_geom_icon("#9fb3cc", "circle")
            upd_btn.setIcon(ic)
        except Exception:
            pass
        upd_btn.clicked.connect(lambda: self._check_updates_async(force=True))
        fl.addRow(upd_btn)

        _sec(self._i3("Рендер", "Render", "渲染"))
        pro_chk = QCheckBox(tr.get("enable_pro_tools", "Enable Pro Tools"))
        pro_chk.setChecked(self.pro_tools)
        fl.addRow(pro_chk)
        threads_spin = QSpinBox()
        threads_spin.setRange(1, 64)
        threads_spin.setValue(self.render_threads)
        _add_row(tr.get("cpu_threads", "CPU threads") + ":", threads_spin)
        codec_combo = QComboBox()
        codec_combo.addItems(["libx264", "mpeg4", "libvpx", "h264"])
        codec_combo.setCurrentText(self.render_codec)
        _add_row(tr.get("codec", "Codec") + ":", codec_combo)
        bitrate_input = QComboBox()
        bitrate_input.addItems(["500k", "1M", "2M", "4M", "8M", "10M"])
        bitrate_input.setCurrentText(self.render_bitrate)
        _add_row(tr.get("bitrate", "Bitrate") + ":", bitrate_input)
        fps_spin = QSpinBox()
        fps_spin.setRange(1, 120)
        fps_spin.setValue(int(getattr(self, "render_fps", 24)))
        _add_row(tr.get("export_fps", "Export FPS") + ":", fps_spin)
        theme_combo = QComboBox()
        theme_combo.addItems(THEME_NAMES)
        theme_combo.setCurrentText(self.theme if self.theme in THEME_NAMES else "dark")
        _add_row(tr.get("theme", "Theme") + ":", theme_combo)
        trail_combo = QComboBox()
        trail_combo.addItems([tr["off"], tr["low"], tr["med"], tr["high"]])
        key_to_label = {"off": tr["off"], "low": tr["low"], "med": tr["med"], "high": tr["high"]}
        trail_combo.setCurrentText(key_to_label.get(self.trail_level, tr["med"]))
        _add_row(tr.get("trail", "Trail") + ":", trail_combo)

        custom_sec = _sec(self._i3("Кастомная тема", "Custom theme", "自定义主题"))
        custom_rows = []
        custom_bg_input = QLineEdit(str(getattr(self, "custom_theme_background", "") or ""))
        custom_bg_btn = QPushButton("...")
        custom_bg_btn.setFixedWidth(36)
        bg_row_w = QWidget()
        bg_row = QHBoxLayout(bg_row_w)
        bg_row.setContentsMargins(0, 0, 0, 0)
        bg_row.setSpacing(6)
        bg_row.addWidget(custom_bg_input, 1)
        bg_row.addWidget(custom_bg_btn)
        custom_rows.append(_add_row(tr.get("custom_bg", "Custom background") + ":", bg_row_w))

        def _mk_color_row(cur_hex):
            le = QLineEdit(str(cur_hex or ""))
            btn = QPushButton("...")
            btn.setFixedWidth(36)
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(6)
            l.addWidget(le, 1)
            l.addWidget(btn)
            def _pick():
                c = QColorDialog.getColor(QColor(le.text() or "#ffffff"), self)
                if c.isValid():
                    le.setText(c.name())
            btn.clicked.connect(_pick)
            return w, le

        c_bg_w, custom_bg_color_input = _mk_color_row(getattr(self, "custom_theme_bg", "#0c1018"))
        c_fg_w, custom_fg_color_input = _mk_color_row(getattr(self, "custom_theme_fg", "#e8f2ff"))
        c_ac_w, custom_accent_color_input = _mk_color_row(getattr(self, "custom_theme_accent", "#5ec8ff"))
        c_panel_w, custom_panel_color_input = _mk_color_row(getattr(self, "custom_theme_panel", "#151c29"))
        custom_rows.append(_add_row(tr.get("custom_color_bg", "BG color") + ":", c_bg_w))
        custom_rows.append(_add_row(tr.get("custom_color_fg", "Text color") + ":", c_fg_w))
        custom_rows.append(_add_row(tr.get("custom_color_accent", "Accent color") + ":", c_ac_w))
        custom_rows.append(_add_row("Panel color:", c_panel_w))

        icon_pack_path_input = QLineEdit(str(getattr(self, "icon_pack_path", "") or ""))
        icon_pack_browse_btn = QPushButton("...")
        icon_pack_browse_btn.setFixedWidth(36)
        ip_w = QWidget()
        ip_l = QHBoxLayout(ip_w)
        ip_l.setContentsMargins(0, 0, 0, 0)
        ip_l.setSpacing(6)
        ip_l.addWidget(icon_pack_path_input, 1)
        ip_l.addWidget(icon_pack_browse_btn)
        custom_rows.append(_add_row(tr.get("icon_pack_path", "Icon pack folder") + ":", ip_w))
        icon_pack_url_input = QLineEdit(str(getattr(self, "icon_pack_url", "") or ""))
        custom_rows.append(_add_row(tr.get("icon_pack_url", "Icon pack URL") + ":", icon_pack_url_input))

        def _toggle_custom_rows():
            on = str(theme_combo.currentText() or "").strip().lower() == "custom"
            custom_sec.setVisible(on)
            for row_lbl, row_widget in custom_rows:
                row_lbl.setVisible(on)
                row_widget.setVisible(on)

        theme_combo.currentTextChanged.connect(lambda *_: _toggle_custom_rows())
        _toggle_custom_rows()

        scroll.setWidget(body)
        c_l.addWidget(scroll, 1)

        row = QHBoxLayout()
        defaults_btn = QPushButton(tr.get("defaults", "Defaults"))
        rec_btn = QPushButton(tr.get("recommended", "Recommended"))
        tut_btn = QPushButton(tr.get("start_tutorial", "Start tutorial"))
        ok = QPushButton(tr.get("ok", "OK"))
        cancel = QPushButton(tr.get("cancel", "Cancel"))
        for b in (defaults_btn, rec_btn, tut_btn, ok, cancel):
            b.setStyleSheet(self._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        try:
            defaults_btn.setIcon(self._load_svg_icon("reset", "#9fb3cc"))
            rec_btn.setIcon(self._load_svg_icon("spark", "#9fb3cc"))
            tut_btn.setIcon(self._load_svg_icon("play-fill", "#9fb3cc"))
        except Exception:
            pass
        row.addWidget(defaults_btn)
        row.addWidget(rec_btn)
        row.addWidget(tut_btn)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        c_l.addLayout(row)

        def _pick_custom_bg():
            fn, _ = QFileDialog.getOpenFileName(
                self,
                tr.get("custom_bg", "Custom background"),
                os.getcwd(),
                "Media (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.avi *.mkv *.webm)",
            )
            if fn:
                custom_bg_input.setText(fn)

        def _pick_icon_pack_dir():
            d = QFileDialog.getExistingDirectory(
                self,
                tr.get("icon_pack_path", "Icon pack folder"),
                os.getcwd(),
            )
            if d:
                icon_pack_path_input.setText(d)

        custom_bg_btn.clicked.connect(_pick_custom_bg)
        icon_pack_browse_btn.clicked.connect(_pick_icon_pack_dir)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        defaults_btn.clicked.connect(lambda: self._apply_settings_to_widgets(lang_combo, dev_combo, threads_spin, codec_combo, bitrate_input, fps_spin, theme_combo, trail_combo, watermark_chk, pro_chk, live_preview_chk, use_recommended=False))
        rec_btn.clicked.connect(lambda: self._apply_settings_to_widgets(lang_combo, dev_combo, threads_spin, codec_combo, bitrate_input, fps_spin, theme_combo, trail_combo, watermark_chk, pro_chk, live_preview_chk, use_recommended=True))

        def _start_tutorial_from_settings():
            try:
                dlg.accept()
            except Exception:
                pass
            try:
                QTimer.singleShot(50, lambda: self._maybe_start_tutorial(first_run=False))
            except Exception:
                self._maybe_start_tutorial(first_run=False)

        tut_btn.clicked.connect(_start_tutorial_from_settings)
        dlg.set_body_widget(content)
        try:
            self._attach_sounds(dlg)
        except Exception:
            pass

        if dlg.exec() == QDialog.Accepted:
            try:
                rev = {tr["off"]: "off", tr["low"]: "low", tr["med"]: "med", tr["high"]: "high"}
                sel_trail = rev.get(trail_combo.currentText(), "med")
            except Exception:
                sel_trail = "med"
            self._apply_settings_dialog(
                lang_combo.currentText(),
                dev_combo.currentData() or dev_combo.currentText(),
                watermark_chk.isChecked(),
                pro_chk.isChecked(),
                threads_spin.value(),
                codec_combo.currentText(),
                bitrate_input.currentText(),
                sel_trail,
                fps_spin.value(),
                theme_combo.currentText(),
                bool(live_preview_chk.isChecked()),
            )
            self.watermark_text = str(watermark_text_input.text() or CORE_WATERMARK)
            try:
                self.watermark_text_edit.setText(self.watermark_text)
            except Exception:
                pass
            self.custom_theme_background = str(custom_bg_input.text() or "").strip()
            self.custom_theme_bg = str(custom_bg_color_input.text() or self.custom_theme_bg).strip() or self.custom_theme_bg
            self.custom_theme_fg = str(custom_fg_color_input.text() or self.custom_theme_fg).strip() or self.custom_theme_fg
            self.custom_theme_accent = str(custom_accent_color_input.text() or self.custom_theme_accent).strip() or self.custom_theme_accent
            self.custom_theme_panel = str(custom_panel_color_input.text() or self.custom_theme_panel).strip() or self.custom_theme_panel
            self.icon_pack_path = str(icon_pack_path_input.text() or "").strip()
            self.icon_pack_url = str(icon_pack_url_input.text() or "").strip()
            if str(getattr(self, "theme", "")) == "custom":
                self._apply_theme("custom")
            self.update_feed_url = str(update_feed_input.text() or DEFAULT_UPDATE_FEED_URL).strip()
            self.auto_check_updates = bool(auto_update_chk.isChecked())
            try:
                s = load_settings()
                s["watermark_text"] = self.watermark_text
                s["custom_theme_background"] = self.custom_theme_background
                s["custom_theme_bg"] = self.custom_theme_bg
                s["custom_theme_fg"] = self.custom_theme_fg
                s["custom_theme_accent"] = self.custom_theme_accent
                s["custom_theme_panel"] = self.custom_theme_panel
                s["icon_pack_path"] = self.icon_pack_path
                s["icon_pack_url"] = self.icon_pack_url
                s["update_feed_url"] = self.update_feed_url
                s["auto_check_updates"] = self.auto_check_updates
                save_settings(s)
            except Exception:
                pass
            self._icon_remote_failed.clear()
            self._refresh_button_icons()
            if self.auto_check_updates:
                QTimer.singleShot(150, lambda: self._check_updates_async(force=True))
        self._restore_modal_ui()

    def _apply_settings_to_widgets(self, lang_combo, dev_combo, threads_spin, codec_combo, bitrate_input, fps_spin, theme_combo, trail_combo, watermark_chk, pro_chk, live_preview_chk=None, use_recommended=False):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS['en'])
        if use_recommended:
            cpu = os.cpu_count() or 4
            threads_spin.setValue(max(1, min(16, cpu)))
            fps_spin.setValue(24)
            codec_combo.setCurrentText("libx264")
            theme_combo.setCurrentText(self.theme)
            trail_combo.setCurrentText(tr.get('med', 'Medium'))
            watermark_chk.setChecked(True)
            pro_chk.setChecked(self.pro_tools)
            if live_preview_chk is not None:
                live_preview_chk.setChecked(True)
            ram_gb = 8
            try:
                if psutil is not None:
                    ram_gb = int(psutil.virtual_memory().total / (1024**3))
            except Exception:
                ram_gb = 8
            if ram_gb <= 8:
                bitrate_input.setCurrentText("1M")
                self.width_slider.setValue(180)
                self.font_slider.setValue(12)
            elif ram_gb <= 16:
                bitrate_input.setCurrentText("2M")
                self.width_slider.setValue(240)
                self.font_slider.setValue(12)
            elif ram_gb <= 32:
                bitrate_input.setCurrentText("4M")
                self.width_slider.setValue(320)
                self.font_slider.setValue(12)
            else:
                bitrate_input.setCurrentText("6M")
                self.width_slider.setValue(420)
                self.font_slider.setValue(12)
        else:
            # defaults from settings_store
            threads_spin.setValue(4)
            fps_spin.setValue(24)
            codec_combo.setCurrentText("libx264")
            bitrate_input.setCurrentText("2M")
            theme_combo.setCurrentText("dark")
            trail_combo.setCurrentText(tr.get('med', 'Medium'))
            watermark_chk.setChecked(True)
            pro_chk.setChecked(False)
            if live_preview_chk is not None:
                live_preview_chk.setChecked(False)
            self.width_slider.setValue(320)
            self.font_slider.setValue(12)
    def _apply_settings_dialog(self, langkey, devicekey, watermark_flag, pro_flag, threads, codec, bitrate, trail_level='med', export_fps=12, theme_name='dark', live_preview=False):
        self._push_undo_state()
        self.lang = langkey
        self._apply_translations()
        # device choice stored but UI device selector moved to settings
        self.device_choice = devicekey
        self.render_device = self._resolve_device_choice(devicekey)
        self.watermark_chk.setChecked(watermark_flag)
        self.pro_tools = bool(pro_flag)
        try:
            self.pro_tools_frame.setVisible(bool(self.pro_tools))
            if hasattr(self, "pro_options_frame"):
                self.pro_options_frame.setVisible(bool(self.pro_tools))
            for w in getattr(self, "_pro_section_widgets", []) or []:
                w.setVisible(bool(self.pro_tools))
            if hasattr(self, "pro_menu"):
                self.pro_menu.menuAction().setVisible(bool(self.pro_tools))
            self._index_right_sections()
            if not self.pro_tools and getattr(self, "_active_right_section", "style") == "pro":
                self._active_right_section = "style"
            self._show_right_section(getattr(self, "_active_right_section", "style"))
        except Exception:
            pass
        self.render_threads = int(threads)
        self.render_codec = codec
        self.render_bitrate = bitrate
        self.export_fps = int(export_fps)
        self.render_fps = int(export_fps)
        self.theme = theme_name if theme_name in THEME_NAMES else self.theme
        self.live_preview = bool(live_preview)
        try:
            self.trail_level = trail_level
        except Exception:
            pass
        # save settings
        s = {
            'lang': self.lang,
            'style': self.style,
            'width_chars': self.width_chars,
            'font_size': self.font_size,
            'fg_hex': self.fg_hex,
            'bg_hex': self.bg_hex,
            'trail_level': self.trail_level,
            'device_choice': devicekey,
            'pro_tools': self.pro_tools,
            'render_device': getattr(self, 'render_device', self.device_choice),
            'render_threads': self.render_threads,
            'render_codec': self.render_codec,
            'render_bitrate': self.render_bitrate,
            'render_fps': self.render_fps,
            'render_scale': int(self.render_scale),
            'render_out_w': int(self.render_out_w),
            'render_out_h': int(self.render_out_h),
            'render_preset': getattr(self, 'render_preset', 'medium'),
            'render_crf': int(getattr(self, 'render_crf', 20)),
            'keep_source_audio': bool(getattr(self, "keep_source_audio", True)),
            'pro_scanlines': bool(self.pro_scanlines_chk.isChecked() if hasattr(self, "pro_scanlines_chk") else self.pro_scanlines),
            'pro_bloom': int(getattr(self, "pro_bloom", 0)),
            'pro_vignette': int(getattr(self, "pro_vignette", 0)),
            'pro_poster_bits': int(getattr(self, "pro_poster_bits", 0)),
            'pro_grain': int(getattr(self, "pro_grain", 0)),
            'pro_chroma': int(getattr(self, "pro_chroma", 0)),
            'pro_scan_strength': int(getattr(self, "pro_scan_strength", 28)),
            'pro_scan_step': int(getattr(self, "pro_scan_step", 3)),
            'pro_curvature': int(getattr(self, "pro_curvature", 0)),
            'pro_concavity': int(getattr(self, "pro_concavity", 0)),
            'pro_curvature_center_x': int(getattr(self, "pro_curvature_center_x", 0)),
            'pro_curvature_expand': int(getattr(self, "pro_curvature_expand", 0)),
            'pro_curvature_type': str(getattr(self, "pro_curvature_type", "spherical") or "spherical"),
            'pro_ribbing': int(getattr(self, "pro_ribbing", 0)),
            'pro_clarity': int(getattr(self, "pro_clarity", 0)),
            'pro_motion_blur': int(getattr(self, "pro_motion_blur", 0)),
            'pro_color_boost': int(getattr(self, "pro_color_boost", 0)),
            'pro_glitch': int(getattr(self, "pro_glitch", 0)),
            'pro_glitch_density': int(getattr(self, "pro_glitch_density", 35)),
            'pro_glitch_shift': int(getattr(self, "pro_glitch_shift", 42)),
            'pro_glitch_rgb': int(getattr(self, "pro_glitch_rgb", 1)),
            'pro_glitch_block': int(getattr(self, "pro_glitch_block", 10)),
            'pro_glitch_jitter': int(getattr(self, "pro_glitch_jitter", 1)),
            'pro_glitch_noise': int(getattr(self, "pro_glitch_noise", 12)),
            'theme': self.theme,
            'trail_length': self.trail_length,
            'export_gif_fps': self.export_fps,
            'gamma_pct': int(self.gamma_pct),
            'denoise': bool(self.denoise_chk.isChecked()),
            'sharpen': bool(self.sharpen_chk.isChecked()),
            'edge_boost': bool(self.edge_chk.isChecked()),
            'show_watermark': self.watermark_chk.isChecked(),
            'watermark_text': str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK),
            'ascii_chars': self.charset_input.currentText(),
            'contrast': self.contrast_slider.value() if hasattr(self, 'contrast_slider') else 100,
            'invert': self.invert_chk.isChecked(),
            'keep_size': self.keep_size_chk.isChecked()
            ,
            'live_preview': bool(getattr(self, "live_preview", False)),
            'custom_theme_background': str(getattr(self, "custom_theme_background", "") or ""),
            'custom_theme_bg': str(getattr(self, "custom_theme_bg", "#0c1018") or "#0c1018"),
            'custom_theme_fg': str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff"),
            'custom_theme_accent': str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff"),
            'custom_theme_panel': str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29"),
            'icon_pack_path': str(getattr(self, "icon_pack_path", "") or ""),
            'icon_pack_url': str(getattr(self, "icon_pack_url", "") or ""),
            'update_feed_url': str(getattr(self, "update_feed_url", DEFAULT_UPDATE_FEED_URL) or DEFAULT_UPDATE_FEED_URL),
            'auto_check_updates': bool(getattr(self, "auto_check_updates", True)),
            'last_update_check': float(getattr(self, "last_update_check", 0) or 0),
            'last_known_version': str(getattr(self, "last_known_version", "") or ""),
        }
        save_settings(s)
        # update UI language sensitive strings
        try:
            self.fps_spin.setValue(int(self.render_fps))
        except Exception:
            pass
        self._apply_translations()
        self._apply_theme(self.theme)

    def _selected_gallery_item(self):
        items = self.gallery_list.selectedItems()
        return items[0] if items else None

    def _apply_tool_to_selected(self, tool_name):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        item = self._selected_gallery_item()
        if item is None:
            self._show_notice(tr.get("tools", "Tools"), tr.get("no_selection", "No gallery item selected."))
            return
        self._push_undo_state()
        data = item.data(Qt.UserRole) or {}
        pil = data.get("pil")
        if pil is None:
            return
        img = pil.convert("RGB")
        try:
            if tool_name == "invert":
                img = ImageOps.invert(img)
            elif tool_name == "edges":
                img = img.filter(ImageFilter.FIND_EDGES)
            elif tool_name == "sharpen":
                img = img.filter(ImageFilter.SHARPEN)
            elif tool_name == "posterize":
                img = ImageOps.posterize(img, 3)
            elif tool_name == "mirror":
                img = ImageOps.mirror(img)
            elif tool_name == "bloom":
                blur = img.filter(ImageFilter.GaussianBlur(radius=2.0))
                img = Image.blend(img, blur, 0.35)
            elif tool_name == "vignette":
                w, h = img.size
                mask = Image.new("L", (w, h), 255)
                md = ImageDraw.Draw(mask)
                border = int(min(w, h) * 0.28)
                md.rectangle((border, border, w - border, h - border), fill=0)
                mask = mask.filter(ImageFilter.GaussianBlur(radius=max(8, int(min(w, h) * 0.08))))
                dark = Image.new("RGB", (w, h), (0, 0, 0))
                img = Image.composite(dark, img, mask)
            elif tool_name == "scanlines":
                w, h = img.size
                over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                od = ImageDraw.Draw(over)
                step = max(1, int(getattr(self, "pro_scan_step", 3)))
                strength = max(0, min(100, int(getattr(self, "pro_scan_strength", 28))))
                alpha = int(8 + strength * 1.1)
                for y in range(0, h, step):
                    od.line((0, y, w, y), fill=(0, 0, 0, alpha), width=1)
                img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
            elif tool_name == "grain":
                arr = np.array(img.convert("RGB"), dtype=np.int16)
                noise = np.random.normal(0.0, 10.0, arr.shape).astype(np.int16)
                arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
                img = Image.fromarray(arr, mode="RGB")
            elif tool_name == "chroma":
                arr = np.array(img.convert("RGB"), dtype=np.uint8)
                arr[:, :, 0] = np.roll(arr[:, :, 0], 2, axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -2, axis=1)
                img = Image.fromarray(arr, mode="RGB")
            elif tool_name == "glitch":
                g = max(1, int(getattr(self, "pro_glitch", 24)))
                img = self._apply_glitch_effect(img, g)
            data["pil"] = img
            item.setData(Qt.UserRole, data)
            thumb = img.copy()
            thumb.thumbnail((190, 190), Image.Resampling.LANCZOS)
            item.setIcon(QIcon(pil_to_qpixmap(thumb)))
            self.current_output = img
            self._show_preview_pil(img)
        except Exception as e:
            print("Tool failed:", e)

    def _set_pro_option(self, key, enabled):
        try:
            if key == "scanlines" and hasattr(self, "pro_scanlines_chk"):
                self.pro_scanlines_chk.setChecked(bool(enabled))
            elif key == "bloom" and hasattr(self, "pro_bloom_slider"):
                self.pro_bloom_slider.setValue(28 if enabled else 0)
            elif key == "vignette" and hasattr(self, "pro_vignette_slider"):
                self.pro_vignette_slider.setValue(24 if enabled else 0)
            elif key == "glitch" and hasattr(self, "pro_glitch_slider"):
                self.pro_glitch_slider.setValue(26 if enabled else 0)
                if hasattr(self, "pro_glitch_density_slider"):
                    self.pro_glitch_density_slider.setValue(58 if enabled else 0)
                if hasattr(self, "pro_glitch_shift_slider"):
                    self.pro_glitch_shift_slider.setValue(54 if enabled else 0)
                if hasattr(self, "pro_glitch_rgb_spin"):
                    self.pro_glitch_rgb_spin.setValue(2 if enabled else 0)
                if hasattr(self, "pro_glitch_block_spin"):
                    self.pro_glitch_block_spin.setValue(16 if enabled else 0)
                if hasattr(self, "pro_glitch_jitter_spin"):
                    self.pro_glitch_jitter_spin.setValue(2 if enabled else 0)
                if hasattr(self, "pro_glitch_noise_slider"):
                    self.pro_glitch_noise_slider.setValue(24 if enabled else 0)
            self._sync_pro_menu_state()
        except Exception:
            pass

    def _apply_pro_preset(self, name):
        try:
            self._push_undo_state()
            if hasattr(self, "pro_preset_combo") and self.pro_preset_combo.currentText() != name:
                self.pro_preset_combo.blockSignals(True)
                self.pro_preset_combo.setCurrentText(name)
                self.pro_preset_combo.blockSignals(False)
            def _sv(attr_name, value):
                w = getattr(self, attr_name, None)
                if w is None:
                    return
                try:
                    w.setValue(value)
                except Exception:
                    pass
            if name == "soft":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(False)
                _sv("pro_bloom_slider", 18)
                _sv("pro_vignette_slider", 12)
                _sv("pro_poster_spin", 0)
                _sv("pro_grain_slider", 8)
                _sv("pro_chroma_spin", 0)
                _sv("pro_scan_strength_slider", 18)
                _sv("pro_scan_step_spin", 3)
                _sv("pro_curvature_slider", 8)
                _sv("pro_ribbing_slider", 12)
                _sv("pro_glitch_slider", 0)
                _sv("pro_glitch_density_slider", 20)
                _sv("pro_glitch_shift_slider", 25)
                _sv("pro_glitch_rgb_spin", 0)
                _sv("pro_glitch_block_spin", 4)
                _sv("pro_glitch_jitter_spin", 0)
                _sv("pro_glitch_noise_slider", 8)
            elif name == "cyber":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(True)
                _sv("pro_bloom_slider", 42)
                _sv("pro_vignette_slider", 22)
                _sv("pro_poster_spin", 4)
                _sv("pro_grain_slider", 18)
                _sv("pro_chroma_spin", 2)
                _sv("pro_scan_strength_slider", 42)
                _sv("pro_scan_step_spin", 2)
                _sv("pro_curvature_slider", 10)
                _sv("pro_ribbing_slider", 18)
                _sv("pro_glitch_slider", 12)
                _sv("pro_glitch_density_slider", 58)
                _sv("pro_glitch_shift_slider", 72)
                _sv("pro_glitch_rgb_spin", 3)
                _sv("pro_glitch_block_spin", 20)
                _sv("pro_glitch_jitter_spin", 2)
                _sv("pro_glitch_noise_slider", 22)
            elif name == "cinematic":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(False)
                _sv("pro_bloom_slider", 28)
                _sv("pro_vignette_slider", 34)
                _sv("pro_poster_spin", 2)
                _sv("pro_grain_slider", 26)
                _sv("pro_chroma_spin", 1)
                _sv("pro_scan_strength_slider", 16)
                _sv("pro_scan_step_spin", 4)
                _sv("pro_curvature_slider", 6)
                _sv("pro_ribbing_slider", 10)
                _sv("pro_glitch_slider", 6)
                _sv("pro_glitch_density_slider", 28)
                _sv("pro_glitch_shift_slider", 36)
                _sv("pro_glitch_rgb_spin", 1)
                _sv("pro_glitch_block_spin", 8)
                _sv("pro_glitch_jitter_spin", 1)
                _sv("pro_glitch_noise_slider", 14)
            elif name == "sketch":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(True)
                _sv("pro_bloom_slider", 6)
                _sv("pro_vignette_slider", 16)
                _sv("pro_poster_spin", 5)
                _sv("pro_grain_slider", 12)
                _sv("pro_chroma_spin", 0)
                _sv("pro_scan_strength_slider", 24)
                _sv("pro_scan_step_spin", 3)
                _sv("pro_curvature_slider", 4)
                _sv("pro_ribbing_slider", 8)
                _sv("pro_glitch_slider", 0)
                _sv("pro_glitch_density_slider", 10)
                _sv("pro_glitch_shift_slider", 18)
                _sv("pro_glitch_rgb_spin", 0)
                _sv("pro_glitch_block_spin", 0)
                _sv("pro_glitch_jitter_spin", 0)
                _sv("pro_glitch_noise_slider", 4)
            elif name == "retro":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(True)
                _sv("pro_bloom_slider", 14)
                _sv("pro_vignette_slider", 30)
                _sv("pro_poster_spin", 3)
                _sv("pro_grain_slider", 24)
                _sv("pro_chroma_spin", 1)
                _sv("pro_scan_strength_slider", 58)
                _sv("pro_scan_step_spin", 3)
                _sv("pro_curvature_slider", 36)
                _sv("pro_ribbing_slider", 44)
                _sv("pro_glitch_slider", 24)
                _sv("pro_glitch_density_slider", 64)
                _sv("pro_glitch_shift_slider", 54)
                _sv("pro_glitch_rgb_spin", 2)
                _sv("pro_glitch_block_spin", 18)
                _sv("pro_glitch_jitter_spin", 2)
                _sv("pro_glitch_noise_slider", 28)
            elif name == "vhs":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(True)
                _sv("pro_bloom_slider", 20)
                _sv("pro_vignette_slider", 26)
                _sv("pro_poster_spin", 2)
                _sv("pro_grain_slider", 34)
                _sv("pro_chroma_spin", 3)
                _sv("pro_scan_strength_slider", 72)
                _sv("pro_scan_step_spin", 2)
                _sv("pro_curvature_slider", 42)
                _sv("pro_ribbing_slider", 62)
                _sv("pro_glitch_slider", 46)
                _sv("pro_glitch_density_slider", 84)
                _sv("pro_glitch_shift_slider", 76)
                _sv("pro_glitch_rgb_spin", 4)
                _sv("pro_glitch_block_spin", 28)
                _sv("pro_glitch_jitter_spin", 3)
                _sv("pro_glitch_noise_slider", 40)
            elif name == "clean":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(False)
                _sv("pro_bloom_slider", 0)
                _sv("pro_vignette_slider", 0)
                _sv("pro_poster_spin", 0)
                _sv("pro_grain_slider", 0)
                _sv("pro_chroma_spin", 0)
                _sv("pro_scan_strength_slider", 0)
                _sv("pro_scan_step_spin", 3)
                _sv("pro_curvature_slider", 0)
                _sv("pro_ribbing_slider", 0)
                _sv("pro_glitch_slider", 0)
                _sv("pro_glitch_density_slider", 0)
                _sv("pro_glitch_shift_slider", 0)
                _sv("pro_glitch_rgb_spin", 0)
                _sv("pro_glitch_block_spin", 0)
                _sv("pro_glitch_jitter_spin", 0)
                _sv("pro_glitch_noise_slider", 0)
            elif name == "none":
                if hasattr(self, "pro_scanlines_chk"):
                    self.pro_scanlines_chk.setChecked(False)
                _sv("pro_bloom_slider", 0)
                _sv("pro_vignette_slider", 0)
                _sv("pro_poster_spin", 0)
                _sv("pro_grain_slider", 0)
                _sv("pro_chroma_spin", 0)
                _sv("pro_scan_strength_slider", 28)
                _sv("pro_scan_step_spin", 3)
                _sv("pro_curvature_slider", 0)
                _sv("pro_ribbing_slider", 0)
                _sv("pro_glitch_slider", 0)
                _sv("pro_glitch_density_slider", 35)
                _sv("pro_glitch_shift_slider", 42)
                _sv("pro_glitch_rgb_spin", 1)
                _sv("pro_glitch_block_spin", 10)
                _sv("pro_glitch_jitter_spin", 1)
                _sv("pro_glitch_noise_slider", 12)
            extra_map = {
                "soft": (6, 14, 4, 0, 0, 6, "spherical"),
                "cyber": (34, 38, 10, 6, 2, 16, "barrel"),
                "cinematic": (22, 28, 14, 0, 0, 22, "spherical"),
                "sketch": (0, 46, 0, 0, 0, 4, "horizontal"),
                "retro": (18, 20, 18, 6, -4, 36, "barrel"),
                "vhs": (30, 16, 28, 14, 5, 44, "pincushion"),
                "clean": (0, 0, 0, 0, 0, 0, "spherical"),
                "none": (0, 0, 0, 0, 0, 0, "spherical"),
            }
            ev = extra_map.get(name, extra_map["none"])
            _sv("pro_color_boost_slider", int(ev[0]))
            _sv("pro_clarity_slider", int(ev[1]))
            _sv("pro_motion_blur_slider", int(ev[2]))
            _sv("pro_concavity_slider", int(ev[3]))
            _sv("pro_curvature_center_x_slider", int(ev[4]))
            _sv("pro_curvature_expand_slider", int(ev[5]))
            if hasattr(self, "pro_curvature_type_combo"):
                self.pro_curvature_type_combo.setCurrentText(str(ev[6] or "spherical"))
            self._sync_pro_menu_state()
        except Exception:
            pass

    def _on_pro_preset_combo_changed(self, name):
        try:
            name = (name or "none").strip().lower()
            if name:
                self._apply_pro_preset(name)
        except Exception:
            pass

    def _reset_pro_tools(self):
        try:
            self._push_undo_state()
            if hasattr(self, "pro_scanlines_chk"):
                self.pro_scanlines_chk.setChecked(False)
            if hasattr(self, "pro_bloom_slider"):
                self.pro_bloom_slider.setValue(0)
            if hasattr(self, "pro_vignette_slider"):
                self.pro_vignette_slider.setValue(0)
            if hasattr(self, "pro_poster_spin"):
                self.pro_poster_spin.setValue(0)
            if hasattr(self, "pro_grain_slider"):
                self.pro_grain_slider.setValue(0)
            if hasattr(self, "pro_chroma_spin"):
                self.pro_chroma_spin.setValue(0)
            if hasattr(self, "pro_color_boost_slider"):
                self.pro_color_boost_slider.setValue(0)
            if hasattr(self, "pro_clarity_slider"):
                self.pro_clarity_slider.setValue(0)
            if hasattr(self, "pro_motion_blur_slider"):
                self.pro_motion_blur_slider.setValue(0)
            if hasattr(self, "pro_scan_strength_slider"):
                self.pro_scan_strength_slider.setValue(28)
            if hasattr(self, "pro_scan_step_spin"):
                self.pro_scan_step_spin.setValue(3)
            if hasattr(self, "pro_curvature_slider"):
                self.pro_curvature_slider.setValue(0)
            if hasattr(self, "pro_concavity_slider"):
                self.pro_concavity_slider.setValue(0)
            if hasattr(self, "pro_curvature_center_x_slider"):
                self.pro_curvature_center_x_slider.setValue(0)
            if hasattr(self, "pro_curvature_expand_slider"):
                self.pro_curvature_expand_slider.setValue(0)
            if hasattr(self, "pro_curvature_type_combo"):
                self.pro_curvature_type_combo.setCurrentText("spherical")
            if hasattr(self, "pro_ribbing_slider"):
                self.pro_ribbing_slider.setValue(0)
            if hasattr(self, "pro_glitch_slider"):
                self.pro_glitch_slider.setValue(0)
            if hasattr(self, "pro_glitch_density_slider"):
                self.pro_glitch_density_slider.setValue(35)
            if hasattr(self, "pro_glitch_shift_slider"):
                self.pro_glitch_shift_slider.setValue(42)
            if hasattr(self, "pro_glitch_rgb_spin"):
                self.pro_glitch_rgb_spin.setValue(1)
            if hasattr(self, "pro_glitch_block_spin"):
                self.pro_glitch_block_spin.setValue(10)
            if hasattr(self, "pro_glitch_jitter_spin"):
                self.pro_glitch_jitter_spin.setValue(1)
            if hasattr(self, "pro_glitch_noise_slider"):
                self.pro_glitch_noise_slider.setValue(12)
            if hasattr(self, "pro_preset_combo"):
                self.pro_preset_combo.blockSignals(True)
                self.pro_preset_combo.setCurrentText("none")
                self.pro_preset_combo.blockSignals(False)
            self._sync_pro_menu_state()
        except Exception:
            pass

    def _sync_pro_menu_state(self):
        try:
            if hasattr(self, "pro_toggle_scan") and hasattr(self, "pro_scanlines_chk"):
                self.pro_toggle_scan.setChecked(bool(self.pro_scanlines_chk.isChecked()))
            if hasattr(self, "pro_toggle_bloom") and hasattr(self, "pro_bloom_slider"):
                self.pro_toggle_bloom.setChecked(int(self.pro_bloom_slider.value()) > 0)
            if hasattr(self, "pro_toggle_vignette") and hasattr(self, "pro_vignette_slider"):
                self.pro_toggle_vignette.setChecked(int(self.pro_vignette_slider.value()) > 0)
        except Exception:
            pass

    def _batch_ascii_render(self):
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        try:
            if self._sound_mgr:
                self._sound_mgr.play_open()
        except Exception:
            pass
        files, _ = QFileDialog.getOpenFileNames(
            self,
            tr.get("batch", "Batch"),
            os.getcwd(),
            "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        try:
            if self._sound_mgr:
                self._sound_mgr.play_close()
        except Exception:
            pass
        if not files:
            return
        try:
            if self._sound_mgr:
                self._sound_mgr.play_open()
        except Exception:
            pass
        out_dir = QFileDialog.getExistingDirectory(self, tr.get("export", "Export"), os.getcwd())
        try:
            if self._sound_mgr:
                self._sound_mgr.play_close()
        except Exception:
            pass
        if not out_dir:
            return
        for f in files:
            try:
                pil = Image.open(f).convert("RGB")
                pil = self._preprocess_pil(pil)
                out = self._render_with_style(pil, output_size=None)
                stem = Path(f).stem
                out.save(str(Path(out_dir) / f"{stem}_ascii.png"))
            except Exception as e:
                print("Batch item failed:", e)
        self._show_notice(tr.get("batch", "Batch"), tr.get("batch_done", "Batch processing complete"))

    def keyPressEvent(self, ev):
        try:
            txt = ""
            try:
                txt = str(ev.text() or "").lower()
            except Exception:
                txt = ""
            if txt and txt.isprintable():
                buf = (str(getattr(self, "_secret_code_buf", "")) + txt)[-32:]
                self._secret_code_buf = buf
                tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
                if buf.endswith("iddqd"):
                    self._apply_theme("aphex twin")
                    self._show_notice("Easter", "IDDQD")
                    self._secret_code_buf = ""
                elif buf.endswith("matrix"):
                    try:
                        self.style_combo.setCurrentText("matrix")
                    except Exception:
                        pass
                    self._show_notice("Easter", "Wake up, Neo.")
                    self._secret_code_buf = ""
                elif buf.endswith("snerk"):
                    try:
                        p = _pick_resource_path("SNERK503.mp3")
                        if p is not None:
                            if self._egg_audio is None:
                                self._egg_audio = QAudioOutput(self)
                                self._egg_audio.setVolume(0.5)
                            if self._egg_player is None:
                                self._egg_player = QMediaPlayer(self)
                                self._egg_player.setAudioOutput(self._egg_audio)
                            self._egg_player.stop()
                            self._egg_player.setSource(QUrl.fromLocalFile(str(p)))
                            self._egg_player.play()
                    except Exception:
                        pass
                    self._secret_code_buf = ""
            if ev.key() == Qt.Key_Escape:
                if self._preview_focus_mode:
                    self._toggle_player_focus_mode()
                    return
        except Exception:
            pass
        return super().keyPressEvent(ev)

    def closeEvent(self, ev):
        try:
            if bool(getattr(self, "confirm_on_close", True)) and not bool(getattr(self, "_closing_by_easter", False)):
                tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
                if not self._confirm_overlay(tr.get("app", "ASCII Studio"), tr.get("confirm_close", "Close application?")):
                    ev.ignore()
                    return
        except Exception:
            pass
        try:
            self._close_embedded_editor(apply=False, restore_modal=False)
        except Exception:
            pass
        try:
            s = load_settings()
            s.update({
                "lang": self.lang,
                "style": self.style,
                "width_chars": int(self.width_chars),
                "font_size": int(self.font_size),
                "fg_hex": self.fg_hex,
                "bg_hex": self.bg_hex,
                "trail_level": self.trail_level,
                "render_threads": int(self.render_threads),
                "render_codec": str(self.render_codec),
                "render_bitrate": str(self.render_bitrate),
                "render_fps": int(self.render_fps),
                "render_scale": int(self.render_scale),
                "render_out_w": int(self.render_out_w),
                "render_out_h": int(self.render_out_h),
                "render_preset": str(getattr(self, "render_preset", "medium")),
                "render_crf": int(getattr(self, "render_crf", 20)),
                "gamma_pct": int(self.gamma_pct),
                "denoise": bool(self.denoise_chk.isChecked()),
                "sharpen": bool(self.sharpen_chk.isChecked()),
                "edge_boost": bool(self.edge_chk.isChecked()),
                "ascii_chars": self.charset_input.currentText(),
                "contrast": int(self.contrast_slider.value()) if hasattr(self, "contrast_slider") else 100,
                "invert": bool(self.invert_chk.isChecked()),
                "keep_size": bool(self.keep_size_chk.isChecked()),
                "show_watermark": bool(self.watermark_chk.isChecked()),
                "watermark_text": str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK),
                "theme": self.theme,
                "custom_theme_background": str(getattr(self, "custom_theme_background", "") or ""),
                "custom_theme_bg": str(getattr(self, "custom_theme_bg", "#0c1018") or "#0c1018"),
                "custom_theme_fg": str(getattr(self, "custom_theme_fg", "#e8f2ff") or "#e8f2ff"),
                "custom_theme_accent": str(getattr(self, "custom_theme_accent", "#5ec8ff") or "#5ec8ff"),
                "custom_theme_panel": str(getattr(self, "custom_theme_panel", "#151c29") or "#151c29"),
                "icon_pack_path": str(getattr(self, "icon_pack_path", "") or ""),
                "icon_pack_url": str(getattr(self, "icon_pack_url", "") or ""),
                "pro_tools": bool(self.pro_tools),
                "keep_source_audio": bool(self.keep_audio_chk.isChecked()) if hasattr(self, "keep_audio_chk") else bool(self.keep_source_audio),
                "pro_scanlines": bool(self.pro_scanlines_chk.isChecked()) if hasattr(self, "pro_scanlines_chk") else bool(self.pro_scanlines),
                "pro_bloom": int(getattr(self, "pro_bloom", 0)),
                "pro_vignette": int(getattr(self, "pro_vignette", 0)),
                "pro_poster_bits": int(getattr(self, "pro_poster_bits", 0)),
                "pro_grain": int(getattr(self, "pro_grain", 0)),
                "pro_chroma": int(getattr(self, "pro_chroma", 0)),
                "pro_scan_strength": int(getattr(self, "pro_scan_strength", 28)),
                "pro_scan_step": int(getattr(self, "pro_scan_step", 3)),
                "pro_curvature": int(getattr(self, "pro_curvature", 0)),
                "pro_concavity": int(getattr(self, "pro_concavity", 0)),
                "pro_curvature_center_x": int(getattr(self, "pro_curvature_center_x", 0)),
                "pro_curvature_expand": int(getattr(self, "pro_curvature_expand", 0)),
                "pro_curvature_type": str(getattr(self, "pro_curvature_type", "spherical") or "spherical"),
                "pro_ribbing": int(getattr(self, "pro_ribbing", 0)),
                "pro_clarity": int(getattr(self, "pro_clarity", 0)),
                "pro_motion_blur": int(getattr(self, "pro_motion_blur", 0)),
                "pro_color_boost": int(getattr(self, "pro_color_boost", 0)),
                "pro_glitch": int(getattr(self, "pro_glitch", 0)),
                "pro_glitch_density": int(getattr(self, "pro_glitch_density", 35)),
                "pro_glitch_shift": int(getattr(self, "pro_glitch_shift", 42)),
                "pro_glitch_rgb": int(getattr(self, "pro_glitch_rgb", 1)),
                "pro_glitch_block": int(getattr(self, "pro_glitch_block", 10)),
                "pro_glitch_jitter": int(getattr(self, "pro_glitch_jitter", 1)),
                "pro_glitch_noise": int(getattr(self, "pro_glitch_noise", 12)),
                "live_preview": bool(getattr(self, "live_preview", False)),
                "update_feed_url": str(getattr(self, "update_feed_url", DEFAULT_UPDATE_FEED_URL) or DEFAULT_UPDATE_FEED_URL),
                "auto_check_updates": bool(getattr(self, "auto_check_updates", True)),
                "last_update_check": float(getattr(self, "last_update_check", 0) or 0),
                "last_known_version": str(getattr(self, "last_known_version", "") or ""),
                "project_file_path": str(getattr(self, "_project_file_path", "") or ""),
            })
            save_settings(s)
        except Exception:
            pass
        try:
            self._stop_preview_media()
        except Exception:
            pass
        try:
            cap = getattr(self, "_custom_bg_video_cap", None)
            if cap is not None:
                cap.release()
                self._custom_bg_video_cap = None
        except Exception:
            pass
        return super().closeEvent(ev)

    def eventFilter(self, obj, ev):
        try:
            if obj in getattr(self, "_undo_widgets", set()):
                et = ev.type()
                if et in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.KeyPress):
                    now = time.time()
                    if now - float(getattr(self, "_undo_event_ts", 0.0)) > 0.18:
                        self._undo_event_ts = now
                        self._push_undo_state()
            if obj is getattr(self, "player_seek_slider", None):
                et = ev.type()
                if et == QEvent.Type.Leave:
                    self._hide_timeline_hover()
                elif et == QEvent.Type.MouseMove:
                    if self._preview_mode == "video" and getattr(self, "current_path", None):
                        now = time.time()
                        if now - self._timeline_hover_last > 0.06:
                            self._timeline_hover_last = now
                            try:
                                x = float(ev.position().x())
                            except Exception:
                                x = float(ev.pos().x())
                            w = max(1.0, float(self.player_seek_slider.width()))
                            self._show_timeline_hover(max(0.0, min(1.0, x / w)))
                    else:
                        self._hide_timeline_hover()
            if obj is getattr(self, "update_status_label", None):
                if ev.type() == QEvent.Type.MouseButtonPress:
                    now = time.time()
                    if now - float(getattr(self, "_version_click_ts", 0.0)) > 2.0:
                        self._version_click_count = 0
                    self._version_click_ts = now
                    self._version_click_count = int(getattr(self, "_version_click_count", 0)) + 1
                    if self._version_click_count >= 5:
                        self._version_click_count = 0
                        self._show_notice("Easter", "я в твоей голове")
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, ev)

# -------------- Fullscreen viewer ------------
class FullscreenViewer(QDialog):
    def __init__(self, parent, pil_img):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        # show frameless but still allow close button
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setWindowState(self.windowState() | Qt.WindowFullScreen)
        self.pil = pil_img
        self.zoom = 1.0
        self.pan = [0,0]
        self.last_pos = None
        # label fills the dialog; we'll manage geometry explicitly so we can pan
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setScaledContents(True)
        self.close_btn = QPushButton("X", self)
        self.close_btn.setFixedSize(64,64)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("background: rgba(30,30,30,0.8); color: white; border-radius:18px; font-size:20px;")
        self.label.installEventFilter(self)
        self._render()
        # ensure dialog covers screen area and button is visible
        self.setModal(True)
        self.close_btn.raise_()

    def _render(self):
        # render current image with zoom and apply pan
        try:
            w = max(1, int(self.pil.width * self.zoom))
            h = max(1, int(self.pil.height * self.zoom))
            # limit rendered size to screen to avoid heavy scaling
            maxw, maxh = self.width() or 1920, self.height() or 1080
            if w > maxw or h > maxh:
                scale = min(maxw / max(1,w), maxh / max(1,h))
                w = max(1, int(w * scale)); h = max(1, int(h * scale))
            img = self.pil.resize((w, h), Image.Resampling.LANCZOS)
            q = pil_to_qpixmap(img)
            self.label.setPixmap(q)
            # size of label equals image size, position it centered + pan
            self.label.resize(q.width(), q.height())
            cx = max(0, (self.width() - q.width()) // 2 + int(self.pan[0]))
            cy = max(0, (self.height() - q.height()) // 2 + int(self.pan[1]))
            self.label.move(cx, cy)
            # ensure close button visible in corner
            self.close_btn.move(self.width()-90, 30)
            self.close_btn.raise_()
        except Exception:
            pass

    def resizeEvent(self, ev):
        # re-render to reposition image on resize
        try:
            self._render()
            self.close_btn.move(self.width()-90, 30)
        except Exception:
            pass
        return super().resizeEvent(ev)
    def showEvent(self, ev):
        # ensure modal and update geometry
        try:
            self.setGeometry(self.parent().geometry())
            self._render()
        except Exception:
            pass
        return super().showEvent(ev)
    def eventFilter(self, obj, ev):
        # Use QEvent types from Qt for comparison and guard attribute access
        try:
            etype = ev.type()
        except Exception:
            return False
        return super().eventFilter(obj, ev)

    def wheelEvent(self, ev):
        try:
            # forward to same zoom logic as in eventFilter
            try:
                delta = ev.angleDelta().y()
            except Exception:
                try:
                    delta = ev.delta()
                except Exception:
                    delta = 0
            if delta != 0:
                factor = 1.12 if delta > 0 else 1/1.12
                self.zoom *= factor
                self.pan[0] = int(self.pan[0] * factor)
                self.pan[1] = int(self.pan[1] * factor)
                self._render()
        except Exception:
            pass

    def keyPressEvent(self, ev):
        try:
            k = ev.key()
            # + / - zoom keys
            if k == Qt.Key_Plus or k == Qt.Key_Equal:
                self.zoom *= 1.12; self._render(); return
            if k == Qt.Key_Minus or k == Qt.Key_Underscore:
                self.zoom /= 1.12; self._render(); return
            if k == Qt.Key_Escape:
                self.close(); return
        except Exception:
            pass
        return super().keyPressEvent(ev)

    def mousePressEvent(self, ev):
        try:
            # store local position for panning
            try:
                gp = ev.globalPosition()
            except Exception:
                gp = ev.globalPos()
            self.last_pos = gp
        except Exception:
            pass
        return super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        try:
            if self.last_pos is None:
                return super().mouseMoveEvent(ev)
            try:
                gp = ev.globalPosition()
            except Exception:
                gp = ev.globalPos()
            dx = gp.x() - self.last_pos.x(); dy = gp.y() - self.last_pos.y()
            self.pan[0] += dx; self.pan[1] += dy
            self.last_pos = gp
            self._render()
        except Exception:
            pass
        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        try:
            self.last_pos = None
        except Exception:
            pass
        return super().mouseReleaseEvent(ev)

        if etype == QEvent.Type.Wheel:
            # wheel event: adjust zoom
            try:
                delta = ev.angleDelta().y()
            except Exception:
                try:
                    delta = ev.delta()
                except Exception:
                    delta = 0
            if delta != 0:
                factor = 1.12 if delta > 0 else 1/1.12
                # center zoom around current view; simple approach keeps pan proportional
                self.zoom *= factor
                # scale pan so image stays roughly under cursor (approx)
                self.pan[0] = int(self.pan[0] * factor)
                self.pan[1] = int(self.pan[1] * factor)
                self._render()
            return True

        if etype == QEvent.Type.MouseButtonPress:
            # store global position for panning
            try:
                gp = ev.globalPosition()
            except Exception:
                try:
                    gp = ev.globalPos()
                except Exception:
                    gp = None
            self.last_pos = gp
            return True

        if etype == QEvent.Type.MouseMove and self.last_pos is not None:
            try:
                try:
                    gp = ev.globalPosition()
                except Exception:
                    gp = ev.globalPos()
                dx = gp.x() - self.last_pos.x()
                dy = gp.y() - self.last_pos.y()
                self.pan[0] += dx; self.pan[1] += dy
                self.last_pos = gp
                self._render()
            except Exception:
                pass
            return True

        if etype == QEvent.Type.MouseButtonRelease:
            self.last_pos = None
            return True
        return super().eventFilter(obj, ev)

# --------------- run ---------------
def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SNERK503.ASCIIStudio")
    except Exception:
        pass
    argv = list(sys.argv)
    force_welcome = False
    try:
        if "--show-welcome" in argv:
            force_welcome = True
            argv = [a for a in argv if a != "--show-welcome"]
    except Exception:
        pass
    app = QApplication(argv)
    try:
        icon_path = _pick_resource_path(
            "QWE1R.ico", "QWE1R.png",
            "QWER.ico", "QWER.png",
            "iconASCII.ico", "iconASCII.png",
            "icons/QWE1R.ico", "icons/QWE1R.png",
            "icons/QWER.ico", "icons/QWER.png",
            "icons/iconASCII.ico", "icons/iconASCII.png"
        )
        if icon_path is not None:
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass
    win = MainWindow(force_welcome=force_welcome)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
