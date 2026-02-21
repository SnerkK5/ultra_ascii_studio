from pathlib import Path

import cv2
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QTimer, Qt, QUrl, QSize, QPoint
from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon, QPolygon, QMovie
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QStackedLayout,
)


class MiniPlayer(QDialog):
    """Compact Telegram-like player for rendered media."""

    def __init__(self, parent, data, tr=None):
        super().__init__(parent)
        self.setModal(True)
        self.resize(960, 620)
        self.data = data or {}
        self.tr = tr or {}
        self.path = self.data.get("path")
        self.type = self.data.get("type", "video")
        self.setWindowTitle(self.tr.get("player_title", "Player"))

        self._mode = "image"
        self._seeking = False
        self._duration_ms = 0
        self._fallback_fps = 24.0
        self._fallback_total = 0
        self._frame_interval_ms = 40
        self._frame_index = 0
        self._playback_rate = 1.0
        self._repeat_loop = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_cv_video)

        self._player = None
        self._audio = None
        self._cap = None
        self._gif_movie = None
        self._gif_frame_count = 0

        self._build_ui()
        self._apply_skin()
        self._init_media()

    def _txt(self, key, fallback):
        return self.tr.get(key, fallback)

    def _make_icon(self, shape, color="#e8edf7", size=14):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor(color))
            p.setPen(Qt.NoPen)
            if shape == "play":
                p.drawPolygon(QPolygon([pm.rect().topLeft() + QPoint(3, 2), pm.rect().bottomLeft() + QPoint(3, -2), pm.rect().center() + QPoint(4, 0)]))
            elif shape == "pause":
                p.drawRect(3, 2, 3, size - 4)
                p.drawRect(size - 6, 2, 3, size - 4)
            elif shape == "stop":
                p.drawRect(3, 3, size - 6, size - 6)
            elif shape == "repeat":
                p.drawRoundedRect(2, 4, size - 4, size - 8, 3, 3)
            elif shape == "close":
                p.setPen(QColor(color))
                p.setBrush(Qt.NoBrush)
                p.drawLine(3, 3, size - 3, size - 3)
                p.drawLine(size - 3, 3, 3, size - 3)
            elif shape == "volume":
                p.drawPolygon(QPolygon([
                    QPoint(2, size // 2),
                    QPoint(5, size // 2 - 3),
                    QPoint(8, size // 2 - 3),
                    QPoint(8, size // 2 + 3),
                    QPoint(5, size // 2 + 3),
                ]))
                p.drawEllipse(size - 5, size // 2 - 2, 2, 4)
        finally:
            if p.isActive():
                p.end()
        return QIcon(pm)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        top = QHBoxLayout()
        self.title = QLabel(Path(self.path).name if self.path else "Media")
        self.title.setStyleSheet("font-size:15px; font-weight:700;")
        top.addWidget(self.title)
        top.addStretch(1)
        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(34, 28)
        self.close_btn.setIcon(self._make_icon("close"))
        self.close_btn.clicked.connect(self.close)
        top.addWidget(self.close_btn)
        root.addLayout(top)

        self.viewport_frame = QFrame()
        self.viewport_frame.setObjectName("viewport")
        self.stack = QStackedLayout(self.viewport_frame)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.video_widget = QVideoWidget(self.viewport_frame)
        self.fallback_label = QLabel(self.viewport_frame)
        self.fallback_label.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self.video_widget)
        self.stack.addWidget(self.fallback_label)
        root.addWidget(self.viewport_frame, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.play_btn = QPushButton(self._txt("play", "Play"))
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.stop_btn = QPushButton(self._txt("stop", "Stop"))
        self.stop_btn.clicked.connect(self._stop)
        controls.addWidget(self.stop_btn)

        self.repeat_btn = QPushButton()
        self.repeat_btn.clicked.connect(self._toggle_repeat)
        controls.addWidget(self.repeat_btn)

        self.pos_slider = QSlider(Qt.Horizontal)
        self.pos_slider.setRange(0, 1000)
        self.pos_slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.pos_slider.sliderReleased.connect(self._on_seek_release)
        controls.addWidget(self.pos_slider, 1)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setMinimumWidth(120)
        controls.addWidget(self.time_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        controls.addWidget(self.speed_combo)

        self.vol_icon = QLabel()
        self.vol_icon.setPixmap(self._make_icon("volume").pixmap(QSize(14, 14)))
        controls.addWidget(self.vol_icon)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.valueChanged.connect(self._on_volume)
        controls.addWidget(self.volume_slider)

        root.addLayout(controls)
        self._set_button_icons(False)
        self._update_repeat_button()

    def _apply_skin(self):
        self.setStyleSheet(
            """
            QDialog { background: rgba(12,18,30,0.96); color: #e8edf7; border: 1px solid rgba(255,255,255,0.10); border-radius: 14px; }
            QFrame#viewport { background: rgba(7,10,18,0.96); border: 1px solid rgba(130,180,255,0.22); border-radius: 12px; }
            QLabel { color: #e8edf7; }
            QPushButton { background: rgba(30,43,70,0.72); color: #eef3ff; border: 1px solid rgba(140,176,230,0.30); border-radius: 8px; padding: 6px 10px; }
            QPushButton:hover { background: rgba(40,58,92,0.86); }
            QSlider::groove:horizontal { height: 6px; background: rgba(255,255,255,0.16); border-radius: 3px; }
            QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #dce8fb; border: 1px solid rgba(70,110,170,0.70); }
            QComboBox { background: rgba(20,30,50,0.88); color: #f0f5ff; border: 1px solid rgba(130,170,230,0.36); border-radius: 7px; padding: 4px 8px; min-width: 72px; }
            """
        )

    def _set_button_icons(self, playing):
        self.play_btn.setIcon(self._make_icon("pause" if playing else "play"))
        self.stop_btn.setIcon(self._make_icon("stop"))
        self.repeat_btn.setIcon(self._make_icon("repeat"))

    def _set_mode(self, mode):
        self._mode = mode
        if mode == "qt_video":
            self.stack.setCurrentWidget(self.video_widget)
        else:
            self.stack.setCurrentWidget(self.fallback_label)

    def _init_media(self):
        if self.type == "video" and self.path:
            if self._init_qt_video():
                return
            self._init_cv_video()
            return
        if self.type == "gif" and self.path:
            self._init_gif()
            return
        pil = self.data.get("pil")
        if pil is not None:
            self._show_pil(pil)
            self._set_mode("image")
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.repeat_btn.setEnabled(False)

    def _init_qt_video(self):
        try:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._audio.setVolume(self.volume_slider.value() / 100.0)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self.video_widget)
            self._player.setSource(QUrl.fromLocalFile(self.path))
            self._player.positionChanged.connect(self._on_qt_position)
            self._player.durationChanged.connect(self._on_qt_duration)
            self._player.mediaStatusChanged.connect(self._on_qt_status)
            self._player.playbackStateChanged.connect(self._on_qt_state)
            self._set_mode("qt_video")
            self._player.play()
            self._set_button_icons(True)
            return True
        except Exception:
            self._player = None
            self._audio = None
            return False

    def _init_cv_video(self):
        try:
            self._cap = cv2.VideoCapture(self.path)
            if not self._cap or not self._cap.isOpened():
                self.play_btn.setEnabled(False)
                self.stop_btn.setEnabled(False)
                self.repeat_btn.setEnabled(False)
                return
            self._set_mode("cv_video")
            fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 24.0)
            self._fallback_fps = fps if fps > 0.1 else 24.0
            self._fallback_total = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            self._duration_ms = int((self._fallback_total / max(0.1, self._fallback_fps)) * 1000)
            self._frame_interval_ms = max(8, int(1000.0 / max(1.0, self._fallback_fps * self._playback_rate)))
            self._frame_index = 0
            self._show_cv_current_frame()
            self._timer.start(self._frame_interval_ms)
            self._set_button_icons(True)
        except Exception:
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.repeat_btn.setEnabled(False)

    def _probe_gif(self):
        total_ms = 0
        frames = 0
        try:
            with Image.open(self.path) as im:
                while True:
                    frames += 1
                    total_ms += int(im.info.get("duration", 80) or 80)
                    try:
                        im.seek(im.tell() + 1)
                    except EOFError:
                        break
        except Exception:
            pass
        return frames, max(1, total_ms)

    def _init_gif(self):
        try:
            self._gif_movie = QMovie(self.path)
            self._gif_movie.setCacheMode(QMovie.CacheNone)
            if not self._gif_movie.isValid():
                self.play_btn.setEnabled(False)
                self.stop_btn.setEnabled(False)
                self.repeat_btn.setEnabled(False)
                return
            self._gif_frame_count, self._duration_ms = self._probe_gif()
            self.fallback_label.setMovie(self._gif_movie)
            self._set_mode("gif")
            self._gif_movie.frameChanged.connect(self._on_gif_frame)
            try:
                self._gif_movie.finished.connect(self._on_gif_finished)
            except Exception:
                pass
            self._apply_gif_speed()
            self._apply_gif_repeat()
            self._gif_movie.start()
            self._set_button_icons(True)
        except Exception:
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.repeat_btn.setEnabled(False)

    def _show_pil(self, pil):
        q = QPixmap.fromImage(ImageQt(pil.convert("RGB")))
        lw = max(240, self.fallback_label.width())
        lh = max(160, self.fallback_label.height())
        q = q.scaled(lw, lh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.fallback_label.setPixmap(q)

    def _show_cv_current_frame(self):
        if self._cap is None or not self._cap.isOpened():
            return
        cur = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
        if cur > 0:
            cur -= 1
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, cur))
        ret, frame = self._cap.read()
        if not ret:
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._show_pil(Image.fromarray(frame))
        self._frame_index = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES) or self._frame_index)
        self._sync_fallback_slider()

    def _tick_cv_video(self):
        if self._mode != "cv_video":
            return
        if self._cap is None or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret:
            if self._repeat_loop:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._frame_index = 0
                return
            self._timer.stop()
            self._set_button_icons(False)
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._show_pil(Image.fromarray(frame))
        self._frame_index = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES) or self._frame_index)
        self._sync_fallback_slider()

    def _sync_fallback_slider(self):
        if self._seeking:
            return
        if self._mode == "cv_video" and self._fallback_total > 0:
            val = int(self._frame_index * 1000 / max(1, self._fallback_total))
            self.pos_slider.setValue(max(0, min(1000, val)))
            cur_ms = int((self._frame_index / max(0.1, self._fallback_fps)) * 1000)
            self._set_time(cur_ms, self._duration_ms)
        elif self._mode == "gif" and self._gif_frame_count > 0:
            idx = 0
            try:
                idx = int(self._gif_movie.currentFrameNumber())
            except Exception:
                idx = 0
            val = int(idx * 1000 / max(1, self._gif_frame_count))
            self.pos_slider.setValue(max(0, min(1000, val)))
            cur_ms = int((idx / max(1, self._gif_frame_count)) * self._duration_ms)
            self._set_time(cur_ms, self._duration_ms)

    def _on_seek_release(self):
        try:
            val = self.pos_slider.value()
            if self._mode == "qt_video" and self._player is not None:
                dur = max(1, int(self._duration_ms or self._player.duration() or 1))
                self._player.setPosition(int(val * dur / 1000))
            elif self._mode == "cv_video" and self._cap is not None and self._fallback_total > 0:
                idx = int(val * self._fallback_total / 1000)
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, idx))
                self._show_cv_current_frame()
            elif self._mode == "gif" and self._gif_movie is not None and self._gif_frame_count > 0:
                idx = int(val * self._gif_frame_count / 1000)
                self._gif_movie.jumpToFrame(max(0, min(self._gif_frame_count - 1, idx)))
                self._sync_fallback_slider()
        except Exception:
            pass
        finally:
            self._seeking = False

    def _on_qt_position(self, pos):
        if self._seeking:
            return
        dur = max(1, int(self._duration_ms or (self._player.duration() if self._player else 0) or 1))
        self.pos_slider.setValue(int(pos * 1000 / dur))
        self._set_time(int(pos), dur)

    def _on_qt_duration(self, dur):
        self._duration_ms = int(dur or 0)
        self._set_time(0, self._duration_ms)

    def _on_qt_status(self, status):
        try:
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                if self._repeat_loop:
                    self._player.setPosition(0)
                    self._player.play()
                else:
                    self._set_button_icons(False)
        except Exception:
            pass

    def _on_qt_state(self, state):
        try:
            playing = state == QMediaPlayer.PlaybackState.PlayingState
            self._set_button_icons(playing)
            self.play_btn.setText(self._txt("pause", "Pause") if playing else self._txt("play", "Play"))
        except Exception:
            pass

    def _on_gif_frame(self, *_):
        self._sync_fallback_slider()

    def _on_gif_finished(self):
        if self._repeat_loop:
            return
        self._set_button_icons(False)
        self.play_btn.setText(self._txt("play", "Play"))

    def _set_time(self, cur_ms, dur_ms):
        def fmt(ms):
            s = max(0, int(ms // 1000))
            return f"{s//60:02d}:{s%60:02d}"

        self.time_label.setText(f"{fmt(cur_ms)} / {fmt(dur_ms)}")

    def _apply_gif_repeat(self):
        if self._gif_movie is None:
            return
        try:
            self._gif_movie.setLoopCount(-1 if self._repeat_loop else 1)
        except Exception:
            pass

    def _apply_gif_speed(self):
        if self._gif_movie is None:
            return
        try:
            self._gif_movie.setSpeed(max(10, int(self._playback_rate * 100)))
        except Exception:
            pass

    def _toggle_repeat(self):
        self._repeat_loop = not self._repeat_loop
        self._apply_gif_repeat()
        self._update_repeat_button()

    def _update_repeat_button(self):
        self.repeat_btn.setText(self._txt("repeat_loop", "Loop") if self._repeat_loop else self._txt("repeat_once", "Once"))

    def _on_speed_changed(self, txt):
        val = 1.0
        try:
            val = float(txt.replace("x", ""))
        except Exception:
            val = 1.0
        self._playback_rate = max(0.25, min(4.0, val))

        if self._mode == "qt_video" and self._player is not None:
            try:
                self._player.setPlaybackRate(self._playback_rate)
            except Exception:
                pass
        elif self._mode == "cv_video":
            self._frame_interval_ms = max(8, int(1000.0 / max(1.0, self._fallback_fps * self._playback_rate)))
            if self._timer.isActive():
                self._timer.start(self._frame_interval_ms)
        elif self._mode == "gif":
            self._apply_gif_speed()

    def _on_volume(self, v):
        if self._audio is not None:
            try:
                self._audio.setVolume(max(0.0, min(1.0, float(v) / 100.0)))
            except Exception:
                pass

    def _toggle_play(self):
        if self._mode == "qt_video" and self._player is not None:
            try:
                st = self._player.playbackState()
                if st == QMediaPlayer.PlaybackState.PlayingState:
                    self._player.pause()
                else:
                    self._player.play()
            except Exception:
                pass
            return

        if self._mode == "cv_video":
            if self._timer.isActive():
                self._timer.stop()
                self._set_button_icons(False)
                self.play_btn.setText(self._txt("play", "Play"))
            else:
                self._timer.start(self._frame_interval_ms)
                self._set_button_icons(True)
                self.play_btn.setText(self._txt("pause", "Pause"))
            return

        if self._mode == "gif" and self._gif_movie is not None:
            try:
                if self._gif_movie.state() == QMovie.Running:
                    self._gif_movie.setPaused(True)
                    self._set_button_icons(False)
                    self.play_btn.setText(self._txt("play", "Play"))
                else:
                    if self._gif_movie.state() == QMovie.NotRunning:
                        self._gif_movie.start()
                    else:
                        self._gif_movie.setPaused(False)
                    self._set_button_icons(True)
                    self.play_btn.setText(self._txt("pause", "Pause"))
            except Exception:
                pass

    def _stop(self):
        if self._mode == "qt_video" and self._player is not None:
            try:
                self._player.stop()
                self._player.setPosition(0)
                self._set_time(0, self._duration_ms)
                self.pos_slider.setValue(0)
            except Exception:
                pass
            self._set_button_icons(False)
            self.play_btn.setText(self._txt("play", "Play"))
            return

        if self._mode == "cv_video":
            try:
                self._timer.stop()
                if self._cap is not None:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self._frame_index = 0
                    self._show_cv_current_frame()
                self.pos_slider.setValue(0)
                self._set_time(0, self._duration_ms)
            except Exception:
                pass
            self._set_button_icons(False)
            self.play_btn.setText(self._txt("play", "Play"))
            return

        if self._mode == "gif" and self._gif_movie is not None:
            try:
                self._gif_movie.stop()
                self._gif_movie.jumpToFrame(0)
                self.pos_slider.setValue(0)
                self._set_time(0, self._duration_ms)
            except Exception:
                pass
            self._set_button_icons(False)
            self.play_btn.setText(self._txt("play", "Play"))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._mode == "gif" and self._gif_movie is not None:
            try:
                self._gif_movie.setScaledSize(self.fallback_label.size())
            except Exception:
                pass

    def closeEvent(self, ev):
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass
        try:
            if self._player is not None:
                self._player.stop()
        except Exception:
            pass
        try:
            if self._gif_movie is not None:
                self._gif_movie.stop()
        except Exception:
            pass
        return super().closeEvent(ev)
