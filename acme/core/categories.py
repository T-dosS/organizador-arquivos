"""Categorias de arquivo por extensão."""

from __future__ import annotations

import os

CATEGORIES: dict[str, tuple[str, ...]] = {
    "PDFs": (".pdf",),
    "Excel": (".xlsx", ".xlsm", ".xlsb", ".xls", ".csv"),
    "Word": (".docx", ".docm", ".doc", ".rtf", ".odt"),
    "PowerPoint": (".pptx", ".pptm", ".ppt", ".odp"),
    "Imagens": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".svg"),
    "Vídeos": (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm"),
    "Arquivos compactados": (".zip", ".rar", ".7z", ".tar", ".gz"),
}
OTHER = "Outros"

_BY_EXTENSION = {ext: name for name, exts in CATEGORIES.items() for ext in exts}


def category_for(filename: str) -> str:
    return _BY_EXTENSION.get(os.path.splitext(filename)[1].lower(), OTHER)
