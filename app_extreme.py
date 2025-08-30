# app_extreme.py
# Interface PyQt5 refinada para deduplicador com presets customizáveis, cancelamento, ProcessPool toggle.

import sys
import threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QLabel, QComboBox, QProgressBar, QCheckBox, QMessageBox, QLineEdit
)
from PyQt5.QtCore import pyqtSignal, QObject

import core_extreme as core

class Worker(QObject):
    finished = pyqtSignal(list, str)
    progress = pyqtSignal(int)

    def __init__(self, directory, algoritmo, criterio, exclusao, emitir_relatorio, flags, cancel_flag):
        super().__init__()
        self.directory = directory
        self.algoritmo = algoritmo
        self.criterio = criterio
        self.exclusao = exclusao
        self.emitir_relatorio = emitir_relatorio
        self.flags = flags
        self.cancel_flag = cancel_flag

    def run(self):
        try:
            duplicatas = core.encontrar_duplicatas(
                self.directory, self.algoritmo, self.criterio, self.exclusao,
                self.emitir_relatorio, cancel_flag=self.cancel_flag, flags=self.flags
            )
            self.finished.emit(duplicatas, "Concluído")
        except Exception as e:
            self.finished.emit([], f"Erro: {str(e)}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Deduper Extreme")
        self.cancel_flag = threading.Event()

        layout = QVBoxLayout()

        self.dir_label = QLabel("Diretório:")
        self.dir_input = QLineEdit()
        browse_btn = QPushButton("Selecionar")
        browse_btn.clicked.connect(self.select_directory)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.dir_input)
        hlayout.addWidget(browse_btn)
        layout.addWidget(self.dir_label)
        layout.addLayout(hlayout)

        self.alg_combo = QComboBox()
        self.alg_combo.addItems(["md5", "sha1", "sha256", "xxh32", "xxh64"])
        layout.addWidget(QLabel("Algoritmo:"))
        layout.addWidget(self.alg_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Easy", "Medium", "Advanced"])
        layout.addWidget(QLabel("Modo:"))
        layout.addWidget(self.mode_combo)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.start_btn = QPushButton("Iniciar")
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.cancel)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.cancel_btn)

        self.save_preset_btn = QPushButton("Salvar Preset")
        self.save_preset_btn.clicked.connect(self.save_preset)
        self.delete_preset_btn = QPushButton("Deletar Preset")
        self.delete_preset_btn.clicked.connect(self.delete_preset)
        layout.addWidget(self.save_preset_btn)
        layout.addWidget(self.delete_preset_btn)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def select_directory(self):
        dir_ = QFileDialog.getExistingDirectory(self, "Selecionar Diretório")
        if dir_:
            self.dir_input.setText(dir_)

    def start(self):
        self.cancel_flag.clear()
        directory = self.dir_input.text()
        algoritmo = self.alg_combo.currentText()
        flags = {"FAST_HASH": self.mode_combo.currentText() == "Easy", "PROCESS_POOL": self.mode_combo.currentText() == "Advanced"}
        self.worker = Worker(directory, algoritmo, "Mais Novo", "nao_excluir", True, flags, self.cancel_flag)
        threading.Thread(target=self.worker.run, daemon=True).start()

    def cancel(self):
        self.cancel_flag.set()
        QMessageBox.information(self, "Cancelado", "Operação cancelada.")

    def save_preset(self):
        config = {
            "algoritmo": self.alg_combo.currentText(),
            "mode": self.mode_combo.currentText()
        }
        core.save_preset("CustomPreset", config)
        QMessageBox.information(self, "Preset", "Preset salvo.")

    def delete_preset(self):
        core.delete_preset("CustomPreset")
        QMessageBox.information(self, "Preset", "Preset deletado.")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
