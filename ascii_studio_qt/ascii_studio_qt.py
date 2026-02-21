# ascii_studio_qt.py
# Ultra ASCII Studio — PySide6 version
# Features: iPhone-glass-like UI, animated blurred background, smoke trail, localization (en/ru/zh), settings (CPU/GPU), preview, gallery, image/video render
#
# Dependencies:
# pip install PySide6 pillow numpy opencv-python imageio imageio-ffmpeg

import sys, os, threading, time, math
from functools import partial
from pathlib import Path
from collections import deque

from PySide6.QtCore import Qt, QSize, QRect, QTimer, QPoint, QThread, Signal, Slot, QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QIcon, QRadialGradient, QBrush, QCursor, QMovie
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox, QFileDialog,
    QColorDialog, QSlider, QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QListWidget,
    QListWidgetItem, QProgressBar, QDialog, QFormLayout, QSpinBox, QCheckBox
)

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import numpy as np
import cv2
import imageio
import tempfile

# import new modules
from mini_player import MiniPlayer
from settings_store import load_settings, save_settings
from core_utils import pil_to_qpixmap, image_to_ascii_data, render_ascii_pil, DEFAULT_ASCII
from core_utils import WATERMARK as CORE_WATERMARK
from render_worker import RenderWorker
from export_progress import ExportProgressDialog


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
        "charset": "Charset", "contrast": "Contrast (%)", "invert": "Invert", "keep_size": "Keep original output size"
        ,"batch":"Batch","palette":"Palette","dither":"Dither","pro_tools":"Pro Tools","enable_pro_tools":"Enable Pro Tools","theme":"Theme"
    },
    "ru": {
        "app": "ASCII Studio", "load": "Загрузить", "render": "Рендер", "export": "Экспорт",
        "settings": "Настройки", "device": "Устройство рендера", "cpu": "CPU", "gpu": "GPU (если доступен)",
        "file": "Файл", "language": "Язык",
        "style": "Стиль", "width": "Ширина (симв.)", "font": "Размер шрифта",
        "text_color": "Цвет текста", "bg_color": "Цвет фона", "gallery": "Галерея",
        "trail": "Интенсивность хвоста", "off": "Выкл", "low": "Низкий", "med": "Средний", "high": "Высокий",
        "watermark": "Водяной знак", "author": "Автор", "ok": "OK", "cancel": "Отмена",
        "charset": "Набор символов", "contrast": "Контраст (%)", "invert": "Инвертировать", "keep_size": "Сохранять оригинальный размер"
        ,"batch":"Пакетно","palette":"Палитра","dither":"Растеризация","pro_tools":"Проф. инструменты","enable_pro_tools":"Включить Pro Tools","theme":"Тема"
    },
    "zh": {
        "app": "ASCII Studio", "load": "加载", "render": "渲染", "export": "导出",
        "settings": "设置", "device": "渲染设备", "cpu": "CPU", "gpu": "GPU（如果可用）",
        "file": "文件", "language": "语言",
        "style": "样式", "width": "宽度（字符）", "font": "字体大小",
        "text_color": "文字颜色", "bg_color": "背景颜色", "gallery": "画廊",
        "trail": "尾迹强度", "off": "关闭", "low": "低", "med": "中", "high": "高",
        "watermark": "水印", "author": "作者", "ok": "确定", "cancel": "取消",
        "charset": "字符集", "contrast": "对比度 (%)", "invert": "反转", "keep_size": "保持原始输出大小"
        ,"batch":"批处理","palette":"调色板","dither":"抖动","pro_tools":"专业工具","enable_pro_tools":"启用专业工具","theme":"主题"
    }
}

# -------------------- Main Window --------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCII Studio – SNERK503")
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
        self.render_device = s.get("render_device", self.device_choice)
        self.render_threads = s.get("render_threads", 4)
        self.render_codec = s.get("render_codec", "libx264")
        self.render_bitrate = s.get("render_bitrate", "2M")
        self.ascii_chars = s.get("ascii_chars", DEFAULT_ASCII)
        self.contrast = s.get("contrast", 100)
        self.invert = s.get("invert", False)
        self.keep_size = s.get("keep_size", False)

        self.trail = deque(maxlen=160)
        self.bg_t = 0.0
        self.render_worker = None
        self.current_output = None
        self.current_path = None
        self._suppress_trail = False
        self._build_ui()
        self._apply_translations()
        self._start_background_animation()
        # precompute circle pixmaps cache for faster drawing
        self._circle_cache = {}
        # sample cursor position even when not moving via timer to ensure continuous trail
        self.cursor_sample_timer = QTimer(self); self.cursor_sample_timer.timeout.connect(self._sample_cursor)
        self.cursor_sample_timer.start(16)
        self.bg_anim_timer = QTimer(self); self.bg_anim_timer.timeout.connect(self._update_background)
        self.trail_timer = QTimer(self); self.trail_timer.timeout.connect(self._update_trail_overlay)
        # start animation timers
        try:
            self.bg_anim_timer.start(160)
            self.trail_timer.start(33)
        except Exception:
            pass
        # set pick buttons enabled state depending on style
        self._update_color_buttons_state()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        tr = TRANSLATIONS.get(self.lang, TRANSLATIONS['en'])
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
        # gallery on the left (larger)
        self.gallery_list = QListWidget()
        self.gallery_list.setFixedWidth(220)
        self.gallery_list.setViewMode(QListWidget.IconMode)
        self.gallery_list.setIconSize(QSize(180,180))
        self.gallery_list.setResizeMode(QListWidget.Adjust)
        self.gallery_list.setMovement(QListWidget.Static)
        self.gallery_list.setFlow(QListWidget.TopToBottom)
        self.gallery_list.setSpacing(8)
        self.gallery_list.setWrapping(False)
        try:
            self.gallery_list.itemClicked.connect(self.on_gallery_click)
            self.gallery_list.itemDoubleClicked.connect(self.on_gallery_double_click)
        except Exception:
            pass
        root.addWidget(self.gallery_list, 0)

        left_frame = QFrame(); left_frame.setObjectName("left_frame"); left_frame.setStyleSheet("QFrame#left_frame { border-radius: 14px; }")
        left_frame.setMouseTracking(True)
        left_layout = QVBoxLayout(left_frame); left_layout.setContentsMargins(12,12,12,12)
        self.preview_label = QLabel(alignment=Qt.AlignCenter); self.preview_label.setStyleSheet("background: transparent;")
        self.preview_label.setMouseTracking(True)
        # overlay on top of preview to draw cursor highlight / spotlight to improve readability
        self.preview_overlay = QLabel(self.preview_label)
        self.preview_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.preview_overlay.setStyleSheet("background: transparent;")
        try:
            self.preview_overlay.resize(self.preview_label.size())
            self.preview_overlay.hide()
        except Exception:
            pass
        left_layout.addWidget(self.preview_label, 1)
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
        right_frame = QFrame(); right_frame.setFixedWidth(380); right_frame.setObjectName("right_frame")
        right_frame.setMouseTracking(True)
        # inner translucent content frame so controls appear on a glass surface
        self.right_content = QFrame(right_frame)
        self.right_content.setObjectName("right_content")
        self.right_content.setStyleSheet("background: rgba(20,20,20,0.25); border-radius:10px;")
        self.right_content.setGeometry(6,6, right_frame.width()-12, right_frame.height()-12)
        right_layout = QVBoxLayout(right_frame); right_layout.setContentsMargins(12,12,12,12); right_layout.setSpacing(8)
        self.title_label = QLabel(tr.get("app", "ASCII Studio"))
        self.title_label.setStyleSheet("font-weight:700; font-size:16px")
        right_layout.addWidget(self.title_label)
        row = QHBoxLayout(); self.load_btn = QPushButton("Load"); self.load_btn.clicked.connect(self.on_load)
        self.render_btn = QPushButton("Render"); self.render_btn.clicked.connect(self.on_render)
        self.export_btn = QPushButton("Export"); self.export_btn.clicked.connect(self.on_export)
        for b in (self.load_btn, self.render_btn, self.export_btn): b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(38); b.setStyleSheet(self._glass_btn_css())
        # set simple geometric icons
        try:
            def make_icon(color, shape='rect'):
                pm = QPixmap(20,20); pm.fill(Qt.transparent)
                p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
                p.setBrush(QColor(color)); p.setPen(Qt.NoPen)
                if shape == 'rect': p.drawRect(2,2,16,16)
                elif shape == 'tri': p.drawPolygon(QPoint(4,16), QPoint(16,10), QPoint(4,4))
                elif shape == 'circle': p.drawEllipse(2,2,16,16)
                p.end(); return QIcon(pm)
            self.load_btn.setIcon(make_icon('#88c0ff','rect'))
            self.render_btn.setIcon(make_icon('#a3be8c','tri'))
            self.export_btn.setIcon(make_icon('#ebcb8b','circle'))
        except Exception:
            pass
        row.addWidget(self.load_btn); row.addWidget(self.render_btn); row.addWidget(self.export_btn)
        right_layout.addLayout(row)
        right_layout.addSpacing(4)
        self.style_label = QLabel(tr.get("style", "Style"))
        right_layout.addWidget(self.style_label)
        self.style_combo = QComboBox(); self.style_combo.addItems(["bw","red","color","matrix","matrix2","neon","pastel","custom"])
        self.style_combo.setCurrentText(self.style); self.style_combo.currentTextChanged.connect(self.on_style_changed)
        right_layout.addWidget(self.style_combo)
        self.width_label = QLabel(tr.get("width", "Width (chars)"))
        right_layout.addWidget(self.width_label)
        wrow = QHBoxLayout(); self.width_slider = QSlider(Qt.Horizontal); self.width_slider.setMinimum(16); self.width_slider.setMaximum(900)
        self.width_slider.setValue(self.width_chars); self.width_slider.valueChanged.connect(self.on_width_changed)
        self.width_val_label = QLabel(str(self.width_chars)); wrow.addWidget(self.width_slider); wrow.addWidget(self.width_val_label); right_layout.addLayout(wrow)
        self.font_label = QLabel(tr.get("font", "Font size"))
        right_layout.addWidget(self.font_label)
        frow = QHBoxLayout(); self.font_slider = QSlider(Qt.Horizontal); self.font_slider.setRange(6, 48); self.font_slider.setValue(self.font_size)
        self.font_slider.valueChanged.connect(self.on_font_changed); self.font_val_label = QLabel(str(self.font_size)); frow.addWidget(self.font_slider); frow.addWidget(self.font_val_label); right_layout.addLayout(frow)
        # charset and controls
        crow = QHBoxLayout(); self.charset_input = QComboBox(); self.charset_input.setEditable(True); self.charset_input.addItem(self.ascii_chars)
        self.charset_input.setFixedHeight(28); crow.addWidget(self.charset_input)
        right_layout.addLayout(crow)
        # contrast and invert
        contr_row = QHBoxLayout(); self.contrast_slider = QSlider(Qt.Horizontal); self.contrast_slider.setRange(20,200); self.contrast_slider.setValue(self.contrast)
        self.contrast_slider.valueChanged.connect(lambda v: setattr(self, 'contrast', v)); contr_row.addWidget(self.contrast_slider); contr_row.addWidget(QLabel(str(self.contrast)))
        right_layout.addLayout(contr_row)
        inv_row = QHBoxLayout(); self.invert_chk = QCheckBox(tr.get('invert','Invert')); self.invert_chk.setChecked(self.invert); inv_row.addWidget(self.invert_chk)
        self.keep_size_chk = QCheckBox(tr.get('keep_size','Keep original output size')); self.keep_size_chk.setChecked(self.keep_size); inv_row.addWidget(self.keep_size_chk)
        right_layout.addLayout(inv_row)
        # keep internal state in sync when user toggles
        try:
            self.invert_chk.stateChanged.connect(lambda s: setattr(self, 'invert', bool(s)))
        except Exception:
            pass
        crow = QHBoxLayout(); self.pick_text_btn = QPushButton(tr.get("text_color", "Text color")); self.pick_text_btn.clicked.connect(self.on_pick_text)
        self.pick_bg_btn = QPushButton(tr.get("bg_color", "BG color")); self.pick_bg_btn.clicked.connect(self.on_pick_bg)
        for b in (self.pick_text_btn, self.pick_bg_btn): b.setStyleSheet(self._glass_btn_css()); b.setCursor(Qt.PointingHandCursor)
        crow.addWidget(self.pick_text_btn); crow.addWidget(self.pick_bg_btn); right_layout.addLayout(crow)
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
        self.theme_combo = QComboBox(); self.theme_combo.addItems(["dark","light","solarized","midnight"])
        self.theme_combo.setCurrentText("dark")
        right_layout.addWidget(QLabel("Theme"))
        right_layout.addWidget(self.theme_combo)

        # connect theme changes to apply style
        try:
            self.theme_combo.currentTextChanged.connect(self._apply_theme)
        except Exception:
            pass

        # device selection moved to settings dialog
        self.watermark_chk = QCheckBox(tr.get('watermark','Watermark')); self.watermark_chk.setChecked(self.show_watermark); right_layout.addWidget(self.watermark_chk)
        self.settings_btn = QPushButton(tr.get("settings", "Settings..."))
        # add a simple icon to settings
        try:
            self.settings_btn.setIcon(make_icon('#c087ff','rect'))
        except Exception:
            pass
        self.settings_btn.setStyleSheet(self._glass_btn_css()); self.settings_btn.clicked.connect(self.open_settings_dialog); right_layout.addWidget(self.settings_btn)
        self.gallery_label = QLabel(tr.get("gallery", "Gallery:"))
        right_layout.addWidget(self.gallery_label)
        # right side small gallery (kept for compatibility) hidden since left gallery is primary
        self.right_gallery = QListWidget(); self.right_gallery.setFixedHeight(140); self.right_gallery.hide(); right_layout.addWidget(self.right_gallery)
        # Pro tools frame: hidden unless enabled in settings
        self.pro_tools_frame = QFrame()
        self.pro_tools_frame.setObjectName('pro_tools_frame')
        pfl = QHBoxLayout(self.pro_tools_frame); pfl.setContentsMargins(0,0,0,0)
        try:
            batch_btn = QPushButton(tr.get('batch','Batch'))
            pal_btn = QPushButton(tr.get('palette','Palette'))
            dither_btn = QPushButton(tr.get('dither','Dither'))
            # connect simple stubs for pro tools
            def _on_batch():
                # placeholder: open file dialog to batch process
                fn, _ = QFileDialog.getOpenFileName(self, tr.get('batch','Batch'), os.getcwd(), "Images (*.png *.jpg *.jpeg *.bmp)")
                if not fn: return
            for b,name in ((batch_btn,'batch'),(pal_btn,'palette'),(dither_btn,'dither')):
                try:
                    b.setIcon(make_icon('#88c0ff','circle'))
                except Exception:
                    pass
                b.setStyleSheet(self._glass_btn_css()); b.setCursor(Qt.PointingHandCursor)
                pfl.addWidget(b)
            # store for translation updates
            self._pro_tool_buttons = {'batch': batch_btn, 'palette': pal_btn, 'dither': dither_btn}
        except Exception:
            pass
        self.pro_tools_frame.setVisible(bool(self.pro_tools))
        right_layout.addWidget(self.pro_tools_frame)
        # gallery appearance
        try:
            self.gallery_list.setViewMode(QListWidget.IconMode)
            self.gallery_list.setIconSize(QSize(140,140))
            self.gallery_list.setFixedHeight(220)
            self.gallery_list.setIconSize(QSize(180,180))
            self.gallery_list.setResizeMode(QListWidget.Adjust)
            self.gallery_list.setMovement(QListWidget.Static)
            self.gallery_list.setFlow(QListWidget.LeftToRight)
            self.gallery_list.setSpacing(8)
            self.gallery_list.setWrapping(True)
            self.gallery_list.setUniformItemSizes(True)
            self.gallery_list.itemSelectionChanged.connect(self._on_gallery_select)
            self.gallery_list.itemDoubleClicked.connect(self.on_gallery_double_click)
        except Exception:
            pass
        root.addWidget(right_frame, 0)
        self._apply_window_style()
        self.preview_label.mousePressEvent = self._preview_clicked
        # overlay label for trail (transparent pixmap painted each frame)
        self.trail_overlay = QLabel(central)
        self.trail_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.trail_overlay.setStyleSheet("background: transparent;")
        # ensure overlay covers central area and sits above the static background but under UI panels
        try:
            self.trail_overlay.setGeometry(0, 0, self.width(), self.height())
            self.trail_overlay.raise_()
            self.trail_overlay.stackUnder(left_frame)
            self.trail_overlay.stackUnder(right_frame)
        except Exception:
            pass

    def _on_gallery_select(self):
        items = self.gallery_list.selectedItems()
        if not items: return
        item = items[0]
        data = item.data(Qt.UserRole)
        if not data: return
        pil = data.get('pil')
        if pil:
            self._show_preview_pil(pil)

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
                self.left_bg_label.setGeometry(lx, ly, lwid, lht); self.left_bg_label.lower()
            if right_img:
                self.right_bg_label.setPixmap(pil_to_qpixmap(right_img).scaled(rwid, rht, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                self.right_bg_label.setGeometry(rx, ry, rwid, rht); self.right_bg_label.lower()
        except Exception:
            pass
        # function finished

    def _glass_btn_css(self):
        return ("QPushButton{ background: rgba(20,20,20,0.55); color: white; border-radius:8px; padding:6px 10px; }"
                "QPushButton:hover{ background: rgba(130,130,130,0.12); }")

    def _apply_window_style(self):
        self.setStyleSheet("""
            QMainWindow { background: transparent; }
            QLabel { color: #e6eef6; }
            QFrame#left_frame { background: rgba(255,255,255,0.04); border-radius:14px; }
            QFrame#right_frame { background: rgba(255,255,255,0.06); border-radius:14px; padding:8px; }
            QListWidget { background: rgba(255,255,255,0.03); border-radius:8px; color: #dfe8f2; }
        """)
        # timers are started after UI build where timers are created

    def _apply_theme(self, name):
        try:
            if name == 'light':
                self.setStyleSheet("QLabel { color: #101010; } QFrame#left_frame { background: rgba(255,255,255,0.9); } QFrame#right_frame { background: rgba(250,250,250,0.95); }")
            elif name == 'solarized':
                self.setStyleSheet("QLabel { color: #fdf6e3; } QFrame#left_frame { background: #073642; } QFrame#right_frame { background: #002b36; }")
            elif name == 'midnight':
                self.setStyleSheet("QLabel { color: #e6eef6; } QFrame#left_frame { background: rgba(8,10,20,0.9); } QFrame#right_frame { background: rgba(12,14,26,0.95); }")
            else:
                self._apply_window_style()
        except Exception:
            pass

    def _apply_translations(self):
        t = TRANSLATIONS[self.lang]
        try:
            self.load_btn.setText(t["load"])
            self.render_btn.setText(t["render"])
            self.export_btn.setText(t["export"])
            self.pick_text_btn.setText(t["text_color"])
            self.pick_bg_btn.setText(t["bg_color"])
        except Exception:
            pass
        # update other labels
        try:
            self.style_label.setText(t.get("style", self.style_label.text()))
            self.width_label.setText(t.get("width", self.width_label.text()))
            self.font_label.setText(t.get("font", self.font_label.text()))
            self.trail_label.setText(t.get("trail", self.trail_label.text()))
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
            self.settings_btn.setText(t.get("settings", self.settings_btn.text()))
            self.gallery_label.setText(t.get("gallery", self.gallery_label.text()))
            # update trail combo labels and selection
            current_key = self.trail_level
            self.trail_combo.blockSignals(True)
            self.trail_combo.clear()
            self.trail_combo.addItems([t["off"], t["low"], t["med"], t["high"]])
            map_key = {"off": t["off"], "low": t["low"], "med": t["med"], "high": t["high"]}
            self.trail_combo.setCurrentText(map_key.get(current_key, t["med"]))
            self.trail_combo.blockSignals(False)
        except Exception:
            pass
        # update menu texts if built
        try:
            if hasattr(self, 'file_menu'):
                self.file_menu.setTitle(TRANSLATIONS[self.lang].get("settings", "File"))
                self.action_load.setText(TRANSLATIONS[self.lang].get("load", "Load"))
                self.action_export.setText(TRANSLATIONS[self.lang].get("export", "Export"))
                self.action_settings.setText(TRANSLATIONS[self.lang].get("settings", "Settings"))
                # update gallery label
                try:
                    self.gallery_label.setText(TRANSLATIONS[self.lang].get('gallery','Gallery:'))
                except Exception:
                    pass
        except Exception:
            pass

    def _start_background_animation(self):
        w = max(1200, self.width()); h = max(800, self.height())
        self.bg_base = Image.new("RGB", (w,h), "#0e1117")
        self._update_background()
    def resizeEvent(self, ev):
        # ensure overlay covers whole window and panel backgrounds update on resize
        try:
            if hasattr(self, 'trail_overlay') and self.trail_overlay is not None:
                self.trail_overlay.setGeometry(0, 0, self.width(), self.height())
            # ensure bg label covers central area
            try:
                cw = self.centralWidget()
                if hasattr(self, 'window_bg_label') and self.window_bg_label is not None and cw is not None:
                    self.window_bg_label.setGeometry(cw.rect())
            except Exception:
                pass
            # update panel crops less often but keep them consistent
            self._update_panel_backgrounds()
        except Exception:
            pass
        return super().resizeEvent(ev)

    def _update_background(self):
        w = max(600, self.width()); h = max(400, self.height())
        self.bg_t += 0.03
        sw, sh = max(200, w//3), max(120, h//3)
        im = Image.new("RGB", (sw, sh), "#0b0d10")
        draw = ImageDraw.Draw(im)
        for y in range(sh):
            a = y / max(1, sh-1)
            r = int(10*(1-a) + 24*a); g = int(12*(1-a) + 30*a); b = int(20*(1-a) + 40*a)
            draw.line([(0,y),(sw,y)], fill=(r,g,b))
        colors = [(60, 160, 255), (120, 60, 220), (30,200,120)]
        for i,c in enumerate(colors):
            cx = int((math.sin(self.bg_t*0.6 + i*1.2)+1)/2 * sw)
            cy = int((math.cos(self.bg_t*0.55 + i*0.9)+1)/2 * sh)
            rad = int(min(sw,sh) * (0.25 + 0.08*i))
            blob = Image.new("RGBA", (sw,sh), (0,0,0,0))
            bd = ImageDraw.Draw(blob)
            bd.ellipse([cx-rad, cy-rad, cx+rad, cy+rad], fill=(c[0],c[1],c[2],100))
            blob = blob.filter(ImageFilter.GaussianBlur(radius=rad//2))
            im = Image.alpha_composite(im.convert("RGBA"), blob).convert("RGB")
        im = im.resize((w,h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(radius=8))
        self.bg_qpix = pil_to_qpixmap(im)
        pix = self.bg_qpix.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        # set as window background label pixmap so trail can be composed onto it
        try:
            self.window_bg_label.setPixmap(pix)
            self.window_bg_label.setGeometry(0,0,self.centralWidget().width(), self.centralWidget().height())
            self.window_bg_label.lower()
            # ensure behind panels
            lf = self.findChild(QFrame, "left_frame")
            rf = self.findChild(QFrame, "right_frame")
            if lf: self.window_bg_label.stackUnder(lf)
            if rf: self.window_bg_label.stackUnder(rf)
        except Exception:
            # fallback to palette
            self.setAutoFillBackground(True)
            palette = self.palette(); palette.setBrush(self.backgroundRole(), pix); self.setPalette(palette)
        self.bg_base = im
        # update background pixmaps for panel crops
        try:
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
            self.trail.append((lx, ly, time.time()))
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
            gp = QCursor.pos()
            local = self.mapFromGlobal(gp)
            x = int(local.x()); y = int(local.y())
            if 0 <= x <= self.width() and 0 <= y <= self.height():
                # Only append when position changed significantly; this preserves the
                # last movement timestamp when cursor is stationary so the trail can fade out.
                if len(self.trail) > 0:
                    lx, ly, _ = self.trail[-1]
                    if abs(lx - x) < 2 and abs(ly - y) < 2:
                        return
                self.trail.append((x, y, time.time()))
        except Exception:
            pass

    def _update_trail_overlay(self):
        # Draw trail into a transparent overlay; always render so smoke shows under translucent panels
        if self.trail_level == "off":
            try:
                self.trail_overlay.clear()
            except Exception:
                pass
            return
        # Note: trail is always rendered; preview spotlight only improves readability but
        # does not suppress the trail entirely.
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        now = time.time()
        pts = list(self.trail)
        # if cursor stationary -> clear tail
        if len(pts) >= 8:
            xs = [p[0] for p in pts[-8:]]; ys = [p[1] for p in pts[-8:]]
            if max(xs)-min(xs) < 4 and max(ys)-min(ys) < 4 and (now - pts[-1][2]) > 0.6:
                self.trail.clear()
                try: self.trail_overlay.clear()
                except Exception: pass
                return
        overlay = QPixmap(size.width(), size.height())
        overlay.fill(Qt.transparent)
        painter = QPainter(overlay)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            pts_to_draw = pts[-120:] if len(pts) > 120 else pts
            for i, (x,y,tval) in enumerate(pts_to_draw):
                age = now - tval
                if age > 2.8: continue
                rel = max(0.0, 1.0 - age/2.8)
                idx_rel = (i+1) / max(1, len(pts_to_draw))
                if self.trail_level == 'high': base_r = 80
                elif self.trail_level == 'med': base_r = 48
                else: base_r = 28
                r = int(2 + rel * base_r * (0.4 + 0.6*idx_rel))
                alpha = int(180 * (0.3 + 0.7*rel) * idx_rel)
                key = (r, alpha)
                if key in self._circle_cache:
                    cpx = self._circle_cache[key]
                else:
                    cpx = QPixmap(r*2, r*2)
                    cpx.fill(Qt.transparent)
                    cp = QPainter(cpx)
                    grad = QRadialGradient(r, r, r)
                    # smoky gradient: soft white center, cool mid, transparent edge
                    grad.setColorAt(0.0, QColor(240,240,240, max(8, int(alpha*0.45))))
                    grad.setColorAt(0.45, QColor(180,200,220, max(6, int(alpha*0.30))))
                    grad.setColorAt(1.0, QColor(0,0,0,0))
                    cp.setBrush(QBrush(grad)); cp.setPen(Qt.NoPen)
                    cp.drawEllipse(0,0,r*2,r*2)
                    cp.end()
                    self._circle_cache[key] = cpx
                # draw primary spot
                painter.drawPixmap(int(x-r), int(y-r), cpx)
                # draw a softer larger halo for smoke feel
                halo_r = int(r * 1.8)
                halo_alpha = max(6, int(alpha*0.28))
                hkey = (halo_r, halo_alpha)
                if hkey in self._circle_cache:
                    hpx = self._circle_cache[hkey]
                else:
                    hpx = QPixmap(halo_r*2, halo_r*2)
                    hpx.fill(Qt.transparent)
                    hcp = QPainter(hpx)
                    hgrad = QRadialGradient(halo_r, halo_r, halo_r)
                    hgrad.setColorAt(0.0, QColor(220,220,220, int(halo_alpha)))
                    hgrad.setColorAt(1.0, QColor(0,0,0,0))
                    hcp.setBrush(QBrush(hgrad)); hcp.setPen(Qt.NoPen)
                    hcp.drawEllipse(0,0,halo_r*2,halo_r*2)
                    hcp.end()
                    self._circle_cache[hkey] = hpx
                painter.drawPixmap(int(x-halo_r), int(y-halo_r), hpx)
                # interpolate to next point to avoid gaps
                if i+1 < len(pts_to_draw):
                    nx, ny, _ = pts_to_draw[i+1]
                    dx = nx - x; dy = ny - y
                    dist = math.hypot(dx, dy)
                    steps = int(min(5, max(0, dist//10)))
                    for s in range(1, steps+1):
                        fx = x + dx * (s/ (steps+1))
                        fy = y + dy * (s/ (steps+1))
                        painter.drawPixmap(int(fx-r), int(fy-r), cpx)
        finally:
            painter.end()
        try:
            self.trail_overlay.setPixmap(overlay)
            self.trail_overlay.setGeometry(0,0,self.width(), self.height())
            # keep overlay under panels so it appears part of background; panels are translucent so trail shows through
            # ensure it's above background but below panels
            self.trail_overlay.raise_()
            lf = self.findChild(QFrame, "left_frame")
            rf = self.findChild(QFrame, "right_frame")
            if lf: self.trail_overlay.stackUnder(lf)
            if rf: self.trail_overlay.stackUnder(rf)
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
        except Exception:
            pass

    def on_load(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Select media", os.getcwd(),
                                            "Images & Videos (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.avi)")
        if not fn: return
        self.current_path = fn
        try:
            low = fn.lower()
            if low.endswith((".mp4", ".avi", ".mov", ".mkv")):
                # video: capture first frame as thumbnail, store path in gallery
                cap = cv2.VideoCapture(fn); ret, frame = cap.read(); cap.release()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(frame)
                    self._show_preview_pil(pil)
                    # add gallery item referencing original video file
                    self._add_gallery_item(pil, path=fn, media_type='video')
            elif low.endswith('.gif'):
                # gif: load first frame and store path
                try:
                    import imageio
                    gframes = imageio.mimread(fn)
                    if gframes:
                        arr = gframes[0]
                        if isinstance(arr, np.ndarray):
                            pil = Image.fromarray(arr)
                        else:
                            pil = Image.fromarray(np.array(arr))
                        self._show_preview_pil(pil)
                        self._add_gallery_item(pil, path=fn, media_type='gif')
                except Exception:
                    pass
            else:
                pil = Image.open(fn).convert('RGB'); self._show_preview_pil(pil)
                self._add_gallery_item(pil, path=fn, media_type='image')
        except Exception as e:
            print("Load preview error:", e)

    def on_render(self):
        if not hasattr(self, "current_path") or not self.current_path: return
        self.render_btn.setEnabled(False)
        # read options
        ascii_chars = self.charset_input.currentText() or DEFAULT_ASCII
        invert = self.invert_chk.isChecked()
        contrast = self.contrast_slider.value() if hasattr(self, 'contrast_slider') else 100
        keep_size = self.keep_size_chk.isChecked()
        # If pro tools enabled -> use RenderWorker for full media; otherwise single-frame render
        try:
            ext = os.path.splitext(self.current_path)[1].lower()
            if getattr(self, 'pro_tools', False) and ext in [".mp4", ".avi", ".mov", ".mkv", ".gif"]:
                # ask for output path temp file and run worker for single preview GIF/MP4
                tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                tmp.close()
                # render first frame via worker-like path but synchronous for preview
                if ext == '.gif':
                    try:
                        frames = imageio.mimread(self.current_path)
                        arr = frames[0]
                        pil = Image.fromarray(np.array(arr))
                    except Exception:
                        pil = Image.open(self.current_path).convert('RGB')
                else:
                    cap = cv2.VideoCapture(self.current_path); ret, frame = cap.read(); cap.release()
                    if not ret:
                        self.render_btn.setEnabled(True); return
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(frame)
                orig_size = pil.size
                data = image_to_ascii_data(pil, self.width_chars, ascii_chars=ascii_chars, invert=invert, contrast_pct=contrast)
                out = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex, output_size=(orig_size if keep_size else None), watermark=self.watermark_chk.isChecked())
                self.current_output = out
                self._show_preview_pil(out)
                # if original was video, add gallery item as video (thumbnail) so player opens
                if ext in [".mp4", ".avi", ".mov", ".mkv"]:
                    self._add_gallery_item(out, path=self.current_path, media_type='video')
                else:
                    self._add_gallery_item(out, path=None, media_type='image')
            else:
                # legacy single-frame render for images or when pro tools disabled
                if ext in [".mp4", ".avi", ".mov", ".mkv", ".gif"]:
                    cap = cv2.VideoCapture(self.current_path)
                    ret, frame = cap.read(); cap.release()
                    if not ret:
                        self.render_btn.setEnabled(True); return
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(frame)
                else:
                    pil = Image.open(self.current_path).convert('RGB')
                orig_size = pil.size
                data = image_to_ascii_data(pil, self.width_chars, ascii_chars=ascii_chars, invert=invert, contrast_pct=contrast)
                out = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex, output_size=(orig_size if keep_size else None), watermark=self.watermark_chk.isChecked())
                self.current_output = out
                self._show_preview_pil(out)
                self._add_gallery_item(out, path=None, media_type='image')
        except Exception as e:
            print("Render error:", e)
        finally:
            self.render_btn.setEnabled(True)

    def _on_render_finished(self, pil_img):
        # legacy hook kept
        self.render_btn.setEnabled(True)
        if pil_img is None: print("Render failed"); return
        self.current_output = pil_img; self._show_preview_pil(pil_img); self._add_gallery_item(pil_img)

    def _clear_render_worker(self, *_):
        try:
            if self.render_worker is not None:
                # ensure thread cleaned up
                self.render_worker.wait(50)
        except Exception:
            pass
        self.render_worker = None

    def on_export(self):
        # If we have a rendered PIL image -> save static formats
        if hasattr(self, "current_output") and self.current_output is not None:
            # allow selecting image or animation containers
            fn, flt = QFileDialog.getSaveFileName(self, "Save image/animation", os.getcwd(), "PNG Image (*.png);;GIF (*.gif);;MP4 Video (*.mp4)")
            if not fn: return
            try:
                ext = fn.split('.')[-1].lower()
                if ext == 'png':
                    self.current_output.save(fn)
                elif ext in ('gif','mp4'):
                    # use worker to avoid blocking UI when writing animations
                    saver = SaveImageWorker(self.current_output, fn, fps=10)
                    dlg = ExportProgressDialog(self, saver)
                    saver.start()
                    dlg.exec()
                else:
                    self.current_output.save(fn)
            except Exception as e:
                print("Export save failed:", e)
            return
        # otherwise offer to export current media (video/gif) to ascii animation
        if not hasattr(self, 'current_path') or not self.current_path:
            return
        outfn, _ = QFileDialog.getSaveFileName(self, "Export animation", os.getcwd(), "MP4 Video (*.mp4);;MOV Video (*.mov);;GIF (*.gif)")
        if not outfn: return
        # prepare parameters
        fps = 24
        width_chars = self.width_chars
        ascii_chars = self.charset_input.currentText() or DEFAULT_ASCII
        invert = self.invert_chk.isChecked()
        contrast = self.contrast_slider.value() if hasattr(self, 'contrast_slider') else 100
        font_size = self.font_size
        style = self.style
        fg = self.fg_hex; bg = self.bg_hex
        watermark = self.watermark_chk.isChecked()
        # create worker thread
        try:
            self.render_worker = RenderWorker(self.current_path, outfn, fps=fps, width_chars=width_chars, ascii_chars=ascii_chars, invert=invert, contrast_pct=contrast, font_size=font_size, style=style, fg_hex=fg, bg_hex=bg, watermark=watermark)
            try:
                self.render_worker.render_device = self.device_choice
            except Exception:
                pass
            dlg = ExportProgressDialog(self, self.render_worker)
            # connect finished signal to show file dialog when done
            self.render_worker.start()
            dlg.exec()
            # open folder when finished (best-effort)
            try:
                if os.path.exists(outfn):
                    os.startfile(outfn)
            except Exception:
                pass
            self._clear_render_worker()
        except Exception as e:
            print('Export failed to start:', e)

    def on_style_changed(self, v):
        self.style = v
        # toggle color pickers
        self._update_color_buttons_state()

    def _trail_combo_changed(self, label):
        """Map translated trail label back to internal key and set trail_level."""
        try:
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            rev = {tr["off"]: "off", tr["low"]: "low", tr["med"]: "med", tr["high"]: "high"}
            key = rev.get(label, "med")
            self.trail_level = key
        except Exception:
            self.trail_level = "med"

    def on_width_changed(self, v):
        self.width_chars = int(v)
        self.width_val_label.setText(str(self.width_chars))

    def on_font_changed(self, v):
        self.font_size = int(v)
        self.font_val_label.setText(str(self.font_size))

    def on_pick_text(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.fg_hex = c.name()
            # update button color
            self.pick_text_btn.setStyleSheet(self._glass_btn_css() + f"QPushButton{{ background:{self.fg_hex}; color:#000; }}")

    def on_pick_bg(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.bg_hex = c.name()
            self._update_background()
            # update button color
            self.pick_bg_btn.setStyleSheet(self._glass_btn_css() + f"QPushButton{{ background:{self.bg_hex}; color:#000; }}")

    def _update_color_buttons_state(self):
        # enable color pickers only when style is custom
        enabled = (self.style_combo.currentText() == "custom")
        try:
            self.pick_text_btn.setEnabled(enabled)
            self.pick_bg_btn.setEnabled(enabled)
            # visually dim when disabled
            if not enabled:
                self.pick_text_btn.setStyleSheet(self._glass_btn_css() + "QPushButton{ opacity:0.45; }")
                self.pick_bg_btn.setStyleSheet(self._glass_btn_css() + "QPushButton{ opacity:0.45; }")
        except Exception:
            pass

    def _show_preview_pil(self, pil):
        lbl_w = max(200, self.preview_label.width() or 800); lbl_h = max(200, self.preview_label.height() or 500)
        # ensure we don't upscale image beyond original preview area
        iw, ih = pil.size; scale = min(lbl_w/iw, lbl_h/ih, 1.0)
        nw, nh = max(1,int(iw*scale)), max(1,int(ih*scale)); res = pil.resize((nw,nh), Image.Resampling.LANCZOS)
        qpix = pil_to_qpixmap(res); self.preview_label.setPixmap(qpix); self.preview_label.setScaledContents(False); self.preview_label.repaint()

    def _add_gallery_item(self, pil, path=None, media_type='image'):
        # media_type: 'image', 'video', 'gif'
        try:
            thumb = pil.copy(); thumb.thumbnail((140,140), Image.Resampling.LANCZOS); qicon = pil_to_qpixmap(thumb)
        except Exception:
            qicon = QPixmap(140,140)
        item = QListWidgetItem(); item.setIcon(QIcon(qicon))
        data = {'type': media_type, 'pil': pil, 'path': path}
        item.setData(Qt.UserRole, data)
        # make item checkable (enable/disable in gallery)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked)
        if path:
            item.setToolTip(path)
        # store pixmap thumbnail and full-sized pixmap for fast preview
        try:
            full_qpix = pil_to_qpixmap(pil)
        except Exception:
            full_qpix = None
        item.setData(Qt.UserRole+1, qicon)
        item.setData(Qt.UserRole+2, full_qpix)
        self.gallery_list.addItem(item)
        # context menu for gallery
        try:
            self.gallery_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.gallery_list.customContextMenuRequested.connect(self._on_gallery_context)
        except Exception:
            pass
        # refresh panels as gallery changed (so glass shows new blurred bg)
        try:
            self._update_panel_backgrounds()
        except Exception:
            pass

    def on_gallery_click(self, item):
        data = item.data(Qt.UserRole)
        qpix = item.data(Qt.UserRole+2)
        if not data:
            return
        mtype = data.get('type', 'image')
        if mtype == 'image':
            # prefer full qpix (fast) else use pil
            if qpix is not None:
                # convert QPixmap back to pil for viewer compatibility
                self.open_fullscreen_viewer(data.get('pil'))
            else:
                self.open_fullscreen_viewer(data.get('pil'))
        else:
            # video or gif: open mini player
            player = MiniPlayer(self, data)
            player.exec()

    def on_gallery_double_click(self, item):
        data = item.data(Qt.UserRole)
        if not data: return
        if data.get('type') == 'image':
            self.open_fullscreen_viewer(data.get('pil'))
        else:
            player = MiniPlayer(self, data); player.exec()

    def _on_gallery_context(self, pos):
        item = self.gallery_list.itemAt(pos)
        if not item: return
        data = item.data(Qt.UserRole)
        menu = []
        # simple remove / toggle
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        a_remove = m.addAction("Remove")
        a_toggle = m.addAction("Toggle enabled")
        act = m.exec(self.gallery_list.mapToGlobal(pos))
        if act == a_remove:
            row = self.gallery_list.row(item); self.gallery_list.takeItem(row)
        elif act == a_toggle:
            # toggle check
            item.setCheckState(Qt.Unchecked if item.checkState()==Qt.Checked else Qt.Checked)

    def _preview_clicked(self, event):
        if hasattr(self, "current_output") and self.current_output: self.open_fullscreen_viewer(self.current_output)

    def open_fullscreen_viewer(self, pil):
        viewer = FullscreenViewer(self, pil)
        viewer.exec()
    def _update_panel_backgrounds(self):
        """Crop bg_base for left and right panels, apply local blur + tint and set to overlay labels."""
        try:
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
                self.left_bg_label.lower()
            if right_img:
                self.right_bg_label.setPixmap(pil_to_qpixmap(right_img).scaled(rwid, rht, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                self.right_bg_label.setGeometry(rx, ry, rwid, rht)
                self.right_bg_label.lower()
        except Exception:
            pass

    def _build_menu(self):
        menubar = self.menuBar()
        # File menu
        self.file_menu = menubar.addMenu(TRANSLATIONS[self.lang].get("file", "File"))
        self.action_load = self.file_menu.addAction(TRANSLATIONS[self.lang].get("load", "Load"))
        self.action_load.triggered.connect(self.on_load)
        self.action_export = self.file_menu.addAction(TRANSLATIONS[self.lang].get("export", "Export"))
        self.action_export.triggered.connect(self.on_export)
        self.action_settings = self.file_menu.addAction(TRANSLATIONS[self.lang].get("settings", "Settings"))
        self.action_settings.triggered.connect(self.open_settings_dialog)
        # Language submenu
        self.lang_menu = menubar.addMenu(TRANSLATIONS[self.lang].get("language", "Lang"))
        for code in TRANSLATIONS.keys():
            act = self.lang_menu.addAction(code)
            act.triggered.connect(lambda _, c=code: self._on_change_language(c))

    def _on_change_language(self, code):
        if code in TRANSLATIONS:
            self.lang = code
            self._apply_translations()

    def open_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get("settings", "Settings"))
        fl = QFormLayout(dlg)
        lang_combo = QComboBox(); lang_combo.addItems(["en","ru","zh"]); lang_combo.setCurrentText(self.lang)
        fl.addRow(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get("language", "Language") + ":", lang_combo)
        dev_combo = QComboBox(); dev_combo.addItem("cpu")
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0: dev_combo.addItem("gpu")
        except Exception:
            pass
        dev_combo.setCurrentText(self.device_choice); fl.addRow(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get("device", "Render device") + ":", dev_combo)
        watermark_chk = QCheckBox(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get("watermark", "Watermark")); watermark_chk.setChecked(self.watermark_chk.isChecked()); fl.addRow(watermark_chk)
        # Pro tools toggle
        pro_chk = QCheckBox("Enable Pro Tools")
        try:
            pro_chk.setText(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get('enable_pro_tools', 'Enable Pro Tools'))
        except Exception:
            pass
        pro_chk.setChecked(self.pro_tools)
        fl.addRow(pro_chk)
        # advanced options
        threads_spin = QSpinBox(); threads_spin.setRange(1, 64); threads_spin.setValue(self.render_threads)
        codec_combo = QComboBox(); codec_combo.addItems(["libx264","mpeg4","libvpx","h264"]); codec_combo.setCurrentText(self.render_codec)
        bitrate_input = QComboBox(); bitrate_input.addItems(["500k","1M","2M","4M","8M","10M"]); bitrate_input.setCurrentText(self.render_bitrate)
        fl.addRow(QLabel(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get("author", "Advanced") + ":"))
        fl.addRow("Render threads:", threads_spin)
        fl.addRow("Codec:", codec_combo)
        fl.addRow("Bitrate:", bitrate_input)
        # trail setting
        trail_combo = QComboBox(); tr = TRANSLATIONS.get(self.lang, TRANSLATIONS['en']); trail_combo.addItems([tr['off'], tr['low'], tr['med'], tr['high']]);
        # map current to label
        key_to_label = {"off": tr['off'], 'low': tr['low'], 'med': tr['med'], 'high': tr['high']}
        trail_combo.setCurrentText(key_to_label.get(self.trail_level, tr['med']))
        fl.addRow(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get('trail','Trail') + ":", trail_combo)
        # ok / cancel
        ok = QPushButton(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get("ok", "OK"))
        cancel = QPushButton(TRANSLATIONS.get(self.lang, TRANSLATIONS['en']).get("cancel", "Cancel"))
        row = QHBoxLayout(); row.addWidget(ok); row.addWidget(cancel)
        fl.addRow(row)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted:
            # map trail label back to key
            try:
                tr = TRANSLATIONS.get(self.lang, TRANSLATIONS['en']); rev = {tr['off']:'off', tr['low']:'low', tr['med']:'med', tr['high']:'high'}
                sel_trail = rev.get(trail_combo.currentText(), 'med')
            except Exception:
                sel_trail = 'med'
            # apply settings
            self._apply_settings_dialog(lang_combo.currentText(), dev_combo.currentText(), watermark_chk.isChecked(), pro_chk.isChecked(), threads_spin.value(), codec_combo.currentText(), bitrate_input.currentText(), sel_trail)

    def _apply_settings_dialog(self, langkey, devicekey, watermark_flag, pro_flag, threads, codec, bitrate, trail_level='med'):
        self.lang = langkey
        self._apply_translations()
        # device choice stored but UI device selector moved to settings
        self.device_choice = devicekey
        self.watermark_chk.setChecked(watermark_flag)
        self.pro_tools = bool(pro_flag)
        try:
            self.pro_tools_frame.setVisible(bool(self.pro_tools))
        except Exception:
            pass
        self.render_threads = int(threads)
        self.render_codec = codec
        self.render_bitrate = bitrate
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
            'show_watermark': self.watermark_chk.isChecked(),
            'ascii_chars': self.charset_input.currentText(),
            'contrast': self.contrast_slider.value() if hasattr(self, 'contrast_slider') else 100,
            'invert': self.invert_chk.isChecked(),
            'keep_size': self.keep_size_chk.isChecked()
        }
        save_settings(s)
        # update UI language sensitive strings
        self._apply_translations()

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
        self.close_btn = QPushButton("✕", self)
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
    app = QApplication(sys.argv); win = MainWindow(); win.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()
