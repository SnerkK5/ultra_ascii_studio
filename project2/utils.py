# utils.py
from PySide6.QtGui import QImage, QPixmap
from PIL import Image
import cv2

def pil_to_qpixmap(pil_image):
    """Конвертация PIL‑изображения в QPixmap"""
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")
    data = pil_image.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)

def gpu_available():
    """
    Проверка наличия GPU с CUDA в OpenCV
    Возвращает True, если cv2.cuda.getCudaEnabledDeviceCount()>0
    """
    try:
        return cv2.cuda.getCudaEnabledDeviceCount() > 0
    except Exception:
        return False
