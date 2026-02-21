# render_core.py
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import cv2

DEFAULT_ASCII = "@%#*+=-:. "

def adjust_image(pil, brightness, contrast, gamma, invert):
    """Коррекция яркости/контраста/гаммы/инверт."""
    img = pil.convert("RGB")
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if gamma != 1.0:
        inv_gamma = 1.0 / gamma
        lut = [pow(i/255.0, inv_gamma)*255 for i in range(256)]
        lut = [int(max(0,min(255,v))) for v in lut]
        img = img.point(lut*3)
    if invert:
        img = ImageOps.invert(img)
    return img

def to_ascii_basic(img, width_chars, ascii_chars):
    """Базовый ASCII рендер."""
    w,h = img.size
    height = max(1, int(h/w * width_chars * 0.55))
    small = img.resize((width_chars,height), Image.Resampling.BICUBIC)
    arr = np.array(small)
    lines = []
    for row in arr:
        rline = ""
        for px in row:
            b = int(px.mean())
            idx = b*(len(ascii_chars)-1)//255
            rline += ascii_chars[idx]
        lines.append(rline)
    return lines

def to_ascii_gradient(img, width_chars, ascii_chars):
    """ASCII с антиалиасом => градиент."""
    arr = np.array(img.convert("L"))
    grad = cv2.Laplacian(arr,cv2.CV_64F)
    grad = np.clip(np.abs(grad),0,255).astype(np.uint8)
    pil = Image.fromarray(grad)
    return to_ascii_basic(pil, width_chars, ascii_chars[::-1])

def to_ascii_edges(img, width_chars, ascii_chars):
    """Edge-Aware ASCII через Sobel."""
    arr = np.array(img.convert("L"))
    sx = cv2.Sobel(arr,cv2.CV_64F,1,0,ksize=3)
    sy = cv2.Sobel(arr,cv2.CV_64F,0,1,ksize=3)
    mag = np.sqrt(sx*sx+sy*sy)
    mag = np.clip(mag,0,255).astype(np.uint8)
    pil = Image.fromarray(mag)
    return to_ascii_basic(pil, width_chars, ascii_chars)

def to_ascii_color(img, width_chars, ascii_chars):
    """Цветной ASCII — яркость + цвет."""
    w,h = img.size
    height = max(1, int(h/w * width_chars * 0.55))
    small = img.resize((width_chars,height), Image.Resampling.BICUBIC)
    arr = np.array(small)
    lines = []
    colors = []
    for row in arr:
        rline = ""
        crow = []
        for px in row:
            b = int(px.mean())
            idx = b*(len(ascii_chars)-1)//255
            rline += ascii_chars[idx]
            crow.append(tuple(px.tolist()))
        lines.append(rline)
        colors.append(crow)
    return lines, colors

def auto_select_mode(img):
    """Автовыбор режима — на основе размера или контраста."""
    # простая эвристика: если много резких деталей → edge
    arr = np.array(img.convert("L"))
    std = arr.std()
    if std > 70:
        return "edge"
    if arr.mean() < 80:
        return "gradient"
    return "basic"
