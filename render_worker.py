from PySide6.QtCore import QThread, Signal
import base64
import hashlib
import io

import imageio, cv2, numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageFont, ImageChops
import tempfile, subprocess, shutil, os, re
from core_utils import image_to_ascii_data, render_ascii_pil, DEFAULT_ASCII, WATERMARK as CORE_WATERMARK

class RenderWorker(QThread):
    progress = Signal(int)
    finished_path = Signal(str)
    error = Signal(str)
    started = Signal()
    stopped = Signal()

    def __init__(self, src_path, out_path, fps=24, width_chars=320, ascii_chars=DEFAULT_ASCII, invert=False, contrast_pct=100, font_size=12, style='bw', fg_hex='#FFFFFF', bg_hex='#0F0F12', watermark=True):
        super().__init__()
        self.src = src_path
        self.out = out_path
        self.fps = fps
        self.width_chars = width_chars
        self.ascii_chars = ascii_chars
        self.invert = invert
        self.contrast_pct = contrast_pct
        self.font_size = font_size
        self.style = style
        self.fg_hex = fg_hex
        self.bg_hex = bg_hex
        self.watermark = watermark
        self.watermark_text = CORE_WATERMARK
        self.gamma_pct = 100
        self.denoise = False
        self.sharpen = False
        self.edge_boost = False
        self.keep_size = False
        self.target_size = None
        self.scale_mult = 1
        # advanced options
        self.codec = 'libx264'
        self.bitrate = None
        self.threads = 4
        self.preset = "medium"
        self.crf = 20
        self._cancel = False
        # rendering device: 'cpu' or 'gpu'
        self.render_device = 'cpu'
        self.keep_source_audio = True
        self.audio_source_path = None
        self.audio_gain_db = 0.0
        self.audio_lowpass_hz = 0
        self.pro_scanlines = False
        self.pro_bloom = 0
        self.pro_vignette = 0
        self.pro_poster_bits = 0
        self.pro_grain = 0
        self.pro_chroma = 0
        self.pro_scan_strength = 28
        self.pro_scan_step = 3
        self.pro_glitch = 0
        self.pro_glitch_density = 35
        self.pro_glitch_shift = 42
        self.pro_glitch_rgb = 1
        self.pro_glitch_block = 10
        self.pro_glitch_jitter = 1
        self.pro_glitch_noise = 12
        self.pro_curvature = 0
        self.pro_concavity = 0
        self.pro_curvature_center_x = 0
        self.pro_curvature_expand = 0
        self.pro_curvature_type = "spherical"
        self.pro_ribbing = 0
        self.pro_clarity = 0
        self.pro_motion_blur = 0
        self.pro_color_boost = 0
        # Optional editor overlay state from UI.
        self.editor_state = None
        self.trim_start_ms = 0
        self.trim_end_ms = 0
        self._media_layer_cache = {}
        self._photo_paint_cache_token = None
        self._photo_paint_cache_base = None
        self._photo_paint_cache_scaled_size = None
        self._photo_paint_cache_scaled = None

    def cancel(self):
        self._cancel = True

    def _has_preprocess_fx(self):
        try:
            if float(getattr(self, "gamma_pct", 100)) != 100.0:
                return True
        except Exception:
            pass
        return any([
            bool(getattr(self, "denoise", False)),
            bool(getattr(self, "sharpen", False)),
            bool(getattr(self, "edge_boost", False)),
        ])

    def _has_postprocess_fx(self):
        return any([
            int(getattr(self, "pro_poster_bits", 0)) > 0,
            int(getattr(self, "pro_bloom", 0)) > 0,
            int(getattr(self, "pro_vignette", 0)) > 0,
            int(getattr(self, "pro_chroma", 0)) > 0,
            int(getattr(self, "pro_grain", 0)) > 0,
            bool(getattr(self, "pro_scanlines", False)),
            int(getattr(self, "pro_glitch", 0)) > 0,
            int(getattr(self, "pro_curvature", 0)) > 0,
            int(getattr(self, "pro_concavity", 0)) > 0,
            int(getattr(self, "pro_ribbing", 0)) > 0,
            int(getattr(self, "pro_clarity", 0)) > 0,
            int(getattr(self, "pro_motion_blur", 0)) > 0,
            int(getattr(self, "pro_color_boost", 0)) > 0,
        ])

    def _resolve_ffmpeg_exe(self):
        ff = shutil.which("ffmpeg")
        if ff and os.path.exists(ff):
            return ff
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
            if ff and os.path.exists(ff):
                return ff
        except Exception:
            pass
        return None

    def _resolve_ffprobe_exe(self):
        fp = shutil.which("ffprobe")
        if fp and os.path.exists(fp):
            return fp
        try:
            ff = self._resolve_ffmpeg_exe()
            if not ff:
                return None
            folder = os.path.dirname(os.path.abspath(ff))
            name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
            cand = os.path.join(folder, name)
            if os.path.exists(cand):
                return cand
        except Exception:
            pass
        return None

    def _file_has_audio(self, path):
        try:
            if not path or not os.path.exists(path):
                return False
            fp = self._resolve_ffprobe_exe()
            if fp:
                cmd = [
                    fp, "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    path,
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                out = (proc.stdout or "").strip().lower()
                if out:
                    return True
            ff = self._resolve_ffmpeg_exe()
            if not ff:
                return False
            proc = subprocess.run([ff, "-i", path], capture_output=True, text=True, check=False)
            txt = ((proc.stderr or "") + "\n" + (proc.stdout or "")).lower()
            return bool(re.search(r"\baudio:\b", txt))
        except Exception:
            return False

    def _apply_glitch_effect(self, img, amount_override=None):
        try:
            amount = int(getattr(self, "pro_glitch", 0) if amount_override is None else amount_override)
            if amount <= 0:
                return img
            arr = np.array(img.convert("RGB"), dtype=np.uint8)
            h, w = arr.shape[:2]
            density = max(0, min(100, int(getattr(self, "pro_glitch_density", 35))))
            shift_strength = max(0, min(100, int(getattr(self, "pro_glitch_shift", 42))))
            rgb_split = max(0, int(getattr(self, "pro_glitch_rgb", 1)))
            block_sz = max(0, int(getattr(self, "pro_glitch_block", 10)))
            jitter = max(0, int(getattr(self, "pro_glitch_jitter", 1)))
            static_noise = max(0, min(100, int(getattr(self, "pro_glitch_noise", 12))))
            rows = max(1, int(h * (0.004 + (density / 100.0) * (0.04 + amount / 2600.0))))
            band_base = max(1, int(h / 180))
            max_shift = max(1, int(w * (0.003 + (shift_strength / 100.0) * (0.11 + amount / 700.0))))
            for _ in range(rows):
                y = np.random.randint(0, max(1, h - 1))
                band = np.random.randint(1, max(2, band_base + amount // 24 + 2))
                shift = np.random.randint(-max_shift, max_shift + 1)
                y2 = min(h, y + band)
                arr[y:y2, :, :] = np.roll(arr[y:y2, :, :], shift, axis=1)
            if rgb_split > 0:
                split = max(1, int(rgb_split + amount / 34.0))
                arr[:, :, 0] = np.roll(arr[:, :, 0], split, axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -split, axis=1)
            if block_sz > 0 and w > 4 and h > 4:
                blocks = max(1, int(1 + amount / 24 + density / 36))
                max_side = min(max(4, block_sz * 2), max(6, min(w, h) // 3))
                for _ in range(blocks):
                    bw = np.random.randint(max(4, block_sz), max(max(5, block_sz + 1), max_side + 1))
                    bh = np.random.randint(max(3, block_sz // 2 + 1), max(max(4, block_sz // 2 + 2), max_side // 2 + 2))
                    x = np.random.randint(0, max(1, w - bw))
                    y = np.random.randint(0, max(1, h - bh))
                    dx = np.random.randint(-max_shift, max_shift + 1)
                    src = arr[y:y + bh, x:x + bw, :].copy()
                    tx = max(0, min(w - bw, x + dx))
                    arr[y:y + bh, tx:tx + bw, :] = src
            if jitter > 0:
                dy = np.random.randint(-jitter, jitter + 1)
                if dy != 0:
                    arr = np.roll(arr, dy, axis=0)
            if static_noise > 0:
                sigma = max(1.0, static_noise * 0.20 + amount * 0.08)
                noise = np.random.normal(0.0, sigma, arr.shape).astype(np.int16)
                arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            if amount > 60 and h > 4:
                y = np.random.randint(0, h - 1)
                line = np.random.randint(120, 255, (1, w, 3), dtype=np.uint8)
                arr[y:y + 1, :, :] = line
            return Image.fromarray(arr, mode="RGB")
        except Exception:
            return img

    def _apply_curvature_effect(self, img, convex_amount, concave_amount=0, center_x=0, expand=0, lens_type="spherical"):
        try:
            convex = max(0, min(100, int(convex_amount)))
            concave = max(0, min(100, int(concave_amount)))
            signed = float(convex - concave)
            cx_shift = max(-100, min(100, int(center_x)))
            expand_val = max(0, min(100, int(expand)))
            if abs(signed) <= 0.01 and expand_val <= 0 and cx_shift == 0:
                return img
            arr = np.array(img.convert("RGB"), dtype=np.uint8)
            h, w = arr.shape[:2]
            if w < 8 or h < 8:
                return img
            lens = str(lens_type or "spherical").strip().lower()
            if lens not in ("spherical", "barrel", "pincushion", "horizontal", "vertical"):
                lens = "spherical"
            cx_off = (float(cx_shift) / 100.0) * 0.45
            zoom = 1.0 + (float(expand_val) / 100.0) * 0.85 + (abs(signed) / 100.0) * 0.28
            x = np.linspace(-1.0, 1.0, w, dtype=np.float32) - np.float32(cx_off)
            y = np.linspace(-1.0, 1.0, h, dtype=np.float32)
            xv, yv = np.meshgrid(x, y)
            xv /= np.float32(max(0.2, zoom))
            yv /= np.float32(max(0.2, zoom))
            r2 = np.clip(xv * xv + yv * yv, 0.0, 8.0)
            k = np.float32((signed / 100.0) * 0.52)
            if lens == "horizontal":
                fx = 1.0 + k * (xv * xv)
                fy = np.ones_like(fx, dtype=np.float32)
                src_x = xv * fx + np.float32(cx_off)
                src_y = yv * fy
            elif lens == "vertical":
                fy = 1.0 + k * (yv * yv)
                fx = np.ones_like(fy, dtype=np.float32)
                src_x = xv * fx + np.float32(cx_off)
                src_y = yv * fy
            else:
                if lens == "barrel":
                    q = r2 + 0.35 * (r2 * r2)
                elif lens == "pincushion":
                    q = 0.55 * r2 + 0.75 * np.sqrt(r2 + 1e-8) * r2
                else:
                    q = r2
                factor = 1.0 + k * q
                src_x = xv * factor + np.float32(cx_off)
                src_y = yv * factor
            map_x = ((src_x + 1.0) * 0.5 * (w - 1)).astype(np.float32)
            map_y = ((src_y + 1.0) * 0.5 * (h - 1)).astype(np.float32)
            warped = cv2.remap(
                arr,
                map_x,
                map_y,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT101,
            )
            return Image.fromarray(warped, mode="RGB")
        except Exception:
            return img

    def _apply_ribbing_effect(self, img, amount):
        try:
            amt = max(0, min(100, int(amount)))
            if amt <= 0:
                return img
            arr = np.array(img.convert("RGB"), dtype=np.int16)
            h, w = arr.shape[:2]
            if w < 6 or h < 6:
                return img
            step = max(2, int(10 - amt / 14.0))
            dark = int(3 + amt * 0.14)
            side = max(1, dark // 3)
            for x in range(0, w, step):
                arr[:, x:x + 1, :] = np.clip(arr[:, x:x + 1, :] - dark, 0, 255)
                if x > 0:
                    arr[:, x - 1:x, :] = np.clip(arr[:, x - 1:x, :] + side, 0, 255)
                if x + 1 < w:
                    arr[:, x + 1:x + 2, :] = np.clip(arr[:, x + 1:x + 2, :] + side, 0, 255)
            if amt >= 12:
                arr[::2, :, :] = np.clip(arr[::2, :, :] - int(1 + amt * 0.05), 0, 255)
            return Image.fromarray(arr.astype(np.uint8), mode="RGB")
        except Exception:
            return img

    def _safe_font(self, family, size):
        try:
            s = max(6, int(size))
        except Exception:
            s = 18
        def _norm(txt):
            return "".join(ch for ch in str(txt or "").lower() if ch.isalnum())
        fam = str(family or "").strip()
        fam_norm = _norm(fam)
        fam_tokens = [
            "".join(ch for ch in str(tok).lower() if ch.isalnum())
            for tok in str(fam).replace("_", " ").replace("-", " ").split()
            if str(tok).strip()
        ]
        candidates = []
        if fam:
            candidates.extend([
                fam,
                fam + ".ttf",
                os.path.join("C:\\Windows\\Fonts", fam + ".ttf"),
                os.path.join("C:\\Windows\\Fonts", fam.replace(" ", "") + ".ttf"),
            ])
        try:
            cache = getattr(self, "_font_family_lookup", None)
            if cache is None:
                cache = {}
                setattr(self, "_font_family_lookup", cache)
            if fam_norm and fam_norm in cache:
                candidates.extend(list(cache.get(fam_norm) or []))
            elif fam_norm:
                roots = []
                win_dir = str(os.environ.get("WINDIR", "C:\\Windows") or "C:\\Windows")
                roots.append(os.path.join(win_dir, "Fonts"))
                roots.extend([
                    "/usr/share/fonts",
                    "/usr/local/share/fonts",
                    os.path.expanduser("~/.fonts"),
                ])
                hits = []
                for root in roots:
                    if not root or (not os.path.isdir(root)):
                        continue
                    try:
                        for fn in os.listdir(root):
                            low = str(fn or "").lower()
                            if not low.endswith((".ttf", ".otf", ".ttc")):
                                continue
                            nn = _norm(low)
                            ok = bool(fam_norm and fam_norm in nn)
                            if (not ok) and fam_tokens:
                                ok = any(tok in nn for tok in fam_tokens if len(tok) >= 3)
                            if ok:
                                hits.append(os.path.join(root, fn))
                                if len(hits) >= 24:
                                    break
                    except Exception:
                        continue
                    if len(hits) >= 24:
                        break
                cache[fam_norm] = list(hits)
                candidates.extend(hits)
        except Exception:
            pass
        candidates.extend([
            os.path.join("C:\\Windows\\Fonts", "arial.ttf"),
            os.path.join("C:\\Windows\\Fonts", "segoeui.ttf"),
            os.path.join("C:\\Windows\\Fonts", "consola.ttf"),
            "arial.ttf",
            "segoeui.ttf",
            "consola.ttf",
        ])
        seen = set()
        for cand in candidates:
            c = str(cand or "").strip()
            if not c or c in seen:
                continue
            seen.add(c)
            try:
                return ImageFont.truetype(c, s)
            except Exception:
                continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _cubic_bezier_progress(self, t, x1, y1, x2, y2):
        tt = max(0.0, min(1.0, float(t)))
        ax = 3.0 * x1 - 3.0 * x2 + 1.0
        bx = -6.0 * x1 + 3.0 * x2
        cx = 3.0 * x1
        ay = 3.0 * y1 - 3.0 * y2 + 1.0
        by = -6.0 * y1 + 3.0 * y2
        cy = 3.0 * y1
        s = tt
        for _ in range(7):
            xs = ((ax * s + bx) * s + cx) * s
            dx = (3.0 * ax * s + 2.0 * bx) * s + cx
            if abs(dx) < 1e-6:
                break
            s2 = s - (xs - tt) / dx
            if s2 < 0.0 or s2 > 1.0:
                break
            s = s2
        lo = 0.0
        hi = 1.0
        for _ in range(12):
            xs = ((ax * s + bx) * s + cx) * s
            if xs < tt:
                lo = s
            else:
                hi = s
            s = (lo + hi) * 0.5
        ys = ((ay * s + by) * s + cy) * s
        return max(0.0, min(1.0, float(ys)))

    def _ease_progress(self, layer, k):
        kk = max(0.0, min(1.0, float(k)))
        ease = str((layer or {}).get("anim_ease", "linear") or "linear").strip().lower()
        if ease == "ease_in":
            return kk * kk
        if ease == "ease_out":
            return 1.0 - (1.0 - kk) * (1.0 - kk)
        if ease == "ease_in_out":
            if kk < 0.5:
                return 2.0 * kk * kk
            return 1.0 - ((-2.0 * kk + 2.0) ** 2) * 0.5
        if ease == "bezier":
            bz = (layer or {}).get("anim_bezier", [0.25, 0.1, 0.25, 1.0])
            if not isinstance(bz, (list, tuple)) or len(bz) < 4:
                bz = [0.25, 0.1, 0.25, 1.0]
            try:
                x1 = max(0.0, min(1.0, float(bz[0])))
                y1 = max(0.0, min(1.0, float(bz[1])))
                x2 = max(0.0, min(1.0, float(bz[2])))
                y2 = max(0.0, min(1.0, float(bz[3])))
            except Exception:
                x1, y1, x2, y2 = 0.25, 0.1, 0.25, 1.0
            return self._cubic_bezier_progress(kk, x1, y1, x2, y2)
        return kk

    def _layer_t_xy(self, layer, t_ms):
        try:
            x0 = float(layer.get("x", 24))
            y0 = float(layer.get("y", 24))
            x1 = float(layer.get("x1", x0))
            y1 = float(layer.get("y1", y0))
            t0 = int(layer.get("anim_in_ms", layer.get("start_ms", 0)) or layer.get("start_ms", 0))
            t1 = int(layer.get("anim_out_ms", layer.get("end_ms", 0)) or layer.get("end_ms", 0))
            c0 = int(layer.get("start_ms", 0) or 0)
            c1 = int(layer.get("end_ms", t1) or t1)
            t0 = max(c0, min(c1, t0))
            t1 = max(t0, min(c1, t1))
            if t1 <= t0:
                return int(round(x0)), int(round(y0))
            if t_ms <= t0:
                k = 0.0
            elif t_ms >= t1:
                k = 1.0
            else:
                k = float(t_ms - t0) / float(max(1, t1 - t0))
            k = self._ease_progress(layer, k)
            return int(round(x0 + (x1 - x0) * k)), int(round(y0 + (y1 - y0) * k))
        except Exception:
            return int(layer.get("x", 24)), int(layer.get("y", 24))

    def _load_media_layer_frame(self, layer, t_ms=0):
        path = str((layer or {}).get("path", "") or "").strip()
        if not path or (not os.path.exists(path)):
            return None
        mtype = str((layer or {}).get("type", "") or "").strip().lower()
        if not mtype:
            low = path.lower()
            if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
                mtype = "video"
            elif low.endswith(".gif"):
                mtype = "gif"
            else:
                mtype = "image"
        try:
            bucket = int(int(t_ms) // 120) if mtype == "video" else int(int(t_ms) // 100)
            key = (path, mtype, bucket if mtype in ("video", "gif") else 0)
            cache = getattr(self, "_media_layer_cache", None)
            if isinstance(cache, dict) and key in cache:
                try:
                    return cache[key].copy()
                except Exception:
                    return cache[key]
            frame = None
            if mtype == "video":
                cap = cv2.VideoCapture(path)
                if cap is not None and cap.isOpened():
                    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t_ms)))
                    ok, fr = cap.read()
                    if not ok:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok, fr = cap.read()
                    if ok and fr is not None:
                        fr = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
                        frame = Image.fromarray(fr).convert("RGBA")
                if cap is not None:
                    cap.release()
            elif mtype == "gif":
                with Image.open(path) as gim:
                    n = max(1, int(getattr(gim, "n_frames", 1) or 1))
                    if n > 1:
                        idx = int(max(0, t_ms) / 80.0) % n
                        gim.seek(idx)
                    frame = gim.convert("RGBA")
            else:
                with Image.open(path) as im:
                    frame = im.convert("RGBA")
            if frame is None:
                return None
            if isinstance(cache, dict):
                if len(cache) > 48:
                    try:
                        for k in list(cache.keys())[:16]:
                            cache.pop(k, None)
                    except Exception:
                        cache.clear()
                cache[key] = frame.copy()
            return frame
        except Exception:
            return None

    def _draw_media_layers(self, pil, st, t_ms=0):
        layers = st.get("media_layers", []) or []
        if not layers:
            return pil
        base = pil.convert("RGBA")
        for layer in layers:
            try:
                if not bool((layer or {}).get("enabled", True)):
                    continue
                t0 = int((layer or {}).get("start_ms", 0) or 0)
                t1 = int((layer or {}).get("end_ms", 0) or 0)
                if t1 > t0 and (int(t_ms) < t0 or int(t_ms) > t1):
                    continue
                try:
                    spd = float((layer or {}).get("speed", 1.0) or 1.0)
                except Exception:
                    spd = 1.0
                spd = max(0.05, min(16.0, spd))
                local_t = int(max(0, (int(t_ms) - t0) * spd))
                ov = self._load_media_layer_frame(layer or {}, t_ms=local_t)
                if ov is None:
                    continue
                sx = max(0.1, min(8.0, float((layer or {}).get("scale_x", 1.0) or 1.0)))
                sy = max(0.1, min(8.0, float((layer or {}).get("scale_y", 1.0) or 1.0)))
                if abs(sx - 1.0) > 0.01 or abs(sy - 1.0) > 0.01:
                    ov = ov.resize((max(1, int(ov.width * sx)), max(1, int(ov.height * sy))), Image.Resampling.LANCZOS)
                alpha = max(0, min(255, int((layer or {}).get("alpha", 255) or 255)))
                if alpha < 255:
                    a = ov.split()[-1]
                    a = a.point(lambda v: int(v * alpha / 255))
                    ov.putalpha(a)
                x, y = self._layer_t_xy(layer or {}, int(t_ms))
                blend = str((layer or {}).get("blend", "normal") or "normal").strip().lower()
                if blend == "normal":
                    base.alpha_composite(ov, (int(x), int(y)))
                    continue
                bx0 = max(0, int(x))
                by0 = max(0, int(y))
                bx1 = min(base.width, int(x) + ov.width)
                by1 = min(base.height, int(y) + ov.height)
                if bx1 <= bx0 or by1 <= by0:
                    continue
                ox0 = max(0, -int(x))
                oy0 = max(0, -int(y))
                ovc = ov.crop((ox0, oy0, ox0 + (bx1 - bx0), oy0 + (by1 - by0)))
                reg = base.crop((bx0, by0, bx1, by1)).convert("RGB")
                ov_rgb = ovc.convert("RGB")
                if blend == "screen":
                    mixed = ImageChops.screen(reg, ov_rgb)
                elif blend == "multiply":
                    mixed = ImageChops.multiply(reg, ov_rgb)
                elif blend == "add":
                    mixed = ImageChops.add(reg, ov_rgb, scale=1.0, offset=0)
                else:
                    mixed = ov_rgb
                rr = reg.convert("RGBA")
                rr.paste(mixed.convert("RGBA"), (0, 0), ovc.split()[-1])
                base.paste(rr, (bx0, by0))
            except Exception:
                continue
        return base.convert("RGB")

    def _apply_editor_basic_fx(self, pil, st):
        img = pil.convert("RGB")
        try:
            img = ImageEnhance.Brightness(img).enhance(max(0.0, float(st.get("brightness", 100)) / 100.0))
        except Exception:
            pass
        try:
            img = ImageEnhance.Contrast(img).enhance(max(0.0, float(st.get("contrast", 100)) / 100.0))
        except Exception:
            pass
        try:
            img = ImageEnhance.Color(img).enhance(max(0.0, float(st.get("saturation", 100)) / 100.0))
        except Exception:
            pass
        try:
            img = ImageEnhance.Sharpness(img).enhance(max(0.0, float(st.get("sharpness", 100)) / 100.0))
        except Exception:
            pass
        try:
            h = int(st.get("hue", 0))
            if h != 0:
                hsv = img.convert("HSV")
                arr = np.array(hsv, dtype=np.uint8)
                arr[:, :, 0] = ((arr[:, :, 0].astype(np.int16) + int(h / 2)) % 256).astype(np.uint8)
                img = Image.fromarray(arr, mode="HSV").convert("RGB")
        except Exception:
            pass
        try:
            ex = int(st.get("exposure", 0))
            if ex != 0:
                img = ImageEnhance.Brightness(img).enhance(max(0.05, 1.0 + (ex / 120.0)))
        except Exception:
            pass
        try:
            temp = int(st.get("temperature", 0))
            if temp != 0:
                arr = np.array(img, dtype=np.int16)
                delta = int(temp * 0.65)
                arr[:, :, 0] = np.clip(arr[:, :, 0] + delta, 0, 255)
                arr[:, :, 2] = np.clip(arr[:, :, 2] - delta, 0, 255)
                img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        except Exception:
            pass
        return img

    def _editor_photo_paint_layer(self, st, target_size):
        if not isinstance(st, dict):
            return None
        payload = str(st.get("photo_paint_png_b64", "") or "").strip()
        if not payload:
            return None
        token = str(st.get("photo_paint_hash", "") or "")
        if not token:
            try:
                token = hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()
            except Exception:
                token = f"len:{len(payload)}"
        if token != getattr(self, "_photo_paint_cache_token", None):
            try:
                raw = base64.b64decode(payload.encode("ascii"), validate=False)
                layer = Image.open(io.BytesIO(raw)).convert("RGBA")
            except Exception:
                layer = None
            self._photo_paint_cache_token = token
            self._photo_paint_cache_base = layer
            self._photo_paint_cache_scaled_size = None
            self._photo_paint_cache_scaled = None
        base_layer = getattr(self, "_photo_paint_cache_base", None)
        if base_layer is None:
            return None
        tgt = (max(1, int(target_size[0])), max(1, int(target_size[1])))
        try:
            if base_layer.size == tgt:
                return base_layer.copy()
            if tgt != getattr(self, "_photo_paint_cache_scaled_size", None):
                self._photo_paint_cache_scaled = base_layer.resize(tgt, Image.Resampling.LANCZOS)
                self._photo_paint_cache_scaled_size = tgt
            scaled = getattr(self, "_photo_paint_cache_scaled", None)
            return scaled.copy() if scaled is not None else None
        except Exception:
            return None

    def _apply_editor_photo_paint(self, pil_img, st):
        if not isinstance(st, dict):
            return pil_img
        if not bool(st.get("photo_paint_enabled", False)):
            return pil_img
        opacity = max(0, min(100, int(st.get("photo_paint_opacity", 100) or 100)))
        if opacity <= 0:
            return pil_img
        layer = self._editor_photo_paint_layer(st, pil_img.size)
        if layer is None:
            return pil_img
        if opacity < 100:
            try:
                a = np.array(layer.split()[-1], dtype=np.float32)
                a *= float(opacity) / 100.0
                layer.putalpha(np.clip(a, 0, 255).astype(np.uint8))
            except Exception:
                pass
        base = pil_img.convert("RGBA")
        try:
            base.alpha_composite(layer)
            return base.convert("RGB")
        except Exception:
            return pil_img

    def _apply_editor_state(self, pil, t_ms=0):
        st = getattr(self, "editor_state", None)
        if not isinstance(st, dict) or not bool(st.get("enabled", False)):
            return pil.convert("RGB")
        img = pil.convert("RGB")
        try:
            if bool(st.get("crop_enabled", False)):
                x = max(0, int(st.get("crop_x", 0)))
                y = max(0, int(st.get("crop_y", 0)))
                w = max(1, int(st.get("crop_w", img.width)))
                h = max(1, int(st.get("crop_h", img.height)))
                x2 = min(img.width, x + w)
                y2 = min(img.height, y + h)
                if x2 > x + 1 and y2 > y + 1:
                    img = img.crop((x, y, x2, y2))
        except Exception:
            pass
        try:
            if bool(st.get("mask_enabled", False)) or bool(st.get("mask_use_image", False)):
                fx = self._apply_editor_basic_fx(img.copy(), st)
                used_media_mask = False
                if bool(st.get("mask_use_image", False)):
                    mpath = str(st.get("mask_image_path", "") or "").strip()
                    if mpath:
                        try:
                            mtype = "image"
                            low = mpath.lower()
                            if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
                                mtype = "video"
                            elif low.endswith(".gif"):
                                mtype = "gif"
                            mlyr = {"path": mpath, "type": mtype}
                            msrc = self._load_media_layer_frame(mlyr, int(t_ms))
                            if msrc is not None:
                                mm = ImageOps.fit(msrc.convert("L"), img.size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                                img = Image.composite(fx, img, mm)
                                used_media_mask = True
                        except Exception:
                            used_media_mask = False
                if not used_media_mask:
                    mx = max(0, int(st.get("mask_x", 0)))
                    my = max(0, int(st.get("mask_y", 0)))
                    mw = max(1, int(st.get("mask_w", img.width)))
                    mh = max(1, int(st.get("mask_h", img.height)))
                    mx2 = min(img.width, mx + mw)
                    my2 = min(img.height, my + mh)
                    if mx2 > mx + 1 and my2 > my + 1:
                        m = Image.new("L", img.size, 0)
                        md = ImageDraw.Draw(m)
                        md.rectangle((mx, my, mx2, my2), fill=255)
                        img = Image.composite(fx, img, m)
                    else:
                        img = fx
            else:
                img = self._apply_editor_basic_fx(img, st)
        except Exception:
            pass
        # Nodes chain + custom python node.
        try:
            if bool(st.get("nodes_enabled", False)):
                chain = [str(x).strip() for x in (st.get("node_chain", []) or []) if str(x).strip()]
                params = st.get("node_params", []) or []
                order = self._resolve_editor_node_chain(st)
                for idx in order:
                    if idx < 0 or idx >= len(chain):
                        continue
                    nid = str(chain[idx] or "").strip().lower()
                    prm = params[idx] if idx < len(params) and isinstance(params[idx], dict) else {}
                    if not bool(prm.get("enabled", True)):
                        continue
                    intensity = max(0, min(100, int(prm.get("intensity", 55) or 55)))
                    radius = max(0, min(32, int(prm.get("radius", 2) or 2)))
                    mix = max(0.0, min(1.0, float(int(prm.get("mix", 100) or 100)) / 100.0))
                    value = max(-200, min(200, int(prm.get("value", 0) or 0)))
                    seed = max(0, min(9999, int(prm.get("seed", 0) or 0)))
                    if nid in ("video-in", "video-out", "audio-in", "audio-gain", "audio-lowpass", "audio-analyzer", "value-node", "math-add", "switch-node", "if-node", "python-script"):
                        continue
                    try:
                        if nid == "bypass":
                            pass
                        elif nid == "blur":
                            rr = max(0.1, float(radius) * (0.35 + intensity / 120.0))
                            fx = img.filter(ImageFilter.GaussianBlur(radius=rr))
                            img = Image.blend(img, fx, mix)
                        elif nid == "brightness-node":
                            factor = max(0.05, 1.0 + ((intensity - 50) / 50.0) * 0.85 + (value / 240.0))
                            fx = ImageEnhance.Brightness(img).enhance(factor)
                            img = Image.blend(img, fx, mix)
                        elif nid == "contrast-node":
                            factor = max(0.05, 1.0 + ((intensity - 50) / 50.0) * 0.95 + (value / 260.0))
                            fx = ImageEnhance.Contrast(img).enhance(factor)
                            img = Image.blend(img, fx, mix)
                        elif nid == "saturation-node":
                            factor = max(0.0, 1.0 + ((intensity - 50) / 50.0) * 1.2 + (value / 220.0))
                            fx = ImageEnhance.Color(img).enhance(factor)
                            img = Image.blend(img, fx, mix)
                        elif nid == "hue-shift":
                            hsv = np.array(img.convert("HSV"), dtype=np.uint8)
                            shift = int(round((intensity - 50) * 0.9 + value))
                            hsv[:, :, 0] = (hsv[:, :, 0].astype(np.int16) + shift) % 255
                            fx = Image.fromarray(hsv, mode="HSV").convert("RGB")
                            img = Image.blend(img, fx, mix)
                        elif nid == "gamma-node":
                            g = max(0.2, min(4.0, 1.0 + ((50 - intensity) / 80.0) + (value / 320.0)))
                            inv = 1.0 / g
                            lut = [int(((i / 255.0) ** inv) * 255.0) for i in range(256)]
                            fx = img.point(lut * 3)
                            img = Image.blend(img, fx, mix)
                        elif nid == "autocontrast":
                            fx = ImageOps.autocontrast(img, cutoff=max(0, min(20, int(10 - intensity / 12))))
                            img = Image.blend(img, fx, mix)
                        elif nid == "equalize":
                            fx = ImageOps.equalize(img.convert("RGB"))
                            img = Image.blend(img, fx, mix)
                        elif nid == "sharpen":
                            fx = img.filter(ImageFilter.UnsharpMask(radius=max(1, radius), percent=max(60, intensity * 2), threshold=2))
                            img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                        elif nid == "median-denoise":
                            ksz = max(3, min(9, int(radius) * 2 + 1))
                            fx = img.filter(ImageFilter.MedianFilter(size=ksz))
                            img = Image.blend(img, fx, mix)
                        elif nid == "motion-blur":
                            arr = np.array(img.convert("RGB"), dtype=np.float32)
                            sh = max(1, int(radius + intensity / 18.0))
                            acc = arr.copy()
                            taps = max(2, min(16, int(2 + intensity / 8.0)))
                            for k in range(1, taps):
                                w = (taps - k) / float(taps)
                                acc += np.roll(arr, shift=int(k * sh / 2), axis=1) * w
                            fx = Image.fromarray(np.clip(acc / (1.0 + sum((taps - k) / float(taps) for k in range(1, taps))), 0, 255).astype(np.uint8), mode="RGB")
                            img = Image.blend(img, fx, mix)
                        elif nid == "edge":
                            fx = img.filter(ImageFilter.FIND_EDGES).convert("RGB")
                            img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                        elif nid == "posterize":
                            bits = max(2, min(8, 8 - int(intensity / 16)))
                            fx = ImageOps.posterize(img.convert("RGB"), bits)
                            img = Image.blend(img, fx, mix)
                        elif nid == "invert":
                            fx = ImageOps.invert(img.convert("RGB"))
                            img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                        elif nid == "emboss":
                            fx = img.filter(ImageFilter.EMBOSS).convert("RGB")
                            img = Image.blend(img, fx, max(0.0, min(1.0, (intensity / 100.0) * mix)))
                        elif nid == "grayscale":
                            fx = ImageOps.grayscale(img).convert("RGB")
                            img = Image.blend(img, fx, mix)
                        elif nid == "solarize":
                            thr = int(max(1, min(254, 128 + value - int((intensity - 50) * 1.2))))
                            fx = ImageOps.solarize(img.convert("RGB"), threshold=thr)
                            img = Image.blend(img, fx, mix)
                        elif nid == "pixelate":
                            step = max(2, int(2 + radius + intensity / 14.0))
                            w, h = img.size
                            sx = max(1, w // step)
                            sy = max(1, h // step)
                            fx = img.resize((sx, sy), Image.Resampling.NEAREST).resize((w, h), Image.Resampling.NEAREST)
                            img = Image.blend(img, fx, mix)
                        elif nid == "glitch-lite":
                            fx = self._apply_glitch_effect(img, amount_override=max(8, int(intensity * 0.75)))
                            img = Image.blend(img, fx, mix)
                        elif nid == "vignette":
                            arr = np.array(img.convert("RGB"), dtype=np.float32)
                            hh, ww = arr.shape[:2]
                            yy, xx = np.ogrid[:hh, :ww]
                            cx = (ww - 1) * 0.5
                            cy = (hh - 1) * 0.5
                            rx = max(1.0, ww * 0.5)
                            ry = max(1.0, hh * 0.5)
                            dist = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
                            power = max(0.4, 0.9 + radius * 0.08)
                            fade = np.clip(1.0 - (dist ** power) * (intensity / 100.0), 0.12, 1.0)
                            arr *= fade[..., None]
                            fx = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
                            img = Image.blend(img, fx, mix)
                        elif nid == "bloom-lite":
                            rr = max(0.8, float(radius) * (0.25 + intensity / 160.0))
                            fx = img.filter(ImageFilter.GaussianBlur(radius=rr)).convert("RGB")
                            img = Image.blend(img, fx, max(0.0, min(0.62, (intensity / 125.0) * mix)))
                        elif nid == "threshold":
                            g = img.convert("L")
                            thr = int(max(8, min(246, 255 * (0.15 + intensity / 140.0) + value)))
                            bw = g.point(lambda p, t=thr: 255 if p >= t else 0).convert("RGB")
                            img = Image.blend(img, bw, max(0.0, min(1.0, (0.25 + intensity / 120.0) * mix)))
                        elif nid == "noise":
                            arr = np.array(img.convert("RGB"), dtype=np.float32)
                            amp = max(1.0, intensity * 0.9)
                            rng = np.random.default_rng(int(seed) + int(t_ms) % 100000)
                            arr += rng.normal(0.0, amp, arr.shape)
                            fx = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
                            img = Image.blend(img, fx, mix)
                        elif nid == "channel-shift":
                            arr = np.array(img.convert("RGB"), dtype=np.uint8)
                            sh = max(1, int(round(radius + intensity / 24.0)))
                            mix2 = max(0.0, min(1.0, mix * (intensity / 100.0)))
                            r = np.roll(arr[:, :, 0], sh, axis=1)
                            b = np.roll(arr[:, :, 2], -sh, axis=0)
                            out = arr.copy()
                            out[:, :, 0] = np.clip((1.0 - mix2) * arr[:, :, 0] + mix2 * r, 0, 255).astype(np.uint8)
                            out[:, :, 2] = np.clip((1.0 - mix2) * arr[:, :, 2] + mix2 * b, 0, 255).astype(np.uint8)
                            img = Image.fromarray(out, mode="RGB")
                    except Exception:
                        continue
                code = str(st.get("nodes_code", "") or "").strip()
                if code:
                    safe_builtins = {
                        "abs": abs,
                        "min": min,
                        "max": max,
                        "round": round,
                        "int": int,
                        "float": float,
                        "len": len,
                        "range": range,
                        "sum": sum,
                        "enumerate": enumerate,
                        "zip": zip,
                        "list": list,
                        "dict": dict,
                        "set": set,
                        "tuple": tuple,
                        "sorted": sorted,
                        "print": print,
                    }
                    env = {
                        "__builtins__": safe_builtins,
                        "np": np,
                        "Image": Image,
                        "ImageFilter": ImageFilter,
                        "ImageEnhance": ImageEnhance,
                        "ImageOps": ImageOps,
                        "cv2": cv2,
                    }
                    local = {}
                    exec(code, env, local)
                    fn = local.get("process", env.get("process"))
                    if callable(fn):
                        out = fn(img.copy(), int(t_ms), dict(st))
                        if isinstance(out, Image.Image):
                            img = out.convert("RGB")
                        elif isinstance(out, np.ndarray):
                            arr = np.array(out)
                            if arr.ndim == 2:
                                arr = np.stack([arr, arr, arr], axis=-1)
                            if arr.dtype != np.uint8:
                                arr = np.clip(arr, 0, 255).astype(np.uint8)
                            img = Image.fromarray(arr[:, :, :3], mode="RGB")
        except Exception:
            pass
        try:
            img = self._draw_media_layers(img, st, t_ms=t_ms)
        except Exception:
            pass
        # Text layers.
        try:
            layers = st.get("text_layers", []) or []
            if layers:
                rgba_img = img.convert("RGBA")
                for lyr in layers:
                    if not bool(lyr.get("enabled", True)):
                        continue
                    txt = str(lyr.get("text", "") or "").strip()
                    if not txt:
                        continue
                    t0 = int(lyr.get("start_ms", 0))
                    t1 = int(lyr.get("end_ms", 0))
                    if t1 > t0 and (t_ms < t0 or t_ms > t1):
                        continue
                    x, y = self._layer_t_xy(lyr, t_ms)
                    size = int(lyr.get("size", 28))
                    font = self._safe_font(lyr.get("font", "Arial"), size)
                    col = lyr.get("color_rgba", (255, 255, 255, 220))
                    try:
                        r, g, b, a = int(col[0]), int(col[1]), int(col[2]), int(col[3])
                    except Exception:
                        r, g, b, a = 255, 255, 255, 220
                    sx = max(0.1, min(8.0, float(lyr.get("scale_x", 1.0))))
                    sy = max(0.1, min(8.0, float(lyr.get("scale_y", 1.0))))
                    if abs(sx - 1.0) > 0.02 or abs(sy - 1.0) > 0.02:
                        tmp = Image.new("RGBA", (max(64, rgba_img.width), max(64, rgba_img.height)), (0, 0, 0, 0))
                        td = ImageDraw.Draw(tmp, "RGBA")
                        td.text((0, 0), txt, fill=(r, g, b, a), font=font)
                        bb = tmp.getbbox()
                        if bb:
                            glyph = tmp.crop(bb)
                            gw = max(1, int(glyph.width * sx))
                            gh = max(1, int(glyph.height * sy))
                            glyph = glyph.resize((gw, gh), Image.Resampling.BICUBIC)
                            rgba_img.alpha_composite(glyph, (x, y))
                    else:
                        d = ImageDraw.Draw(rgba_img, "RGBA")
                        d.text((x, y), txt, fill=(r, g, b, a), font=font)
                img = rgba_img.convert("RGB")
        except Exception:
            pass
        try:
            img = self._apply_editor_photo_paint(img, st)
        except Exception:
            pass
        return img

    def _resolve_editor_node_chain(self, st):
        chain = [str(x).strip() for x in (st.get("node_chain", []) or []) if str(x).strip()]
        if not chain:
            return []
        links = []
        for link in (st.get("node_links", []) or []):
            try:
                if isinstance(link, dict):
                    a = int(link.get("src", -1))
                    b = int(link.get("dst", -1))
                else:
                    a, b = int(link[0]), int(link[1])
            except Exception:
                continue
            if a < 0 or b < 0 or a >= len(chain) or b >= len(chain) or a == b:
                continue
            links.append((a, b))
        if not links:
            return list(range(len(chain)))
        incoming = {i: 0 for i in range(len(chain))}
        out = {i: [] for i in range(len(chain))}
        for a, b in links:
            out[a].append(b)
            incoming[b] += 1
        ready = [i for i in range(len(chain)) if incoming[i] == 0]
        ordered = []
        while ready:
            n = ready.pop(0)
            ordered.append(n)
            for m in out.get(n, []):
                incoming[m] -= 1
                if incoming[m] == 0:
                    ready.append(m)
            ready.sort()
        if len(ordered) < len(chain):
            for i in range(len(chain)):
                if i not in ordered:
                    ordered.append(i)
        return [i for i in ordered if 0 <= i < len(chain)]

    def _preprocess_frame(self, pil):
        img = pil.convert("RGB")
        if not self._has_preprocess_fx():
            return img
        # For ASCII styles we can process a smaller working frame
        # (conversion itself downsamples to character grid anyway).
        try:
            if str(getattr(self, "style", "bw")).lower() != "none":
                max_w = max(96, int(getattr(self, "width_chars", 320)) * 2)
                if img.width > max_w:
                    nh = max(1, int(img.height * (max_w / float(img.width))))
                    img = img.resize((max_w, nh), Image.Resampling.BILINEAR)
        except Exception:
            pass
        try:
            gp = float(getattr(self, "gamma_pct", 100))
        except Exception:
            gp = 100.0
        if gp != 100.0:
            gamma = max(0.2, min(4.0, gp / 100.0))
            inv = 1.0 / gamma
            lut = [int(((i / 255.0) ** inv) * 255.0) for i in range(256)]
            img = img.point(lut * 3)
        if bool(getattr(self, "denoise", False)):
            img = img.filter(ImageFilter.MedianFilter(size=3))
        if bool(getattr(self, "sharpen", False)):
            img = img.filter(ImageFilter.SHARPEN)
        if bool(getattr(self, "edge_boost", False)):
            img = ImageEnhance.Contrast(img).enhance(1.18)
        return img

    def _postprocess_frame(self, pil):
        img = pil.convert("RGB")
        if not self._has_postprocess_fx():
            return img
        try:
            bits = int(getattr(self, "pro_poster_bits", 0))
            if bits > 0:
                bits = max(1, min(8, bits))
                img = ImageOps.posterize(img, bits)
        except Exception:
            pass
        try:
            bloom = int(getattr(self, "pro_bloom", 0))
            if bloom > 0:
                blur = img.filter(ImageFilter.GaussianBlur(radius=max(1.0, 4.0 * bloom / 100.0)))
                img = Image.blend(img, blur, min(0.6, bloom / 180.0))
        except Exception:
            pass
        try:
            clarity = int(getattr(self, "pro_clarity", 0))
            if clarity > 0:
                arr = np.array(img.convert("RGB"), dtype=np.float32)
                sigma = max(0.6, 0.55 + clarity / 32.0)
                blur = cv2.GaussianBlur(arr, (0, 0), sigmaX=sigma, sigmaY=sigma)
                amt = min(1.7, clarity / 68.0)
                arr = np.clip(arr + (arr - blur) * amt, 0, 255).astype(np.uint8)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            vig = int(getattr(self, "pro_vignette", 0))
            if vig > 0:
                w, h = img.size
                mask = Image.new("L", (w, h), 255)
                md = ImageDraw.Draw(mask)
                border = int(min(w, h) * min(0.45, vig / 140.0))
                md.rectangle((0, 0, w, h), fill=255)
                md.rectangle((border, border, w - border, h - border), fill=0)
                mask = mask.filter(ImageFilter.GaussianBlur(radius=max(8, int(min(w, h) * 0.08))))
                dark = Image.new("RGB", (w, h), (0, 0, 0))
                img = Image.composite(dark, img, mask)
        except Exception:
            pass
        try:
            chroma = int(getattr(self, "pro_chroma", 0))
            if chroma > 0:
                arr = np.array(img.convert("RGB"), dtype=np.uint8)
                arr[:, :, 0] = np.roll(arr[:, :, 0], int(chroma), axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -int(chroma), axis=1)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            color_boost = int(getattr(self, "pro_color_boost", 0))
            if color_boost > 0:
                img = ImageEnhance.Color(img).enhance(1.0 + min(2.0, color_boost / 62.0))
        except Exception:
            pass
        try:
            grain = int(getattr(self, "pro_grain", 0))
            if grain > 0:
                arr = np.array(img.convert("RGB"), dtype=np.int16)
                sigma = max(1.0, float(grain) * 0.8)
                noise = np.random.normal(0.0, sigma, arr.shape).astype(np.int16)
                arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            motion_blur = int(getattr(self, "pro_motion_blur", 0))
            if motion_blur > 0:
                arr = np.array(img.convert("RGB"), dtype=np.uint8)
                k = max(3, int(3 + motion_blur * 0.34))
                if k % 2 == 0:
                    k += 1
                kernel = np.zeros((k, k), dtype=np.float32)
                kernel[k // 2, :] = 1.0 / float(k)
                arr = cv2.filter2D(arr, -1, kernel, borderType=cv2.BORDER_REFLECT101)
                img = Image.fromarray(arr, mode="RGB")
        except Exception:
            pass
        try:
            if bool(getattr(self, "pro_scanlines", False)):
                w, h = img.size
                over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                od = ImageDraw.Draw(over)
                step = max(1, int(getattr(self, "pro_scan_step", 3)))
                strength = max(0, min(100, int(getattr(self, "pro_scan_strength", 28))))
                alpha = int(8 + strength * 1.1)
                for y in range(0, h, step):
                    od.line((0, y, w, y), fill=(0, 0, 0, alpha), width=1)
                img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
        except Exception:
            pass
        try:
            glitch = int(getattr(self, "pro_glitch", 0))
            if glitch > 0:
                img = self._apply_glitch_effect(img, glitch)
        except Exception:
            pass
        try:
            curvature = int(getattr(self, "pro_curvature", 0))
            concavity = int(getattr(self, "pro_concavity", 0))
            if curvature > 0 or concavity > 0:
                img = self._apply_curvature_effect(
                    img,
                    curvature,
                    concavity,
                    int(getattr(self, "pro_curvature_center_x", 0)),
                    int(getattr(self, "pro_curvature_expand", 0)),
                    str(getattr(self, "pro_curvature_type", "spherical") or "spherical"),
                )
        except Exception:
            pass
        try:
            ribbing = int(getattr(self, "pro_ribbing", 0))
            if ribbing > 0:
                img = self._apply_ribbing_effect(img, ribbing)
        except Exception:
            pass
        return img

    def _ensure_even(self, pil):
        w, h = pil.size
        pad_w = w % 2
        pad_h = h % 2
        if pad_w == 0 and pad_h == 0:
            return pil
        try:
            fill = self.bg_hex
            if isinstance(fill, str) and (fill.lower() == "transparent" or (len(fill) == 9 and fill.startswith("#"))):
                fill = "#000000"
            return ImageOps.expand(pil, border=(0, 0, pad_w, pad_h), fill=fill)
        except Exception:
            return pil

    def _target_size(self, pil):
        out_size = self.target_size if self.target_size else (pil.size if self.keep_size else None)
        if out_size is None and int(self.scale_mult) > 1:
            out_size = pil.size
        if out_size and int(self.scale_mult) > 1:
            out_size = (int(out_size[0] * int(self.scale_mult)), int(out_size[1] * int(self.scale_mult)))
        return out_size

    def _render_frame(self, pil):
        out_size = self._target_size(pil)
        if str(getattr(self, "style", "bw")).lower() == "none":
            out = pil.convert("RGB")
            if out_size and isinstance(out_size, tuple):
                try:
                    out = out.resize((max(1, int(out_size[0])), max(1, int(out_size[1]))), Image.Resampling.LANCZOS)
                except Exception:
                    pass
            if bool(getattr(self, "watermark", False)):
                try:
                    d = ImageDraw.Draw(out)
                    txt = str(getattr(self, "watermark_text", CORE_WATERMARK) or CORE_WATERMARK).strip()
                    if txt:
                        d.text((10, max(2, out.height - 20)), txt, fill=(130, 130, 130))
                except Exception:
                    pass
            return out
        data = image_to_ascii_data(
            pil,
            self.width_chars,
            ascii_chars=self.ascii_chars,
            invert=self.invert,
            contrast_pct=self.contrast_pct,
        )
        return render_ascii_pil(
            data,
            self.font_size,
            self.style,
            self.fg_hex,
            self.bg_hex,
            output_size=out_size,
            watermark=self.watermark,
            watermark_text=getattr(self, "watermark_text", CORE_WATERMARK),
        )

    def run(self):
        try:
            out_ext = self.out.split('.')[-1].lower()
            in_ext = self.src.split('.')[-1].lower()

            # helper to create writer for video/gif outputs
            writer = None
            def make_writer_for_output(path, ext):
                try:
                    if ext == 'gif':
                        return imageio.get_writer(path, mode='I', fps=self.fps)
                    # try to use ffmpeg backend for videos (mp4, mov, mkv, avi)
                    kw = {'fps': self.fps}
                    if getattr(self, 'codec', None):
                        kw['codec'] = self.codec
                    # only set bitrate if explicitly provided (not None/empty)
                    if getattr(self, 'bitrate', None) is not None:
                        kw['bitrate'] = self.bitrate
                    # force ffmpeg thread count for CPU mode when requested
                    params = []
                    if int(getattr(self, 'threads', 0) or 0) > 0:
                        params += ['-threads', str(int(self.threads))]
                    # apply preset/crf for H.264 variants
                    if str(getattr(self, 'codec', '')).lower() in ('libx264', 'h264'):
                        preset = getattr(self, 'preset', None)
                        if preset:
                            params += ['-preset', str(preset)]
                        crf = getattr(self, 'crf', None)
                        if crf is not None:
                            params += ['-crf', str(int(crf))]
                    if params:
                        kw['ffmpeg_params'] = params
                    # force ffmpeg format for better compatibility
                    kw['format'] = 'FFMPEG'
                    # keep exact frame size from ASCII renderer (no implicit resize)
                    kw['macro_block_size'] = 1
                    return imageio.get_writer(path, **kw)
                except Exception:
                    # fallback to simple writer without extra kwargs
                    try:
                        return imageio.get_writer(path, fps=self.fps)
                    except Exception:
                        raise

            # signal started
            try:
                self.started.emit()
            except Exception:
                pass
            need_preprocess = self._has_preprocess_fx()
            need_postprocess = self._has_postprocess_fx()

            # read frames from source
            frames_count = 0
            if in_ext in ('mp4', 'mov', 'mkv', 'avi'):
                cap = cv2.VideoCapture(self.src)
                if not cap or not cap.isOpened():
                    self.error.emit('Cannot open source')
                    return
                frames_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                trim_start = max(0, int(getattr(self, "trim_start_ms", 0) or 0))
                trim_end = max(0, int(getattr(self, "trim_end_ms", 0) or 0))
                try:
                    if trim_start > 0:
                        cap.set(cv2.CAP_PROP_POS_MSEC, float(trim_start))
                except Exception:
                    pass
                # write to temp file first so we can mux audio later
                tmpf = tempfile.NamedTemporaryFile(suffix='.'+out_ext, delete=False)
                tmpf.close()
                writer = make_writer_for_output(tmpf.name, out_ext)
                idx = 0
                try:
                    while True:
                        if self._cancel:
                            break
                        ret, frame = cap.read()
                        if not ret:
                            break
                        cur_ms = 0
                        try:
                            cur_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
                        except Exception:
                            cur_ms = 0
                        if trim_end > 0 and cur_ms > trim_end:
                            break
                        # attempt GPU accelerated color conversion if requested
                        try:
                            if getattr(self, 'render_device', 'cpu') == 'gpu' and cv2.cuda.getCudaEnabledDeviceCount() > 0:
                                g = cv2.cuda_GpuMat()
                                g.upload(frame)
                                try:
                                    g2 = cv2.cuda.cvtColor(g, cv2.COLOR_BGR2RGB)
                                    frame = g2.download()
                                except Exception:
                                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            else:
                                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        except Exception:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        pil = Image.fromarray(frame)
                        pil = self._apply_editor_state(pil, t_ms=cur_ms)
                        if need_preprocess:
                            pil = self._preprocess_frame(pil)
                        out_img = self._render_frame(pil)
                        if need_postprocess:
                            out_img = self._postprocess_frame(out_img)
                        if out_ext in ("mp4", "mov", "mkv", "avi"):
                            out_img = self._ensure_even(out_img)
                        arr = np.array(out_img.convert('RGB'))
                        # ensure uint8
                        if arr.dtype != np.uint8:
                            arr = arr.astype(np.uint8)
                        writer.append_data(arr)
                        idx += 1
                        if frames_count:
                            self.progress.emit(int(idx * 100 / max(1, frames_count)))
                finally:
                    try: writer.close()
                    except Exception: pass
                    try: cap.release()
                    except Exception: pass
                # try to mux audio from source using ffmpeg if available
                try:
                    ff = self._resolve_ffmpeg_exe()
                    audio_src = None
                    if bool(getattr(self, "keep_source_audio", True)):
                        cand = getattr(self, "audio_source_path", None)
                        if cand and os.path.exists(cand):
                            audio_src = cand
                        elif os.path.exists(self.src):
                            audio_src = self.src
                    if ff and audio_src:
                        muxed = False
                        src_has_audio = self._file_has_audio(audio_src)
                        out_tmp = self.out
                        gain_db = float(getattr(self, "audio_gain_db", 0.0) or 0.0)
                        lowpass_hz = int(getattr(self, "audio_lowpass_hz", 0) or 0)
                        af_parts = []
                        if abs(gain_db) > 0.001:
                            af_parts.append(f"volume={gain_db:.2f}dB")
                        if lowpass_hz > 0:
                            af_parts.append(f"lowpass=f={max(20, lowpass_hz)}")
                        afilter = ",".join(af_parts)
                        use_audio_fx = bool(afilter)
                        if not src_has_audio:
                            use_audio_fx = False
                        # strategy 0: stream-copy audio/video where possible.
                        cmd0 = [
                            ff, '-y',
                            '-i', tmpf.name,
                            '-i', audio_src,
                            '-map_metadata', '-1',
                            '-map', '0:v:0',
                            '-map', '1:a:0?',
                            '-c:v', 'copy',
                            '-c:a', 'copy',
                            '-shortest',
                            '-movflags', '+faststart',
                            out_tmp
                        ]
                        # strategy 1: copy video stream + encode audio to AAC.
                        cmd1 = [
                            ff, '-y',
                            '-i', tmpf.name,
                            '-i', audio_src,
                            '-map_metadata', '-1',
                            '-map', '0:v:0',
                            '-map', '1:a:0?',
                            '-c:v', 'copy',
                            '-c:a', 'aac',
                            '-b:a', '192k',
                            '-shortest',
                            '-movflags', '+faststart',
                            out_tmp
                        ]
                        if use_audio_fx:
                            cmd1 = cmd1[:-3] + ['-af', afilter] + cmd1[-3:]
                        # strategy 2: re-encode video if copy is incompatible.
                        cmd2 = [
                            ff, '-y',
                            '-i', tmpf.name,
                            '-i', audio_src,
                            '-map_metadata', '-1',
                            '-map', '0:v:0',
                            '-map', '1:a:0?',
                            '-c:v', 'libx264',
                            '-preset', str(getattr(self, "preset", "medium") or "medium"),
                            '-crf', str(int(getattr(self, "crf", 20) or 20)),
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-b:a', '192k',
                            '-shortest',
                            '-movflags', '+faststart',
                            out_tmp
                        ]
                        if use_audio_fx:
                            cmd2 = cmd2[:-3] + ['-af', afilter] + cmd2[-3:]
                        cmd_chain = (cmd1, cmd2) if use_audio_fx else (cmd0, cmd1, cmd2)
                        for cmd in cmd_chain:
                            try:
                                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                if (not src_has_audio) or self._file_has_audio(out_tmp):
                                    muxed = True
                                    break
                            except Exception:
                                muxed = False
                        if not muxed:
                            # fallback: move tmp to final
                            try:
                                os.replace(tmpf.name, self.out)
                            except Exception:
                                try:
                                    shutil.copy(tmpf.name, self.out)
                                except Exception:
                                    pass
                    else:
                        try:
                            os.replace(tmpf.name, self.out)
                        except Exception:
                            try:
                                shutil.copy(tmpf.name, self.out)
                            except Exception:
                                pass
                except Exception:
                    # best-effort: copy tmp to out
                    try:
                        shutil.copy(tmpf.name, self.out)
                    except Exception:
                        pass
                finally:
                    try:
                        if os.path.exists(tmpf.name):
                            try: os.remove(tmpf.name)
                            except Exception: pass
                    except Exception:
                        pass
                try:
                    self.finished_path.emit(self.out)
                finally:
                    try: self.stopped.emit()
                    except Exception: pass
                return

            if in_ext in ('gif',):
                try:
                    reader = imageio.get_reader(self.src)
                except Exception:
                    reader = None
                total_frames = 0
                if reader is not None:
                    try:
                        meta = reader.get_meta_data()
                        total_frames = int(meta.get('nframes', 0) or 0)
                    except Exception:
                        total_frames = 0
                    w = None
                    try:
                        if out_ext == 'gif':
                            w = imageio.get_writer(self.out, mode='I', fps=self.fps)
                        else:
                            w = make_writer_for_output(self.out, out_ext)
                    except Exception as e:
                        self.error.emit(str(e))
                        return
                    idx = 0
                    src_idx = 0
                    trim_start = max(0, int(getattr(self, "trim_start_ms", 0) or 0))
                    trim_end = max(0, int(getattr(self, "trim_end_ms", 0) or 0))
                    frame_ms = max(1.0, 1000.0 / float(max(1, int(getattr(self, "fps", 24) or 24))))
                    try:
                        for f in reader:
                            if self._cancel:
                                break
                            t_ms = int(src_idx * frame_ms)
                            src_idx += 1
                            if trim_start > 0 and t_ms < trim_start:
                                continue
                            if trim_end > 0 and t_ms > trim_end:
                                break
                            arr = np.array(f)
                            pil = Image.fromarray(arr)
                            pil = self._apply_editor_state(pil, t_ms=t_ms)
                            if need_preprocess:
                                pil = self._preprocess_frame(pil)
                            out_img = self._render_frame(pil)
                            if need_postprocess:
                                out_img = self._postprocess_frame(out_img)
                            if out_ext in ("mp4", "mov", "mkv", "avi"):
                                out_img = self._ensure_even(out_img)
                            if out_ext == 'gif':
                                w.append_data(np.array(out_img.convert('RGBA')).astype(np.uint8))
                            else:
                                w.append_data(np.array(out_img.convert('RGB')).astype(np.uint8))
                            idx += 1
                            if total_frames:
                                self.progress.emit(int(idx * 100 / max(1, total_frames)))
                    except Exception as e:
                        self.error.emit(str(e))
                        return
                    finally:
                        try:
                            if w is not None:
                                w.close()
                        except Exception:
                            pass
                        try:
                            if reader is not None:
                                reader.close()
                        except Exception:
                            pass
                try:
                    self.finished_path.emit(self.out)
                finally:
                    try: self.stopped.emit()
                    except Exception: pass
                return

            # otherwise treat source as static image
            try:
                pil = Image.open(self.src).convert('RGB')
            except Exception:
                self.error.emit('Cannot open source')
                return
            pil = self._apply_editor_state(pil, t_ms=0)
            if need_preprocess:
                pil = self._preprocess_frame(pil)
            out_img = self._render_frame(pil)
            if need_postprocess:
                out_img = self._postprocess_frame(out_img)
            if out_ext in ("mp4", "mov", "mkv", "avi"):
                out_img = self._ensure_even(out_img)
            # if output is gif or video, write single-frame animation
            if out_ext == 'gif':
                try:
                    imageio.mimsave(self.out, [np.array(out_img.convert('RGBA'))], fps=self.fps)
                except Exception as e:
                    self.error.emit(str(e)); return
            else:
                try:
                    w = make_writer_for_output(self.out, out_ext)
                    w.append_data(np.array(out_img.convert('RGB')))
                    try: w.close()
                    except Exception: pass
                except Exception as e:
                    self.error.emit(str(e)); return
            self.finished_path.emit(self.out)
            return
        except Exception as e:
            self.error.emit(str(e))
