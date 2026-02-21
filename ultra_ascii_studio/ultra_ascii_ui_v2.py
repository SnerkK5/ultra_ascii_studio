# ultra_ascii_ui_v2.py
# Modern Premium UI for ASCII Studio (v2)
# Requirements: Python 3.10+, pip install customtkinter pillow numpy opencv-python imageio

import os
import threading
import traceback
import random
import time
from tkinter import filedialog, colorchooser, Toplevel, Canvas
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter
import numpy as np
import cv2
import imageio

# ---------------- Config / Palette ----------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

APP_TITLE = "ASCII ULTRA PREMIUM PRO – SNERK503"

PALETTE = {
    "bg0": "#0e1117",
    "bg1": "#121826",
    "panel": "#0f151b",
    "glass": "#12151a",   # CTk frame color (solid)
    "accent": "#1DB954",
    "cyan": "#00E5FF",
    "purple": "#8A2BE2",
    "muted": "#9aa4b2",
    "white": "#FFFFFF"
}

ASCII_CHARS = "@%#*+=-:. "
WATERMARK_TEXT = "SNERK503"
DEFAULT_FONT_SIZE = 12
DEFAULT_FONT_PATHS = [
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
]

# ---------------- Utilities ----------------
def safe_font(size):
    for p in DEFAULT_FONT_PATHS:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def color_to_rgb(hexc):
    hexc = hexc.lstrip("#")
    return tuple(int(hexc[i:i+2], 16) for i in (0, 2, 4))

def blend(fg_rgb, bg_rgb, a):
    r = int(round(fg_rgb[0]*a + bg_rgb[0]*(1-a)))
    g = int(round(fg_rgb[1]*a + bg_rgb[1]*(1-a)))
    b = int(round(fg_rgb[2]*a + bg_rgb[2]*(1-a)))
    return (r, g, b)

# ---------------- ASCII Engine ----------------
def image_to_ascii_data(img_pil, width_chars, chars=ASCII_CHARS):
    if img_pil.mode != "RGB":
        img = img_pil.convert("RGB")
    else:
        img = img_pil
    w, h = img.size
    rows = max(1, int((h / w) * width_chars * 0.55))
    small = img.resize((width_chars, rows), Image.Resampling.BICUBIC)
    arr = np.array(small)
    out = []
    for row in arr:
        line = []
        for px in row:
            brightness = int(px.mean())
            idx = brightness * (len(chars) - 1) // 255
            line.append((chars[idx], tuple(int(x) for x in px)))
        out.append(line)
    return out

def render_ascii_image(ascii_data, font_size=DEFAULT_FONT_SIZE, style="bw", custom_fg_hex="#FFFFFF", bg_hex="#0F0F12"):
    font = safe_font(font_size)
    bbox = font.getbbox("A")
    char_w = bbox[2] - bbox[0]
    char_h = bbox[3] - bbox[1]
    cols = len(ascii_data[0])
    rows = len(ascii_data)
    w = max(1, int(char_w * cols))
    h = max(1, int(char_h * rows))
    out = Image.new("RGB", (w, h), bg_hex)
    draw = ImageDraw.Draw(out)
    # compute custom fg rgb
    try:
        custom_rgb = color_to_rgb(custom_fg_hex)
    except Exception:
        custom_rgb = (255,255,255)
    for y, row in enumerate(ascii_data):
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
    # watermark
    draw.text((10, max(h-20, 0)), WATERMARK_TEXT, fill=(120,120,120), font=font)
    return out

# ---------------- Video -> frames (simple) ----------------
def process_video_to_frames(input_path, width_chars, style, custom_fg, bg_hex, progress_callback=None, stop_event=None):
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
        out = render_ascii_image(asc, font_size=12, style=style, custom_fg_hex=custom_fg, bg_hex=bg_hex)
        frames.append(np.array(out))
        idx += 1
        if progress_callback and total > 0:
            progress_callback(idx, total)
    cap.release()
    return frames, fps

# ---------------- UI App ----------------
class UltraASCIIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1100,700)

        # state
        self.file_path = None
        self.output_pil = None
        self.output_tk = None
        self.gallery = []
        self.render_thread = None
        self.stop_event = None

        # user settings
        self.style = "bw"
        self.width_chars = 400
        self.font_size = 12
        self.custom_fg = "#FFFFFF"
        self.bg_hex = "#0F1113"

        # background assets
        self.bg_base = None    # PIL base blurred background
        self.bg_overlay = None # particles overlay PIL
        self.bg_combo_tk = None

        # particles (initialize before building UI because background composition uses them)
        self.particles = []

        # build
        self._build_ui()
        self.bind("<Configure>", self._on_resize)
        self.bind("<Motion>", self._on_mouse_move)
        self.after(40, self._update_bg)

    # --- UI build
    def _build_ui(self):
        # main canvas for blurred background + overlay
        self.canvas = Canvas(self, bg=PALETTE["bg0"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # create blurred background once (will be resized)
        self._regen_bg_base((1400,900))

        # top left glass panel (menu)
        self.top_panel = ctk.CTkFrame(self.canvas, fg_color=PALETTE["glass"], corner_radius=12)
        self.top_win = self.canvas.create_window(20, 14, anchor="nw", window=self.top_panel, width=560, height=86)

        # right panel for controls
        self.right_panel = ctk.CTkFrame(self.canvas, fg_color=PALETTE["glass"], corner_radius=12)
        self.right_win = self.canvas.create_window(980, 20, anchor="nw", window=self.right_panel, width=380, height=660)

        # center preview panel (glass)
        self.preview_panel = ctk.CTkFrame(self.canvas, fg_color="#0b0f12", corner_radius=14)
        self.preview_win = self.canvas.create_window(20, 120, anchor="nw", window=self.preview_panel, width=940, height=560)

        # bottom gallery panel
        self.gallery_panel = ctk.CTkFrame(self.canvas, fg_color=PALETTE["glass"], corner_radius=12)
        self.gallery_win = self.canvas.create_window(20, 700, anchor="nw", window=self.gallery_panel, width=1340, height=160)

        # populate top panel
        left = ctk.CTkFrame(self.top_panel, fg_color="transparent")
        left.pack(side="left", padx=12)
        ctk.CTkLabel(left, text="ASCII ULTRA", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkLabel(left, text="SNERK503", text_color=PALETTE["muted"]).pack(side="left", padx=(8,0))

        right = ctk.CTkFrame(self.top_panel, fg_color="transparent")
        right.pack(side="right", padx=12)
        self.lang_opt = ctk.CTkOptionMenu(right, values=["en","ru","zh"], width=90)
        self.lang_opt.set("en")
        self.lang_opt.pack(side="left", padx=6)
        self.theme_opt = ctk.CTkOptionMenu(right, values=["dark","light","accent"], width=120, command=self._set_theme)
        self.theme_opt.set("dark")
        self.theme_opt.pack(side="left", padx=6)

        # populate right panel (controls)
        ctk.CTkLabel(self.right_panel, text="Controls", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(8,6))
        # buttons row
        btns = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        btns.pack(padx=10)
        self.load_btn = ctk.CTkButton(btns, text="Load", width=90, command=self._load_file, fg_color="#14181b", hover_color="#1b2226")
        self.load_btn.pack(side="left", padx=6)
        self.render_btn = ctk.CTkButton(btns, text="Render", width=90, command=self._render_image, fg_color=PALETTE["accent"])
        self.render_btn.pack(side="left", padx=6)
        self.export_btn = ctk.CTkButton(btns, text="Export", width=90, command=self._export_image, fg_color="#14181b")
        self.export_btn.pack(side="left", padx=6)

        # style selector
        ctk.CTkLabel(self.right_panel, text="Style").pack(anchor="w", padx=10, pady=(10,0))
        self.style_opt = ctk.CTkOptionMenu(self.right_panel, values=["bw","red","color","matrix","custom"], command=self._style_change)
        self.style_opt.set(self.style)
        self.style_opt.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(self.right_panel, text="Width (chars)").pack(anchor="w", padx=10)
        self.width_slider = ctk.CTkSlider(self.right_panel, from_=80, to=900, command=self._width_change)
        self.width_slider.set(self.width_chars)
        self.width_slider.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(self.right_panel, text="Font size").pack(anchor="w", padx=10)
        self.font_slider = ctk.CTkSlider(self.right_panel, from_=6, to=28, command=self._font_change)
        self.font_slider.set(self.font_size)
        self.font_slider.pack(fill="x", padx=10, pady=6)

        # color pickers row
        color_row = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        color_row.pack(padx=10, pady=(8,6))
        self.pick_text = ctk.CTkButton(color_row, text="Text", command=self._pick_text_color, width=100)
        self.pick_text.pack(side="left", padx=6)
        self.text_indicator = ctk.CTkFrame(color_row, width=28, height=28, fg_color=self.custom_fg, corner_radius=6)
        self.text_indicator.pack(side="left", padx=(6,12))
        self.pick_bg = ctk.CTkButton(color_row, text="BG", command=self._pick_bg_color, width=100)
        self.pick_bg.pack(side="left", padx=6)
        self.bg_indicator = ctk.CTkFrame(color_row, width=28, height=28, fg_color=self.bg_hex, corner_radius=6)
        self.bg_indicator.pack(side="left", padx=6)

        # progress bar
        self.prog = ctk.CTkProgressBar(self.right_panel, width=340)
        self.prog.set(0)
        self.prog.pack(padx=10, pady=(12,6))

        # preview canvas inside preview_panel
        self.preview_canvas = Canvas(self.preview_panel, bg=PALETTE["bg1"], highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_img_ref = None

        # gallery scroll
        self.gallery_scroll = ctk.CTkScrollableFrame(self.gallery_panel, orientation="horizontal")
        self.gallery_scroll.pack(fill="both", expand=True, padx=8, pady=8)

    # --- theme
    def _set_theme(self, val):
        if val == "light":
            ctk.set_appearance_mode("light")
        else:
            ctk.set_appearance_mode("dark")

    # --- events
    def _on_resize(self, event):
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        self._regen_bg_base((w, h))
        # reposition background image on canvas
        if self.bg_combo_tk:
            self.canvas.delete("bgimg")
            self.canvas.create_image(0,0, anchor="nw", image=self.bg_combo_tk, tags="bgimg")
            # ensure windows kept above bgimg
            self.canvas.tag_raise(self.top_win)
            self.canvas.tag_raise(self.right_win)
            self.canvas.tag_raise(self.preview_win)
            self.canvas.tag_raise(self.gallery_win)

    def _regen_bg_base(self, size):
        w, h = size
        # create gradient base
        base = Image.new("RGB", (w, h), PALETTE["bg0"])
        draw = ImageDraw.Draw(base)
        # simple vertical gradient
        for i in range(h):
            t = i / max(1, h-1)
            r1,g1,b1 = color_to_rgb(PALETTE["bg0"])
            r2,g2,b2 = color_to_rgb(PALETTE["bg1"])
            r = int(r1*(1-t)+r2*t)
            g = int(g1*(1-t)+g2*t)
            b = int(b1*(1-t)+b2*t)
            draw.line([(0,i),(w,i)], fill=(r,g,b))
        # add soft colored glows (ellipses)
        glow = Image.new("RGBA",(w,h),(0,0,0,0))
        gd = ImageDraw.Draw(glow)
        # random-ish but stable glows
        spots = [
            (int(w*0.2), int(h*0.2), int(w*0.6), int(h*0.6), PALETTE["purple"]),
            (int(w*0.75), int(h*0.15), int(w*0.45), int(h*0.45), PALETTE["cyan"]),
            (int(w*0.8), int(h*0.7), int(w*0.5), int(h*0.5), PALETTE["accent"])
        ]
        for (cx, cy, rw, rh, col) in spots:
            rgb = color_to_rgb(col)
            maxr = max(rw, rh)//2
            for k in range(maxr,0,-int(max(2, maxr/12))):
                a = int(8 + (200*(1 - k/maxr)))  # alpha
                fill = (rgb[0], rgb[1], rgb[2], a)
                gd.ellipse([cx-k, cy-k, cx+k, cy+k], fill=fill)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=40))
        base = Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")
        # final blur for glass-like base
        base = base.filter(ImageFilter.GaussianBlur(radius=18))
        self.bg_base = base
        # create initial combo
        self._composite_bg_with_particles()

    # --- particle system: render into overlay (PIL) and composite on top of bg_base
    def _composite_bg_with_particles(self):
        base = self.bg_base.copy()
        w, h = base.size
        overlay = Image.new("RGBA", (w, h), (0,0,0,0))
        od = ImageDraw.Draw(overlay)
        # draw a few particles stored in self.particles
        for p in list(self.particles):
            x, y, r, a = p
            rgb = (255,255,255)
            # multiple concentric rings with alpha for glow
            for k,alpha in [(r, int(80*a)), (int(r*0.6), int(40*a)), (int(r*0.3), int(18*a))]:
                if k <=0: continue
                od.ellipse([x-k, y-k, x+k, y+k], fill=(rgb[0],rgb[1],rgb[2], max(1,int(alpha))))
        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=6))
        combo = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
        self.bg_overlay = overlay
        self.bg_combo_tk = ImageTk.PhotoImage(combo)
        # put on canvas (or update existing)
        self.canvas.delete("bgimg")
        self.canvas.create_image(0,0, anchor="nw", image=self.bg_combo_tk, tags="bgimg")
        # raise windows (ensure UI visible) if they exist
        for attr in ("top_win", "right_win", "preview_win", "gallery_win"):
            if hasattr(self, attr):
                try:
                    win = getattr(self, attr)
                    # some values may be None until created
                    if win:
                        self.canvas.tag_raise(win)
                except Exception:
                    pass

    def _update_bg(self):
        # particle lifecycle update
        newp = []
        w = self.bg_base.size[0]
        h = self.bg_base.size[1]
        for p in self.particles:
            x,y,r,a = p
            y -= random.uniform(0.2, 1.0)
            a -= 0.006
            r -= 0.02
            if a > 0.02 and r > 0.5 and 0 <= x <= w and 0 <= y <= h:
                newp.append([x,y,r,a])
        self.particles = newp
        # occasionally add slight floating ambient particles
        if random.random() < 0.03 and len(self.particles) < 220:
            self.particles.append([random.randint(0, max(1,self.bg_base.size[0])), random.randint(0, max(1,self.bg_base.size[1])), random.randint(8,26), random.uniform(0.08,0.35)])
        # composite and update canvas
        try:
            self._composite_bg_with_particles()
        except Exception:
            pass
        self.after(50, self._update_bg)

    def _on_mouse_move(self, event):
        # add particle at mouse with modest size
        x = event.x
        y = event.y
        if 0 <= x <= self.bg_base.size[0] and 0 <= y <= self.bg_base.size[1]:
            self.particles.append([x, y, random.randint(8,20), random.uniform(0.12,0.42)])
            if len(self.particles) > 300:
                self.particles = self.particles[-300:]

    # --- file / rendering
    def _load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Media","*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.avi")])
        if not path:
            return
        self.file_path = path
        # quick preview first item
        try:
            if path.lower().endswith((".mp4", ".avi", ".mov")):
                cap = cv2.VideoCapture(path)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(frame)
                    self._show_preview_pil(pil)
            else:
                pil = Image.open(path)
                self._show_preview_pil(pil)
        except Exception as e:
            print("preview error", e)

    def _render_image(self):
        if not self.file_path:
            return
        # render in background
        def job():
            try:
                pil = Image.open(self.file_path)
                asc = image_to_ascii_data(pil, self.width_chars)
                out = render_ascii_image(asc, font_size=self.font_size, style=self.style, custom_fg_hex=self.custom_fg, bg_hex=self.bg_hex)
                self.output_pil = out
                self.after(0, lambda: self._on_render_done(out))
            except Exception as e:
                print("render error", e)
                traceback.print_exc()
        t = threading.Thread(target=job, daemon=True)
        t.start()
        self.render_thread = t

    def _on_render_done(self, pil):
        self._show_preview_pil(pil)
        self._add_to_gallery(pil)

    def _export_image(self):
        if not self.output_pil:
            return
        save = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG","*.png"),("GIF","*.gif")])
        if not save:
            return
        try:
            ext = os.path.splitext(save)[1].lower()
            if ext == ".png":
                self.output_pil.save(save)
            elif ext == ".gif":
                imageio.mimsave(save, [np.array(self.output_pil)], duration=0.6)
        except Exception as e:
            print("save error", e)

    def _show_preview_pil(self, pil):
        # fit into preview_canvas
        c_w = self.preview_canvas.winfo_width() or 900
        c_h = self.preview_canvas.winfo_height() or 560
        iw, ih = pil.size
        scale = min(c_w/iw, c_h/ih, 1.0)
        nw = max(1, int(iw*scale))
        nh = max(1, int(ih*scale))
        resized = pil.resize((nw, nh), Image.Resampling.LANCZOS)
        self.preview_img_ref = ImageTk.PhotoImage(resized)
        self.preview_canvas.delete("PREV")
        self.preview_canvas.create_image(c_w//2, c_h//2, image=self.preview_img_ref, tags="PREV", anchor="center")
        self.preview_canvas.tag_bind("PREV", "<Button-1>", lambda e: self._open_fullscreen(pil))

    def _add_to_gallery(self, pil):
        thumb = pil.copy()
        thumb.thumbnail((150,150), Image.Resampling.LANCZOS)
        tkthumb = ImageTk.PhotoImage(thumb)
        lbl = ctk.CTkLabel(self.gallery_scroll, image=tkthumb, text="")
        lbl.image = tkthumb
        lbl.pack(side="left", padx=6, pady=6)
        lbl.bind("<Button-1>", lambda e, i=pil: self._open_fullscreen(i))
        self.gallery.append(pil)

    def _style_change(self, v):
        self.style = v
        # enable color pickers only for custom
        if v != "custom":
            self.pick_text.configure(state="disabled")
            self.pick_bg.configure(state="disabled")
        else:
            self.pick_text.configure(state="normal")
            self.pick_bg.configure(state="normal")

    def _width_change(self, v):
        self.width_chars = int(float(v))

    def _font_change(self, v):
        self.font_size = int(float(v))

    def _pick_text_color(self):
        c = colorchooser.askcolor()[1]
        if c:
            self.custom_fg = c
            self.text_indicator.configure(fg_color=c)

    def _pick_bg_color(self):
        c = colorchooser.askcolor()[1]
        if c:
            self.bg_hex = c
            self.bg_indicator.configure(fg_color=c)
            # regenerate base to reflect new BG tint
            self._regen_bg_base((max(200,self.winfo_width()), max(200,self.winfo_height())))

    def _open_fullscreen(self, pil):
        if not pil:
            return
        fs = FullscreenViewer(self, pil)
        fs.grab_set()

# ---------------- Fullscreen viewer ----------------
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
        self.dragging = False
        self.last = (0,0)
        self.canvas = Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._render_image()
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        # exit button
        exit_btn = ctk.CTkButton(self, text="✕", width=60, height=40, corner_radius=12, command=self.destroy, fg_color="#222426")
        exit_btn.place(relx=0.98, rely=0.02, anchor="ne")

    def _render_image(self):
        w = max(1, int(self.pil.width * self.zoom))
        h = max(1, int(self.pil.height * self.zoom))
        img = self.pil.resize((w,h), Image.Resampling.LANCZOS)
        self.tkimg = ImageTk.PhotoImage(img)
        self.canvas.delete("IMG")
        cx = self.winfo_screenwidth()//2 + self.offset_x
        cy = self.winfo_screenheight()//2 + self.offset_y
        self.canvas.create_image(cx, cy, image=self.tkimg, tags="IMG", anchor="center")

    def _on_wheel(self, e):
        factor = 1.15 if e.delta > 0 else 1/1.15
        self.zoom *= factor
        self._render_image()

    def _on_down(self, e):
        self.dragging = True
        self.last = (e.x, e.y)

    def _on_drag(self, e):
        dx = e.x - self.last[0]
        dy = e.y - self.last[1]
        self.offset_x += dx
        self.offset_y += dy
        self.last = (e.x, e.y)
        self._render_image()

# ---------------- Run ----------------
def main():
    app = UltraASCIIApp()
    app.mainloop()

if __name__ == "__main__":
    main()
