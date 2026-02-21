# ui_main.py
import os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QSlider, QComboBox, QFileDialog, QCheckBox, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox
)
from PIL import Image

from localization import LOCALES
from themes import THEMES
from utils import pil_to_qpixmap, gpu_available
from render_core import (
    adjust_image, to_ascii_basic, to_ascii_gradient,
    to_ascii_edges, to_ascii_color, auto_select_mode
)
from trail_effect import TrailEffect
from gallery import GalleryList
from fullscreen_viewer import FullscreenViewer
from settings_dialog import SettingsManager


class MainWindow(QWidget):
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings

        self.lang = settings.get("language", "en")
        self.theme_name = settings.get("theme", "dark")
        self.device = settings.get("render_device", "cpu")
        self.mode = settings.get("default_mode", "Auto")
        self.trail_effect = TrailEffect(settings.get("trail_intensity", "med"))
        self.current_output = None
        self.current_path = None

        self.width_chars = 240
        self.font_size = 12

        self.init_ui()
        self.apply_theme(self.theme_name)
        self.apply_locale(self.lang)

        self.trail_timer = QTimer(self)
        self.trail_timer.timeout.connect(self.repaint)
        self.trail_timer.start(30)

        self.setMouseTracking(True)

    def init_ui(self):
        self.setWindowTitle("ASCII Studio – SNERK503")
        self.setMinimumSize(1200, 720)

        root = QHBoxLayout(self); self.setLayout(root)

        self.preview_label = QLabel(alignment=Qt.AlignCenter)
        self.preview_label.setStyleSheet("background: transparent;")
        self.preview_label.setMinimumSize(680, 380)
        root.addWidget(self.preview_label, 1)

        right = QVBoxLayout(); root.addLayout(right, 0)

        self.btn_load = QPushButton()
        self.btn_render = QPushButton()
        self.btn_export = QPushButton()

        self.btn_load.clicked.connect(self.on_load)
        self.btn_render.clicked.connect(self.on_render)
        self.btn_export.clicked.connect(self.on_export)

        for b in (self.btn_load, self.btn_render, self.btn_export):
            b.setFixedHeight(40); b.setCursor(Qt.PointingHandCursor)

        row = QHBoxLayout()
        row.addWidget(self.btn_load); row.addWidget(self.btn_render); row.addWidget(self.btn_export)
        right.addLayout(row)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        right.addWidget(self.theme_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Auto", "Basic", "Gradient", "Edges", "Color"])
        self.mode_combo.currentTextChanged.connect(lambda v: setattr(self, "mode", v))
        self.mode_combo.setCurrentText(self.mode)
        right.addWidget(self.mode_combo)

        right.addWidget(QLabel("Width (chars):"))
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(80, 700); self.width_slider.setValue(self.width_chars)
        self.width_slider.valueChanged.connect(self.on_width_changed)
        self.width_label = QLabel(str(self.width_chars))
        wrow = QHBoxLayout()
        wrow.addWidget(self.width_slider); wrow.addWidget(self.width_label)
        right.addLayout(wrow)

        right.addWidget(QLabel("Font size:"))
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(6, 36); self.font_slider.setValue(self.font_size)
        self.font_slider.valueChanged.connect(self.on_font_changed)
        self.font_label = QLabel(str(self.font_size))
        frow = QHBoxLayout()
        frow.addWidget(self.font_slider); frow.addWidget(self.font_label)
        right.addLayout(frow)

        adv = QGroupBox("Render settings")
        adv_layout = QFormLayout(adv)

        self.brightness = QSpinBox(); self.brightness.setRange(50, 200)
        self.brightness.setValue(int(self.settings.get("brightness",1.0)*100))
        adv_layout.addRow("Brightness:", self.brightness)

        self.contrast = QSpinBox(); self.contrast.setRange(50, 200)
        self.contrast.setValue(int(self.settings.get("contrast",1.0)*100))
        adv_layout.addRow("Contrast:", self.contrast)

        self.gamma = QSpinBox(); self.gamma.setRange(50, 200)
        self.gamma.setValue(int(self.settings.get("gamma",1.0)*100))
        adv_layout.addRow("Gamma:", self.gamma)

        self.chk_invert = QCheckBox(); self.chk_invert.setChecked(self.settings.get("invert",False))
        adv_layout.addRow("Invert:", self.chk_invert)

        self.chk_water = QCheckBox(); self.chk_water.setChecked(self.settings.get("watermark",True))
        adv_layout.addRow("Watermark:", self.chk_water)

        self.charset_input = QLineEdit(self.settings.get("ascii_chars","@%#*+=-:. "))
        adv_layout.addRow("ASCII charset:", self.charset_input)

        right.addWidget(adv)

        right.addWidget(QLabel("Render device:"))
        self.device_combo = QComboBox()
        self.device_combo.addItem("cpu")
        if gpu_available():
            self.device_combo.addItem("gpu")
        self.device_combo.setCurrentText(self.device)
        right.addWidget(self.device_combo)

        right.addWidget(QLabel("Trail intensity:"))
        self.trail_combo = QComboBox()
        self.trail_combo.addItems(["off","low","med","high"])
        self.trail_combo.setCurrentText(self.settings.get("trail_intensity","med"))
        self.trail_combo.currentTextChanged.connect(self.on_trail_changed)
        right.addWidget(self.trail_combo)

        right.addWidget(QLabel("Gallery:"))
        self.gallery = GalleryList()
        self.gallery.itemClicked.connect(self.on_gallery_click)
        right.addWidget(self.gallery)

        right.addStretch(1)

    # ---------- UI callbacks ----------

    def on_width_changed(self,val):
        self.width_chars = val; self.width_label.setText(str(val))

    def on_font_changed(self,val):
        self.font_size = val; self.font_label.setText(str(val))

    def on_trail_changed(self,val):
        self.trail_effect.set_intensity(val)
        self.settings.set("trail_intensity", val)

    def on_theme_changed(self,val):
        self.apply_theme(val)
        self.settings.set("theme",val)

    def on_load(self):
        fn,_ = QFileDialog.getOpenFileName(self,"Select media",os.getcwd(),
            "Images & Video (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.avi)")
        if fn:
            try:
                img = Image.open(fn)
                self.current_path = fn
                self.draw_preview(img)
            except Exception as e:
                print("Load:",e)

    def on_gallery_click(self,item):
        pil = item.data(256)
        if pil:
            viewer = FullscreenViewer(pil, self)
            viewer.exec()

    def on_export(self):
        if not self.current_output:
            return
        fn,_ = QFileDialog.getSaveFileName(self,"Save",os.getcwd(),"PNG Image (*.png)")
        if fn:
            try:
                self.current_output.save(fn)
            except Exception as e:
                print("Export:",e)

    def on_render(self):
        if not self.current_path:
            return
        self.btn_render.setEnabled(False)

        img = Image.open(self.current_path)
        adj = adjust_image(img,
            self.brightness.value()/100.0,
            self.contrast.value()/100.0,
            self.gamma.value()/100.0,
            self.chk_invert.isChecked()
        )

        cs = self.charset_input.text() or "@%#*+=-:."
        mode = self.mode
        if mode=="Auto":
            mode = auto_select_mode(adj)

        if mode=="Basic":
            lines = to_ascii_basic(adj,self.width_chars,cs)
        elif mode=="Gradient":
            lines = to_ascii_gradient(adj,self.width_chars,cs)
        elif mode=="Edges":
            lines = to_ascii_edges(adj,self.width_chars,cs)
        elif mode=="Color":
            lines,colors = to_ascii_color(adj,self.width_chars,cs)
        else:
            lines = to_ascii_basic(adj,self.width_chars,cs)

        from PIL import ImageDraw,ImageFont
        text = "\n".join(lines)
        img_out = Image.new("RGB",(self.width_chars*self.font_size, len(lines)*self.font_size), "#000000")
        try:
            font = ImageFont.truetype("Consolas.ttf",self.font_size)
        except:
            font = ImageFont.load_default()
        draw = ImageDraw.Draw(img_out)
        y=0
        for row in lines:
            draw.text((0,y),row,fill="#FFFFFF",font=font)
            y+=self.font_size

        self.current_output = img_out
        self.btn_render.setEnabled(True)
        self.draw_preview(img_out)
        self.gallery.add_pil(img_out)

        self.settings.set("language",self.lang)
        self.settings.set("default_mode",self.mode)
        self.settings.set("ascii_chars",cs)
        self.settings.set("brightness",self.brightness.value()/100.0)
        self.settings.set("contrast",self.contrast.value()/100.0)
        self.settings.set("gamma",self.gamma.value()/100.0)
        self.settings.set("invert",self.chk_invert.isChecked())
        self.settings.set("watermark",self.chk_water.isChecked())

    def draw_preview(self,pil):
        w = max(200,self.preview_label.width())
        h = max(150,self.preview_label.height())
        img = pil.copy()
        img.thumbnail((w,h),Image.Resampling.LANCZOS)
        pix = pil_to_qpixmap(img)
        self.preview_label.setPixmap(pix)

    def apply_theme(self,name):
        t = THEMES.get(name, THEMES["dark"])
        self.setStyleSheet(f"""
            QWidget{{background:{t['bg']};color:{t['font_color']};}}
            QPushButton{{background:{t['glass']};border-radius:6px;padding:6px;}}
            QPushButton:hover{{background:rgba(255,255,255,0.08);}}
        """)

    def apply_locale(self,lang):
        self.lang = lang
        L = LOCALES.get(lang, LOCALES["en"])
        self.btn_load.setText(L["load"])
        self.btn_render.setText(L["render"])
        self.btn_export.setText(L["export"])
