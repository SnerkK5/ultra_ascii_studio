# gallery.py
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtGui import QIcon
from utils import pil_to_qpixmap

class GalleryList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(self.iconSize())
        self.setResizeMode(QListWidget.Adjust)

    def add_pil(self, pil_img):
        thumb = pil_img.copy()
        thumb.thumbnail((140,140),Image.Resampling.LANCZOS)
        pix = pil_to_qpixmap(thumb)
        item = QListWidgetItem(QIcon(pix), "")
        item.setData(256,pil_img)  # Qt.UserRole = 256
        self.addItem(item)
