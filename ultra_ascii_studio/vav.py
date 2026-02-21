# ascii_studio_qt_v2.py
# Upgraded version: smoke trail, fullscreen close button, improved gallery, more render settings, multiple themes, higher fps
# Requires: PySide6, pillow, numpy, opencv-python, imageio, imageio-ffmpeg (optional)
# Install: pip install PySide6 pillow numpy opencv-python imageio imageio-ffmpeg

import sys, os, time, math, random
from collections import deque
from functools import partial

from PySide6.QtCore import Qt, QTimer, QSize, QPoint
from PySide6.QtGui import QPixmap, QImage, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QFileDialog, QColorDialog, QSlider, QHBoxLayout, QVBoxLayout, QFrame,
    QListWidget, QListWidgetItem, QDialog, QFormLayout, QSpinBox, QCheckBox,
    QLineEdit, QGridLayout, QGroupBox
)

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps
import numpy as np
import cv2
import imageio

# -------------------- Translations --------------------
TRANSLATIONS = {
    "en": {"load":"Load","render":"Render","export":"Export","settings":"Settings","gallery":"Gallery"},
    "ru": {"load":"Загрузить","render":"Рендер","export":"Экспорт","settings":"Настройки","gallery":"Галерея"},
    "zh": {"load":"加载","render":"渲染","export":"导出","settings":"设置","gallery":"画廊"}
}

# -------------------- Defaults / Themes --------------------
DEFAULT_ASCII = "@%#*+=-:. "
WATERMARK = "SNERK503"
THEMES = {
    "dark": {"bg":"#0b0f14", "glass":"rgba(255,255,255,0.03)", "accent":"#2dd4bf"},
    "midnight": {"bg":"#08101a", "glass":"rgba(255,255,255,0.025)", "accent":"#7c3aed"},
    "neon": {"bg":"#05040a", "glass":"rgba(255,255,255,0.02)", "accent":"#00e5ff"},
    "warm": {"bg":"#17120f", "glass":"rgba(255,255,255,0.03)", "accent":"#ff8a65"}
}

# -------------------- Utilities --------------------
def pil_to_qpixmap(pil_image):
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")
    data = pil_image.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)

def image_to_ascii_data(pil_img, width_chars, ascii_chars=DEFAULT_ASCII, brightness=1.0, contrast=1.0, invert=False, gamma=1.0):
    img = pil_img.convert("RGB")
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if gamma != 1.0:
        inv_gamma = 1.0 / gamma
        lut = [pow(i/255.0, inv_gamma)*255 for i in range(256)]
        lut = [int(max(0, min(255, v))) for v in lut]
        img = img.point(lut*3)
    if invert:
        img = ImageOps.invert(img)
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

def render_ascii_pil(ascii_data, font_size=12, style="bw", fg_hex="#FFFFFF", bg_hex="#0f0f12", watermark=True):
    try:
        font = ImageFont.truetype("Consolas.ttf", font_size)
    except:
        font = ImageFont.load_default()
    bbox = font.getbbox("A") if hasattr(font, "getbbox") else (0,0,font_size,int(font_size*1.2))
    cw = (bbox[2]-bbox[0]) or int(font_size*0.6)
    ch = (bbox[3]-bbox[1]) or font_size
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
    if watermark:
        draw.text((8, max(h-18,0)), WATERMARK, fill=(120,120,120), font=font)
    return im

# -------------------- Worker thread (simple) --------------------
from PySide6.QtCore import QThread, Signal
class RenderWorker(QThread):
    finished = Signal(object)
    def __init__(self, path, width_chars, font_size, style, fg_hex, bg_hex, settings):
        super().__init__()
        self.path = path
        self.width_chars = width_chars
        self.font_size = font_size
        self.style = style
        self.fg_hex = fg_hex
        self.bg_hex = bg_hex
        self.settings = settings
    def run(self):
        try:
            ext = os.path.splitext(self.path)[1].lower()
            if ext in [".mp4", ".avi", ".mov", ".mkv", ".gif"]:
                cap = cv2.VideoCapture(self.path)
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    self.finished.emit(None); return
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(frame)
            else:
                pil = Image.open(self.path)
            data = image_to_ascii_data(
                pil, self.width_chars,
                ascii_chars=self.settings.get("ascii_chars", DEFAULT_ASCII),
                brightness=self.settings.get("brightness",1.0),
                contrast=self.settings.get("contrast",1.0),
                invert=self.settings.get("invert", False),
                gamma=self.settings.get("gamma",1.0)
            )
            out = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex, watermark=self.settings.get("watermark",True))
            self.finished.emit(out)
        except Exception as e:
            print("RenderWorker exception:", e)
            self.finished.emit(None)

# -------------------- Fullscreen viewer dialog --------------------
from PySide6.QtWidgets import QDialog
class FullscreenViewer(QDialog):
    def __init__(self, parent, pil_img):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setWindowState(self.windowState() | Qt.WindowFullScreen)
        self.pil = pil_img.copy()
        self.zoom = 1.0
        self.pan_offset = [0,0]
        self.label = QLabel(self); self.label.setAlignment(Qt.AlignCenter)
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(56,56)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(25,25,30,0.55);
                border-radius: 28px;
                color: white;
                font-size: 20px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.addWidget(self.label)
        self.label.installEventFilter(self)
        self.last_pos = None
        self._render()

    def _render(self):
        w = max(1, int(self.pil.width * self.zoom)); h = max(1, int(self.pil.height * self.zoom))
        img = self.pil.resize((w,h), Image.Resampling.LANCZOS)
        qpix = pil_to_qpixmap(img)
        self.label.setPixmap(qpix)
        self.close_btn.move(self.width() - 80, 30)

    def eventFilter(self, obj, ev):
        from PySide6.QtGui import QWheelEvent, QMouseEvent
        if isinstance(ev, QWheelEvent):
            delta = ev.angleDelta().y()
            if delta > 0: self.zoom *= 1.12
            else: self.zoom /= 1.12
            self._render()
            return True
        if ev.type() == QMouseEvent.MouseButtonPress:
            self.last_pos = ev.pos()
            return True
        if ev.type() == QMouseEvent.MouseMove and self.last_pos is not None:
            dx = ev.pos().x() - self.last_pos.x(); dy = ev.pos().y() - self.last_pos.y()
            self.pan_offset[0] += dx; self.pan_offset[1] += dy
            self.label.move(self.label.x()+dx, self.label.y()+dy)
            self.last_pos = ev.pos()
            return True
        if ev.type() == QMouseEvent.MouseButtonRelease:
            self.last_pos = None
            return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.close()

# -------------------- Main Window --------------------
from PySide6.QtWidgets import QMainWindow
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCII Studio – SNERK503")
        self.setMinimumSize(1100, 700)
        # state
        self.lang = "en"
        self.style = "bw"
        self.width_chars = 320
        self.font_size = 12
        self.fg_hex = "#FFFFFF"
        self.bg_hex = THEMES["dark"]["bg"]
        self.trail_level = "med"
        self.trail = deque(maxlen=120)
        self.settings = {
            "ascii_chars": DEFAULT_ASCII, "brightness":1.0, "contrast":1.0,
            "gamma":1.0, "invert":False, "watermark":True
        }
        self.current_output = None
        self.current_path = None
        self._build_ui()
        self._apply_theme("dark")
        # timers: background and trail
        self.bg_timer = QTimer(self); self.bg_timer.timeout.connect(self._update_background); self.bg_timer.start(33)  # ~30fps
        self.trail_timer = QTimer(self); self.trail_timer.timeout.connect(self._update_trail_overlay); self.trail_timer.start(20)  # ~50fps
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(12,12,12,12); root.setSpacing(12)

        # left preview frame
        left_frame = QFrame(); left_frame.setObjectName("left_frame")
        left_layout = QVBoxLayout(left_frame); left_layout.setContentsMargins(12,12,12,12)
        self.preview_label = QLabel(alignment=Qt.AlignCenter)
        self.preview_label.setStyleSheet("background: transparent;")
        self.preview_label.setMinimumSize(640,360)
        left_layout.addWidget(self.preview_label, 1)
        root.addWidget(left_frame, 1)

        # right controls
        right_frame = QFrame(); right_frame.setObjectName("right_frame"); right_frame.setFixedWidth(420)
        right_layout = QVBoxLayout(right_frame); right_layout.setContentsMargins(12,12,12,12); right_layout.setSpacing(8)
        self.title_label = QLabel("ASCII Studio"); self.title_label.setStyleSheet("font-weight:700; font-size:16px")
        right_layout.addWidget(self.title_label)

        # Load/Render/Export row
        row = QHBoxLayout()
        self.load_btn = QPushButton("Load"); self.load_btn.clicked.connect(self.on_load)
        self.render_btn = QPushButton("Render"); self.render_btn.clicked.connect(self.on_render)
        self.export_btn = QPushButton("Export"); self.export_btn.clicked.connect(self.on_export)
        for b in (self.load_btn, self.render_btn, self.export_btn):
            b.setFixedHeight(40); b.setCursor(Qt.PointingHandCursor); b.setStyleSheet(self._glass_button_css())
        row.addWidget(self.load_btn); row.addWidget(self.render_btn); row.addWidget(self.export_btn)
        right_layout.addLayout(row)

        # Themes
        right_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox(); self.theme_combo.addItems(list(THEMES.keys())); self.theme_combo.currentTextChanged.connect(self._apply_theme)
        right_layout.addWidget(self.theme_combo)

        # Style
        right_layout.addWidget(QLabel("Style:"))
        self.style_combo = QComboBox(); self.style_combo.addItems(["bw","red","color","matrix","custom"]); self.style_combo.setCurrentText(self.style)
        self.style_combo.currentTextChanged.connect(lambda v: setattr(self, "style", v))
        right_layout.addWidget(self.style_combo)

        # width slider + display
        right_layout.addWidget(QLabel("Width (chars):"))
        wrow = QHBoxLayout()
        self.width_slider = QSlider(Qt.Horizontal); self.width_slider.setMinimum(80); self.width_slider.setMaximum(900); self.width_slider.setValue(self.width_chars)
        self.width_slider.valueChanged.connect(self.on_width_changed)
        self.width_val_label = QLabel(str(self.width_chars))
        wrow.addWidget(self.width_slider); wrow.addWidget(self.width_val_label)
        right_layout.addLayout(wrow)

        # font size
        right_layout.addWidget(QLabel("Font size:"))
        frow = QHBoxLayout()
        self.font_slider = QSlider(Qt.Horizontal); self.font_slider.setRange(6,36); self.font_slider.setValue(self.font_size)
        self.font_slider.valueChanged.connect(self.on_font_changed)
        self.font_val_label = QLabel(str(self.font_size))
        frow.addWidget(self.font_slider); frow.addWidget(self.font_val_label)
        right_layout.addLayout(frow)

        # advanced render settings group
        adv_group = QGroupBox("Render settings"); adv_layout = QGridLayout(); adv_group.setLayout(adv_layout)
        adv_layout.addWidget(QLabel("Brightness"), 0,0); self.brightness_slider = QSlider(Qt.Horizontal); self.brightness_slider.setRange(50,200); self.brightness_slider.setValue(100)
        adv_layout.addWidget(self.brightness_slider, 0,1); self.brightness_val = QLabel("100%"); adv_layout.addWidget(self.brightness_val,0,2)
        self.brightness_slider.valueChanged.connect(lambda v: self.brightness_val.setText(f"{v}%"))

        adv_layout.addWidget(QLabel("Contrast"), 1,0); self.contrast_slider = QSlider(Qt.Horizontal); self.contrast_slider.setRange(50,200); self.contrast_slider.setValue(100)
        adv_layout.addWidget(self.contrast_slider,1,1); self.contrast_val = QLabel("100%"); adv_layout.addWidget(self.contrast_val,1,2)
        self.contrast_slider.valueChanged.connect(lambda v: self.contrast_val.setText(f"{v}%"))

        adv_layout.addWidget(QLabel("Gamma"), 2,0); self.gamma_slider = QSlider(Qt.Horizontal); self.gamma_slider.setRange(50,200); self.gamma_slider.setValue(100)
        adv_layout.addWidget(self.gamma_slider,2,1); self.gamma_val = QLabel("1.00"); adv_layout.addWidget(self.gamma_val,2,2)
        self.gamma_slider.valueChanged.connect(lambda v: self.gamma_val.setText(f"{v/100:.2f}"))

        self.invert_chk = QCheckBox("Invert colors"); adv_layout.addWidget(self.invert_chk,3,0,1,2)
        self.watermark_chk = QCheckBox("Show watermark"); self.watermark_chk.setChecked(True); adv_layout.addWidget(self.watermark_chk,3,2)

        adv_layout.addWidget(QLabel("ASCII charset"),4,0); self.ascii_input = QLineEdit(DEFAULT_ASCII); adv_layout.addWidget(self.ascii_input,4,1,1,2)

        right_layout.addWidget(adv_group)

        # trail controls
        right_layout.addWidget(QLabel("Trail intensity:"))
        self.trail_combo = QComboBox(); self.trail_combo.addItems(["off","low","med","high"]); self.trail_combo.setCurrentText(self.trail_level)
        self.trail_combo.currentTextChanged.connect(lambda v: setattr(self, "trail_level", v))
        right_layout.addWidget(self.trail_combo)

        # device selection
        right_layout.addWidget(QLabel("Render device:"))
        self.device_combo = QComboBox()
        gpu_ok = False
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                gpu_ok = True
        except:
            gpu_ok = False
        self.device_combo.addItem("cpu")
        if gpu_ok:
            self.device_combo.addItem("gpu")
        else:
            self.device_combo.addItem("gpu (not available)")
        right_layout.addWidget(self.device_combo)

        # settings & spacer
        settings_btn = QPushButton("Settings")
        settings_btn.setStyleSheet(self._glass_button_css()); settings_btn.clicked.connect(self.open_settings_dialog)
        right_layout.addWidget(settings_btn)
        right_layout.addStretch(1)

        # gallery
        right_layout.addWidget(QLabel("Gallery:"))
        self.gallery_list = QListWidget(); self.gallery_list.setFixedHeight(180)
        self.gallery_list.setViewMode(QListWidget.IconMode); self.gallery_list.setIconSize(QSize(140,140)); self.gallery_list.setResizeMode(QListWidget.Adjust)
        self.gallery_list.itemClicked.connect(self.on_gallery_click)
        right_layout.addWidget(self.gallery_list)

        root.addWidget(left_frame, 1)
        root.addWidget(right_frame, 0)

        # connections for sliders
        self.brightness_slider.valueChanged.connect(lambda v: None)
        self.contrast_slider.valueChanged.connect(lambda v: None)
        self.gamma_slider.valueChanged.connect(lambda v: None)

        # styling
        self._apply_stylesheet()
        self.preview_label.mousePressEvent = self._preview_clicked

    def _glass_button_css(self):
        return ("QPushButton{ background: rgba(20,20,25,0.55); color: white; border-radius:8px; padding:6px 8px; }"
                "QPushButton:hover{ background: rgba(255,255,255,0.08); }")

    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: transparent; }}
            QLabel {{ color: #e6eef6; }}
            QFrame#left_frame {{ background: rgba(255,255,255,0.02); border-radius:14px; }}
            QFrame#right_frame {{ background: rgba(255,255,255,0.03); border-radius:14px; padding:8px; }}
            QListWidget {{ background: rgba(255,255,255,0.02); border-radius:12px; color: #dfe8f2; }}
            QListWidget::item {{ border-radius:10px; padding:6px; }}
            QListWidget::item:hover {{ background: rgba(255,255,255,0.06); }}
        """)

    # ------------ Background animation (low-res + scale) --------------
    def _update_background(self):
        # draw small canvas and upscale to full
        w, h = max(600, self.width()), max(400, self.height())
        sw, sh = max(200, w//3), max(120, h//3)
        im = Image.new("RGB", (sw, sh), self.bg_hex)
        draw = ImageDraw.Draw(im)
        # gradient
        for y in range(sh):
            a = y / max(1, sh-1)
            r = int(5*(1-a) + 20*a); g = int(8*(1-a) + 30*a); b = int(12*(1-a) + 40*a)
            draw.line([(0,y),(sw,y)], fill=(r,g,b))
        # animated blobs
        t = time.time()
        colors = [(40,160,255),(120,60,220),(30,200,120)]
        for i,c in enumerate(colors):
            cx = int((math.sin(t*0.6 + i*1.2)+1)/2 * sw)
            cy = int((math.cos(t*0.55 + i*0.9)+1)/2 * sh)
            rad = int(min(sw,sh) * (0.18 + 0.06*i))
            blob = Image.new("RGBA",(sw,sh),(0,0,0,0)); bd = ImageDraw.Draw(blob)
            bd.ellipse([cx-rad, cy-rad, cx+rad, cy+rad], fill=(c[0],c[1],c[2],80))
            blob = blob.filter(ImageFilter.GaussianBlur(radius=max(4,rad//3)))
            im = Image.alpha_composite(im.convert("RGBA"), blob).convert("RGB")
        im = im.resize((w,h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(radius=6))
        self.bg_qpix = pil_to_qpixmap(im)
        pix = self.bg_qpix.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        palette = self.palette(); palette.setBrush(self.backgroundRole(), pix); self.setPalette(palette)
        self.bg_base = im

    # ---------------- Trail effect (smoky line + blur) ----------------
    def mouseMoveEvent(self, ev):
        pos = ev.position() if hasattr(ev, "position") else ev.windowPos()
        x, y = int(pos.x()), int(pos.y())
        self.trail.append((x, y, time.time()))
        super().mouseMoveEvent(ev)

    def _update_trail_overlay(self):
        if not hasattr(self, "bg_base"): return
        base = self.bg_base.copy().convert("RGBA")
        sw, sh = max(200, base.width//3), max(120, base.height//3)
        overlay = Image.new("RGBA", (sw, sh), (0,0,0,0)); draw = ImageDraw.Draw(overlay)
        pts = list(self.trail)
        if len(pts) >= 2 and self.trail_level != "off":
            # draw lines on small overlay
            for i in range(1, len(pts)):
                x1, y1, t1 = pts[i-1]; x2, y2, t2 = pts[i]
                sx1 = int(x1 * sw / max(1, self.width())); sy1 = int(y1 * sh / max(1, self.height()))
                sx2 = int(x2 * sw / max(1, self.width())); sy2 = int(y2 * sh / max(1, self.height()))
                age = time.time() - t2
                alpha = max(20, int(220 * max(0.0, 1 - age/1.6)))
                base_width = 14 if self.trail_level=="high" else (9 if self.trail_level=="med" else 5)
                width = max(1, int(base_width * (1 - age/2)))
                draw.line([(sx1,sy1),(sx2,sy2)], fill=(200,230,255,alpha), width=width)
            blur_amount = {"low":4,"med":8,"high":12}.get(self.trail_level,8)
            overlay = overlay.filter(ImageFilter.GaussianBlur(radius=blur_amount))
            overlay_large = overlay.resize(base.size, Image.Resampling.BICUBIC)
            base = Image.alpha_composite(base, overlay_large)
            self.bg_qpix = pil_to_qpixmap(base.convert("RGB"))
            pix = self.bg_qpix.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            palette = self.palette(); palette.setBrush(self.backgroundRole(), pix); self.setPalette(palette)

    # ---------------- UI actions ----------------
    def on_load(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Select media", os.getcwd(),
                                            "Images & Videos (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.avi)")
        if not fn: return
        self.current_path = fn
        try:
            if fn.lower().endswith((".mp4",".avi",".mov")):
                cap = cv2.VideoCapture(fn); ret, frame = cap.read(); cap.release()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(frame)
                    self._show_preview_pil(pil)
            else:
                pil = Image.open(fn)
                self._show_preview_pil(pil)
        except Exception as e:
            print("Load error:", e)

    def on_render(self):
        if not self.current_path: return
        # collect settings
        self.settings["ascii_chars"] = self.ascii_input.text() or DEFAULT_ASCII
        self.settings["brightness"] = self.brightness_slider.value()/100.0
        self.settings["contrast"] = self.contrast_slider.value()/100.0
        self.settings["gamma"] = self.gamma_slider.value()/100.0
        self.settings["invert"] = self.invert_chk.isChecked()
        self.settings["watermark"] = self.watermark_chk.isChecked()
        self.render_btn.setEnabled(False)
        worker = RenderWorker(self.current_path, self.width_chars, self.font_size, self.style, self.fg_hex, self.bg_hex, self.settings)
        worker.finished.connect(self._on_render_finished)
        worker.start()

    def _on_render_finished(self, pil_img):
        self.render_btn.setEnabled(True)
        if pil_img is None:
            print("Render failed")
            return
        self.current_output = pil_img
        self._show_preview_pil(pil_img)
        self._add_gallery_item(pil_img)

    def on_export(self):
        if not self.current_output: return
        fn, _ = QFileDialog.getSaveFileName(self, "Save", os.getcwd(), "PNG Image (*.png);;GIF (*.gif)")
        if not fn: return
        try:
            if fn.lower().endswith(".gif"):
                imageio.mimsave(fn, [np.array(self.current_output)], duration=0.6)
            else:
                self.current_output.save(fn)
        except Exception as e:
            print("Export error:", e)

    def on_width_changed(self, v):
        self.width_chars = int(v); self.width_val_label.setText(str(self.width_chars))

    def on_font_changed(self, v):
        self.font_size = int(v); self.font_val_label.setText(str(self.font_size))

    def on_gallery_click(self, item):
        pil = item.data(Qt.UserRole)
        if pil:
            viewer = FullscreenViewer(self, pil)
            viewer.exec_()

    def _add_gallery_item(self, pil):
        thumb = pil.copy(); thumb.thumbnail((140,140), Image.Resampling.LANCZOS)
        qpix = pil_to_qpixmap(thumb)
        item = QListWidgetItem()
        item.setIcon(QIcon(qpix)); item.setData(Qt.UserRole, pil)
        self.gallery_list.addItem(item)

    def _show_preview_pil(self, pil):
        lbl_w = max(300, self.preview_label.width() or 800); lbl_h = max(200, self.preview_label.height() or 500)
        iw, ih = pil.size; scale = min(lbl_w/iw, lbl_h/ih, 1.0)
        nw, nh = max(1,int(iw*scale)), max(1,int(ih*scale))
        res = pil.resize((nw,nh), Image.Resampling.LANCZOS)
        qpix = pil_to_qpixmap(res)
        self.preview_label.setPixmap(qpix)

    def _preview_clicked(self, event):
        if self.current_output is not None:
            viewer = FullscreenViewer(self, self.current_output)
            viewer.exec_()

    # ------------- Settings dialog --------------
    def open_settings_dialog(self):
        dlg = QDialog(self); dlg.setWindowTitle("Settings"); fl = QFormLayout(dlg)
        lang_combo = QComboBox(); lang_combo.addItems(list(TRANSLATIONS.keys())); lang_combo.setCurrentText(self.lang)
        fl.addRow("Language:", lang_combo)
        device_combo = QComboBox(); device_combo.addItem("cpu")
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0: device_combo.addItem("gpu")
        except: pass
        device_combo.setCurrentText(self.device_combo.currentText())
        fl.addRow("Device:", device_combo)
        ok = QPushButton("OK"); cancel = QPushButton("Cancel")
        row = QHBoxLayout(); row.addWidget(ok); row.addWidget(cancel); fl.addRow(row)
        ok.clicked.connect(lambda: (self._apply_settings_dialog(lang_combo.currentText(), device_combo.currentText()), dlg.accept()))
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _apply_settings_dialog(self, langkey, devicekey):
        self.lang = langkey
        # apply device if present
        if "gpu" in devicekey: self.device_combo.setCurrentText("gpu")
        else: self.device_combo.setCurrentText("cpu")
        # update translations simple (load/render/export)
        t = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        self.load_btn.setText(t["load"]); self.render_btn.setText(t["render"]); self.export_btn.setText(t["export"])
        self.title_label.setText("ASCII Studio - " + t.get("settings","Settings"))

    # -------------- Themes --------------
    def _apply_theme(self, name):
        theme = THEMES.get(name, THEMES["dark"])
        self.bg_hex = theme["bg"]
        accent = theme["accent"]
        glass = theme["glass"]
        # update some CSS dynamic parts
        self.setStyleSheet(f"""
            QLabel {{ color: #e6eef6; }}
            QFrame#left_frame {{ background: rgba(255,255,255,0.02); border-radius:14px; }}
            QFrame#right_frame {{ background: {glass}; border-radius:14px; padding:8px; }}
            QPushButton {{ background: rgba(20,20,25,0.55); color: white; border-radius:8px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.06); }}
            QListWidget {{ background: rgba(255,255,255,0.02); border-radius:12px; color: #dfe8f2; }}
        """)
        self._update_background()

# -------------------- Run --------------------
def main():
    app = QApplication(sys.argv)
    win = MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
