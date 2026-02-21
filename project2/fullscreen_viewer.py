# fullscreen_viewer.py
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent, QMouseEvent
from utils import pil_to_qpixmap
from PIL import Image

class FullscreenViewer(QDialog):
    def __init__(self, pil_img, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.setWindowState(self.windowState() | Qt.WindowFullScreen)
        self.setWindowFlag(Qt.FramelessWindowHint)

        self.orig = pil_img.copy()
        self.zoom = 1.0
        self.pan = [0,0]

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)

        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(56,56)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton{background:rgba(0,0,0,0.55);color:white;border:0;border-radius:28px;}
            QPushButton:hover{background:rgba(255,255,255,0.15);}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.label)
        self.label.installEventFilter(self)
        self._update()

    def _update(self):
        w = max(1,int(self.orig.width*self.zoom))
        h = max(1,int(self.orig.height*self.zoom))
        img = self.orig.resize((w,h),Image.Resampling.LANCZOS)
        pix = pil_to_qpixmap(img)
        self.label.setPixmap(pix)
        self.close_btn.move(self.width()-80,20)

    def eventFilter(self,obj,event):
        if isinstance(event,QWheelEvent):
            if event.angleDelta().y()>0: self.zoom*=1.15
            else: self.zoom/=1.15
            self._update()
            return True
        return super().eventFilter(obj,event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:
            self.close()
