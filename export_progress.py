import math
import random
import time

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QBrush
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QHBoxLayout,
    QFrame,
    QGraphicsBlurEffect,
)

try:
    import psutil
except Exception:
    psutil = None

try:
    import GPUtil
except Exception:
    GPUtil = None


class RenderLoadBars(QFrame):
    """Rounded bars driven by render progress (not random standalone CPU meter)."""

    def __init__(self, parent=None, theme="dark"):
        super().__init__(parent)
        self.theme = str(theme or "dark")
        self.setMinimumHeight(78)
        self.setMaximumHeight(92)
        self.values = [0.0] * 24
        self._progress = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._phase = 0.0
        self.setStyleSheet("background: rgba(0,0,0,0.14); border-radius: 12px;")

    def set_progress(self, v):
        try:
            self._progress = max(0, min(100, int(v)))
        except Exception:
            self._progress = 0

    def start(self):
        if not self._timer.isActive():
            self._timer.start(90)
        self.show()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def _tick(self):
        # Tie visual load to render progress and add small live jitter.
        progress = float(self._progress)
        cpu_now = 0.0
        try:
            if psutil is not None:
                cpu_now = float(psutil.cpu_percent(interval=None))
            else:
                cpu_now = random.uniform(15.0, 75.0)
        except Exception:
            cpu_now = random.uniform(15.0, 75.0)
        target = max(progress * 0.65, min(100.0, progress + 12.0))
        mix = (target * 0.78) + (cpu_now * 0.22)
        self._phase += 0.35
        jitter = (math.sin(self._phase) * 4.5) + random.uniform(-3.0, 3.0)
        val = max(0.0, min(100.0, mix + jitter))
        self.values = self.values[1:] + [val]
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            w = max(1, self.width() - 12)
            h = max(1, self.height() - 12)
            x0, y0 = 6, 6
            n = max(1, len(self.values))
            spacing = 3
            bw = max(3, int((w - (n - 1) * spacing) / n))
            for i, v in enumerate(self.values):
                bh = max(2, int((h - 2) * (v / 100.0)))
                x = x0 + i * (bw + spacing)
                y = y0 + (h - bh)
                bar_rect_w = max(2, bw)
                r = min(6, max(2, bar_rect_w // 2))
                if self.theme == "cyberpunk 2077":
                    color = QColor(255, 116, 136, 228) if i % 2 == 0 else QColor(198, 18, 36, 220)
                elif self.theme == "retro":
                    color = QColor(194, 220, 249, 228)
                elif self.theme == "aphex twin":
                    color = QColor(214, 228, 246, 220)
                elif self.theme == "sketch":
                    color = QColor(240, 245, 252, 218)
                else:
                    color = QColor(232, 244, 255, 230)
                p.setBrush(color)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(x, y, bar_rect_w, bh, r, r)
        finally:
            if p.isActive():
                p.end()


class ExportProgressDialog(QDialog):
    def __init__(self, parent, worker, theme="dark", tr=None):
        super().__init__(parent)
        self.worker = worker
        self.theme = str(theme or "dark")
        self.tr = tr or {}
        self._blur_targets = []
        self._finished = False
        self._started_ts = None
        self._last_progress = 0
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.main = QFrame(self)
        self.main.setObjectName("render_progress_panel")
        self.main.setStyleSheet(self._panel_css())
        self.main_lay = QVBoxLayout(self.main)
        self.main_lay.setContentsMargins(16, 14, 16, 14)
        self.main_lay.setSpacing(10)

        self.label = QLabel(self._t("render", "Render") + "...")
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size:14px; font-weight:700;")
        self.main_lay.addWidget(self.label)

        self.pbar = QProgressBar(self)
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setStyleSheet(self._progress_css())
        self.main_lay.addWidget(self.pbar)

        stats_row = QHBoxLayout()
        self.cpu_stat = QLabel(f"{self._t('cpu_load', 'CPU load')}: --")
        self.gpu_stat = QLabel(f"{self._t('gpu_load', 'GPU load')}: --")
        self.eta_stat = QLabel(f"{self._t('eta', 'ETA')}: --:--")
        self.speed_stat = QLabel(f"{self._t('render_speed', 'Speed')}: 0.0%/s")
        for s in (self.cpu_stat, self.gpu_stat, self.eta_stat, self.speed_stat):
            s.setStyleSheet("font-size:11px; color:rgba(235,244,255,0.92);")
            stats_row.addWidget(s, 1)
        self.main_lay.addLayout(stats_row)

        self.cpu_title = QLabel(self._t("cpu_load", "CPU load"))
        self.cpu_title.setStyleSheet("font-size:12px;")
        self.main_lay.addWidget(self.cpu_title)

        self.load_bars = RenderLoadBars(self.main, theme=self.theme)
        self.main_lay.addWidget(self.load_bars)

        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton(self._t("cancel", "Cancel"))
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(self._button_css())
        self.cancel_btn.clicked.connect(self._on_cancel)
        row.addWidget(self.cancel_btn)
        self.main_lay.addLayout(row)

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_runtime_stats)

        worker.progress.connect(self._on_progress)
        worker.finished_path.connect(self._on_finished)
        worker.error.connect(self._on_error)
        try:
            worker.started.connect(self._on_started)
            worker.stopped.connect(lambda: self.load_bars.stop())
        except Exception:
            pass

    def _t(self, key, fallback):
        try:
            return str(self.tr.get(key, fallback))
        except Exception:
            return fallback

    def _panel_css(self):
        if self.theme == "light":
            return (
                "QFrame#render_progress_panel{background: rgba(255,255,255,0.96); border:1px solid #cfd9e8; border-radius:18px; color:#172537;}"
            )
        if self.theme == "retro":
            return (
                "QFrame#render_progress_panel{background: rgba(36,70,112,0.92); border:1px solid rgba(194,220,249,0.56); border-radius:10px; color:#eef5ff;}"
            )
        if self.theme == "cyberpunk 2077":
            return (
                "QFrame#render_progress_panel{background: rgba(18,8,12,0.94); border:1px solid rgba(234,48,72,0.56); border-radius:8px; color:#fff4f6;}"
            )
        if self.theme == "aphex twin":
            return (
                "QFrame#render_progress_panel{background: rgba(18,24,34,0.92); border:1px solid rgba(210,224,243,0.40); border-radius:16px; color:#edf4fb;}"
            )
        if self.theme == "sketch":
            return (
                "QFrame#render_progress_panel{background: rgba(18,20,24,0.92); border:1px solid rgba(230,236,245,0.32); border-radius:14px; color:#f2f6fb;}"
            )
        return (
            "QFrame#render_progress_panel{background: rgba(18,22,32,0.92); border:1px solid rgba(145,190,255,0.30); border-radius:18px; color:#e9f1fb;}"
        )

    def _progress_css(self):
        if self.theme == "light":
            return (
                "QProgressBar{border:1px solid #c6d4e8; border-radius:10px; background: rgba(0,0,0,0.08); color:#10243a; text-align:center; min-height:20px;}"
                "QProgressBar::chunk{border-radius:9px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6aa7f4, stop:1 #7ac7ff);}"
            )
        if self.theme == "retro":
            return (
                "QProgressBar{border:1px solid rgba(194,220,249,0.60); border-radius:10px; background: rgba(18,43,74,0.68); color:#eef5ff; text-align:center; min-height:20px;}"
                "QProgressBar::chunk{border-radius:9px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #89b7eb, stop:1 #c2dcf9);}"
            )
        if self.theme == "cyberpunk 2077":
            return (
                "QProgressBar{border:1px solid rgba(234,48,72,0.60); border-radius:10px; background: rgba(10,8,14,0.82); color:#fff4f6; text-align:center; min-height:20px;}"
                "QProgressBar::chunk{border-radius:9px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff7a92, stop:1 #c50024);}"
            )
        if self.theme == "aphex twin":
            return (
                "QProgressBar{border:1px solid rgba(210,224,243,0.50); border-radius:10px; background: rgba(10,14,22,0.74); color:#edf4fb; text-align:center; min-height:20px;}"
                "QProgressBar::chunk{border-radius:9px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #9db5d4, stop:1 #d4e2f4);}"
            )
        if self.theme == "sketch":
            return (
                "QProgressBar{border:1px solid rgba(225,234,245,0.42); border-radius:10px; background: rgba(10,12,16,0.74); color:#eef3fa; text-align:center; min-height:20px;}"
                "QProgressBar::chunk{border-radius:9px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #c7d3e3, stop:1 #f0f5fc);}"
            )
        return (
            "QProgressBar{border:1px solid rgba(145,190,255,0.42); border-radius:10px; background: rgba(8,12,20,0.72); color:#ecf6ff; text-align:center; min-height:20px;}"
            "QProgressBar::chunk{border-radius:9px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #66b8ff, stop:1 #88c8ff);}"
        )

    def _button_css(self):
        if self.theme == "light":
            return (
                "QPushButton{background: rgba(245,249,255,0.98); color:#10243a; border:1px solid #bfd0e8; border-radius:12px; padding:6px 14px;}"
                "QPushButton:hover{background: rgba(230,240,252,0.98);}"
            )
        if self.theme == "retro":
            return (
                "QPushButton{background: rgba(62,104,158,0.96); color:#eef5ff; border:1px solid rgba(194,220,249,0.62); border-radius:12px; padding:6px 14px;}"
                "QPushButton:hover{background: rgba(84,128,184,0.98);}"
            )
        if self.theme == "cyberpunk 2077":
            return (
                "QPushButton{background: rgba(190,22,44,0.24); color:#fff4f6; border:1px solid rgba(234,48,72,0.66); border-radius:10px; padding:6px 14px;}"
                "QPushButton:hover{background: rgba(220,34,58,0.30);}"
            )
        if self.theme == "aphex twin":
            return (
                "QPushButton{background: rgba(145,168,196,0.20); color:#edf4fb; border:1px solid rgba(210,224,243,0.52); border-radius:12px; padding:6px 14px;}"
                "QPushButton:hover{background: rgba(165,186,212,0.26);}"
            )
        if self.theme == "sketch":
            return (
                "QPushButton{background: rgba(235,239,244,0.16); color:#f2f6fb; border:1px solid rgba(230,236,245,0.46); border-radius:12px; padding:6px 14px;}"
                "QPushButton:hover{background: rgba(235,239,244,0.24);}"
            )
        return (
            "QPushButton{background: rgba(40,55,82,0.90); color:#e9f1fb; border:1px solid rgba(145,190,255,0.34); border-radius:12px; padding:6px 14px;}"
            "QPushButton:hover{background: rgba(62,84,118,0.94);}"
        )

    def _apply_blur(self, enable):
        parent = self.parentWidget()
        if parent is None:
            return
        if enable:
            self._blur_targets.clear()
            names = ("gallery_frame", "left_frame", "right_frame", "right_tabs_rail", "right_footer")
            for n in names:
                try:
                    w = parent.findChild(QFrame, n)
                    if w is None:
                        continue
                    eff = QGraphicsBlurEffect(w)
                    eff.setBlurRadius(8.0)
                    w.setGraphicsEffect(eff)
                    self._blur_targets.append(w)
                except Exception:
                    pass
            try:
                mb = parent.menuBar() if hasattr(parent, "menuBar") else None
                if mb is not None:
                    eff = QGraphicsBlurEffect(mb)
                    eff.setBlurRadius(5.0)
                    mb.setGraphicsEffect(eff)
                    self._blur_targets.append(mb)
            except Exception:
                pass
        else:
            for w in self._blur_targets:
                try:
                    w.setGraphicsEffect(None)
                except Exception:
                    pass
            self._blur_targets.clear()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        w, h = self.width(), self.height()
        mw = min(560, max(420, int(w * 0.56)))
        mh = min(360, max(260, int(h * 0.38)))
        self.main.setGeometry((w - mw) // 2, (h - mh) // 2, mw, mh)

    def showEvent(self, ev):
        super().showEvent(ev)
        p = self.parentWidget()
        if p is not None:
            try:
                r = p.geometry()
                self.setGeometry(r)
            except Exception:
                self.setGeometry(p.rect())
        self._apply_blur(True)
        self.load_bars.start()
        self._started_ts = time.time()
        self._stats_timer.start(420)
        self._update_runtime_stats()

    def closeEvent(self, ev):
        self._apply_blur(False)
        self.load_bars.stop()
        try:
            self._stats_timer.stop()
        except Exception:
            pass
        try:
            p = self.parentWidget()
            if p is not None and hasattr(p, "_force_clear_blur_effects"):
                p._force_clear_blur_effects()
        except Exception:
            pass
        return super().closeEvent(ev)

    def hideEvent(self, ev):
        try:
            self._apply_blur(False)
            self._stats_timer.stop()
            p = self.parentWidget()
            if p is not None and hasattr(p, "_force_clear_blur_effects"):
                p._force_clear_blur_effects()
        except Exception:
            pass
        return super().hideEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor(0, 0, 0, 158))
            glow = QRadialGradient(self.width() * 0.5, self.height() * 0.46, max(180, int(min(self.width(), self.height()) * 0.42)))
            if self.theme == "cyberpunk 2077":
                glow.setColorAt(0.0, QColor(0, 246, 255, 58))
                glow.setColorAt(0.6, QColor(255, 46, 154, 36))
            elif self.theme == "aphex twin":
                glow.setColorAt(0.0, QColor(210, 224, 243, 52))
                glow.setColorAt(0.6, QColor(120, 145, 172, 28))
            elif self.theme == "sketch":
                glow.setColorAt(0.0, QColor(225, 234, 245, 48))
                glow.setColorAt(0.6, QColor(142, 152, 164, 24))
            elif self.theme == "retro":
                glow.setColorAt(0.0, QColor(194, 220, 249, 50))
                glow.setColorAt(0.6, QColor(90, 130, 180, 28))
            else:
                glow.setColorAt(0.0, QColor(130, 180, 255, 50))
                glow.setColorAt(0.6, QColor(60, 100, 170, 24))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(glow))
        finally:
            if p.isActive():
                p.end()

    def _on_started(self):
        self.label.setText(self._t("render", "Render") + "...")
        self.cancel_btn.setText(self._t("cancel", "Cancel"))
        self._finished = False
        self._started_ts = time.time()
        self._last_progress = 0
        self._update_runtime_stats()

    def _on_progress(self, v):
        vv = int(v)
        self._last_progress = vv
        self.pbar.setValue(vv)
        self.load_bars.set_progress(vv)
        self._update_runtime_stats()

    def _on_finished(self, path):
        self._finished = True
        self.pbar.setValue(100)
        self.load_bars.set_progress(100)
        self.label.setText(f"{self._t('done', 'Done')}: {path}")
        self.cancel_btn.setText(self._t("close", "Close"))
        self._update_runtime_stats(force_done=True)
        try:
            self._stats_timer.stop()
        except Exception:
            pass

    def _on_error(self, msg):
        self._finished = True
        self.label.setText("Error: " + str(msg))
        self.cancel_btn.setText(self._t("close", "Close"))
        try:
            self._stats_timer.stop()
        except Exception:
            pass

    def _sample_gpu_percent(self):
        try:
            if GPUtil is None:
                return None
            gpus = GPUtil.getGPUs()
            if not gpus:
                return None
            return int(max(0.0, min(100.0, float(gpus[0].load) * 100.0)))
        except Exception:
            return None

    def _update_runtime_stats(self, force_done=False):
        try:
            cpu = None
            if psutil is not None:
                try:
                    cpu = int(max(0.0, min(100.0, float(psutil.cpu_percent(interval=None)))))
                except Exception:
                    cpu = None
            gpu = self._sample_gpu_percent()
            pr = int(self.pbar.value())
            elapsed = max(0.001, float((time.time() - self._started_ts) if self._started_ts else 0.0))
            speed = (pr / elapsed) if elapsed > 0 else 0.0
            if force_done or pr >= 100:
                eta_txt = "00:00"
            elif speed > 0.01:
                eta_s = int((100 - pr) / speed)
                eta_txt = f"{eta_s // 60:02d}:{eta_s % 60:02d}"
            else:
                eta_txt = "--:--"
            self.cpu_stat.setText(f"{self._t('cpu_load', 'CPU load')}: {cpu if cpu is not None else '--'}%")
            self.gpu_stat.setText(f"{self._t('gpu_load', 'GPU load')}: {gpu if gpu is not None else '--'}%")
            self.eta_stat.setText(f"{self._t('eta', 'ETA')}: {eta_txt}")
            self.speed_stat.setText(f"{self._t('render_speed', 'Speed')}: {speed:.2f}%/s")
        except Exception:
            pass

    def _on_cancel(self):
        if not self._finished:
            try:
                self.worker.cancel()
            except Exception:
                pass
        self.accept()

    def accept(self):
        try:
            self._apply_blur(False)
            self.load_bars.stop()
            self._stats_timer.stop()
            p = self.parentWidget()
            if p is not None and hasattr(p, "_force_clear_blur_effects"):
                p._force_clear_blur_effects()
        except Exception:
            pass
        return super().accept()

    def reject(self):
        try:
            self._apply_blur(False)
            self.load_bars.stop()
            self._stats_timer.stop()
            p = self.parentWidget()
            if p is not None and hasattr(p, "_force_clear_blur_effects"):
                p._force_clear_blur_effects()
        except Exception:
            pass
        return super().reject()
