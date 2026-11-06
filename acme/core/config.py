"""Pasta de dados do aplicativo (histórico e regras), fora do OneDrive."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("ACME_DATA_DIR")
    if override:
        base = Path(override)
    elif os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"]) / "organizador_acme"
    else:
        base = Path.home() / ".organizador_acme"
    base.mkdir(parents=True, exist_ok=True)
    return base
