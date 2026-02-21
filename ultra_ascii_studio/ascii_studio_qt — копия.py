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
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox, QFileDialog,
    QColorDialog, QSlider, QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QListWidget,
    QListWidgetItem, QProgressBar, QDialog, QFormLayout, QSpinBox, QCheckBox
)

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import numpy as np
import cv2
import imageio

# -------------------- Translations --------------------
TRANSLATIONS = {
    "en": {
        "app": "ASCII Studio", "load": "Load", "render": "Render", "export": "Export",
        "settings": "Settings", "device": "Render device", "cpu": "CPU", "gpu": "GPU (if available)",
        "file": "File", "language": "Language",
        "style": "Style", "width": "Width (chars)", "font": "Font size",
        "text_color": "Text color", "bg_color": "BG color", "gallery": "Gallery",
        "trail": "Trail intensity", "off": "Off", "low": "Low", "med": "Medium", "high": "High",
        "watermark": "Watermark", "author": "Author", "ok": "OK", "cancel": "Cancel"
    },
    "ru": {
        "app": "ASCII Studio", "load": "Загрузить", "render": "Рендер", "export": "Экспорт",
        "settings": "Настройки", "device": "Устройство рендера", "cpu": "CPU", "gpu": "GPU (если доступен)",
        "file": "Файл", "language": "Язык",
        "style": "Стиль", "width": "Ширина (симв.)", "font": "Размер шрифта",
        "text_color": "Цвет текста", "bg_color": "Цвет фона", "gallery": "Галерея",
        "trail": "Интенсивность хвоста", "off": "Выкл", "low": "Низкий", "med": "Средний", "high": "Высокий",
        "watermark": "Водяной знак", "author": "Автор", "ok": "OK", "cancel": "Отмена"
    },
    "zh": {
        "app": "ASCII Studio", "load": "加载", "render": "渲染", "export": "导出",
        "settings": "设置", "device": "渲染设备", "cpu": "CPU", "gpu": "GPU（如果可用）",
        "file": "文件", "language": "语言",
        "style": "样式", "width": "宽度（字符）", "font": "字体大小",
        "text_color": "文字颜色", "bg_color": "背景颜色", "gallery": "画廊",
        "trail": "尾迹强度", "off": "关闭", "low": "低", "med": "中", "high": "高",
        "watermark": "水印", "author": "作者", "ok": "确定", "cancel": "取消"
    }
}

# -------------------- Utility / ASCII Engine --------------------
DEFAULT_ASCII = "@%#*+=-:. "
WATERMARK = "SNERK503"

def pil_to_qpixmap(pil_image):
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")
    data = pil_image.tobytes("raw", "RGBA")
    qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage)

def image_to_ascii_data(pil_img, width_chars, ascii_chars=DEFAULT_ASCII):
    img = pil_img.convert("RGB")
    w, h = img.size
    height = max(1, int((h / w) * width_chars * 0.55))
    small = img.resize((width_chars, height), Image.Resampling.BICUBIC)
    arr = np.array(small)
    out = []
    for row in arr:
        rline = []
        for px in row:
            b = int(px.mean())
            idx = b * (len(ascii_chars)-1) // 255
            rline.append((ascii_chars[idx], tuple(int(x) for x in px)))
        out.append(rline)
    return out

def render_ascii_pil(ascii_data, font_size=12, style="bw", fg_hex="#FFFFFF", bg_hex="#0F0F12"):
    try:
        font = ImageFont.truetype("Consolas.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    bbox = font.getbbox("A")
    cw = bbox[2]-bbox[0] or int(font_size*0.6)
    ch = bbox[3]-bbox[1] or font_size
    rows = len(ascii_data); cols = len(ascii_data[0]) if rows>0 else 1
    w = max(1, int(cols * cw)); h = max(1, int(rows * ch))
    im = Image.new("RGB", (w,h), bg_hex)
    draw = ImageDraw.Draw(im)
    rfg = tuple(int(fg_hex.lstrip("#")[i:i+2],16) for i in (0,2,4))
    for y,row in enumerate(ascii_data):
        for x,(chc, color) in enumerate(row):
            if style == "bw":
                fill=(255,255,255)
            elif style=="red":
                fill=(255,60,60)
            elif style=="color":
                fill=color
            elif style=="matrix":
                fill=(0,255,120)
            elif style=="custom":
                fill=rfg
            else:
                fill=(255,255,255)
            draw.text((x*cw, y*ch), chc, fill=fill, font=font)
    draw.text((8, max(h-18,0)), WATERMARK, fill=(120,120,120), font=font)
    return im

# --------------- QThread worker for rendering ----------------
class RenderWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(object)
    def __init__(self, path, width_chars, font_size, style, fg_hex, bg_hex, device="cpu"):
        super().__init__()
        self.path = path
        self.width_chars = width_chars
        self.font_size = font_size
        self.style = style
        self.fg_hex = fg_hex
        self.bg_hex = bg_hex
        self.device = device
    def run(self):
        try:
            ext = os.path.splitext(self.path)[1].lower()
            if ext in [".mp4", ".avi", ".mov", ".mkv", ".gif"]:
                cap = cv2.VideoCapture(self.path)
                ret, frame = cap.read()
                if not ret:
                    self.finished.emit(None); return
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(frame)
                data = image_to_ascii_data(pil, self.width_chars)
                out = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex)
                self.finished.emit(out)
                cap.release()
            else:
                pil = Image.open(self.path)
                data = image_to_ascii_data(pil, self.width_chars)
                out = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex)
                self.finished.emit(out)
        except Exception as e:
            print("RenderWorker error:", e)
            self.finished.emit(None)

# -------------------- Main Window --------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCII Studio – SNERK503")
        self.setMinimumSize(1100, 700)
        self.lang = "en"
        self.style = "bw"
        self.width_chars = 320
        self.font_size = 12
        self.fg_hex = "#FFFFFF"
        self.bg_hex = "#0F1013"
        self.trail_level = "med"
        self.show_watermark = True
        self.device_choice = "cpu"
        self.trail = deque(maxlen=48)
        self.bg_t = 0.0
        self.render_worker = None
        self._build_ui()
        self._apply_translations()
        self._start_background_animation()

    def _trail_combo_changed(self, label):
        """Map translated trail label back to internal key and set trail_level."""
        try:
            tr = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
            rev = {tr["off"]: "off", tr["low"]: "low", tr["med"]: "med", tr["high"]: "high"}
            key = rev.get(label, "med")
            self.trail_level = key
        except Exception:
            self.trail_level = "med"

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        # enable mouse tracking so mouseMoveEvent fires without mouse buttons pressed
        self.setMouseTracking(True)
        root = QHBoxLayout(central); root.setContentsMargins(8,8,8,8); root.setSpacing(12)
        left_frame = QFrame(); left_frame.setObjectName("left_frame"); left_frame.setStyleSheet("QFrame#left_frame { border-radius: 14px; }")
        left_frame.setMouseTracking(True)
        left_layout = QVBoxLayout(left_frame); left_layout.setContentsMargins(12,12,12,12)
        self.preview_label = QLabel(alignment=Qt.AlignCenter); self.preview_label.setStyleSheet("background: transparent;")
        self.preview_label.setMouseTracking(True)
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
        self.title_label = QLabel(TRANSLATIONS[self.lang].get("app", "ASCII Studio"))
        self.title_label.setStyleSheet("font-weight:700; font-size:16px")
        right_layout.addWidget(self.title_label)
        row = QHBoxLayout(); self.load_btn = QPushButton("Load"); self.load_btn.clicked.connect(self.on_load)
        self.render_btn = QPushButton("Render"); self.render_btn.clicked.connect(self.on_render)
        self.export_btn = QPushButton("Export"); self.export_btn.clicked.connect(self.on_export)
        for b in (self.load_btn, self.render_btn, self.export_btn): b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(38); b.setStyleSheet(self._glass_btn_css())
        row.addWidget(self.load_btn); row.addWidget(self.render_btn); row.addWidget(self.export_btn)
        right_layout.addLayout(row)
        right_layout.addSpacing(4)
        self.style_label = QLabel(TRANSLATIONS[self.lang]["style"])
        right_layout.addWidget(self.style_label)
        self.style_combo = QComboBox(); self.style_combo.addItems(["bw","red","color","matrix","custom"])
        self.style_combo.setCurrentText(self.style); self.style_combo.currentTextChanged.connect(self.on_style_changed)
        right_layout.addWidget(self.style_combo)
        self.width_label = QLabel(TRANSLATIONS[self.lang]["width"])
        right_layout.addWidget(self.width_label)
        wrow = QHBoxLayout(); self.width_slider = QSlider(Qt.Horizontal); self.width_slider.setMinimum(80); self.width_slider.setMaximum(900)
        self.width_slider.setValue(self.width_chars); self.width_slider.valueChanged.connect(self.on_width_changed)
        self.width_val_label = QLabel(str(self.width_chars)); wrow.addWidget(self.width_slider); wrow.addWidget(self.width_val_label); right_layout.addLayout(wrow)
        self.font_label = QLabel(TRANSLATIONS[self.lang]["font"])
        right_layout.addWidget(self.font_label)
        frow = QHBoxLayout(); self.font_slider = QSlider(Qt.Horizontal); self.font_slider.setRange(6, 28); self.font_slider.setValue(self.font_size)
        self.font_slider.valueChanged.connect(self.on_font_changed); self.font_val_label = QLabel(str(self.font_size)); frow.addWidget(self.font_slider); frow.addWidget(self.font_val_label); right_layout.addLayout(frow)
        crow = QHBoxLayout(); self.pick_text_btn = QPushButton(TRANSLATIONS[self.lang]["text_color"]); self.pick_text_btn.clicked.connect(self.on_pick_text)
        self.pick_bg_btn = QPushButton(TRANSLATIONS[self.lang]["bg_color"]); self.pick_bg_btn.clicked.connect(self.on_pick_bg)
        for b in (self.pick_text_btn, self.pick_bg_btn): b.setStyleSheet(self._glass_btn_css()); b.setCursor(Qt.PointingHandCursor)
        crow.addWidget(self.pick_text_btn); crow.addWidget(self.pick_bg_btn); right_layout.addLayout(crow)
        self.trail_label = QLabel(TRANSLATIONS[self.lang]["trail"])
        right_layout.addWidget(self.trail_label)
        self.trail_combo = QComboBox()
        # fill with translated labels
        tr = TRANSLATIONS[self.lang]
        self.trail_combo.addItems([tr["off"], tr["low"], tr["med"], tr["high"]])
        # map current trail_level key to label
        key_to_label = {"off": tr["off"], "low": tr["low"], "med": tr["med"], "high": tr["high"]}
        self.trail_combo.setCurrentText(key_to_label.get(self.trail_level, tr["med"]))
        self.trail_combo.currentTextChanged.connect(self._trail_combo_changed)
        right_layout.addWidget(self.trail_combo)
        self.device_label = QLabel(TRANSLATIONS[self.lang].get("device", "Render device"))
        right_layout.addWidget(self.device_label)
        self.device_combo = QComboBox(); gpu_ok = False
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0: gpu_ok = True
        except Exception:
            gpu_ok = False
        self.device_combo.addItem("cpu")
        if gpu_ok: self.device_combo.addItem("gpu")
        else: self.device_combo.addItem("gpu (not available)")
        self.device_combo.setCurrentText(self.device_choice); right_layout.addWidget(self.device_combo)
        self.watermark_chk = QCheckBox("Show watermark"); self.watermark_chk.setChecked(self.show_watermark); right_layout.addWidget(self.watermark_chk)
        self.settings_btn = QPushButton(TRANSLATIONS[self.lang].get("settings", "Settings..."))
        self.settings_btn.setStyleSheet(self._glass_btn_css()); self.settings_btn.clicked.connect(self.open_settings_dialog); right_layout.addWidget(self.settings_btn)
        right_layout.addStretch(1)
        self.gallery_label = QLabel(TRANSLATIONS[self.lang].get("gallery", "Gallery:"))
        right_layout.addWidget(self.gallery_label)
        self.gallery_list = QListWidget(); self.gallery_list.setFixedHeight(140); self.gallery_list.itemClicked.connect(self.on_gallery_click); right_layout.addWidget(self.gallery_list)
        root.addWidget(right_frame, 0)
        self._apply_window_style()
        self.preview_label.mousePressEvent = self._preview_clicked
        self.bg_anim_timer = QTimer(self); self.bg_anim_timer.timeout.connect(self._update_background)
        self.trail_timer = QTimer(self); self.trail_timer.timeout.connect(self._update_trail_overlay)
        # start animation timers
        try:
            self.bg_anim_timer.start(40)
            self.trail_timer.start(60)
        except Exception:
            pass
        # set pick buttons enabled state depending on style
        self._update_color_buttons_state()

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

    def _apply_translations(self):
        t = TRANSLATIONS[self.lang]
        self.load_btn.setText(t["load"])
        self.render_btn.setText(t["render"])
        self.export_btn.setText(t["export"])
        self.pick_text_btn.setText(t["text_color"])
        self.pick_bg_btn.setText(t["bg_color"])
        # update other labels
        try:
            self.style_label.setText(t.get("style", self.style_label.text()))
            self.width_label.setText(t.get("width", self.width_label.text()))
            self.font_label.setText(t.get("font", self.font_label.text()))
            self.trail_label.setText(t.get("trail", self.trail_label.text()))
            self.device_label.setText(t.get("device", self.device_label.text()))
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
        except Exception:
            pass

    def _start_background_animation(self):
        w = max(1200, self.width()); h = max(800, self.height())
        self.bg_base = Image.new("RGB", (w,h), "#0e1117")
        self._update_background()

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
        self.setAutoFillBackground(True)
        palette = self.palette(); palette.setBrush(self.backgroundRole(), pix); self.setPalette(palette)
        self.bg_base = im
        # update background pixmaps for panel crops
        try:
            self._update_panel_backgrounds()
        except Exception:
            pass

    def mouseMoveEvent(self, evt):
        # windowPos() is deprecated; use position() or localPos() depending on Qt version
        try:
            pos = evt.position()
        except Exception:
            try:
                pos = evt.localPos()
            except Exception:
                pos = evt.windowPos()
        self.trail.append((int(pos.x()), int(pos.y()), time.time()))
        return super().mouseMoveEvent(evt)

    def _update_trail_overlay(self):
        if not hasattr(self, "bg_base"): return
        base = self.bg_base.copy()
        sw, sh = max(200, base.width//2), max(120, base.height//2)
        overlay = Image.new("RGBA", (sw, sh), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        if len(self.trail) >= 2 and self.trail_level != "off":
            pts = list(self.trail)
            for i,(x,y,tval) in enumerate(pts):
                sx = int(x * sw / max(1, self.width())); sy = int(y * sh / max(1, self.height()))
                alpha = max(8, int(180 * (1 - (time.time()-tval)/1.6)))
                size = 6 + (len(pts)-i) * (2 if self.trail_level=="high" else (1 if self.trail_level=="med" else 0.6))
                draw.ellipse([sx-size, sy-size, sx+size, sy+size], fill=(255,255,255,alpha))
            overlay = overlay.filter(ImageFilter.GaussianBlur(radius=8 if self.trail_level=="high" else (6 if self.trail_level=="med" else 3)))
            overlay_large = overlay.resize(base.size, Image.Resampling.BICUBIC)
            base = Image.alpha_composite(base.convert("RGBA"), overlay_large).convert("RGB")
            self.bg_qpix = pil_to_qpixmap(base)
            pix = self.bg_qpix.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            palette = self.palette(); palette.setBrush(self.backgroundRole(), pix); self.setPalette(palette)
        # also refresh panel backgrounds when overlay updated
        try:
            self._update_panel_backgrounds()
        except Exception:
            pass

    def on_load(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Select media", os.getcwd(),
                                            "Images & Videos (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.avi)")
        if not fn: return
        self.current_path = fn
        try:
            if fn.lower().endswith((".mp4", ".avi", ".mov")):
                cap = cv2.VideoCapture(fn); ret, frame = cap.read(); cap.release()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); pil = Image.fromarray(frame); self._show_preview_pil(pil)
            else:
                pil = Image.open(fn); self._show_preview_pil(pil)
        except Exception as e:
            print("Load preview error:", e)

    def on_render(self):
        if not hasattr(self, "current_path") or not self.current_path: return
        self.render_btn.setEnabled(False)
        worker = RenderWorker(self.current_path, self.width_chars, self.font_size, self.style, self.fg_hex, self.bg_hex,
                              device=self.device_combo.currentText())
        # keep reference so thread isn't GC'd and can be stopped
        self.render_worker = worker
        worker.finished.connect(self._on_render_finished)
        worker.finished.connect(self._clear_render_worker)
        worker.start()

    def _on_render_finished(self, pil_img):
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
        if not hasattr(self, "current_output") or self.current_output is None: return
        fn, _ = QFileDialog.getSaveFileName(self, "Save image", os.getcwd(), "PNG Image (*.png);;GIF (*.gif)")
        if not fn: return
        try:
            if fn.lower().endswith(".png"): self.current_output.save(fn)
            elif fn.lower().endswith(".gif"): imageio.mimsave(fn, [np.array(self.current_output)], duration=0.6)
            else: self.current_output.save(fn)
        except Exception as e: print("Export save failed:", e)

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
        iw, ih = pil.size; scale = min(lbl_w/iw, lbl_h/ih, 1.0)
        nw, nh = max(1,int(iw*scale)), max(1,int(ih*scale)); res = pil.resize((nw,nh), Image.Resampling.LANCZOS)
        qpix = pil_to_qpixmap(res); self.preview_label.setPixmap(qpix); self.preview_label.setScaledContents(False); self.preview_label.repaint()

    def _add_gallery_item(self, pil):
        thumb = pil.copy(); thumb.thumbnail((140,140), Image.Resampling.LANCZOS); qpix = pil_to_qpixmap(thumb)
        item = QListWidgetItem(); item.setIcon(QIcon(qpix)); item.setData(Qt.UserRole, pil);
        # store pixmap for quick preview
        item.setData(Qt.UserRole+1, qpix)
        self.gallery_list.addItem(item)
        # refresh panels as gallery changed (so glass shows new blurred bg)
        try:
            self._update_panel_backgrounds()
        except Exception:
            pass

    def on_gallery_click(self, item):
        pil = item.data(Qt.UserRole)
        qpix = item.data(Qt.UserRole+1)
        if pil:
            # if thumbnail pixmap exists, show scaled full image in preview dialog
            self.open_fullscreen_viewer(pil)

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
        dlg.setWindowTitle(TRANSLATIONS[self.lang].get("settings", "Settings"))
        fl = QFormLayout(dlg)
        lang_combo = QComboBox(); lang_combo.addItems(["en","ru","zh"]); lang_combo.setCurrentText(self.lang)
        fl.addRow(TRANSLATIONS[self.lang].get("language", "Language") + ":", lang_combo)
        dev_combo = QComboBox(); dev_combo.addItem("cpu")
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0: dev_combo.addItem("gpu")
        except Exception:
            pass
        dev_combo.setCurrentText(self.device_combo.currentText()); fl.addRow(TRANSLATIONS[self.lang].get("device", "Render device") + ":", dev_combo)
        watermark_chk = QCheckBox(TRANSLATIONS[self.lang].get("watermark", "Watermark")); watermark_chk.setChecked(self.watermark_chk.isChecked()); fl.addRow(watermark_chk)
        ok = QPushButton(TRANSLATIONS[self.lang].get("ok", "OK")); cancel = QPushButton(TRANSLATIONS[self.lang].get("cancel", "Cancel"))
        row = QHBoxLayout(); row.addWidget(ok); row.addWidget(cancel); fl.addRow(row)
        ok.clicked.connect(lambda: (self._apply_settings_dialog(lang_combo.currentText(), dev_combo.currentText(), watermark_chk.isChecked()), dlg.accept()))
        cancel.clicked.connect(dlg.reject)
        dlg.exec()

    def _apply_settings_dialog(self, langkey, devicekey, watermark_flag):
        self.lang = langkey
        self._apply_translations()
        if "gpu" in devicekey: self.device_combo.setCurrentText("gpu")
        else: self.device_combo.setCurrentText("cpu")
        self.watermark_chk.setChecked(watermark_flag)
        # update UI language sensitive strings
        self._apply_translations()

# -------------- Fullscreen viewer ------------
class FullscreenViewer(QDialog):
    def __init__(self, parent, pil_img):
        super().__init__(parent)
        self.setWindowTitle("Preview")
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
        self.close_btn.setFixedSize(48,48)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("background: rgba(30,30,30,0.6); color: white; border-radius:18px;")
        self.label.installEventFilter(self)
        self._render()

    def _render(self):
        # render current image with zoom and apply pan
        try:
            w = max(1, int(self.pil.width * self.zoom))
            h = max(1, int(self.pil.height * self.zoom))
            img = self.pil.resize((w, h), Image.Resampling.LANCZOS)
            q = pil_to_qpixmap(img)
            self.label.setPixmap(q)
            # size of label equals image size, position it centered + pan
            self.label.resize(q.width(), q.height())
            cx = max(0, (self.width() - q.width()) // 2 + int(self.pan[0]))
            cy = max(0, (self.height() - q.height()) // 2 + int(self.pan[1]))
            self.label.move(cx, cy)
            self.close_btn.move(self.width()-70, 20)
        except Exception:
            pass

    def resizeEvent(self, ev):
        # re-render to reposition image on resize
        try:
            self._render()
            self.close_btn.move(self.width()-70, 20)
        except Exception:
            pass
        return super().resizeEvent(ev)
    def eventFilter(self, obj, ev):
        # Use QEvent types from Qt for comparison and guard attribute access
        try:
            etype = ev.type()
        except Exception:
            return super().eventFilter(obj, ev)

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
