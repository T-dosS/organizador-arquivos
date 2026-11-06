"""Testes de fumaça da interface: analisar, organizar com prévia, confirmar e desfazer."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QCoreApplication, QElapsedTimer

from acme.ui.main_window import MainWindow


def wait_until(condition, ms=10_000):
    timer = QElapsedTimer()
    timer.start()
    while not condition() and timer.elapsed() < ms:
        QCoreApplication.processEvents()
    assert condition()


@pytest.fixture
def window():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    yield w
    w.close()
    app.processEvents()


def test_janela_analisa_pasta(tmp_path, window):
    (tmp_path / "a.xlsx").write_bytes(b"conteudo" * 100)
    (tmp_path / "b.xlsx").write_bytes(b"conteudo" * 100)
    (tmp_path / "c.pdf").write_bytes(b"unico")
    assert window.set_folder(str(tmp_path))
    page = window.duplicates
    page.start_analysis()
    wait_until(lambda: page.result is not None)
    assert page.ind_files.value.text() == "3"
    assert page.ind_dups.value.text() == "2"
    assert page.dup_tree.topLevelItemCount() == 1
    assert page.export_button.isEnabled()
    page.thread.wait(2000)


def test_organizar_previa_confirmar_desfazer(tmp_path, window, caixas_de_dialogo_nao_bloqueiam):
    (tmp_path / "a.pdf").write_bytes(b"1")
    (tmp_path / "b.xlsx").write_bytes(b"2")
    assert window.set_folder(str(tmp_path))
    page = window.organize
    assert not page.confirm_button.isEnabled()  # sem prévia não há confirmação
    page.start_preview()
    wait_until(lambda: page.plan is not None)
    page.thread.wait(2000)
    assert page.preview.rowCount() == 2
    assert sorted(os.listdir(tmp_path)) == ["a.pdf", "b.xlsx"]  # a prévia não move nada
    assert page.confirm_button.isEnabled()
    page.confirm()
    wait_until(lambda: (tmp_path / "PDFs" / "a.pdf").exists() and page.plan is None)
    page.thread.wait(2000)
    assert (tmp_path / "Excel" / "b.xlsx").exists()

    history = window.history
    history.refresh()
    assert history.ops_table.rowCount() == 1
    history.ops_table.selectRow(0)
    assert history.moves_table.rowCount() == 2
    history.undo()
    wait_until(lambda: (tmp_path / "a.pdf").exists() and (tmp_path / "b.xlsx").exists())
    history.thread.wait(2000)
    QCoreApplication.processEvents()
    assert sorted(os.listdir(tmp_path)) == ["a.pdf", "b.xlsx"]


def test_pasta_protegida_recusada(window, caixas_de_dialogo_nao_bloqueiam):
    assert not window.set_folder(os.path.abspath(os.sep))
    assert caixas_de_dialogo_nao_bloqueiam and "Pasta não permitida" in caixas_de_dialogo_nao_bloqueiam[0]
