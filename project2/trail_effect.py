# trail_effect.py
import time
from collections import deque
from PIL import Image, ImageDraw, ImageFilter

class TrailEffect:
    def __init__(self, intensity="med"):
        self.trail = deque(maxlen=120)
        self.intensity = intensity

    def set_intensity(self, level):
        self.intensity = level
        sizes = {"off":0,"low":40,"med":80,"high":120}
        self.trail = deque(maxlen=sizes.get(level,80))

    def add_point(self, x,y):
        self.trail.append((x,y,time.time()))

    def render(self, base_image, size):
        if self.intensity=="off" or len(self.trail)<3:
            return base_image
        sw,sh = size
        overlay = Image.new("RGBA",(sw,sh),(0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        pts = list(self.trail)
        now = time.time()
        for i in range(1,len(pts)):
            x1,y1,t1 = pts[i-1]
            x2,y2,t2 = pts[i]
            age = now - t2
            if age>1.5: continue
            alpha = int(200*(1-age/1.5))
            width = 14 if self.intensity=="high" else (8 if self.intensity=="med" else 4)
            draw.line([(x1,y1),(x2,y2)], fill=(220,230,255,alpha), width=width)
        blur = {"low":3,"med":6,"high":9}.get(self.intensity,6)
        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=blur))
        return Image.alpha_composite(base_image.convert("RGBA"), overlay)
