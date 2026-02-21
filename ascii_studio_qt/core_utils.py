from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance
import numpy as np
from PySide6.QtGui import QImage, QPixmap

# Shared constants
DEFAULT_ASCII = "@%#*+=-:. "
WATERMARK = "SNERK503"

def pil_to_qpixmap(pil_image):
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")
    data = pil_image.tobytes("raw", "RGBA")
    qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage)

def image_to_ascii_data(pil_img, width_chars, ascii_chars=DEFAULT_ASCII, invert=False, contrast_pct=100):
    img = pil_img.convert("RGB")
    if contrast_pct != 100:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(max(0.01, contrast_pct/100.0))
    if invert:
        # invert per-channel
        r,g,b = img.split()
        img = Image.merge('RGB', (ImageOps.invert(r), ImageOps.invert(g), ImageOps.invert(b)))
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

def render_ascii_pil(ascii_data, font_size=12, style="bw", fg_hex="#FFFFFF", bg_hex="#0F0F12", output_size=None, watermark=True):
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
    try:
        rfg = tuple(int(fg_hex.lstrip("#")[i:i+2],16) for i in (0,2,4))
    except Exception:
        rfg = (255,255,255)
    for y,row in enumerate(ascii_data):
        for x,(chc, color) in enumerate(row):
            # style mapping
            if style == "bw":
                fill = (255,255,255)
            elif style == "red":
                fill = (255,60,60)
            elif style == "color":
                # use source pixel color but darken for visibility
                fill = tuple(max(0, int(c*0.9)) for c in color)
            elif style == "matrix":
                fill = (0,255,120)
            elif style == "matrix2":
                fill = (0,200,80)
            elif style == "neon":
                # neon: brighten and bias towards cyan/magenta
                fill = (min(255, color[0]+60), min(255, color[1]+20), min(255, color[2]+80))
            elif style == "pastel":
                fill = (min(255, int((color[0]+240)/2)), min(255, int((color[1]+220)/2)), min(255, int((color[2]+200)/2)))
            elif style == "custom":
                fill = rfg
            else:
                fill = (255,255,255)
            draw.text((x*cw, y*ch), chc, fill=fill, font=font)
    if watermark:
        draw.text((8, max(h-18,0)), WATERMARK, fill=(120,120,120), font=font)
    if output_size and isinstance(output_size, tuple) and output_size != (w,h):
        try:
            im = im.resize(output_size, Image.Resampling.LANCZOS)
        except Exception:
            pass
    return im
