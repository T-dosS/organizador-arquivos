"""Ajustes de teste para o Windows e para a interface.

No Windows o pytest cria pastas temporárias em %LOCALAPPDATA%\\Temp, que o app bloqueia de propósito
(pasta do sistema). Lá os testes usam uma pasta própria na pasta do usuário.
"""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

import pytest

from acme.core.paths import long_path

if sys.platform == "win32":

    @pytest.fixture
    def tmp_path():
        pasta = Path.home() / ".organizador_acme_testes" / uuid.uuid4().hex[:12]
        pasta.mkdir(parents=True)
        yield pasta
        shutil.rmtree(long_path(str(pasta)), ignore_errors=True)


@pytest.fixture(autouse=True)
def dados_do_app(tmp_path_factory, monkeypatch):
    """Histórico e regras de cada teste ficam numa pasta própria, nunca na do usuário."""
    monkeypatch.setenv("ACME_DATA_DIR", str(tmp_path_factory.mktemp("dados_app")))


@pytest.fixture(autouse=True)
def caixas_de_dialogo_nao_bloqueiam(monkeypatch):
    """Uma caixa de mensagem esperando clique travaria o gerar_executavel.ps1; nos testes ela só registra."""
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:
        yield []
        return
    mostradas: list[str] = []

    def registrar(resposta):
        def _caixa(parent, titulo, texto, *args, **kwargs):
            mostradas.append(f"{titulo}: {texto}")
            return resposta
        return staticmethod(_caixa)

    monkeypatch.setattr(QMessageBox, "critical", registrar(QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", registrar(QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", registrar(QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", registrar(QMessageBox.Yes))
    yield mostradas
