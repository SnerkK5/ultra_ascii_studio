from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PySide6.QtCore import QRect, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "ASCIIStudio"


def _resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def _quote_ps(s: str) -> str:
    return s.replace("'", "''")


class InstallWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    done = Signal(str, str)
    error = Signal(str)

    def __init__(self, package_zip: str, out_dir: str, desktop_shortcut: bool):
        super().__init__()
        self.package_zip = package_zip
        self.out_dir = out_dir
        self.desktop_shortcut = desktop_shortcut

    @staticmethod
    def _find_exe(out_dir: Path) -> Path | None:
        cands = [
            out_dir / APP_NAME / f"{APP_NAME}.exe",
            out_dir / f"{APP_NAME}.exe",
        ]
        for c in cands:
            if c.exists():
                return c
        return None

    @staticmethod
    def _create_desktop_shortcut(exe_path: Path) -> None:
        desktop = Path(os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"))
        if not desktop.exists():
            return
        lnk = desktop / "ASCII Studio.lnk"
        icon_ico = exe_path.parent / "QWE1R.ico"
        if not icon_ico.exists():
            icon_ico = exe_path.parent / "_internal" / "QWE1R.ico"
        if not icon_ico.exists():
            icon_ico = exe_path.parent / "QWER.ico"
        if not icon_ico.exists():
            icon_ico = exe_path.parent / "_internal" / "QWER.ico"
        icon_loc = str(icon_ico) if icon_ico.exists() else str(exe_path)
        ps = (
            "$w = New-Object -ComObject WScript.Shell;"
            f"$s = $w.CreateShortcut('{_quote_ps(str(lnk))}');"
            f"$s.TargetPath = '{_quote_ps(str(exe_path))}';"
            f"$s.WorkingDirectory = '{_quote_ps(str(exe_path.parent))}';"
            f"$s.IconLocation = '{_quote_ps(icon_loc)},0';"
            "$s.Save();"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def _harden_installation(out_dir: Path) -> None:
        # Best-effort protection from accidental edits/deletes by standard users.
        try:
            if os.name == "nt":
                # Mark files/directories as read-only.
                subprocess.run(
                    f'attrib +R "{str(out_dir)}\\*" /S /D',
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=True,
                )
                # SID-based ACLs (language-independent):
                # Administrators: Full, SYSTEM: Full, Users: Read+Execute.
                sid_admin = "*S-1-5-32-544"
                sid_system = "*S-1-5-18"
                sid_users = "*S-1-5-32-545"
                subprocess.run(
                    [
                        "icacls", str(out_dir),
                        "/grant:r",
                        f"{sid_admin}:(OI)(CI)F",
                        f"{sid_system}:(OI)(CI)F",
                        f"{sid_users}:(OI)(CI)RX",
                        "/T", "/C", "/Q",
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # Unix-like: remove write bits for group/others on files.
                for p in out_dir.rglob("*"):
                    if p.is_file():
                        try:
                            p.chmod(0o644)
                        except Exception:
                            pass
        except Exception:
            pass

    def run(self):
        try:
            pkg = Path(self.package_zip)
            if not pkg.exists():
                raise FileNotFoundError(f"Package not found: {pkg}")

            out = Path(self.out_dir)
            out.mkdir(parents=True, exist_ok=True)

            self.status.emit("Подготовка...")
            with zipfile.ZipFile(pkg, "r") as zf:
                files = [m for m in zf.infolist() if not m.is_dir()]
                total = max(1, len(files))
                for idx, m in enumerate(files, start=1):
                    zf.extract(m, out)
                    self.progress.emit(int(idx * 100 / total))
                    if idx % 30 == 0:
                        self.status.emit(f"Распаковка: {idx}/{total}")

            self.status.emit("Финализация...")
            entries = [p for p in out.iterdir() if p.name != "_ascii_studio_pkg.zip"]
            if len(entries) == 1 and entries[0].is_dir() and entries[0].name.lower().startswith("asciistudio"):
                top = entries[0]
                for p in list(top.iterdir()):
                    dst = out / p.name
                    if dst.exists():
                        if dst.is_dir():
                            shutil.rmtree(dst, ignore_errors=True)
                        else:
                            dst.unlink(missing_ok=True)
                    shutil.move(str(p), str(dst))
                shutil.rmtree(top, ignore_errors=True)

            exe = self._find_exe(out)
            if exe is None:
                raise RuntimeError("Executable not found after extraction")

            self.status.emit("Защита файлов установки...")
            self._harden_installation(out)

            if self.desktop_shortcut:
                self.status.emit("Создание ярлыка...")
                try:
                    self._create_desktop_shortcut(exe)
                except Exception:
                    pass

            self.progress.emit(100)
            self.status.emit("Установка завершена")
            self.done.emit(str(out), str(exe))
        except Exception as e:
            self.error.emit(str(e))


class InstallerWindow(QWidget):
    def __init__(self, auto_install: dict | None = None):
        super().__init__()
        self.setWindowTitle("ASCII Studio Setup")
        try:
            icon_path = _resource_path("QWE1R.ico")
            if not icon_path.exists():
                icon_path = _resource_path("QWE1R.png")
            if not icon_path.exists():
                icon_path = _resource_path("QWER.ico")
            if not icon_path.exists():
                icon_path = _resource_path("QWER.png")
            if not icon_path.exists():
                icon_path = _resource_path("iconASCII.ico")
            if not icon_path.exists():
                icon_path = _resource_path("iconASCII.png")
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                app = QApplication.instance()
                if app is not None:
                    app.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        self.setMinimumSize(1060, 690)
        self.resize(1220, 780)

        self._worker: InstallWorker | None = None
        self._installed_dir: str | None = None
        self._installed_exe: str | None = None
        self._auto_install = auto_install or {}

        base = Path(__file__).resolve().parent
        self.bg_path = base / "3hg46u.png"
        self.music_path = base / "SNERK503.mp3"

        embedded_zip = _resource_path("ASCIIStudio_package.zip")
        local_zip = base / "release" / "ASCIIStudio_package.zip"
        self.package_zip = embedded_zip if embedded_zip.exists() else local_zip

        self._bg_pixmap = QPixmap(str(self.bg_path)) if self.bg_path.exists() else QPixmap()

        self._apply_styles()
        self._build_ui()
        self._init_music()
        self._schedule_auto_install()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 24, 26, 24)
        outer.setSpacing(0)
        outer.addStretch(1)

        center = QHBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.addStretch(1)

        self.panel = QFrame(self)
        self.panel.setObjectName("installerPanel")
        self.panel.setMinimumWidth(860)
        self.panel.setMaximumWidth(980)

        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(52)
        shadow.setOffset(0, 18)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.panel.setGraphicsEffect(shadow)

        center.addWidget(self.panel)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(1)

        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(30, 24, 30, 20)
        lay.setSpacing(12)

        self.title = QLabel("ASCII Studio")
        self.title.setObjectName("titleLabel")
        self.subtitle = QLabel("SETUP WIZARD")
        self.subtitle.setObjectName("subtitleLabel")
        self.step_label = QLabel("Шаг 1 из 4")
        self.step_label.setObjectName("stepLabel")

        lay.addWidget(self.title)
        lay.addWidget(self.subtitle)
        lay.addWidget(self.step_label)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        lay.addWidget(divider)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_welcome())
        self.stack.addWidget(self._build_page_options())
        self.stack.addWidget(self._build_page_install())
        self.stack.addWidget(self._build_page_finish())
        lay.addWidget(self.stack, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.back_btn = QPushButton("Назад")
        self.next_btn = QPushButton("Далее")
        self.cancel_btn = QPushButton("Отмена")
        for b in (self.back_btn, self.next_btn, self.cancel_btn):
            b.setObjectName("actionButton")
            b.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(self.back_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.next_btn)
        btn_row.addWidget(self.cancel_btn)
        lay.addLayout(btn_row)

        self.back_btn.clicked.connect(self._go_back)
        self.next_btn.clicked.connect(self._go_next)
        self.cancel_btn.clicked.connect(self.close)

        self._update_nav()

    def _build_page_welcome(self) -> QWidget:
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        hdr = QLabel("Добро пожаловать в установщик ASCII Studio")
        hdr.setObjectName("pageHeader")
        txt = QLabel(
            "Этот установщик полностью офлайн: все файлы приложения уже встроены в setup.exe.\n\n"
            "На следующих шагах вы выберете путь установки и создание ярлыка на рабочем столе."
        )
        txt.setWordWrap(True)
        txt.setObjectName("pageText")

        self.pkg_info = QLabel(f"Пакет: {self.package_zip.name}")
        self.pkg_info.setObjectName("mutedText")

        l.addWidget(hdr)
        l.addWidget(txt)
        l.addWidget(self.pkg_info)
        l.addStretch(1)
        return page

    def _build_page_options(self) -> QWidget:
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        hdr = QLabel("Параметры установки")
        hdr.setObjectName("pageHeader")
        l.addWidget(hdr)

        path_lbl = QLabel("Каталог установки")
        path_lbl.setObjectName("sectionLabel")
        l.addWidget(path_lbl)

        self.path_edit = QLineEdit(str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / APP_NAME))
        self.path_edit.setObjectName("lineEdit")
        self.path_edit.setPlaceholderText("Путь установки")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.path_edit, 1)

        self.browse_btn = QPushButton("Обзор...")
        self.browse_btn.setObjectName("actionButton")
        self.browse_btn.clicked.connect(self._pick_dir)
        row.addWidget(self.browse_btn)
        l.addLayout(row)

        self.desktop_shortcut_chk = QCheckBox("Создать ярлык на рабочем столе")
        self.desktop_shortcut_chk.setChecked(True)
        self.desktop_shortcut_chk.setObjectName("check")
        l.addWidget(self.desktop_shortcut_chk)

        self.run_after_install_chk = QCheckBox("Запустить ASCII Studio после завершения")
        self.run_after_install_chk.setChecked(True)
        self.run_after_install_chk.setObjectName("check")
        l.addWidget(self.run_after_install_chk)
        protect_hint = QLabel("После установки файлы будут защищены: для Users только чтение/запуск.")
        protect_hint.setObjectName("mutedText")
        protect_hint.setWordWrap(True)
        l.addWidget(protect_hint)

        self.option_warn = QLabel("")
        self.option_warn.setObjectName("warnText")
        l.addWidget(self.option_warn)
        l.addStretch(1)
        return page


    def _schedule_auto_install(self):
        cfg = self._auto_install or {}
        if not cfg:
            return
        try:
            out = str(cfg.get("out", "")).strip()
            if out:
                self.path_edit.setText(out)
            self.desktop_shortcut_chk.setChecked(bool(int(cfg.get("shortcut", 1))))
            self.run_after_install_chk.setChecked(bool(int(cfg.get("run_after", 1))))
            self.stack.setCurrentIndex(1)
            self._update_nav()
            QTimer.singleShot(140, self._start_install)
        except Exception:
            pass

    def _build_page_install(self) -> QWidget:
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        hdr = QLabel("Установка")
        hdr.setObjectName("pageHeader")
        self.install_status = QLabel("Ожидание запуска...")
        self.install_status.setObjectName("pageText")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setObjectName("progressBar")

        l.addWidget(hdr)
        l.addWidget(self.install_status)
        l.addWidget(self.progress)
        l.addStretch(1)
        return page

    def _build_page_finish(self) -> QWidget:
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        hdr = QLabel("Готово")
        hdr.setObjectName("pageHeader")
        self.finish_text = QLabel("ASCII Studio успешно установлен.")
        self.finish_text.setWordWrap(True)
        self.finish_text.setObjectName("pageText")

        l.addWidget(hdr)
        l.addWidget(self.finish_text)
        l.addStretch(1)
        return page

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                color: #eaf2ff;
                font-family: Segoe UI;
                font-size: 13px;
                background: transparent;
            }
            #installerPanel {
                background-color: rgba(8, 12, 22, 188);
                border: 1px solid rgba(145, 196, 255, 110);
                border-radius: 22px;
            }
            #titleLabel {
                font-size: 44px;
                font-weight: 800;
                letter-spacing: 0.3px;
                color: #f6fbff;
            }
            #subtitleLabel {
                font-size: 12px;
                letter-spacing: 2px;
                color: #95c5ff;
                font-weight: 700;
            }
            #stepLabel {
                color: #a9cdf8;
                font-size: 12px;
                margin-top: 2px;
            }
            #divider {
                background: rgba(151, 196, 255, 95);
                border: none;
                margin-top: 2px;
                margin-bottom: 2px;
            }
            #pageHeader {
                font-size: 22px;
                font-weight: 700;
                color: #f0f7ff;
            }
            #pageText {
                color: #d2e7ff;
                font-size: 13px;
            }
            #mutedText {
                color: #9ebbe0;
                font-size: 11px;
            }
            #sectionLabel {
                color: #cce4ff;
                font-size: 12px;
                letter-spacing: 0.6px;
                font-weight: 600;
                margin-top: 4px;
            }
            #warnText {
                color: #ffb4b4;
                min-height: 16px;
                font-size: 12px;
            }
            #lineEdit {
                background: rgba(8, 16, 32, 194);
                border: 1px solid rgba(146, 192, 255, 92);
                border-radius: 10px;
                padding: 10px 12px;
                selection-background-color: #3f8dff;
            }
            #lineEdit:focus {
                border: 1px solid rgba(136, 200, 255, 196);
            }
            #check {
                color: #d8e9ff;
                spacing: 8px;
            }
            #check::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 1px solid rgba(160, 201, 255, 120);
                background: rgba(13, 19, 33, 180);
            }
            #check::indicator:checked {
                background: #4eb3ff;
                border: 1px solid #7ed0ff;
            }
            #progressBar {
                border: 1px solid rgba(149, 194, 255, 92);
                border-radius: 10px;
                background: rgba(8, 16, 32, 194);
                text-align: center;
                padding: 2px;
                color: #f2f8ff;
                font-weight: 700;
                min-height: 26px;
            }
            #progressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3cb4ff, stop:1 #7d86ff);
                border-radius: 8px;
            }
            #actionButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(55, 100, 170, 225), stop:1 rgba(53, 79, 152, 225));
                color: #f3f9ff;
                border: 1px solid rgba(160, 201, 255, 108);
                border-radius: 11px;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 600;
                min-width: 120px;
            }
            #actionButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(70, 125, 207, 235), stop:1 rgba(73, 98, 186, 235));
            }
            #actionButton:pressed {
                padding-top: 11px;
            }
            #actionButton:disabled {
                color: #9db4d2;
                background: rgba(40, 53, 84, 175);
                border: 1px solid rgba(130, 153, 193, 70);
            }
            """
        )

    def _init_music(self):
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.18)
        self._player.setAudioOutput(self._audio)
        if self.music_path.exists():
            self._player.setSource(QUrl.fromLocalFile(str(self.music_path)))
            self._player.mediaStatusChanged.connect(self._on_music_status)
            self._player.play()

    def _on_music_status(self, status):
        try:
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                self._player.setPosition(0)
                self._player.play()
        except Exception:
            pass

    @staticmethod
    def _cover_source_rect(pixmap: QPixmap, target_rect: QRect) -> QRect:
        if pixmap.isNull() or target_rect.isEmpty():
            return QRect()
        pw, ph = pixmap.width(), pixmap.height()
        tw, th = target_rect.width(), target_rect.height()
        scale = max(tw / pw, th / ph)
        src_w = max(1, int(round(tw / scale)))
        src_h = max(1, int(round(th / scale)))
        src_x = max(0, (pw - src_w) // 2)
        src_y = max(0, (ph - src_h) // 2)
        return QRect(src_x, src_y, src_w, src_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = self.rect()

        if not self._bg_pixmap.isNull():
            src = self._cover_source_rect(self._bg_pixmap, rect)
            painter.drawPixmap(rect, self._bg_pixmap, src)
        else:
            painter.fillRect(rect, QColor(6, 10, 18))

        darken = QLinearGradient(0, 0, 0, rect.height())
        darken.setColorAt(0.0, QColor(6, 10, 18, 208))
        darken.setColorAt(0.5, QColor(7, 14, 24, 170))
        darken.setColorAt(1.0, QColor(5, 10, 18, 218))
        painter.fillRect(rect, darken)

        side_glow = QLinearGradient(0, 0, rect.width(), 0)
        side_glow.setColorAt(0.0, QColor(55, 132, 255, 16))
        side_glow.setColorAt(0.45, QColor(110, 120, 255, 10))
        side_glow.setColorAt(1.0, QColor(63, 239, 215, 16))
        painter.fillRect(rect, side_glow)

        super().paintEvent(event)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Каталог установки", self.path_edit.text())
        if d:
            self.path_edit.setText(d)

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx <= 0:
            return
        if idx == 2:
            return
        self.stack.setCurrentIndex(idx - 1)
        self._update_nav()

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            self.stack.setCurrentIndex(1)
            self._update_nav()
            return
        if idx == 1:
            self._start_install()
            return
        if idx == 3:
            if self.run_after_install_chk.isChecked():
                self._run_app()
            self.close()

    def _update_nav(self):
        idx = self.stack.currentIndex()
        self.step_label.setText(f"Шаг {idx + 1} из 4")
        self.back_btn.setEnabled(idx in (1,))

        if idx == 0:
            self.next_btn.setText("Далее")
            self.next_btn.setEnabled(True)
        elif idx == 1:
            self.next_btn.setText("Установить")
            self.next_btn.setEnabled(True)
        elif idx == 2:
            self.next_btn.setText("Установка...")
            self.next_btn.setEnabled(False)
        else:
            self.next_btn.setText("Готово")
            self.next_btn.setEnabled(True)

    def _start_install(self):
        if not self.package_zip.exists():
            self.option_warn.setText("Встроенный пакет не найден в установщике.")
            return

        out = self.path_edit.text().strip()
        if not out:
            self.option_warn.setText("Укажите каталог установки.")
            return

        if not self._can_write_target(Path(out)):
            if not self._is_admin():
                if self._relaunch_elevated_install(out):
                    return
                self.option_warn.setText("Нужны права администратора для выбранного пути.")
                return
            self.option_warn.setText("Нет доступа к выбранному пути.")
            return

        self.option_warn.setText("")
        self.stack.setCurrentIndex(2)
        self._update_nav()
        self.cancel_btn.setEnabled(False)

        self.progress.setValue(0)
        self.install_status.setText("Запуск установки...")

        self._worker = InstallWorker(str(self.package_zip), out, bool(self.desktop_shortcut_chk.isChecked()))
        self._worker.progress.connect(self.progress.setValue)
        self._worker.status.connect(self.install_status.setText)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()


    @staticmethod
    def _is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def _can_write_target(out_path: Path) -> bool:
        try:
            probe_root = out_path
            while not probe_root.exists():
                parent = probe_root.parent
                if parent == probe_root:
                    break
                probe_root = parent
            probe_root.mkdir(parents=True, exist_ok=True)
            probe = probe_root / '.ascii_installer_write_test.tmp'
            with open(probe, 'w', encoding='utf-8') as f:
                f.write('ok')
            probe.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def _relaunch_elevated_install(self, out_dir: str) -> bool:
        try:
            shortcut = 1 if self.desktop_shortcut_chk.isChecked() else 0
            run_after = 1 if self.run_after_install_chk.isChecked() else 0
            if getattr(sys, 'frozen', False):
                exe = sys.executable
                params = f'--auto-install --out "{out_dir}" --shortcut {shortcut} --run-after {run_after}'
            else:
                exe = sys.executable
                script = str(Path(__file__).resolve())
                params = f'"{script}" --auto-install --out "{out_dir}" --shortcut {shortcut} --run-after {run_after}'
            ret = ctypes.windll.shell32.ShellExecuteW(None, 'runas', exe, params, None, 1)
            if int(ret) <= 32:
                return False
            self.close()
            return True
        except Exception:
            return False

    def _on_done(self, path: str, exe: str):
        self._installed_dir = path
        self._installed_exe = exe
        self.finish_text.setText(
            f"ASCII Studio установлен в:\n{path}\n\n"
            f"Исполняемый файл:\n{exe}\n\n"
            "Нажмите 'Готово' для выхода из установщика."
        )
        self.stack.setCurrentIndex(3)
        self.cancel_btn.setEnabled(True)
        self._update_nav()

    def _on_error(self, msg: str):
        self.install_status.setText(f"Ошибка: {msg}")
        self.cancel_btn.setEnabled(True)
        self.next_btn.setText("Повторить")
        self.next_btn.setEnabled(True)
        self.next_btn.clicked.disconnect()
        self.next_btn.clicked.connect(self._retry_install)

    def _retry_install(self):
        try:
            self.next_btn.clicked.disconnect()
        except Exception:
            pass
        self.next_btn.clicked.connect(self._go_next)
        self.stack.setCurrentIndex(1)
        self._update_nav()

    def _run_app(self):
        try:
            exe = Path(self._installed_exe) if self._installed_exe else None
            if exe and exe.exists():
                subprocess.Popen([str(exe), "--show-welcome"], shell=False)
        except Exception:
            pass


def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SNERK503.ASCIIStudioInstaller")
    except Exception:
        pass
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--auto-install", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--shortcut", default="1")
    parser.add_argument("--run-after", default="1")
    args, _ = parser.parse_known_args()

    auto_cfg = None
    if args.auto_install:
        auto_cfg = {
            "out": args.out,
            "shortcut": args.shortcut,
            "run_after": args.run_after,
        }

    app = QApplication(sys.argv)
    w = InstallerWindow(auto_install=auto_cfg)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
