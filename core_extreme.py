# core_extreme.py
# Núcleo do deduplicador extremo com todas as melhorias

import os
import hashlib
import xxhash
import zlib
import time
import sqlite3
import threading
import concurrent.futures
from pathlib import Path
from datetime import datetime
import openpyxl

try:
    import send2trash
except ImportError:
    send2trash = None

class CancelFlag:
    def __init__(self):
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def is_set(self):
        return self._cancel.is_set()

def calcular_hash_multimodal(path, algoritmos=("md5", "sha1"), use_xxhash=True, use_crc=True):
    hashes = []
    try:
        with open(path, "rb") as f:
            data = f.read()
            for alg in algoritmos:
                h = hashlib.new(alg)
                h.update(data)
                hashes.append(h.hexdigest())
            if use_xxhash:
                hashes.append(xxhash.xxh64(data).hexdigest())
            if use_crc:
                hashes.append(str(zlib.crc32(data)))
    except Exception:
        return ["ERROR"]
    return hashes

def processar_diretorio(
    diretorio,
    algoritmo="md5",
    excluir_opcao="nao",
    criterio="novo",
    emitir_relatorio=True,
    relatorio_path=None,
    checkpoint_path=None,
    cancel_flag=None,
    throttle_io=False,
    compare_dir=None,
    use_sqlite=False,
):
    arquivos_por_hash = {}
    arquivos_duplicados = []
    relatorio_duplicatas = []

    diretorio = Path(diretorio)
    data_hora = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    if relatorio_path is None:
        relatorio_path = diretorio / f"relatorio-{data_hora}.xlsx"

    total_arquivos = sum(1 for _ in diretorio.rglob("*") if _.is_file())
    progresso_atual = 0
    inicio = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {}
        for arquivo in diretorio.rglob("*"):
            if cancel_flag and cancel_flag.is_set():
                break
            if arquivo.is_file():
                futures[executor.submit(calcular_hash_multimodal, arquivo)] = arquivo

        for fut in concurrent.futures.as_completed(futures):
            if cancel_flag and cancel_flag.is_set():
                break
            arquivo = futures[fut]
            try:
                hash_arquivo = tuple(fut.result())
            except Exception:
                hash_arquivo = ("ERROR",)
            if hash_arquivo in arquivos_por_hash:
                arquivos_duplicados.append((arquivo, hash_arquivo))
            else:
                arquivos_por_hash[hash_arquivo] = arquivo
            progresso_atual += 1
            if throttle_io and progresso_atual % 10 == 0:
                time.sleep(0.01)

    for arquivo, hash_arquivo in arquivos_duplicados:
        if not arquivo.exists():
            continue
        arquivo_original = arquivos_por_hash.get(hash_arquivo)
        if not arquivo_original:
            continue
        excluir = False
        if criterio == "novo":
            excluir = arquivo.stat().st_mtime > arquivo_original.stat().st_mtime
        elif criterio == "antigo":
            excluir = arquivo.stat().st_mtime < arquivo_original.stat().st_mtime

        if excluir:
            if excluir_opcao == "permanente":
                arquivo.unlink()
            elif excluir_opcao == "lixeira" and send2trash:
                send2trash.send2trash(str(arquivo))
            elif excluir_opcao == "renomear":
                arquivo.rename(f"{arquivo.stem}-dupe{arquivo.suffix}")
        relatorio_duplicatas.append((str(arquivo), str(arquivo_original), criterio, str(hash_arquivo)))

    if emitir_relatorio:
        gerar_relatorio(relatorio_path, relatorio_duplicatas)

    duracao = time.time() - inicio
    return {
        "duplicatas": len(relatorio_duplicatas),
        "total": total_arquivos,
        "duracao": duracao,
        "relatorio": str(relatorio_path) if emitir_relatorio else None,
    }

def gerar_relatorio(path, duplicatas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Duplicatas"
    ws.append(["Arquivo", "Original", "Critério", "Hash"])
    for arquivo, original, criterio, hash_arquivo in duplicatas:
        ws.append([arquivo, original, criterio, hash_arquivo])
    path = str(path)
    wb.save(path)
