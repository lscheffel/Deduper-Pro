# core_extreme.py
# Núcleo avançado do deduplicador com cancelamento cooperativo, ProcessPool, relatório xlsx avançado e suporte a presets.

import os
import hashlib
import sqlite3
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import openpyxl
from openpyxl.styles import Font

try:
    import xxhash
except ImportError:
    xxhash = None

try:
    import send2trash
except ImportError:
    send2trash = None

DB_PATH = str(Path.home() / ".deduper_extreme_history.sqlite3")
PRESET_PATH = str(Path.home() / ".deduper_extreme_presets.json")

def calcular_hash_arquivo(path, algoritmo="md5", fast=False):
    h = None
    if xxhash and algoritmo.startswith("xxh"):
        h = xxhash.xxh64() if algoritmo == "xxh64" else xxhash.xxh32()
    else:
        h = hashlib.new(algoritmo)
    bloco = 65536
    with open(path, "rb") as f:
        while True:
            data = f.read(bloco)
            if not data:
                break
            h.update(data)
            if fast:
                break
    return h.hexdigest()

def _hash_worker(path, algoritmo, fast, cancel_flag):
    if cancel_flag.is_set():
        return None, None
    try:
        return path, calcular_hash_arquivo(path, algoritmo, fast=fast)
    except Exception:
        return path, None

def encontrar_duplicatas(diretorio, algoritmo="md5", criterio="Mais Novo", exclusao="nao_excluir",
                         emitir_relatorio=True, cancel_flag=None, flags=None):
    if flags is None:
        flags = {}

    arquivos_por_hash = {}
    duplicatas = []
    diretorio = Path(diretorio)
    data_hora = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    relatorio_path = diretorio / f"relatorio-{data_hora}.xlsx"

    all_files = [f for f in diretorio.rglob("*") if f.is_file()]
    if cancel_flag and cancel_flag.is_set():
        return []

    max_workers = os.cpu_count() or 4
    executor_cls = ProcessPoolExecutor if flags.get("PROCESS_POOL") else ThreadPoolExecutor

    with executor_cls(max_workers=max_workers) as executor:
        futures = {executor.submit(_hash_worker, str(f), algoritmo, flags.get("FAST_HASH", False), cancel_flag): f for f in all_files}
        for future in as_completed(futures):
            if cancel_flag and cancel_flag.is_set():
                break
            path, h = future.result()
            if h is None:
                continue
            if h in arquivos_por_hash:
                duplicatas.append((path, arquivos_por_hash[h], h))
            else:
                arquivos_por_hash[h] = path

    if cancel_flag and cancel_flag.is_set():
        return []

    if emitir_relatorio:
        gerar_relatorio(relatorio_path, duplicatas, arquivos_por_hash, algoritmo)

    return duplicatas

def gerar_relatorio(relatorio_path, duplicatas, arquivos_por_hash, algoritmo):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Relatório"
    headers = ["Arquivo 1", "Arquivo 2", "Hash", "Critério"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for dup in duplicatas:
        ws.append([dup[0], dup[1], dup[2], ""])

    ws.auto_filter.ref = "A1:D1"
    ws.freeze_panes = "A2"

    summary = wb.create_sheet("Resumo")
    summary.append(["Total Arquivos", len(arquivos_por_hash)])
    summary.append(["Total Duplicatas", len(duplicatas)])

    wb.save(str(relatorio_path))

def save_preset(name, config):
    presets = load_presets()
    presets[name] = config
    with open(PRESET_PATH, "w") as f:
        json.dump(presets, f, indent=2)

def load_presets():
    if os.path.exists(PRESET_PATH):
        with open(PRESET_PATH, "r") as f:
            return json.load(f)
    return {}

def delete_preset(name):
    presets = load_presets()
    if name in presets:
        del presets[name]
        with open(PRESET_PATH, "w") as f:
            json.dump(presets, f, indent=2)
