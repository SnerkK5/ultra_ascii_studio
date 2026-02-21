# main.py
import sys
from PySide6.QtWidgets import QApplication
from ui_main import MainWindow
from settings_dialog import SettingsManager

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ASCII Studio – SNERK503")

    # загрузка настроек
    settings = SettingsManager()
    settings.load_settings()

    # запуск окна
    win = MainWindow(settings)
    win.show()

    exit_code = app.exec()

    # сохраним настройки при выходе
    settings.save_settings()

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
