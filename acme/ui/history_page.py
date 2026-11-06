"""Página Histórico: operações feitas, detalhes de cada movimento e Desfazer."""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from acme.core import history as h
from acme.core.executor import UndoResult, undo_operation
from acme.core.planner import MODE_NAMES

from .worker import TaskWorker, start_in_thread


def _date(iso: str | None) -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setAlternatingRowColors(True)
    return table


class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.operations: list[h.Operation] = []
        self.thread: QThread | None = None
        self.worker: TaskWorker | None = None
        self._build()
        hist = h.History()
        try:
            hist.mark_interrupted()  # operações que ficaram pela metade (programa fechado, queda de energia)
        finally:
            hist.close()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        title = QLabel("Histórico")
        title.setObjectName("title")
        subtitle = QLabel("Toda organização fica registrada. O Desfazer só devolve um arquivo se ele não foi alterado "
                          "depois e se o local original continua livre.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        buttons = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        refresh = QPushButton("Atualizar")
        refresh.clicked.connect(self.refresh)
        self.undo_button = QPushButton("Desfazer operação selecionada")
        self.undo_button.setObjectName("primary")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo)
        buttons.addWidget(self.status, 1)
        buttons.addWidget(refresh)
        buttons.addWidget(self.undo_button)
        root.addLayout(buttons)

        self.ops_table = _table(["Data", "Pasta", "Modo", "Movidos", "Erros", "Situação", "Usuário"])
        self.ops_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ops_table.itemSelectionChanged.connect(self._show_moves)
        self.moves_table = _table(["Arquivo", "De", "Para", "Situação", "Observação", "Quando"])
        for col in (1, 2, 4):
            self.moves_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.ops_table)
        splitter.addWidget(self.moves_table)
        splitter.setSizes([260, 340])
        root.addWidget(splitter, 1)

    def refresh(self) -> None:
        hist = h.History()
        try:
            self.operations = hist.operations()
        finally:
            hist.close()
        self.ops_table.setRowCount(len(self.operations))
        for row, op in enumerate(self.operations):
            cells = (_date(op.started), op.root, MODE_NAMES.get(op.mode, op.mode), f"{op.moved:n}",
                     f"{op.errors:n}", op.status, op.user)
            for col, text in enumerate(cells):
                self.ops_table.setItem(row, col, QTableWidgetItem(text))
        self.ops_table.resizeColumnToContents(0)
        self.moves_table.setRowCount(0)
        self.undo_button.setEnabled(False)
        if not self.operations:
            self.status.setText("Nenhuma organização feita ainda.")
        else:
            self.status.setText("Selecione uma operação para ver os detalhes.")

    def _selected(self) -> h.Operation | None:
        rows = self.ops_table.selectionModel().selectedRows()
        return self.operations[rows[0].row()] if rows else None

    def _show_moves(self) -> None:
        op = self._selected()
        if op is None:
            return
        hist = h.History()
        try:
            moves = hist.moves(op.id)
        finally:
            hist.close()
        self.moves_table.setRowCount(len(moves))
        for row, m in enumerate(moves):
            cells = (os.path.basename(m.source), os.path.relpath(os.path.dirname(m.source), op.root),
                     os.path.relpath(m.destination, op.root), m.status, m.error or "", _date(m.when))
            for col, text in enumerate(cells):
                self.moves_table.setItem(row, col, QTableWidgetItem("(pasta principal)" if text == "." else text))
        self.moves_table.resizeColumnToContents(0)
        self.undo_button.setEnabled(op.status not in (h.UNDONE, h.RUNNING) and op.moved > 0)

    def undo(self) -> None:
        op = self._selected()
        if op is None:
            return
        answer = QMessageBox.question(
            self, "Desfazer organização",
            f"Devolver {op.moved:n} arquivos aos locais originais em:\n{op.root}\n\n"
            "Arquivos alterados depois da organização, ou cujo local original já esteja ocupado, ficam onde estão.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return

        def run(cancel, progress):
            hist = h.History()
            try:
                return undo_operation(hist, op.id, progress)
            finally:
                hist.close()

        self.undo_button.setEnabled(False)
        self.status.setText("Desfazendo...")
        self.worker = TaskWorker(run)
        self.thread = start_in_thread(self, self.worker, self._undone, self._failed, self._failed)

    def _undone(self, result: UndoResult) -> None:
        self.refresh()
        text = f"{result.restored:n} arquivos devolvidos ao local original."
        if result.blocked:
            text += f" {len(result.blocked):n} ficaram onde estão (veja a coluna Observação)."
        self.status.setText(text)

    def _failed(self, message: str = "Operação cancelada.") -> None:
        self.refresh()
        if message:
            QMessageBox.warning(self, "Desfazer", message)

    def stop(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(5000)

