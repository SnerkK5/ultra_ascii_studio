# ultra_ascii_studio.py
# Полнофункциональное приложение ASCII Studio (v3)
# Требования: Python 3.10+, pip install customtkinter pillow numpy opencv-python imageio

import os
import threading
import traceback
import json
from tkinter import filedialog, colorchooser, Toplevel, Canvas
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk
import numpy as np
import cv2
import imageio
import random

# -------------- Конфигурация ----------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

APP_TITLE = "ASCII ULTRA PREMIUM PRO – SNERK503"
ASCII_CHARS = "@%#*+=-:. "  # плотность символов
WATERMARK_TEXT = "SNERK503"
DEFAULT_FONT_PATHS = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/Consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]
DEFAULT_FONT_SIZE = 12

# load translations from root translations.json (safe)
def load_translations():
    try:
        base = os.path.dirname(__file__)
        p = os.path.normpath(os.path.join(base, '..', 'translations.json'))
        if not os.path.exists(p):
            p = os.path.normpath(os.path.join(base, 'translations.json'))
        with open(p, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}

TRANSLATIONS = load_translations()

def t(lang, key, default=None):
    try:
        return TRANSLATIONS.get(lang, {}).get(key, default or key)
    except Exception:
        return default or key

# ----------------- Утилиты --------------------
def colorchooser_to_hex():
    col = colorchooser.askcolor()[1]
    return col  # возвращает '#rrggbb' или None

def blend_with_bg(fg_rgb, bg_rgb, alpha):
    r = int(round(fg_rgb[0] * alpha + bg_rgb[0] * (1 - alpha)))
    g = int(round(fg_rgb[1] * alpha + bg_rgb[1] * (1 - alpha)))
    b = int(round(fg_rgb[2] * alpha + bg_rgb[2] * (1 - alpha)))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)

def safe_font(font_size):
    for p in DEFAULT_FONT_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, font_size)
            except Exception:
                continue
    return ImageFont.load_default()

# ---------------- ASCII Engine ------------------
def image_to_ascii_data(image_pil, width_chars, ascii_chars=ASCII_CHARS):
    if image_pil.mode != "RGB":
        img = image_pil.convert("RGB")
    else:
        img = image_pil
    w, h = img.size
    aspect = h / w if w != 0 else 1
    rows = max(1, int(aspect * width_chars * 0.55))
    small = img.resize((max(1, width_chars), max(1, rows)), Image.Resampling.BICUBIC)
    arr = np.array(small)
    out = []
    for row in arr:
        line = []
        for px in row:
            brightness = int(px.mean())
            idx = brightness * (len(ascii_chars) - 1) // 255
            line.append((ascii_chars[idx], tuple(int(x) for x in px)))
        out.append(line)
    return out

def render_ascii_image(ascii_data, font_size=DEFAULT_FONT_SIZE, style="bw", custom_fg="#ffffff", bg="#0f0f12"):
    font = safe_font(font_size)
    try:
        bbox = font.getbbox("A")
        char_width, char_height = bbox[2], bbox[3]
    except Exception:
        char_width, char_height = font.getsize("A")
    cols = len(ascii_data[0]) if ascii_data else 0
    rows = len(ascii_data)
    img_w = max(1, int(char_width * cols))
    img_h = max(1, int(char_height * rows))
    out_img = Image.new("RGB", (img_w, img_h), bg)
    draw = ImageDraw.Draw(out_img)
    for y, row in enumerate(ascii_data):
        for x, (ch, color) in enumerate(row):
            if style == "bw":
                draw_color = (255, 255, 255)
            elif style == "red":
                draw_color = (255, 60, 60)
            elif style == "color":
                draw_color = color
            elif style == "matrix":
                draw_color = (0, 255, 120)
            elif style == "custom":
                hexc = custom_fg.lstrip("#")
                try:
                    draw_color = tuple(int(hexc[i:i+2], 16) for i in (0, 2, 4))
                except Exception:
                    draw_color = (255,255,255)
            else:
                draw_color = (255, 255, 255)
            draw.text((x*char_width, y*char_height), ch, fill=draw_color, font=font)
    try:
        draw.text((10, img_h - int(char_height*1.2)), WATERMARK_TEXT, fill=(120,120,120), font=font)
    except Exception:
        pass
    return out_img

# ---------------- Video processing ----------------
def process_video_to_frames(input_path, width_chars, style, custom_fg_hex, bg_hex, progress_callback=None, stop_event=None):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError("Can't open video file")
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
        asc = image_to_ascii_data(pil, width_chars)
        img = render_ascii_image(asc, font_size=12, style=style, custom_fg=custom_fg_hex, bg=bg_hex)
        frames.append(np.array(img))
        idx += 1
        if progress_callback and total > 0:
            progress_callback(idx / total, idx, total)
    cap.release()
    return frames, fps

# ----------------- UI App ---------------------
class PremiumASCII(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1100, 700)

        # state
        self.file_path = None
        self.output_image_pil = None
        self.output_tkimg = None
        self.gallery = []
        self.render_thread = None
        self.render_stop_event = None

        # settings
        self.style = "bw"
        self.width_chars = 400
        self.font_size = 12
        self.custom_fg = "#FFFFFF"
        self.bg_hex = "#0F0F12"
        self.lang = "en"
        self.theme = "dark"
        # advanced render settings
        self.codec = 'libx264'
        self.bitrate = None
        self.crf = None
        self.preset = 'medium'
        self.gif_palette = False
        self.gif_dither = True

        # particles
        self.particles = []
        self.max_particles = 220
        self.bg_color_rgb = (17,17,17)
        self._build_ui()
        self.bind("<Motion>", self._on_mouse_move)
        self.after(30, self._update_particles)

    def _build_ui(self):
        self.bg_canvas = Canvas(self, bg="#111111", highlightthickness=0)
        self.bg_canvas.pack(fill="both", expand=True)

        self.top_bar = ctk.CTkFrame(self.bg_canvas, fg_color="#121217", corner_radius=12)
        self.top_window = self.bg_canvas.create_window(20, 20, anchor="nw", window=self.top_bar, width=540, height=84)

        self.right_panel = ctk.CTkFrame(self.bg_canvas, fg_color="#121217", corner_radius=12)
        self.right_window = self.bg_canvas.create_window(980, 20, anchor="nw", window=self.right_panel, width=380, height=640)

        self.preview_frame = ctk.CTkFrame(self.bg_canvas, fg_color="#0f1113", corner_radius=12)
        self.preview_window = self.bg_canvas.create_window(20, 120, anchor="nw", window=self.preview_frame, width=940, height=560)

        self.gallery_frame = ctk.CTkFrame(self.bg_canvas, fg_color="#121217", corner_radius=12)
        self.gallery_window = self.bg_canvas.create_window(20, 700, anchor="nw", window=self.gallery_frame, width=1340, height=160)

        left_row = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        left_row.pack(side="left", padx=8)
        self.menu_btn = ctk.CTkButton(left_row, text="≡", width=40, height=40, corner_radius=8, command=self._toggle_menu)
        self.menu_btn.pack(side="left", padx=(2,8))
        self.title_lbl = ctk.CTkLabel(left_row, text="ASCII ULTRA PREMIUM PRO", font=ctk.CTkFont(size=16, weight="bold"))
        self.title_lbl.pack(side="left")
        self.author_lbl = ctk.CTkLabel(left_row, text="SNERK503", fg_color="transparent")
        self.author_lbl.pack(side="left", padx=(8,0))

        self.menu_panel = ctk.CTkFrame(self.top_bar, fg_color="#0e0e10")
        self.menu_panel.pack(side="left", padx=6)
        self.menu_panel.pack_forget()

        right_row = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        right_row.pack(side="right", padx=6)
        self.lang_opt = ctk.CTkOptionMenu(right_row, values=["en","ru","zh"], command=self._set_lang, width=90)
        self.lang_opt.set(self.lang)
        self.lang_opt.pack(side="left", padx=6)
        self.theme_opt = ctk.CTkOptionMenu(right_row, values=["dark","light","accent"], command=self._set_theme, width=120)
        self.theme_opt.set(self.theme)
        self.theme_opt.pack(side="left", padx=6)

        rp = self.right_panel
        ctk.CTkLabel(rp, text="Controls", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(8,6))
        btns_frame = ctk.CTkFrame(rp, fg_color="transparent")
        btns_frame.pack(fill="x", padx=10, pady=6)
        self.load_btn = ctk.CTkButton(btns_frame, text=t(self.lang, 'load', 'Load'), command=self._load_file, fg_color="#222428")
        self.load_btn.pack(side="left", padx=6, pady=6)
        self.render_btn = ctk.CTkButton(btns_frame, text=t(self.lang, 'render', 'Render'), command=self._render_media, fg_color="#2a7")
        self.render_btn.pack(side="left", padx=6, pady=6)
        self.render_video_btn = ctk.CTkButton(btns_frame, text=t(self.lang, 'render', 'Render')+" Video", command=self._render_video_thread, fg_color="#2a7")
        self.render_video_btn.pack(side="left", padx=6, pady=6)
        self.export_btn = ctk.CTkButton(btns_frame, text=t(self.lang, 'export', 'Export'), command=self._export_media, fg_color="#222428")
        self.export_btn.pack(side="left", padx=6, pady=6)

        ctk.CTkLabel(rp, text=t(self.lang, 'style', 'Style')).pack(anchor="w", padx=10, pady=(8,0))
        self.style_opt = ctk.CTkOptionMenu(rp, values=["bw","red","color","matrix","custom"], command=self._style_changed, width=120)
        self.style_opt.set(self.style)
        self.style_opt.pack(anchor="w", padx=10, pady=6)

        ctk.CTkLabel(rp, text=t(self.lang, 'width', 'Width (chars)')).pack(anchor="w", padx=10, pady=(6,0))
        self.width_slider = ctk.CTkSlider(rp, from_=80, to=900, command=self._width_changed)
        self.width_slider.set(self.width_chars)
        self.width_slider.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(rp, text=t(self.lang, 'font', 'Font size')).pack(anchor="w", padx=10)
        self.font_slider = ctk.CTkSlider(rp, from_=6, to=28, command=self._font_changed)
        self.font_slider.set(self.font_size)
        self.font_slider.pack(fill="x", padx=10, pady=6)

        color_row = ctk.CTkFrame(rp, fg_color="transparent")
        color_row.pack(fill="x", padx=10, pady=6)
        self.pick_text_btn = ctk.CTkButton(color_row, text=t(self.lang,'text_color','Text color'), command=self._pick_text_color)
        self.pick_text_btn.pack(side="left", padx=(0,6))
        self.text_indicator = ctk.CTkFrame(color_row, width=28, height=28, fg_color=self.custom_fg, corner_radius=6)
        self.text_indicator.pack(side="left", padx=(0,18))
        self.pick_bg_btn = ctk.CTkButton(color_row, text=t(self.lang,'bg_color','Bg color'), command=self._pick_bg_color)
        self.pick_bg_btn.pack(side="left", padx=(0,6))
        self.bg_indicator = ctk.CTkFrame(color_row, width=28, height=28, fg_color=self.bg_hex, corner_radius=6)
        self.bg_indicator.pack(side="left", padx=(0,6))

        ctk.CTkLabel(rp, text="Progress").pack(anchor="w", padx=10, pady=(8,0))
        self.prog = ctk.CTkProgressBar(rp, width=340)
        self.prog.set(0)
        self.prog.pack(padx=10, pady=(6,0))

        pf = self.preview_frame
        self.preview_canvas = Canvas(pf, bg="#0b0b0d", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_tk = None

        gf = self.gallery_frame
        self.gallery_scroll = ctk.CTkScrollableFrame(gf, orientation="horizontal")
        self.gallery_scroll.pack(fill="both", expand=True, padx=8, pady=8)
        ctk.CTkLabel(gf, text="Gallery").pack(anchor="w", padx=12, pady=(0,6))

        self.status_lbl = ctk.CTkLabel(self, text="Ready", fg_color="transparent")
        self.bg_canvas.create_window(20, 870, anchor="nw", window=self.status_lbl)

        # loader/spinner window (lazy)
        self._loader_win = None
        self._loader_job = None
        self._spinner_seq = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spinner_idx = 0

    def _toggle_menu(self):
        if self.menu_panel.winfo_ismapped():
            self.menu_panel.pack_forget()
        else:
            if not self.menu_panel.winfo_children():
                ctk.CTkLabel(self.menu_panel, text="Settings", font=ctk.CTkFont(size=12, weight="bold")).pack(padx=6, pady=(6,2))
                ctk.CTkLabel(self.menu_panel, text="Author: SNERK503").pack(padx=6, pady=2)
                ctk.CTkLabel(self.menu_panel, text=t(self.lang,'gallery','Language')).pack(padx=6, pady=(6,2))
                ctk.CTkOptionMenu(self.menu_panel, values=["en","ru","zh"], command=self._set_lang).pack(padx=6, pady=2)
                # advanced render settings
                ctk.CTkLabel(self.menu_panel, text="Advanced").pack(padx=6, pady=(8,2))
                self.codec_entry = ctk.CTkEntry(self.menu_panel, placeholder_text=self.codec)
                self.codec_entry.pack(padx=6, pady=2)
                self.bitrate_entry = ctk.CTkEntry(self.menu_panel, placeholder_text="bitrate (eg. 500k)")
                self.bitrate_entry.pack(padx=6, pady=2)
                self.crf_entry = ctk.CTkEntry(self.menu_panel, placeholder_text="crf (quality, eg. 23)")
                self.crf_entry.pack(padx=6, pady=2)
                def _apply_adv():
                    try:
                        v = self.codec_entry.get().strip()
                        if v:
                            self.codec = v
                    except Exception:
                        pass
                    try:
                        v = self.bitrate_entry.get().strip()
                        self.bitrate = v if v else None
                    except Exception:
                        pass
                    try:
                        v = self.crf_entry.get().strip()
                        self.crf = int(v) if v else None
                    except Exception:
                        pass
                    self.status_lbl.configure(text="Advanced updated")
                ctk.CTkButton(self.menu_panel, text="Apply", command=_apply_adv).pack(padx=6, pady=(6,6))
            self.menu_panel.pack(side="left", padx=6)

    def _set_lang(self, val):
        self.lang = val
        # update visible texts (basic)
        try:
            self.load_btn.configure(text=t(self.lang,'load','Load'))
            self.render_btn.configure(text=t(self.lang,'render','Render'))
            self.export_btn.configure(text=t(self.lang,'export','Export'))
            self.style_opt.set(self.style)
        except Exception:
            pass
        self.status_lbl.configure(text=f"Language set: {val}")

    # loader spinner simple implementation
    def _show_loader(self, text="Working..."):
        if self._loader_win is not None:
            return
        self._loader_win = Toplevel(self)
        self._loader_win.overrideredirect(True)
        self._loader_win.attributes("-topmost", True)
        lbl = ctk.CTkLabel(self._loader_win, text=text)
        lbl.pack(padx=12, pady=12)
        self._loader_label = lbl
        def _spin():
            try:
                self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_seq)
                self._loader_label.configure(text=self._spinner_seq[self._spinner_idx] + " " + text)
                self._loader_job = self.after(120, _spin)
            except Exception:
                pass
        x = self.winfo_rootx() + 20
        y = self.winfo_rooty() + 120
        self._loader_win.geometry(f"160x48+{x}+{y}")
        _spin()

    def _hide_loader(self):
        try:
            if self._loader_job:
                self.after_cancel(self._loader_job)
                self._loader_job = None
        except Exception:
            pass
        try:
            if self._loader_win:
                self._loader_win.destroy()
                self._loader_win = None
        except Exception:
            pass

    def _set_theme(self, val):
        self.theme = val
        if val == "light":
            ctk.set_appearance_mode("light")
        else:
            ctk.set_appearance_mode("dark")
        self.status_lbl.configure(text=f"Theme: {val}")

    def _style_changed(self, val):
        self.style = val
        if val != "custom":
            self.pick_text_btn.configure(state="disabled")
            self.pick_bg_btn.configure(state="disabled")
        else:
            self.pick_text_btn.configure(state="normal")
            self.pick_bg_btn.configure(state="normal")

    def _width_changed(self, val):
        self.width_chars = int(float(val))

    def _font_changed(self, val):
        self.font_size = int(float(val))

    def _pick_text_color(self):
        col = colorchooser_to_hex()
        if col:
            self.custom_fg = col
            self.text_indicator.configure(fg_color=col)

    def _pick_bg_color(self):
        col = colorchooser_to_hex()
        if col:
            self.bg_hex = col
            self.bg_indicator.configure(fg_color=col)
            try:
                r = int(self.bg_hex[1:3], 16)
                g = int(self.bg_hex[3:5], 16)
                b = int(self.bg_hex[5:7], 16)
                self.bg_color_rgb = (r, g, b)
            except Exception:
                pass

    def _load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Media","*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.avi *.mov")])
        if path:
            self.file_path = path
            self.status_lbl.configure(text=f"Loaded: {os.path.basename(path)}")
            try:
                if any(path.lower().endswith(ext) for ext in [".mp4", ".avi", ".mov"]):
                    cap = cv2.VideoCapture(path)
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        pil = Image.fromarray(frame)
                        self._display_preview_pil(pil)
                else:
                    pil = Image.open(path)
                    self._display_preview_pil(pil)
            except Exception as e:
                self.status_lbl.configure(text=f"Preview failed: {e}")

    def _disable_controls(self):
        for w in [self.load_btn, self.render_btn, self.render_video_btn, self.export_btn]:
            try:
                w.configure(state="disabled")
            except Exception:
                pass

    def _enable_controls(self):
        for w in [self.load_btn, self.render_btn, self.render_video_btn, self.export_btn]:
            try:
                w.configure(state="normal")
            except Exception:
                pass

    def _render_media(self):
        if not self.file_path:
            self.status_lbl.configure(text="Load file first")
            return
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext in [".mp4", ".avi", ".mov"]:
            self._render_video_thread()
            return
        self._disable_controls()
        self.prog.set(0)
        self.status_lbl.configure(text="Rendering image...")
        def job():
            try:
                pil = Image.open(self.file_path)
                asc = image_to_ascii_data(pil, self.width_chars)
                out = render_ascii_image(asc, font_size=self.font_size, style=self.style, custom_fg=self.custom_fg, bg=self.bg_hex)
                self.output_image_pil = out
                self.after(0, lambda: self._on_render_done(out))
            except Exception as e:
                self.after(0, lambda: self._on_render_error(e))
        t = threading.Thread(target=job, daemon=True)
        t.start()
        self.render_thread = t

    def _render_video_thread(self):
        if not self.file_path:
            self.status_lbl.configure(text="Load video first")
            return
        save = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4","*.mp4"),("MOV","*.mov"),("MKV","*.mkv"),("GIF","*.gif")])
        if not save:
            return
        self._disable_controls()
        self.prog.set(0)
        self.status_lbl.configure(text="Rendering video...")
        self._show_loader("Rendering video...")
        self.render_stop_event = threading.Event()

        def progress_callback(ratio, current, total):
            self.after(0, lambda: self.prog.set(min(1.0, ratio)))
            self.after(0, lambda: self.status_lbl.configure(text=f"Frame {current}/{total}"))

        def job():
            try:
                frames, fps = process_video_to_frames(self.file_path, self.width_chars, self.style, self.custom_fg, self.bg_hex, progress_callback, self.render_stop_event)
                ext = os.path.splitext(save)[1].lower()
                if ext == ".gif":
                    imageio.mimsave(save, frames, duration=1/max(1,int(fps)))
                else:
                    try:
                        # try to use ffmpeg writer with codec/bitrate from settings
                        kw = {'fps': fps, 'format': 'FFMPEG'}
                        if getattr(self, 'codec', None): kw['codec'] = self.codec
                        if getattr(self, 'bitrate', None) and self.bitrate:
                            kw['bitrate'] = self.bitrate
                        writer = imageio.get_writer(save, **kw)
                        for fr in frames:
                            arr = fr
                            if isinstance(arr, np.ndarray) and arr.dtype != np.uint8:
                                arr = arr.astype(np.uint8)
                            writer.append_data(arr)
                        writer.close()
                    except Exception:
                        # fallback
                        imageio.mimsave(save + ".tmp.gif", frames, duration=1/max(1,int(fps)))
                        raise
                self.after(0, lambda: self.status_lbl.configure(text=f"Saved: {save}"))
                if frames:
                    pil_first = Image.fromarray(frames[0])
                    self.after(0, lambda: self.add_to_gallery(pil_first))
            except Exception as e:
                self.after(0, lambda: self.status_lbl.configure(text=f"Video render error: {e}"))
                print("Video render error:", e)
                traceback.print_exc()
            finally:
                self.after(0, self._enable_controls)
                self.render_stop_event = None
                self.after(0, self._hide_loader)

        t = threading.Thread(target=job, daemon=True)
        t.start()
        self.render_thread = t

    def _on_render_done(self, pil_img):
        self.prog.set(1)
        self.status_lbl.configure(text="Render done")
        self._display_preview_pil(pil_img)
        self.add_to_gallery(pil_img)
        self._enable_controls()

    def _on_render_error(self, err):
        self.status_lbl.configure(text=f"Render failed: {err}")
        print("Render error:", err)
        traceback.print_exc()
        self._enable_controls()

    def _render_video_thread(self):
        if not self.file_path:
            self.status_lbl.configure(text="Load video first")
            return
        save = filedialog.asksaveasfilename(defaultextension=".gif", filetypes=[("GIF","*.gif"),("MP4","*.mp4")])
        if not save:
            return
        self._disable_controls()
        self.prog.set(0)
        self.status_lbl.configure(text="Rendering video...")
        self.render_stop_event = threading.Event()

        def progress_callback(ratio, current, total):
            self.after(0, lambda: self.prog.set(min(1.0, ratio)))
            self.after(0, lambda: self.status_lbl.configure(text=f"Frame {current}/{total}"))

        def job():
            try:
                frames, fps = process_video_to_frames(self.file_path, self.width_chars, self.style, self.custom_fg, self.bg_hex, progress_callback, self.render_stop_event)
                ext = os.path.splitext(save)[1].lower()
                if ext == ".gif":
                    imageio.mimsave(save, frames, duration=1/max(1,int(fps)))
                else:
                    try:
                        writer = imageio.get_writer(save, fps=fps)
                        for fr in frames:
                            writer.append_data(fr)
                        writer.close()
                    except Exception:
                        imageio.mimsave(save + ".tmp.gif", frames, duration=1/max(1,int(fps)))
                        raise
                self.after(0, lambda: self.status_lbl.configure(text=f"Saved: {save}"))
                if frames:
                    pil_first = Image.fromarray(frames[0])
                    self.after(0, lambda: self.add_to_gallery(pil_first))
            except Exception as e:
                self.after(0, lambda: self.status_lbl.configure(text=f"Video render error: {e}"))
                print("Video render error:", e)
                traceback.print_exc()
            finally:
                self.after(0, self._enable_controls)
                self.render_stop_event = None

        t = threading.Thread(target=job, daemon=True)
        t.start()
        self.render_thread = t

    def _export_media(self):
        if not self.output_image_pil:
            self.status_lbl.configure(text="Nothing to export")
            return
        save = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG","*.png"),("GIF","*.gif")])
        if not save:
            return
        try:
            ext = os.path.splitext(save)[1].lower()
            if ext == ".png":
                self.output_image_pil.save(save)
            elif ext == ".gif":
                imageio.mimsave(save, [np.array(self.output_image_pil)], duration=0.5)
            self.status_lbl.configure(text=f"Saved: {save}")
        except Exception as e:
            self.status_lbl.configure(text=f"Save error: {e}")
            traceback.print_exc()

    def _display_preview_pil(self, pil_img):
        self.output_image_pil = pil_img
        w = self.preview_canvas.winfo_width() or 900
        h = self.preview_canvas.winfo_height() or 560
        img_w, img_h = pil_img.size
        scale = min(w/img_w, h/img_h, 1.0)
        new_w = max(1, int(img_w*scale))
        new_h = max(1, int(img_h*scale))
        resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(resized)
        self.preview_canvas.delete("IMG")
        self.preview_canvas.create_image(w//2, h//2, image=self.preview_tk, anchor="center", tags="IMG")
        self.preview_canvas.tag_bind("IMG", "<Button-1>", lambda e: self._open_fullscreen(self.output_image_pil))

    def add_to_gallery(self, pil_img):
        thumb = pil_img.copy()
        thumb.thumbnail((150,150), Image.Resampling.LANCZOS)
        tkthumb = ImageTk.PhotoImage(thumb)
        b = ctk.CTkLabel(self.gallery_scroll, image=tkthumb, text="")
        b.image = tkthumb
        b.pack(side="left", padx=6, pady=6)
        b.bind("<Button-1>", lambda e, img=pil_img: self._open_fullscreen(img))
        self.gallery.append(pil_img)

    def _open_fullscreen(self, pil_img):
        fs = FullscreenViewer(self, pil_img)
        fs.grab_set()

    def _on_mouse_move(self, event):
        if len(self.particles) > self.max_particles:
            return
        x = event.x
        y = event.y
        for _ in range(1):
            r = random.randint(8, 24)
            a = random.uniform(0.08, 0.35)
            speed = random.uniform(0.3, 1.5)
            self.particles.append([x, y, r, a, speed])

    def _update_particles(self):
        self.bg_canvas.delete("particle")
        new = []
        bg_rgb = self.bg_color_rgb
        for p in self.particles:
            x, y, r, a, speed = p
            color_hex = blend_with_bg((255,255,255), bg_rgb, a)
            self.bg_canvas.create_oval(x-r, y-r, x+r, y+r, fill=color_hex, outline="", tags="particle")
            y -= speed
            a -= 0.008 * speed
            r -= 0.1 * speed
            if a > 0.01 and r > 0.5:
                new.append([x, y, r, a, speed])
        self.particles = new
        self.after(30, self._update_particles)


class FullscreenViewer(Toplevel):
    def __init__(self, parent, pil_img):
        super().__init__(parent)
        self.title("Preview")
        self.configure(bg="black")
        self.attributes("-fullscreen", True)
        self.pil = pil_img
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.last = (0,0)
        self.canvas = Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._render_image()
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        close_btn = ctk.CTkButton(self, text="✕", width=60, height=40, corner_radius=12, command=self.destroy)
        close_btn.place(relx=0.98, rely=0.02, anchor="ne")

    def _render_image(self):
        w = int(self.pil.width * self.zoom)
        h = int(self.pil.height * self.zoom)
        if w < 1: w = 1
        if h < 1: h = 1
        img = self.pil.resize((w,h), Image.Resampling.LANCZOS)
        self.tkimg = ImageTk.PhotoImage(img)
        self.canvas.delete("IMG")
        self.canvas.create_image(self.winfo_screenwidth()//2 + self.offset_x,
                                 self.winfo_screenheight()//2 + self.offset_y,
                                 image=self.tkimg, anchor="center", tags="IMG")

    def _on_wheel(self, event):
        delta = 1.1 if event.delta > 0 else 0.9
        self.zoom *= delta
        self._render_image()

    def _on_mouse_down(self, event):
        self.last = (event.x, event.y)

    def _on_mouse_drag(self, event):
        dx = event.x - self.last[0]
        dy = event.y - self.last[1]
        self.offset_x += dx
        self.offset_y += dy
        self.last = (event.x, event.y)
        self._render_image()


def main():
    app = PremiumASCII()
    app.mainloop()


if __name__ == "__main__":
    main()
