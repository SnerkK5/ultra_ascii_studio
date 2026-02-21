# ultra_ascii_ui_v5.py
# Ultra ASCII Studio v5 — polished UI: localization, glass panels, smoke trail, responsive layout, performance
# Dependencies: customtkinter, pillow, numpy, opencv-python, imageio

import os
import json
import threading
import traceback
import random
import time
from pathlib import Path
from tkinter import filedialog, colorchooser, Toplevel, Canvas
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter
import numpy as np
import cv2
import imageio

# ---------------- CONFIG ----------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

APP_TITLE = "ASCII ULTRA PREMIUM PRO – SNERK503"

PALETTE = {
    "bg0": "#0e1117",
    "bg1": "#121826",
    "glass_tint": (18, 20, 24),
    "accent": "#1DB954",
    "cyan": "#00E5FF",
    "purple": "#8A2BE2",
    "muted": "#9aa4b2",
}

ASCII_CHARS = "@%#*+=-:. "
WATERMARK_TEXT = "SNERK503"

DEFAULT_FONT_PATHS = [
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
]

TRANSLATIONS = {}

# load bundled translations
def load_bundled_translations():
    global TRANSLATIONS
    TRANSLATIONS = {
        "en": {
            "app": "ASCII ULTRA",
            "author": "SNERK503",
            "controls": "Controls",
            "load": "Load",
            "render": "Render",
            "export": "Export",
            "style": "Style",
            "width": "Width (chars)",
            "font": "Font size",
            "text_color": "Text color",
            "bg_color": "BG color",
            "gallery": "Gallery",
            "trail": "Trail",
            "trail_off": "Off",
            "trail_low": "Low",
            "trail_med": "Medium",
            "trail_high": "High",
            "theme": "Theme",
        },
        "ru": {
            "app": "ASCII ULTRA",
            "author": "SNERK503",
            "controls": "Управление",
            "load": "Загрузить",
            "render": "Рендер",
            "export": "Экспорт",
            "style": "Стиль",
            "width": "Ширина (симв.)",
            "font": "Размер шрифта",
            "text_color": "Цвет текста",
            "bg_color": "Цвет фона",
            "gallery": "Галерея",
            "trail": "Хвост",
            "trail_off": "Выкл",
            "trail_low": "Низкий",
            "trail_med": "Средний",
            "trail_high": "Высокий",
            "theme": "Тема",
        },
        "zh": {
            "app": "ASCII ULTRA",
            "author": "SNERK503",
            "controls": "控制",
            "load": "加载",
            "render": "渲染",
            "export": "导出",
            "style": "样式",
            "width": "宽度 (字符)",
            "font": "字体大小",
            "text_color": "文字颜色",
            "bg_color": "背景颜色",
            "gallery": "画廊",
            "trail": "尾迹",
            "trail_off": "关闭",
            "trail_low": "低",
            "trail_med": "中",
            "trail_high": "高",
            "theme": "主题",
        }
    }

# dynamic load translations from folder translations/
def load_translations_from_folder(folder="translations"):
    global TRANSLATIONS
    p = Path(folder)
    if not p.exists():
        return
    for j in p.glob("*.json"):
        try:
            with open(j, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        TRANSLATIONS.setdefault(k, {}).update(v)
        except Exception:
            pass

# initial load
load_bundled_translations()
load_translations_from_folder()

# -------------- Utils ----------------
_font_cache = {}
_ascii_cache = {}
_settings_path = Path("~").expanduser() / ".ultra_ascii_settings.json"


def save_settings(d):
    try:
        _settings = {}
        if _settings := d:
            with open(_settings_path, "w", encoding="utf-8") as f:
                json.dump(_settings, f)
    except Exception:
        pass


def load_settings():
    try:
        if _settings_path.exists():
            with open(_settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def safe_font(size):
    if size in _font_cache:
        return _font_cache[size]
    for p in DEFAULT_FONT_PATHS:
        try:
            if os.path.exists(p):
                f = ImageFont.truetype(p, size)
                _font_cache[size] = f
                return f
        except Exception:
            continue
    f = ImageFont.load_default()
    _font_cache[size] = f
    return f


def color_to_rgb(hexc):
    hexc = hexc.lstrip("#")
    return tuple(int(hexc[i:i+2], 16) for i in (0, 2, 4))


# ---------------- ASCII engine (with cache) ----------------
def image_to_ascii_data(image_pil, width_chars, ascii_chars=ASCII_CHARS, src_path=None):
    key = (src_path, width_chars, ascii_chars)
    if key in _ascii_cache:
        return _ascii_cache[key]
    if image_pil.mode != "RGB":
        img = image_pil.convert("RGB")
    else:
        img = image_pil
    w, h = img.size
    rows = max(1, int((h / w) * width_chars * 0.55))
    small = img.resize((width_chars, rows), Image.Resampling.BICUBIC)
    arr = np.array(small)
    data = []
    for row in arr:
        line = []
        for px in row:
            b = int(px.mean())
            idx = b * (len(ascii_chars)-1) // 255
            line.append((ascii_chars[idx], tuple(int(x) for x in px)))
        data.append(line)
    _ascii_cache[key] = data
    return data


def render_ascii_image(data, font_size=12, style="bw", custom_fg="#FFFFFF", bg_hex="#0F0F12"):
    font = safe_font(font_size)
    try:
        bbox = font.getbbox("A")
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]
    except Exception:
        char_w, char_h = font.getsize("A")
    cols = len(data[0]) if data else 0
    rows = len(data)
    w = max(1, int(cols * char_w))
    h = max(1, int(rows * char_h))
    out = Image.new("RGB", (w, h), bg_hex)
    draw = ImageDraw.Draw(out)
    try:
        custom_rgb = color_to_rgb(custom_fg)
    except Exception:
        custom_rgb = (255,255,255)
    for y, row in enumerate(data):
        for x, (ch, color) in enumerate(row):
            if style == "bw":
                fill = (255,255,255)
            elif style == "red":
                fill = (255,60,60)
            elif style == "color":
                fill = color
            elif style == "matrix":
                fill = (0,255,120)
            elif style == "custom":
                fill = custom_rgb
            else:
                fill = (255,255,255)
            draw.text((x*char_w, y*char_h), ch, fill=fill, font=font)
    draw.text((10, max(h-20,0)), WATERMARK_TEXT, fill=(120,120,120), font=font)
    return out


# ---------------- Video frames ----------------
def process_video_to_frames(input_path, width_chars, style, custom_fg, bg_hex, progress_cb=None, stop_event=None):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError("Can't open video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or -1
    frames = []
    idx = 0
    while True:
        if stop_event and stop_event.is_set():
            break
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(frame)
        data = image_to_ascii_data(pil, width_chars, src_path=input_path)
        out = render_ascii_image(data, font_size=12, style=style, custom_fg=custom_fg, bg_hex=bg_hex)
        frames.append(np.array(out))
        idx += 1
        if progress_cb and total>0:
            progress_cb(idx, total)
    cap.release()
    return frames, fps


# ----------------- App --------------------
class UltraASCIIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1000,700)

        # load settings
        self.settings = load_settings() or {}

        # state
        self.file_path = None
        self.output_pil = None
        self.gallery = []
        self.render_thread = None
        self.stop_event = None

        # settings
        self.lang = self.settings.get("lang", "en") if self.settings else "en"
        if self.lang not in TRANSLATIONS:
            self.lang = list(TRANSLATIONS.keys())[0]
        self.style = "bw"
        self.width_chars = self.settings.get("width_chars", 400)
        self.font_size = self.settings.get("font_size", 12)
        self.custom_fg = self.settings.get("custom_fg", "#FFFFFF")
        self.bg_hex = self.settings.get("bg_hex", "#0F1113")
        self.trail_mode = self.settings.get("trail_mode", "med")

        # background
        self.bg_base = None
        self.bg_combo_tk = None

        # trail history (motion sampling)
        self.trail_history = []  # recent mouse points (x,y,t)
        self.trail_max_history = 40
        self.trail_params = {"off": (0,0.0), "low": (20,0.6), "med": (40,0.5), "high": (60,0.4)}

        # build UI
        self._build_ui()
        self.bind("<Configure>", self._on_resize)
        self.bind("<Motion>", self._on_mouse_move)
        # start background loop at ~25fps
        self._last_frame_time = 0
        self.after(16, self._bg_update_loop)

    # --- UI build
    def _build_ui(self):
        self.canvas = Canvas(self, bg=PALETTE["bg0"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # initial bg
        self._regen_bg((1400,900))
        self.canvas.create_image(0,0,anchor="nw",image=self.bg_combo_tk,tags="bgimg")

        # top panel (glass image + transparent frame)
        self.top_frame = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self.top_win = self.canvas.create_window(20, 16, anchor="nw", window=self.top_frame)
        # references for labels to update on locale change
        self.app_lbl = ctk.CTkLabel(self.top_frame, text=TRANSLATIONS[self.lang]["app"], font=ctk.CTkFont(size=16, weight="bold"))
        self.app_lbl.pack(side="left")
        self.author_lbl = ctk.CTkLabel(self.top_frame, text=TRANSLATIONS[self.lang]["author"], text_color=PALETTE["muted"]) 
        self.author_lbl.pack(side="left", padx=(8,0))

        # right controls
        self.right_frame = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self.right_win = self.canvas.create_window(980, 20, anchor="nw", window=self.right_frame)

        # preview
        self.preview_frame = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self.preview_win = self.canvas.create_window(20, 120, anchor="nw", window=self.preview_frame)

        # gallery
        self.gallery_frame = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self.gallery_win = self.canvas.create_window(20, 700, anchor="nw", window=self.gallery_frame)

        # right controls content
        self.controls_lbl = ctk.CTkLabel(self.right_frame, text=TRANSLATIONS[self.lang]["controls"], font=ctk.CTkFont(size=14, weight="bold"))
        self.controls_lbl.pack(pady=(8,6))

        btn_row = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        btn_row.pack(padx=8, pady=(6,8))
        self.load_btn = ctk.CTkButton(btn_row, text=TRANSLATIONS[self.lang]["load"], command=self._load_file, fg_color="#172022", hover_color="#29403a")
        self.load_btn.pack(side="left", padx=6)
        self.render_btn = ctk.CTkButton(btn_row, text=TRANSLATIONS[self.lang]["render"], command=self._render_image, fg_color=PALETTE["accent"], hover_color="#279a4a")
        self.render_btn.pack(side="left", padx=6)
        self.export_btn = ctk.CTkButton(btn_row, text=TRANSLATIONS[self.lang]["export"], command=self._export_image, fg_color="#172022", hover_color="#2b3335")
        self.export_btn.pack(side="left", padx=6)

        # style
        self.style_lbl = ctk.CTkLabel(self.right_frame, text=TRANSLATIONS[self.lang]["style"]) 
        self.style_lbl.pack(anchor="w", padx=8)
        self.style_opt = ctk.CTkOptionMenu(self.right_frame, values=["bw","red","color","matrix","custom"], command=self._style_changed)
        self.style_opt.set(self.style)
        self.style_opt.pack(padx=8, pady=6, fill="x")

        # width slider + indicator
        self.width_title_lbl = ctk.CTkLabel(self.right_frame, text=TRANSLATIONS[self.lang]["width"]) 
        self.width_title_lbl.pack(anchor="w", padx=8)
        wrow = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        wrow.pack(fill="x", padx=8)
        self.width_slider = ctk.CTkSlider(wrow, from_=80, to=900, command=self._width_changed)
        self.width_slider.set(self.width_chars)
        self.width_slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self.width_val_lbl = ctk.CTkLabel(wrow, text=str(self.width_chars), width=48)
        self.width_val_lbl.pack(side="left")

        # font slider + indicator
        self.font_title_lbl = ctk.CTkLabel(self.right_frame, text=TRANSLATIONS[self.lang]["font"]) 
        self.font_title_lbl.pack(anchor="w", padx=8)
        frow = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        frow.pack(fill="x", padx=8)
        self.font_slider = ctk.CTkSlider(frow, from_=6, to=28, command=self._font_changed)
        self.font_slider.set(self.font_size)
        self.font_slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self.font_val_lbl = ctk.CTkLabel(frow, text=str(self.font_size), width=48)
        self.font_val_lbl.pack(side="left")

        # trail intensity
        self.trail_lbl = ctk.CTkLabel(self.right_frame, text=TRANSLATIONS[self.lang]["trail"]) 
        self.trail_lbl.pack(anchor="w", padx=8)
        self.trail_opt = ctk.CTkOptionMenu(self.right_frame, values=[TRANSLATIONS[self.lang]["trail_off"], TRANSLATIONS[self.lang]["trail_low"], TRANSLATIONS[self.lang]["trail_med"], TRANSLATIONS[self.lang]["trail_high"]], command=self._trail_changed)
        # map stored mode to label
        mode_map = {"off": TRANSLATIONS[self.lang]["trail_off"], "low": TRANSLATIONS[self.lang]["trail_low"], "med": TRANSLATIONS[self.lang]["trail_med"], "high": TRANSLATIONS[self.lang]["trail_high"]}
        self.trail_opt.set(mode_map.get(self.trail_mode, TRANSLATIONS[self.lang]["trail_med"]))
        self.trail_opt.pack(padx=8, pady=6, fill="x")

        # color pickers
        crow = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        crow.pack(padx=8, pady=8)
        self.pick_text_btn = ctk.CTkButton(crow, text=TRANSLATIONS[self.lang]["text_color"], command=self._pick_text_color)
        self.pick_text_btn.pack(side="left", padx=6)
        self.text_ind = ctk.CTkFrame(crow, width=28, height=28, fg_color=self.custom_fg, corner_radius=6)
        self.text_ind.pack(side="left", padx=(6,12))
        self.pick_bg_btn = ctk.CTkButton(crow, text=TRANSLATIONS[self.lang]["bg_color"], command=self._pick_bg_color)
        self.pick_bg_btn.pack(side="left", padx=6)
        self.bg_ind = ctk.CTkFrame(crow, width=28, height=28, fg_color=self.bg_hex, corner_radius=6)
        self.bg_ind.pack(side="left", padx=6)

        # progress bar
        self.prog = ctk.CTkProgressBar(self.right_frame, width=300)
        self.prog.set(0)
        self.prog.pack(padx=8, pady=(6,12))

        # preview canvas
        self.preview_canvas = Canvas(self.preview_frame, bg=PALETTE["bg1"], highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_tk = None

        # gallery scroll
        self.gallery_scroll = ctk.CTkScrollableFrame(self.gallery_frame, orientation="horizontal")
        self.gallery_scroll.pack(fill="both", expand=True, padx=6, pady=6)
        self.gallery_lbl = ctk.CTkLabel(self.gallery_frame, text=TRANSLATIONS[self.lang]["gallery"]) 
        self.gallery_lbl.pack(anchor="w", padx=6)

        self._layout_update()

    # ---------------- Layout & BG ----------------
    def _layout_update(self):
        W = max(800, self.winfo_width())
        H = max(600, self.winfo_height())
        # adaptive right width (clamped)
        right_w = max(320, min(420, int(W * 0.24)))
        top_h = 88
        # positions
        self.canvas.coords(self.top_win, 20, 16)
        self.canvas.itemconfigure(self.top_win, width=min(760, W-40), height=top_h)
        self.canvas.coords(self.right_win, W - right_w - 20, 20)
        self.canvas.itemconfigure(self.right_win, width=right_w, height=H - 160)
        self.canvas.coords(self.preview_win, 20, top_h + 28)
        preview_w = W - right_w - 60
        preview_h = H - 300
        self.canvas.itemconfigure(self.preview_win, width=preview_w, height=preview_h)
        self.canvas.coords(self.gallery_win, 20, top_h + preview_h + 40)
        self.canvas.itemconfigure(self.gallery_win, width=W - 40, height=160)
        # regenerate glass panels images (crop from bg)
        self._regen_panel_images()

    def _on_resize(self, event):
        w = max(800, self.winfo_width())
        h = max(600, self.winfo_height())
        if self.bg_base is None or self.bg_base.size[0] < w or self.bg_base.size[1] < h:
            self._regen_bg((w, h))
            self.canvas.delete("bgimg")
            self.canvas.create_image(0,0,anchor="nw",image=self.bg_combo_tk,tags="bgimg")
        self._layout_update()

    def _regen_bg(self, size):
        w, h = size
        base = Image.new("RGB", (w, h), PALETTE["bg0"])
        draw = ImageDraw.Draw(base)
        c1 = color_to_rgb(PALETTE["bg0"])
        c2 = color_to_rgb(PALETTE["bg1"])
        for y in range(h):
            t = y/(h-1)
            r = int(c1[0]*(1-t) + c2[0]*t)
            g = int(c1[1]*(1-t) + c2[1]*t)
            b = int(c1[2]*(1-t) + c2[2]*t)
            draw.line([(0,y),(w,y)], fill=(r,g,b))
        # soft glows
        glow = Image.new("RGBA", (w,h), (0,0,0,0))
        gd = ImageDraw.Draw(glow)
        spots = [
            (int(w*0.2), int(h*0.22), 0.5, PALETTE["purple"]),
            (int(w*0.8), int(h*0.16), 0.42, PALETTE["cyan"]),
            (int(w*0.75), int(h*0.78), 0.5, PALETTE["accent"]),
        ]
        for (cx, cy, scale, col) in spots:
            rgb = color_to_rgb(col)
            maxr = int(min(w,h)*0.5*scale)
            step = max(6, maxr//18)
            for r in range(maxr, 0, -step):
                alpha = int(max(2, 200*(1 - r/maxr)))
                gd.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(rgb[0],rgb[1],rgb[2], alpha))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=40))
        base = Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")
        base = base.filter(ImageFilter.GaussianBlur(radius=12))
        self.bg_base = base
        self.bg_combo_tk = ImageTk.PhotoImage(base)

    def _regen_panel_images(self):
        # crop+local blur+overlay+tinted rounded mask, place under each CTkFrame window
        for win_tag in [self.top_win, self.right_win, self.preview_win, self.gallery_win]:
            bbox = self.canvas.bbox(win_tag)
            if not bbox:
                continue
            x1,y1,x2,y2 = bbox
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            # crop region
            src = self.bg_base.crop((int(x1), int(y1), int(x1)+w, int(y1)+h)).convert("RGBA")
            # downscale local region for cheaper blur
            scale = 0.5
            small = src.resize((max(1,int(w*scale)), max(1,int(h*scale))), Image.Resampling.BILINEAR)
            small = small.filter(ImageFilter.GaussianBlur(radius=8))
            src_blur = small.resize((w,h), Image.Resampling.BILINEAR)
            overlay = Image.new("RGBA", (w,h), (PALETTE["glass_tint"][0], PALETTE["glass_tint"][1], PALETTE["glass_tint"][2], 110))
            # rounded mask
            radius = min(24, max(6, w//14), max(6, h//14))
            mask = Image.new("L", (w,h), 0)
            md = ImageDraw.Draw(mask)
            md.rounded_rectangle((0,0,w,h), radius=radius, fill=255)
            comp = Image.composite(overlay, src_blur, mask)
            final = Image.alpha_composite(src_blur, comp)
            tk = ImageTk.PhotoImage(final.convert("RGB"))
            img_tag = f"panel_bg_{win_tag}"
            self.canvas.delete(img_tag)
            self.canvas.create_image(int(x1), int(y1), anchor="nw", image=tk, tags=(img_tag,"panel_img"))
            setattr(self, f"_img_{win_tag}", tk)
            # make sure panel is above panel image but below other controls
            self.canvas.tag_lower(img_tag, "bgimg")
            self.canvas.tag_raise(win_tag)

    # ---------------- Trail (mouse history + low-res buffer) ----------------
    def _on_mouse_move(self, event):
        t = time.time()
        self.trail_history.append((event.x, event.y, t))
        # cap history
        maxh = self.trail_params.get(self._trail_key(), (40,0.5))[0]
        if len(self.trail_history) > maxh:
            self.trail_history = self.trail_history[-maxh:]

    def _trail_key(self):
        return {TRANSLATIONS[self.lang]["trail_off"]: "off",
                TRANSLATIONS[self.lang]["trail_low"]: "low",
                TRANSLATIONS[self.lang]["trail_med"]: "med",
                TRANSLATIONS[self.lang]["trail_high"]: "high"}.get(self.trail_opt.get(), "med")

    def _trail_changed(self, label):
        # map label back to key
        rev = {TRANSLATIONS[self.lang]["trail_off"]: "off",
               TRANSLATIONS[self.lang]["trail_low"]: "low",
               TRANSLATIONS[self.lang]["trail_med"]: "med",
               TRANSLATIONS[self.lang]["trail_high"]: "high"}
        key = rev.get(label, "med")
        self.trail_mode = key
        self.settings["trail_mode"] = key
        save_settings(self.settings)

    def _bg_update_loop(self):
        # throttle ~25fps
        now = time.time()
        if now - self._last_frame_time < 1/25:
            self.after(8, self._bg_update_loop)
            return
        self._last_frame_time = now

        # compose low-res trail overlay
        if self.trail_mode == "off":
            # just show bg_base
            combo = self.bg_base
        else:
            w, h = self.bg_base.size
            # choose downscale factor based on mode
            scale = self.trail_params.get(self.trail_mode, (40,0.5))[1]
            sw = max(1, int(w * scale))
            sh = max(1, int(h * scale))
            overlay_small = Image.new("RGBA", (sw, sh), (0,0,0,0))
            od = ImageDraw.Draw(overlay_small)
            # draw trail points scaled down
            n = len(self.trail_history)
            for i, (x,y,t) in enumerate(self.trail_history):
                sx = int(x * sw / w)
                sy = int(y * sh / h)
                age = n - i
                # size attenuates with age
                maxr = max(1, int(24 * (1 + 0.2 * (1 if self.trail_mode=="high" else 0))))
                r = max(1, int(maxr * (1 - i / max(1, n))))
                alpha = int(max(8, 220 * (1 - i / max(1, n))))
                # concentric circles
                od.ellipse([sx-r, sy-r, sx+r, sy+r], fill=(255,255,255, alpha))
                if r>2:
                    od.ellipse([sx-int(r*0.6), sy-int(r*0.6), sx+int(r*0.6), sy+int(r*0.6)], fill=(255,255,255, int(alpha*0.45)))
            # blur and upscale
            overlay_small = overlay_small.filter(ImageFilter.GaussianBlur(radius=4))
            overlay = overlay_small.resize((w,h), Image.Resampling.BILINEAR)
            combo = Image.alpha_composite(self.bg_base.convert("RGBA"), overlay).convert("RGB")

        self.bg_combo_tk = ImageTk.PhotoImage(combo)
        self.canvas.delete("bgimg")
        self.canvas.create_image(0,0,anchor="nw",image=self.bg_combo_tk,tags="bgimg")
        # update panels (but avoid heavy regen every frame — only update images positions)
        self._regen_panel_images()
        self.after(40, self._bg_update_loop)

    # ---------------- UI interactions ----------------
    def _set_lang(self, key):
        # when switching language update UI texts
        if key not in TRANSLATIONS:
            return
        self.lang = key
        self.settings["lang"] = key
        save_settings(self.settings)
        tr = TRANSLATIONS[key]
        # update labels/buttons
        self.app_lbl.configure(text=tr.get("app", self.app_lbl.cget("text")))
        self.author_lbl.configure(text=tr.get("author", self.author_lbl.cget("text")))
        self.controls_lbl.configure(text=tr.get("controls", self.controls_lbl.cget("text")))
        self.load_btn.configure(text=tr.get("load", self.load_btn.cget("text")))
        self.render_btn.configure(text=tr.get("render", self.render_btn.cget("text")))
        self.export_btn.configure(text=tr.get("export", self.export_btn.cget("text")))
        self.style_lbl.configure(text=tr.get("style", self.style_lbl.cget("text")))
        self.width_title_lbl.configure(text=tr.get("width", self.width_title_lbl.cget("text")))
        self.font_title_lbl.configure(text=tr.get("font", self.font_title_lbl.cget("text")))
        self.trail_lbl.configure(text=tr.get("trail", self.trail_lbl.cget("text")))
        # update trail option labels
        self.trail_opt.configure(values=[tr.get("trail_off"), tr.get("trail_low"), tr.get("trail_med"), tr.get("trail_high")])
        mode_map = {"off": tr.get("trail_off"), "low": tr.get("trail_low"), "med": tr.get("trail_med"), "high": tr.get("trail_high")}
        self.trail_opt.set(mode_map.get(self.trail_mode, tr.get("trail_med")))
        # gallery
        self.gallery_lbl.configure(text=tr.get("gallery", self.gallery_lbl.cget("text")))

    def _set_theme(self, val):
        if val == "light":
            ctk.set_appearance_mode("light")
        elif val == "neo":
            # custom theme - placeholder for more advanced tinting
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("dark")
        self.settings["theme"] = val
        save_settings(self.settings)

    def _style_changed(self, val):
        self.style = val
        if val != "custom":
            try:
                self.pick_text_btn.configure(state="disabled")
                self.pick_bg_btn.configure(state="disabled")
            except Exception:
                pass
        else:
            try:
                self.pick_text_btn.configure(state="normal")
                self.pick_bg_btn.configure(state="normal")
            except Exception:
                pass

    def _width_changed(self, v):
        self.width_chars = int(float(v))
        self.width_val_lbl.configure(text=str(self.width_chars))

    def _font_changed(self, v):
        self.font_size = int(float(v))
        self.font_val_lbl.configure(text=str(self.font_size))

    def _pick_text_color(self):
        c = colorchooser.askcolor()[1]
        if c:
            self.custom_fg = c
            self.text_ind.configure(fg_color=c)
            self.settings["custom_fg"] = c
            save_settings(self.settings)

    def _pick_bg_color(self):
        c = colorchooser.askcolor()[1]
        if c:
            self.bg_hex = c
            self.bg_ind.configure(fg_color=c)
            self.settings["bg_hex"] = c
            save_settings(self.settings)
            self._regen_bg((max(800, self.winfo_width()), max(600, self.winfo_height())))
            self.canvas.delete("bgimg")
            self.canvas.create_image(0,0,anchor="nw",image=self.bg_combo_tk,tags="bgimg")

    def _load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Media","*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.avi")])
        if not path:
            return
        self.file_path = path
        try:
            if path.lower().endswith((".mp4", ".avi", ".mov")):
                cap = cv2.VideoCapture(path)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(frame)
                    self._show_preview(pil)
            else:
                pil = Image.open(path)
                self._show_preview(pil)
        except Exception as e:
            print("Preview error:", e)

    def _render_image(self):
        if not self.file_path:
            return
        # block buttons
        for b in (self.load_btn, self.render_btn, self.export_btn):
            try:
                b.configure(state="disabled")
            except Exception:
                pass
        self.prog.set(0)
        def job():
            try:
                pil = Image.open(self.file_path)
                data = image_to_ascii_data(pil, self.width_chars, src_path=self.file_path)
                out = render_ascii_image(data, font_size=self.font_size, style=self.style, custom_fg=self.custom_fg, bg_hex=self.bg_hex)
                self.output_pil = out
                self.after(0, lambda: self._on_render_done(out))
            except Exception as e:
                print("Render error:", e)
                traceback.print_exc()
            finally:
                self.after(0, lambda: [b.configure(state="normal") for b in (self.load_btn, self.render_btn, self.export_btn)])
        t = threading.Thread(target=job, daemon=True)
        t.start()
        self.render_thread = t

    def _on_render_done(self, pil):
        self._show_preview(pil)
        self._add_gallery(pil)
        self.prog.set(1)

    def _export_image(self):
        if not self.output_pil:
            return
        save = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG","*.png"),("GIF","*.gif")])
        if not save:
            return
        ext = os.path.splitext(save)[1].lower()
        try:
            if ext == ".png":
                self.output_pil.save(save)
            elif ext == ".gif":
                imageio.mimsave(save, [np.array(self.output_pil)], duration=0.6)
        except Exception as e:
            print("Save error:", e)

    def _show_preview(self, pil):
        c_w = self.preview_canvas.winfo_width() or 800
        c_h = self.preview_canvas.winfo_height() or 500
        iw, ih = pil.size
        scale = min(c_w/iw, c_h/ih, 1.0)
        nw = max(1, int(iw*scale))
        nh = max(1, int(ih*scale))
        res = pil.resize((nw, nh), Image.Resampling.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(res)
        self.preview_canvas.delete("PREVIMG")
        self.preview_canvas.create_image(c_w//2, c_h//2, image=self.preview_tk, tags="PREVIMG", anchor="center")
        self.preview_canvas.tag_bind("PREVIMG", "<Button-1>", lambda e: self._open_fullscreen(pil))

    def _add_gallery(self, pil):
        thumb = pil.copy()
        thumb.thumbnail((150,150), Image.Resampling.LANCZOS)
        tkimg = ImageTk.PhotoImage(thumb)
        lbl = ctk.CTkLabel(self.gallery_scroll, image=tkimg, text="")
        lbl.image = tkimg
        lbl.pack(side="left", padx=6, pady=6)
        lbl.bind("<Button-1>", lambda e, p=pil: self._open_fullscreen(p))
        self.gallery.append(pil)
        # simple pop animation: schedule small raised padding then revert
        def anim(step=0):
            if step < 6:
                lbl.pack_configure(padx=6, pady=6-step)
                self.after(30, lambda: anim(step+1))
            else:
                lbl.pack_configure(padx=6, pady=6)
        anim()

    def _open_fullscreen(self, pil):
        fs = FullscreenViewer(self, pil)
        fs.grab_set()


# ------------ Fullscreen viewer ------------
class FullscreenViewer(Toplevel):
    def __init__(self, parent, pil):
        super().__init__(parent)
        self.title("Preview")
        self.attributes("-fullscreen", True)
        self.configure(bg="black")
        self.pil = pil
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.last = (0,0)
        self.canvas = Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._render()
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        exit_btn = ctk.CTkButton(self, text="✕", width=60, height=40, corner_radius=12, command=self.destroy, fg_color="#222426")
        exit_btn.place(relx=0.98, rely=0.02, anchor="ne")

    def _render(self):
        w = max(1, int(self.pil.width * self.zoom))
        h = max(1, int(self.pil.height * self.zoom))
        img = self.pil.resize((w,h), Image.Resampling.LANCZOS)
        self.tkimg = ImageTk.PhotoImage(img)
        self.canvas.delete("IMG")
        cx = self.winfo_screenwidth()//2 + self.offset_x
        cy = self.winfo_screenheight()//2 + self.offset_y
        self.canvas.create_image(cx, cy, image=self.tkimg, tags="IMG", anchor="center")

    def _on_wheel(self, e):
        factor = 1.12 if e.delta > 0 else 1/1.12
        self.zoom *= factor
        self._render()

    def _on_down(self, e):
        self.last = (e.x, e.y)

    def _on_drag(self, e):
        dx = e.x - self.last[0]
        dy = e.y - self.last[1]
        self.offset_x += dx
        self.offset_y += dy
        self.last = (e.x, e.y)
        self._render()


# --------------- Run ----------------------
def main():
    app = UltraASCIIApp()
    app.mainloop()

if __name__ == "__main__":
    main()
