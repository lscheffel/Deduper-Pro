# app_extreme.py
# UI em PyQt para o deduplicador extremo

import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QVBoxLayout,
    QPushButton, QLabel, QProgressBar, QComboBox, QTextEdit, QLineEdit
)
from PyQt5.QtCore import QThread, pyqtSignal
from core_extreme import processar_diretorio, CancelFlag

class Worker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)
    log = pyqtSignal(str)

    def __init__(self, diretorio, modo="easy", cancel_flag=None):
        super().__init__()
        self.diretorio = diretorio
        self.modo = modo
        self.cancel_flag = cancel_flag

    def run(self):
        self.log.emit(f"Iniciando deduplicação no modo {self.modo}...")
        if self.modo == "easy":
            result = processar_diretorio(self.diretorio, cancel_flag=self.cancel_flag)
        elif self.modo == "medium":
            result = processar_diretorio(self.diretorio, throttle_io=True, cancel_flag=self.cancel_flag)
        else:
            result = processar_diretorio(self.diretorio, throttle_io=True, cancel_flag=self.cancel_flag, use_sqlite=True)
        self.finished.emit(result)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Deduper Extreme")
        self.resize(800, 600)
        self.cancel_flag = CancelFlag()
        self.worker = None

        layout = QVBoxLayout()

        self.label = QLabel("Selecione o diretório:")
        layout.addWidget(self.label)

        self.input = QLineEdit()
        layout.addWidget(self.input)

        self.browse = QPushButton("Procurar")
        self.browse.clicked.connect(self.selecionar_diretorio)
        layout.addWidget(self.browse)

        self.mode_box = QComboBox()
        self.mode_box.addItems(["easy", "medium", "advanced"])
        layout.addWidget(QLabel("Modo:"))
        layout.addWidget(self.mode_box)

        self.start_btn = QPushButton("Iniciar")
        self.start_btn.clicked.connect(self.iniciar)
        layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.cancelar)
        layout.addWidget(self.cancel_btn)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def selecionar_diretorio(self):
        dir_ = QFileDialog.getExistingDirectory(self, "Selecione o diretório")
        if dir_:
            self.input.setText(dir_)

    def iniciar(self):
        diretorio = self.input.text()
        if not Path(diretorio).is_dir():
            self.log_box.append("Diretório inválido!")
            return
        modo = self.mode_box.currentText()
        self.worker = Worker(diretorio, modo=modo, cancel_flag=self.cancel_flag)
        self.worker.log.connect(self.log_box.append)
        self.worker.finished.connect(self.finalizado)
        self.worker.start()

    def cancelar(self):
        self.cancel_flag.cancel()
        self.log_box.append("Cancelamento solicitado.")

    def finalizado(self, result):
        self.log_box.append(f"Processo finalizado: {result}")
        self.progress.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
