"""Página Organizar: escolher o modo, ver a prévia e só então confirmar."""

from __future__ import annotations

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from acme.core import planner as pl
from acme.core.executor import ExecutionResult, execute_plan
from acme.core.history import History
from acme.core.paths import shared_location_warning

from .duplicates_page import Indicator
from .worker import TaskWorker, start_in_thread

PREVIEW_LIMIT = 5000  # linhas mostradas na prévia; o plano completo é executado mesmo assim


class OrganizePage(QWidget):
    organized = Signal()

    def __init__(self):
        super().__init__()
        self.folder: str | None = None
        self.plan: pl.Plan | None = None
        self.thread: QThread | None = None
        self.worker: TaskWorker | None = None
        self._build()
        self._load_rules()
        self._mode_changed()

    # ---------- construção da tela ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        title = QLabel("Organizar arquivos")
        title.setObjectName("title")
        subtitle = QLabel("Nada é movido antes da sua confirmação. Nenhum arquivo é excluído ou sobrescrito, "
                          "e toda organização pode ser desfeita no Histórico.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        options = QHBoxLayout()
        self.mode = QComboBox()
        for key, name in pl.MODE_NAMES.items():
            self.mode.addItem(name, key)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.date_kind = QComboBox()
        self.date_kind.addItem("Data de modificação", pl.DATE_MODIFIED)
        self.date_kind.addItem("Data de criação", pl.DATE_CREATED)
        self.date_kind.currentIndexChanged.connect(self._invalidate)
        self.subfolders = QCheckBox("Incluir arquivos das subpastas")
        self.subfolders.setToolTip("Desmarcado: organiza só os arquivos soltos na pasta escolhida.")
        self.subfolders.toggled.connect(self._invalidate)
        self.preview_button = QPushButton("Gerar prévia")
        self.preview_button.clicked.connect(self.start_preview)
        self.confirm_button = QPushButton("Confirmar organização")
        self.confirm_button.setObjectName("primary")
        self.confirm_button.clicked.connect(self.confirm)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        options.addWidget(QLabel("Modo:"))
        options.addWidget(self.mode)
        options.addWidget(self.date_kind)
        options.addWidget(self.subfolders)
        options.addStretch(1)
        options.addWidget(self.preview_button)
        options.addWidget(self.confirm_button)
        options.addWidget(self.cancel_button)
        root.addLayout(options)

        self.rules_box = QFrame()
        self.rules_box.setObjectName("indicator")
        rules_layout = QVBoxLayout(self.rules_box)
        rules_layout.setContentsMargins(14, 10, 14, 10)
        rules_title = QLabel("REGRAS: se o nome do arquivo contém a palavra, vai para a pasta (maiúsculas e acentos "
                             "não importam; vale a primeira regra que combinar)")
        rules_title.setObjectName("indicatorCaption")
        rules_title.setWordWrap(True)
        self.rules_table = QTableWidget(0, 2)
        self.rules_table.setHorizontalHeaderLabels(["Palavra no nome do arquivo", "Pasta de destino (ex.: RH/Admissões)"])
        self.rules_table.verticalHeader().setVisible(False)
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rules_table.setMaximumHeight(130)
        self.rules_table.itemChanged.connect(self._invalidate)
        rules_buttons = QHBoxLayout()
        add = QPushButton("Adicionar regra")
        add.clicked.connect(lambda: self._add_rule_row("", ""))
        remove = QPushButton("Remover regra")
        remove.clicked.connect(self._remove_rule_row)
        save = QPushButton("Salvar regras")
        save.clicked.connect(self._save_rules)
        rules_buttons.addWidget(add)
        rules_buttons.addWidget(remove)
        rules_buttons.addStretch(1)
        rules_buttons.addWidget(save)
        rules_layout.addWidget(rules_title)
        rules_layout.addWidget(self.rules_table)
        rules_layout.addLayout(rules_buttons)
        root.addWidget(self.rules_box)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.status = QLabel("Selecione uma pasta e gere a prévia.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        root.addWidget(self.progress)
        root.addWidget(self.status)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.ind_move = Indicator("SERÃO MOVIDOS")
        self.ind_stay = Indicator("PERMANECEM NO LUGAR")
        self.ind_conflicts = Indicator("CONFLITOS DE NOME")
        self.ind_skipped = Indicator("NÃO INCLUÍDOS")
        for col, ind in enumerate((self.ind_move, self.ind_stay, self.ind_conflicts, self.ind_skipped)):
            grid.addWidget(ind, 0, col)
        root.addLayout(grid)

        self.preview = QTableWidget(0, 4)
        self.preview.setHorizontalHeaderLabels(["Arquivo", "Local atual", "Novo local", "Observação"])
        self.preview.verticalHeader().setVisible(False)
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.setAlternatingRowColors(True)
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        root.addWidget(self.preview, 1)
        self._set_running(False)

    # ---------- regras ----------

    def _load_rules(self) -> None:
        self.rules_table.blockSignals(True)
        for rule in pl.load_rules():
            self._add_rule_row(rule.keyword, rule.destination)
        self.rules_table.blockSignals(False)

    def _add_rule_row(self, keyword: str, destination: str) -> None:
        row = self.rules_table.rowCount()
        self.rules_table.insertRow(row)
        self.rules_table.setItem(row, 0, QTableWidgetItem(keyword))
        self.rules_table.setItem(row, 1, QTableWidgetItem(destination))

    def _remove_rule_row(self) -> None:
        row = self.rules_table.currentRow()
        if row >= 0:
            self.rules_table.removeRow(row)
            self._invalidate()

    def rules(self) -> list[pl.Rule]:
        """Regras da tabela; linhas vazias são ignoradas e destinos inválidos geram ValueError."""
        rules = []
        for row in range(self.rules_table.rowCount()):
            keyword = (self.rules_table.item(row, 0) or QTableWidgetItem("")).text().strip()
            destination = (self.rules_table.item(row, 1) or QTableWidgetItem("")).text().strip()
            if not keyword and not destination:
                continue
            if not keyword:
                raise ValueError(f"Regra {row + 1}: informe a palavra.")
            try:
                pl.validate_destination(destination)
            except ValueError as exc:
                raise ValueError(f"Regra {row + 1} ({keyword}): {exc}") from None
            rules.append(pl.Rule(keyword, destination))
        return rules

    def _save_rules(self) -> None:
        try:
            pl.save_rules(self.rules())
        except ValueError as exc:
            QMessageBox.warning(self, "Regra inválida", str(exc))
            return
        self.status.setText("Regras salvas.")

    # ---------- prévia e execução ----------

    def set_folder(self, folder: str | None) -> None:
        self.folder = folder
        self._invalidate()

    def _mode_changed(self) -> None:
        mode = self.mode.currentData()
        self.date_kind.setVisible(mode == pl.MODE_PERIOD)
        self.rules_box.setVisible(mode == pl.MODE_RULES)
        self._invalidate()

    def _invalidate(self, *_args) -> None:
        """Qualquer mudança de opção descarta a prévia: só se confirma o que foi visto."""
        self.plan = None
        self.preview.setRowCount(0)
        for ind in (self.ind_move, self.ind_stay, self.ind_conflicts, self.ind_skipped):
            ind.set("–")
        self._set_running(False)
        if self.folder:
            self.status.setText("Gere a prévia para ver o que vai mudar.")

    def start_preview(self) -> None:
        if not self.folder:
            return
        mode = self.mode.currentData()
        try:
            rules = self.rules() if mode == pl.MODE_RULES else None
        except ValueError as exc:
            QMessageBox.warning(self, "Regra inválida", str(exc))
            return
        if mode == pl.MODE_RULES and not rules:
            QMessageBox.warning(self, "Sem regras", "Adicione pelo menos uma regra.")
            return
        folder, subfolders, date_kind = self.folder, self.subfolders.isChecked(), self.date_kind.currentData()
        self._run(
            lambda cancel, progress: pl.build_plan(folder, mode, subfolders, date_kind, rules, cancel, progress),
            self._show_plan,
            "Montando a prévia...",
        )

    def _show_plan(self, plan: pl.Plan) -> None:
        self._set_running(False)
        self.plan = plan
        self.ind_move.set(f"{len(plan.moves):n}")
        self.ind_stay.set(f"{plan.unchanged:n}", "já no lugar ou sem regra")
        self.ind_conflicts.set(f"{plan.conflicts:n}", "recebem (2), (3)..." if plan.conflicts else "")
        self.ind_skipped.set(f"{len(plan.skipped):n}", "links, bloqueados, sem permissão" if plan.skipped else "")
        shown = plan.moves[:PREVIEW_LIMIT]
        self.preview.setRowCount(len(shown))
        for row, move in enumerate(shown):
            note = "Renomeado: o nome já existe no destino" if move.renamed else ""
            cells = (os.path.basename(move.source), self._relative(os.path.dirname(move.source)),
                     self._relative(move.destination), note)
            for col, text in enumerate(cells):
                self.preview.setItem(row, col, QTableWidgetItem(text))
        self.preview.resizeColumnToContents(0)
        extra = f" Mostrando os primeiros {PREVIEW_LIMIT:n}." if len(plan.moves) > PREVIEW_LIMIT else ""
        if plan.moves:
            self.status.setText(f"Prévia pronta: {len(plan.moves):n} arquivos serão movidos dentro de {plan.root}.{extra} "
                                "Revise e clique em Confirmar organização.")
        else:
            self.status.setText("Nada a organizar com essas opções.")
        self._set_running(False)

    def _relative(self, path: str) -> str:
        if self.plan is None:
            return path
        rel = os.path.relpath(path, self.plan.root)
        return "(pasta principal)" if rel == "." else rel

    def confirm(self) -> None:
        plan = self.plan
        if plan is None or not plan.moves:
            return
        text = (f"Mover {len(plan.moves):n} arquivos dentro de:\n{plan.root}\n\n"
                "Nenhum arquivo será excluído ou sobrescrito. Você poderá desfazer pelo Histórico.")
        warning = shared_location_warning(plan.root)
        if warning:
            text += f"\n\nAtenção: {warning}"
        answer = QMessageBox.question(self, "Confirmar organização", text, QMessageBox.Yes | QMessageBox.No,
                                      QMessageBox.No)
        if answer != QMessageBox.Yes:
            return

        def run(cancel, progress):
            hist = History()
            try:
                return execute_plan(plan, hist, cancel, progress)
            finally:
                hist.close()

        self._run(run, self._show_result, "Organizando...")

    def _show_result(self, result: ExecutionResult) -> None:
        self._set_running(False)
        self.plan = None
        self.confirm_button.setEnabled(False)
        parts = [f"{result.moved:n} arquivos movidos"]
        if result.renamed:
            parts.append(f"{result.renamed:n} renomeados para não sobrescrever")
        if result.failed:
            parts.append(f"{result.failed:n} não movidos (veja o motivo no Histórico)")
        prefix = "Organização interrompida: " if result.cancelled else "Organização concluída: "
        self.status.setText(prefix + ", ".join(parts) + ". Para reverter, use Histórico > Desfazer.")
        self.organized.emit()

    # ---------- execução em segundo plano ----------

    def _run(self, fn, on_done, message: str) -> None:
        self._set_running(True)
        self.progress.setRange(0, 0)
        self.status.setText(message)
        self.worker = TaskWorker(fn)
        self.thread = start_in_thread(self, self.worker, on_done, self._failed, self._cancelled, self._progress)

    def _progress(self, stage: str, done: int, total: int) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status.setText(f"{stage}: {done:n} de {total:n}")
        else:
            self.status.setText(f"{stage}: {done:n}")

    def _failed(self, message: str) -> None:
        self._set_running(False)
        self.status.setText("Não foi possível concluir.")
        QMessageBox.critical(self, "Erro", message)

    def _cancelled(self) -> None:
        self._set_running(False)
        self.status.setText("Cancelado.")

    def cancel(self) -> None:
        if self.worker is not None and self.thread is not None and self.thread.isRunning():
            self.worker.cancel()
            self.status.setText("Cancelando...")

    def _set_running(self, running: bool) -> None:
        self.preview_button.setEnabled(not running and bool(self.folder))
        self.confirm_button.setEnabled(not running and self.plan is not None and bool(self.plan.moves))
        self.cancel_button.setEnabled(running)
        self.mode.setEnabled(not running)
        self.rules_box.setEnabled(not running)
        if not running:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)

    def stop(self) -> None:
        if self.worker is not None and self.thread is not None and self.thread.isRunning():
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(5000)
