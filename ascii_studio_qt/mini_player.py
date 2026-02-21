from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QSlider
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PIL import Image
import imageio
import cv2
import numpy as np
from PIL.ImageQt import ImageQt
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import QUrl


class MiniPlayer(QDialog):
    """Simple resilient media player dialog.

    Tries QMediaPlayer (hardware) first; if it fails, falls back to frame-by-frame
    decoding using OpenCV (or imageio for GIFs). Provides Play/Pause and a slider
    when QMediaPlayer is used.
    """

    def __init__(self, parent, data):
        super().__init__(parent)
        self.setWindowTitle("Player")
        self.setModal(True)
        self.data = data
        self.path = data.get('path')
        self.type = data.get('type', 'video')

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.close_btn = QPushButton('✕', self)
        self.close_btn.clicked.connect(self.close)

        self.layout = QVBoxLayout(self)
        hdr = QHBoxLayout()
        hdr.addStretch(1)
        hdr.addWidget(self.close_btn)
        self.layout.addLayout(hdr)
        self.layout.addWidget(self.label)

        # controls
        self.ctrl_row = QHBoxLayout()
        self.play_btn = QPushButton('Play')
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._toggle_play)
        self.ctrl_row.addWidget(self.play_btn)
        self.pos_slider = None
        self.layout.addLayout(self.ctrl_row)

        # state
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.frames = []
        self.frame_index = 0
        self.cap = None
        self.player = None
        self.video_widget = None

        # load depending on type
        if self.type == 'gif':
            try:
                self.frames = imageio.mimread(self.path)
            except Exception:
                self.frames = []

        if self.type == 'video':
            # attempt QMediaPlayer (preferred)
            try:
                self.video_widget = QVideoWidget(self)
                self.video_widget.setMinimumSize(320, 200)
                try:
                    self.layout.removeWidget(self.label)
                    self.label.hide()
                except Exception:
                    pass
                self.layout.addWidget(self.video_widget)

                self.player = QMediaPlayer(self)
                audio = QAudioOutput(self)
                self.player.setAudioOutput(audio)
                self.player.setVideoOutput(self.video_widget)
                try:
                    self.player.setSource(QUrl.fromLocalFile(self.path))
                except Exception:
                    try:
                        self.player.setSource(self.path)
                    except Exception:
                        self.player = None

                if self.player is not None:
                    # add slider
                    self.pos_slider = QSlider(Qt.Horizontal)
                    self.pos_slider.setRange(0, 1000)
                    self.pos_slider.sliderPressed.connect(lambda: setattr(self, '_seeking', True))
                    self.pos_slider.sliderReleased.connect(self._on_slider_released)
                    self.ctrl_row.addWidget(self.pos_slider)
                    try:
                        self.player.positionChanged.connect(self._on_position_changed)
                        self.player.durationChanged.connect(self._on_duration_changed)
                    except Exception:
                        pass
            except Exception:
                self.player = None

            # if QMediaPlayer not available, try OpenCV
            if self.player is None:
                try:
                    self.cap = cv2.VideoCapture(self.path)
                    if not self.cap or not self.cap.isOpened():
                        self.cap = None
                except Exception:
                    self.cap = None

        # start playback (or show static preview)
        self._start_playback()

    def _start_playback(self):
        if self.type == 'gif' and self.frames:
            self.frame_index = 0
            self.timer.start(100)
        elif self.type == 'video':
            if getattr(self, 'player', None) is not None:
                try:
                    if self.video_widget:
                        self.video_widget.show()
                        # try to size dialog to video widget preferred size
                        self.resize(max(640, self.video_widget.minimumWidth()), max(360, self.video_widget.minimumHeight()))
                    self.player.play()
                    # fallback check
                    QTimer.singleShot(800, self._check_player_output)
                except Exception:
                    # fallback to frame loop using OpenCV
                    try:
                        if self.cap is None:
                            self.cap = cv2.VideoCapture(self.path)
                            if not self.cap or not self.cap.isOpened():
                                self.cap = None
                    except Exception:
                        self.cap = None
                    if getattr(self, 'cap', None) is not None:
                        try:
                            if self.video_widget:
                                self.video_widget.hide()
                            self.label.show()
                        except Exception:
                            pass
                        self.timer.start(40)
            elif getattr(self, 'cap', None) is not None:
                self.timer.start(40)
        else:
            pil = self.data.get('pil')
            if pil is not None:
                q = QPixmap.fromImage(ImageQt(pil))
                self.label.setPixmap(q)

        available = (getattr(self, 'player', None) is not None) or (getattr(self, 'cap', None) is not None) or (self.type == 'gif' and bool(self.frames))
        try:
            self.play_btn.setEnabled(bool(available))
        except Exception:
            pass

    def _check_player_output(self):
        # if QMediaPlayer didn't render video, fallback to frame loop
        try:
            if getattr(self, 'player', None) is None:
                return
            if self.cap is None:
                try:
                    self.cap = cv2.VideoCapture(self.path)
                except Exception:
                    self.cap = None
            if self.cap is None or not self.cap.isOpened():
                return
            ret, frame = self.cap.read()
            if not ret:
                return
            try:
                self.player.stop()
            except Exception:
                pass
            if self.video_widget:
                self.video_widget.hide()
            self.label.show()
            self.timer.start(40)
        except Exception:
            pass

    def _tick(self):
        if self.type == 'gif':
            if not self.frames:
                return
            frame = self.frames[self.frame_index % len(self.frames)]
            arr = np.array(frame)
            img = Image.fromarray(arr)
            q = QPixmap.fromImage(ImageQt(img))
            self.label.setPixmap(q)
            self.frame_index += 1
        elif self.type == 'video':
            if getattr(self, 'cap', None) is None:
                return
            if not self.cap.isOpened():
                return
            ret, frame = self.cap.read()
            if not ret:
                try:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                except Exception:
                    pass
                return
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            q = QPixmap.fromImage(ImageQt(img))
            # scale to fit label while preserving aspect
            try:
                lw, lh = self.label.width() or q.width(), self.label.height() or q.height()
                q = q.scaled(lw, lh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception:
                pass
            self.label.setPixmap(q)

    def closeEvent(self, ev):
        try:
            if getattr(self, 'timer', None) is not None and self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, 'cap', None) is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
        except Exception:
            pass
        try:
            if getattr(self, 'player', None) is not None:
                try:
                    self.player.stop()
                except Exception:
                    pass
                self.player = None
        except Exception:
            pass
        return super().closeEvent(ev)

    def _toggle_play(self):
        try:
            if getattr(self, 'player', None) is not None:
                # QMediaPlayer
                state = self.player.playbackState()
                # PlaybackState enum available on some platforms; use play/pause toggles defensively
                try:
                    from PySide6.QtMultimedia import QMediaPlayer as _MP
                    playing = (state == _MP.PlaybackState.PlayingState)
                except Exception:
                    playing = False
                if playing:
                    self.player.pause(); self.play_btn.setText('Play')
                else:
                    self.player.play(); self.play_btn.setText('Pause')
                return
        except Exception:
            pass
        try:
            if self.timer.isActive():
                self.timer.stop(); self.play_btn.setText('Play')
            else:
                self.timer.start(40); self.play_btn.setText('Pause')
        except Exception:
            pass

    def _on_position_changed(self, pos):
        try:
            if self.pos_slider and not getattr(self, '_seeking', False):
                dur = 0
                try:
                    dur = self.player.duration()
                except Exception:
                    try:
                        dur = getattr(self.player, 'duration', 0)
                    except Exception:
                        dur = 0
                dur = max(1, int(dur))
                val = int(pos * 1000 / max(1, dur))
                self.pos_slider.setValue(val)
        except Exception:
            pass

    def _on_duration_changed(self, dur):
        try:
            if self.pos_slider:
                self.pos_slider.setEnabled(dur > 0)
        except Exception:
            pass

    def _on_slider_released(self):
        try:
            if not self.pos_slider:
                return
            val = self.pos_slider.value()
            dur = 0
            try:
                dur = self.player.duration()
            except Exception:
                try:
                    dur = getattr(self.player, 'duration', 0)
                except Exception:
                    dur = 0
            dur = max(1, int(dur))
            target = int(val * dur / 1000)
            try:
                self.player.setPosition(target)
            except Exception:
                pass
        finally:
            setattr(self, '_seeking', False)

