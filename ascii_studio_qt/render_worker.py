from PySide6.QtCore import QThread, Signal
import imageio, cv2, numpy as np
from PIL import Image
import tempfile, subprocess, shutil, os
from core_utils import image_to_ascii_data, render_ascii_pil, DEFAULT_ASCII

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
        # advanced options
        self.codec = 'libx264'
        self.bitrate = None
        self._cancel = False
        # rendering device: 'cpu' or 'gpu'
        self.render_device = 'cpu'

    def cancel(self):
        self._cancel = True

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
                    # force ffmpeg format for better compatibility
                    kw['format'] = 'FFMPEG'
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

            # read frames from source
            frames_count = 0
            if in_ext in ('mp4', 'mov', 'mkv', 'avi'):
                cap = cv2.VideoCapture(self.src)
                if not cap or not cap.isOpened():
                    self.error.emit('Cannot open source')
                    return
                frames_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
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
                        data = image_to_ascii_data(pil, self.width_chars, ascii_chars=self.ascii_chars, invert=self.invert, contrast_pct=self.contrast_pct)
                        out_img = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex, watermark=self.watermark)
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
                    ff = shutil.which('ffmpeg')
                    if ff:
                        muxed = False
                        out_tmp = self.out
                        # attempt to map video from tmp and audio from source
                        cmd = [ff, '-y', '-i', tmpf.name, '-i', self.src, '-c', 'copy', '-map', '0:v:0', '-map', '1:a:0', out_tmp]
                        try:
                            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            muxed = True
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
                frames = []
                total_frames = 0
                if reader is not None:
                    try:
                        meta = reader.get_meta_data()
                        total_frames = int(meta.get('nframes', 0) or 0)
                    except Exception:
                        total_frames = 0
                    idx = 0
                    for f in reader:
                        if self._cancel:
                            break
                        arr = np.array(f)
                        pil = Image.fromarray(arr)
                        data = image_to_ascii_data(pil, self.width_chars, ascii_chars=self.ascii_chars, invert=self.invert, contrast_pct=self.contrast_pct)
                        out_img = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex, watermark=self.watermark)
                        frames.append(np.array(out_img.convert('RGBA')))
                        idx += 1
                        if total_frames:
                            self.progress.emit(int(idx * 100 / max(1, total_frames)))
                # write out
                try:
                    if out_ext == 'gif':
                        # imageio expects either PIL images or numpy arrays
                        imageio.mimsave(self.out, frames, fps=self.fps)
                    else:
                        w = make_writer_for_output(self.out, out_ext)
                        for fr in frames:
                            # fr is a numpy array (RGBA) -> convert to RGB
                            if fr.ndim == 3 and fr.shape[2] == 4:
                                rgb = fr[..., :3]
                            else:
                                rgb = fr
                            w.append_data(rgb.astype(np.uint8))
                        try: w.close()
                        except Exception: pass
                except Exception as e:
                    self.error.emit(str(e)); return
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
            data = image_to_ascii_data(pil, self.width_chars, ascii_chars=self.ascii_chars, invert=self.invert, contrast_pct=self.contrast_pct)
            out_img = render_ascii_pil(data, self.font_size, self.style, self.fg_hex, self.bg_hex, watermark=self.watermark)
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
