"""Exportação do resultado da análise para CSV (abre direto no Excel)."""

from __future__ import annotations

import csv
import os
from datetime import datetime

from .duplicates import DuplicateReport


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "bytes":
                return f"{int(size)} bytes"
            return f"{size:,.1f} {unit}".replace(",", "X").replace(".", ",").replace("X", ".")
        size /= 1024
    return f"{size:.1f} TB"


def format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y %H:%M")


def export_csv(report: DuplicateReport, destination: str) -> None:
    """Grava um CSV com ponto e vírgula e BOM UTF-8, o formato que o Excel em português abre corretamente."""
    if os.path.exists(destination):
        raise FileExistsError(f"O arquivo já existe e não será sobrescrito: {destination}")
    with open(destination, "x", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            ["Grupo", "Classificação", "Nome", "Localização", "Tamanho (bytes)", "Modificado em",
             "Cópias no grupo", "Espaço potencialmente recuperável (bytes)", "SHA-256", "Confirmado byte a byte"]
        )
        for number, group in enumerate(report.groups, start=1):
            for entry in group.files:
                writer.writerow(
                    [number, group.classification, entry.name, entry.folder, entry.size, format_time(entry.mtime),
                     group.copies, group.recoverable_bytes, group.sha256, "Sim" if group.byte_verified else "Não"]
                )
