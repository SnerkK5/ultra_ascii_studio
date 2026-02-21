from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QHBoxLayout

class ExportProgressDialog(QDialog):
    def __init__(self, parent, worker):
        super().__init__(parent)
        self.setWindowTitle('Export')
        self.worker = worker
        self.layout = QVBoxLayout(self)
        self.label = QLabel('Rendering...')
        self.pbar = QProgressBar(self)
        self.pbar.setRange(0, 100)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.pbar)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(self.cancel_btn)
        self.layout.addLayout(h)
        worker.progress.connect(self._on_progress)
        worker.finished_path.connect(self._on_finished)
        worker.error.connect(self._on_error)
        try:
            worker.started.connect(lambda: self.label.setText('Rendering...'))
            worker.stopped.connect(lambda: self.label.setText(self.label.text()))
        except Exception:
            pass

    def _on_progress(self, v):
        self.pbar.setValue(v)

    def _on_finished(self, path):
        self.label.setText('Finished: ' + path)
        self.cancel_btn.setText('Close')

    def _on_error(self, msg):
        self.label.setText('Error: ' + msg)
        self.cancel_btn.setText('Close')

    def _on_cancel(self):
        try:
            self.worker.cancel()
        except Exception:
            pass
        self.accept()