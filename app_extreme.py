import os
import json
import sqlite3
import hashlib
import shutil
import time
import concurrent.futures
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QComboBox, QCheckBox,
    QSpinBox, QPlainTextEdit, QProgressBar, QTabWidget,
    QGroupBox, QFormLayout, QStackedWidget, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import openpyxl


# ==============================
# CORE (deduplicação)
# ==============================
def calcular_hash_arquivo(arquivo, algoritmo="md5", block_size=65536):
    h = hashlib.new(algoritmo)
    with open(arquivo, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
    return h.hexdigest()


def comparar_arquivos_byte_a_byte(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            ba = fa.read(65536)
            bb = fb.read(65536)
            if ba != bb:
                return False
            if not ba:
                break
    return True


def gerar_relatorio_xlsx(path, duplicatas, algoritmo):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Duplicatas"
    ws.append(["Arquivo", "Original", "Critério", "Hash"])
    for dup in duplicatas:
        ws.append(list(dup))
    wb.save(path)


def executar_dedup(config, progress_callback=None, log_callback=None, cancel_flag=None):
    pasta = Path(config["diretorio"])
    algoritmo = config["algoritmo"]
    criterio = config["criterio"]
    exclusao = config["exclusao"]
    emitir_relatorio = config.get("emitir_relatorio", False)
    block_size = config.get("block_size", 65536)
    advanced_flags = config.get("flags", {})

    arquivos_por_hash = {}
    duplicatas = []
    total = sum(1 for _ in pasta.rglob("*") if _.is_file())
    atual = 0

    for arquivo in pasta.rglob("*"):
        if cancel_flag and cancel_flag():
            if log_callback: log_callback("Processo cancelado.")
            return duplicatas
        if arquivo.is_file():
            try:
                h = calcular_hash_arquivo(str(arquivo), algoritmo, block_size)
                if h in arquivos_por_hash:
                    orig = arquivos_por_hash[h]
                    if advanced_flags.get("byte_compare", False):
                        if not comparar_arquivos_byte_a_byte(str(arquivo), str(orig)):
                            continue
                    duplicatas.append((str(arquivo), str(orig), criterio, h))
                    if exclusao == "Excluir permanentemente":
                        os.remove(arquivo)
                    elif exclusao == "Excluir para a Lixeira":
                        try:
                            import send2trash
                            send2trash.send2trash(str(arquivo))
                        except:
                            os.remove(arquivo)
                else:
                    arquivos_por_hash[h] = arquivo
            except Exception as e:
                if log_callback: log_callback(f"Erro: {e}")
        atual += 1
        if progress_callback:
            progress_callback(atual, total)

    if emitir_relatorio:
        out = pasta / f"relatorio-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
        gerar_relatorio_xlsx(out, duplicatas, algoritmo)
        if log_callback: log_callback(f"Relatório salvo em {out}")

    return duplicatas


# ==============================
# THREAD (para UI responsiva)
# ==============================
class DedupThread(QThread):
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str)
    done = pyqtSignal(list)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        dups = executar_dedup(
            self.config,
            progress_callback=lambda a, t: self.progress.emit(a, t),
            log_callback=lambda m: self.log.emit(m),
            cancel_flag=lambda: self._cancel
        )
        self.done.emit(dups)


# ==============================
# UI (PyQt6)
# ==============================
class DedupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Deduper Avançado")
        self.resize(900, 700)
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2f;
                color: #f0f0f0;
                font-size: 14px;
            }
            QPushButton {
                background-color: #3b3b5c;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #50507a;
            }
            QProgressBar {
                height: 20px;
                border-radius: 5px;
                text-align: center;
            }
        """)

        layout = QVBoxLayout()

        # modo
        self.mode_select = QComboBox()
        self.mode_select.addItems(["Easy", "Medium", "Advanced"])
        self.mode_select.currentIndexChanged.connect(self.change_mode)
        layout.addWidget(QLabel("Selecione o Modo:"))
        layout.addWidget(self.mode_select)

        # stack
        self.stack = QStackedWidget()
        self.easy = self.build_easy()
        self.medium = self.build_medium()
        self.advanced = self.build_advanced()
        self.stack.addWidget(self.easy)
        self.stack.addWidget(self.medium)
        self.stack.addWidget(self.advanced)
        layout.addWidget(self.stack)

        # logs
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(QLabel("Logs:"))
        layout.addWidget(self.logs)

        # progresso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.setLayout(layout)
        self.thread = None

    def build_easy(self):
        box = QGroupBox("Easy Mode")
        form = QFormLayout()
        self.dir_easy = QLineEdit()
        btn = QPushButton("Escolher Pasta")
        btn.clicked.connect(lambda: self.choose_folder(self.dir_easy))
        hb = QHBoxLayout()
        hb.addWidget(self.dir_easy)
        hb.addWidget(btn)
        form.addRow("Diretório:", hb)
        self.alg_easy = QComboBox()
        self.alg_easy.addItems(["md5", "sha1", "sha256"])
        form.addRow("Algoritmo:", self.alg_easy)
        self.excl_easy = QComboBox()
        self.excl_easy.addItems(["Excluir para a Lixeira", "Manter Ambos"])
        form.addRow("Exclusão:", self.excl_easy)
        run = QPushButton("Iniciar")
        run.clicked.connect(self.run_easy)
        form.addRow(run)
        box.setLayout(form)
        return box

    def build_medium(self):
        box = QGroupBox("Medium Mode")
        form = QFormLayout()
        self.dir_med = QLineEdit()
        btn = QPushButton("Escolher Pasta")
        btn.clicked.connect(lambda: self.choose_folder(self.dir_med))
        hb = QHBoxLayout()
        hb.addWidget(self.dir_med)
        hb.addWidget(btn)
        form.addRow("Diretório:", hb)
        self.alg_med = QComboBox()
        self.alg_med.addItems(sorted(hashlib.algorithms_available))
        form.addRow("Algoritmo:", self.alg_med)
        self.excl_med = QComboBox()
        self.excl_med.addItems(["Excluir permanentemente", "Excluir para a Lixeira", "Manter Ambos"])
        form.addRow("Exclusão:", self.excl_med)
        self.crit_med = QComboBox()
        self.crit_med.addItems(["Mais Novo", "Mais Antigo"])
        form.addRow("Critério:", self.crit_med)
        self.chk_rel_med = QCheckBox("Emitir Relatório XLSX")
        form.addRow(self.chk_rel_med)
        run = QPushButton("Iniciar")
        run.clicked.connect(self.run_medium)
        form.addRow(run)
        box.setLayout(form)
        return box

    def build_advanced(self):
        box = QGroupBox("Advanced Mode")
        form = QFormLayout()
        self.dir_adv = QLineEdit()
        btn = QPushButton("Escolher Pasta")
        btn.clicked.connect(lambda: self.choose_folder(self.dir_adv))
        hb = QHBoxLayout()
        hb.addWidget(self.dir_adv)
        hb.addWidget(btn)
        form.addRow("Diretório:", hb)
        self.alg_adv = QComboBox()
        self.alg_adv.addItems(sorted(hashlib.algorithms_available))
        form.addRow("Algoritmo:", self.alg_adv)
        self.excl_adv = QComboBox()
        self.excl_adv.addItems(["Excluir permanentemente", "Excluir para a Lixeira", "Manter Ambos"])
        form.addRow("Exclusão:", self.excl_adv)
        self.crit_adv = QComboBox()
        self.crit_adv.addItems(["Mais Novo", "Mais Antigo"])
        form.addRow("Critério:", self.crit_adv)
        self.chk_rel_adv = QCheckBox("Emitir Relatório XLSX")
        form.addRow(self.chk_rel_adv)
        self.chk_byte = QCheckBox("Byte-Compare após Hash")
        form.addRow(self.chk_byte)
        self.spin_block = QSpinBox()
        self.spin_block.setRange(1024, 10**7)
        self.spin_block.setValue(65536)
        form.addRow("Tamanho Bloco (bytes):", self.spin_block)
        run = QPushButton("Iniciar")
        run.clicked.connect(self.run_advanced)
        form.addRow(run)
        box.setLayout(form)
        return box

    def choose_folder(self, widget):
        d = QFileDialog.getExistingDirectory(self, "Selecione um diretório")
        if d:
            widget.setText(d)

    def run_easy(self):
        cfg = dict(
            diretorio=self.dir_easy.text(),
            algoritmo=self.alg_easy.currentText(),
            exclusao=self.excl_easy.currentText(),
            criterio="Mais Novo",
            emitir_relatorio=False,
            block_size=65536,
            flags={}
        )
        self.start_thread(cfg)

    def run_medium(self):
        cfg = dict(
            diretorio=self.dir_med.text(),
            algoritmo=self.alg_med.currentText(),
            exclusao=self.excl_med.currentText(),
            criterio=self.crit_med.currentText(),
            emitir_relatorio=self.chk_rel_med.isChecked(),
            block_size=65536,
            flags={}
        )
        self.start_thread(cfg)

    def run_advanced(self):
        cfg = dict(
            diretorio=self.dir_adv.text(),
            algoritmo=self.alg_adv.currentText(),
            exclusao=self.excl_adv.currentText(),
            criterio=self.crit_adv.currentText(),
            emitir_relatorio=self.chk_rel_adv.isChecked(),
            block_size=self.spin_block.value(),
            flags=dict(
                byte_compare=self.chk_byte.isChecked()
            )
        )
        self.start_thread(cfg)

    def start_thread(self, config):
        if not config["diretorio"]:
            QMessageBox.warning(self, "Erro", "Escolha um diretório válido.")
            return
        self.logs.clear()
        self.progress.setValue(0)
        self.thread = DedupThread(config)
        self.thread.progress.connect(self.update_progress)
        self.thread.log.connect(self.add_log)
        self.thread.done.connect(self.done_process)
        self.thread.start()

    def update_progress(self, atual, total):
        val = int((atual/total)*100)
        self.progress.setValue(val)

    def add_log(self, msg):
        self.logs.appendPlainText(msg)

    def done_process(self, dups):
        self.add_log(f"Processo concluído. {len(dups)} duplicatas detectadas.")

    def change_mode(self, idx):
        self.stack.setCurrentIndex(idx)


if __name__ == "__main__":
    app = QApplication([])
    w = DedupApp()
    w.show()
    app.exec()
