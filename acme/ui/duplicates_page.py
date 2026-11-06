"""Página Duplicados exatos: analisar a pasta e revisar os grupos (somente leitura)."""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
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
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from acme.core.categories import category_for
from acme.core.report import export_csv, format_size, format_time

from .worker import AnalysisResult, AnalysisWorker

PATH_ROLE = Qt.UserRole + 1


class Indicator(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("indicator")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self.value = QLabel("–")
        self.value.setObjectName("indicatorValue")
        self.caption = QLabel(title)
        self.caption.setObjectName("indicatorCaption")
        self.detail = QLabel("")
        self.detail.setObjectName("indicatorDetail")
        layout.addWidget(self.value)
        layout.addWidget(self.caption)
        layout.addWidget(self.detail)

    def set(self, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)


class DuplicatesPage(QWidget):
    def __init__(self):
        super().__init__()
        self.folder: str | None = None
        self.result: AnalysisResult | None = None
        self.thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self._build()

    # ---------- construção da tela ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        title = QLabel("Duplicados exatos")
        title.setObjectName("title")
        subtitle = QLabel("Análise somente leitura: nesta tela nenhum arquivo é movido, renomeado ou excluído.")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        actions = QHBoxLayout()
        self.strict_box = QCheckBox("Confirmação rigorosa (byte a byte)")
        self.strict_box.setToolTip("Além do SHA-256, compara os bytes de cada grupo. Mais lento, mesma segurança prática.")
        self.analyze_button = QPushButton("Analisar arquivos")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.start_analysis)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        actions.addStretch(1)
        actions.addWidget(self.strict_box)
        actions.addWidget(self.analyze_button)
        actions.addWidget(self.cancel_button)
        root.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.status = QLabel("Selecione uma pasta para começar.")
        self.status.setObjectName("status")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.ind_files = Indicator("TOTAL DE ARQUIVOS")
        self.ind_folders = Indicator("TOTAL DE PASTAS")
        self.ind_dups = Indicator("DUPLICADOS EXATOS")
        self.ind_space = Indicator("ESPAÇO POTENCIALMENTE RECUPERÁVEL")
        self.ind_skipped = Indicator("NÃO ANALISADOS")
        self.ind_time = Indicator("TEMPO DE ANÁLISE")
        for col, ind in enumerate(
            (self.ind_files, self.ind_folders, self.ind_dups, self.ind_space, self.ind_skipped, self.ind_time)
        ):
            grid.addWidget(ind, 0, col)
        root.addLayout(grid)

        self.tabs = QTabWidget()
        self.dup_tree = QTreeWidget()
        self.dup_tree.setHeaderLabels(["Nome", "Localização (dentro da pasta analisada)", "Tamanho", "Modificado em", "Classificação"])
        self.dup_tree.setAlternatingRowColors(True)
        self.dup_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.dup_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dup_tree.itemDoubleClicked.connect(lambda item, _col: self.open_location(item))
        self.category_table = self._table(["Categoria", "Arquivos", "Tamanho total"])
        self.skipped_table = self._table(["Caminho", "Motivo"])
        self.tabs.addTab(self.dup_tree, "Duplicados exatos")
        self.tabs.addTab(self.category_table, "Arquivos por categoria")
        self.tabs.addTab(self.skipped_table, "Não analisados")
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        hint = QLabel("Dê dois cliques num arquivo para abrir a pasta onde ele está.")
        hint.setObjectName("status")
        self.open_button = QPushButton("Abrir local do arquivo")
        self.open_button.clicked.connect(lambda: self.open_location(self.dup_tree.currentItem()))
        self.export_button = QPushButton("Exportar relatório (CSV)")
        self.export_button.clicked.connect(self.export_report)
        self.export_button.setEnabled(False)
        footer.addWidget(hint, 1)
        footer.addWidget(self.open_button)
        footer.addWidget(self.export_button)
        root.addLayout(footer)


    def _table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        return table

    # ---------- ações ----------

    def set_folder(self, folder: str | None) -> None:
        self.folder = folder
        self.analyze_button.setEnabled(bool(folder) and not self.cancel_button.isEnabled())
        if folder:
            self.status.setText("Pronto para analisar. Os arquivos serão apenas lidos.")

    def start_analysis(self) -> None:
        if not self.folder:
            return
        self._set_running(True)
        self.progress.setRange(0, 0)
        self.status.setText("Listando arquivos...")
        self.thread = QThread(self)
        self.worker = AnalysisWorker(self.folder, self.strict_box.isChecked())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.cancelled.connect(self.on_cancelled)
        for signal in (self.worker.finished, self.worker.failed, self.worker.cancelled):
            signal.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def cancel_analysis(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.status.setText("Cancelando...")

    def on_progress(self, stage: str, done: int, total: int) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status.setText(f"{stage}: {done:n} de {total:n}")
        else:
            self.progress.setRange(0, 0)
            self.status.setText(f"{stage}: {done:n} encontrados")

    def on_failed(self, message: str) -> None:
        self._set_running(False)
        self.status.setText("A análise não foi concluída. Nenhum arquivo foi alterado.")
        QMessageBox.critical(self, "Erro na análise", message)

    def on_cancelled(self) -> None:
        self._set_running(False)
        self.status.setText("Análise cancelada. Nenhum arquivo foi alterado.")

    def on_finished(self, result: AnalysisResult) -> None:
        self._set_running(False)
        self.result = result
        scanned, report = result.scan, result.duplicates
        skipped = scanned.skipped + report.not_analyzed

        self.ind_files.set(f"{len(scanned.files):n}", format_size(scanned.total_size))
        self.ind_folders.set(f"{scanned.folder_count:n}")
        self.ind_dups.set(f"{report.duplicate_files:n}", f"em {len(report.groups):n} grupos")
        self.ind_space.set(format_size(report.recoverable_bytes), "nada foi excluído")
        self.ind_skipped.set(f"{len(skipped):n}", "ver aba Não analisados" if skipped else "")
        self.ind_time.set(f"{result.seconds:.1f} s".replace(".", ","), f"{format_size(report.bytes_hashed)} lidos")

        self._fill_duplicates(report, scanned.root)
        self._fill_categories(scanned)
        self._fill_skipped(skipped)
        self.export_button.setEnabled(bool(report.groups))
        self.status.setText(
            f"Análise concluída: {len(report.groups):n} grupos de duplicados exatos, "
            f"{report.unique_files:n} arquivos únicos, {len(report.empty_files):n} arquivos vazios."
        )

    def _fill_duplicates(self, report, root: str) -> None:
        self.dup_tree.clear()
        for number, group in enumerate(report.groups, start=1):
            verified = " · confirmado byte a byte" if group.byte_verified else ""
            parent = QTreeWidgetItem(
                [f"Grupo {number}: {group.copies} cópias", "", format_size(group.size), "",
                 f"{group.classification}{verified}"]
            )
            parent.setToolTip(0, f"SHA-256: {group.sha256}")
            parent.setText(1, f"{format_size(group.recoverable_bytes)} potencialmente recuperáveis")
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            for entry in group.files:
                relative = os.path.relpath(entry.folder, root)
                child = QTreeWidgetItem(
                    [entry.name, "(pasta principal)" if relative == "." else relative, format_size(entry.size), format_time(entry.mtime), group.classification]
                )
                child.setData(0, PATH_ROLE, entry.path)
                child.setToolTip(1, entry.path)
                parent.addChild(child)
            self.dup_tree.addTopLevelItem(parent)
            parent.setExpanded(number <= 20)
        for col in (0, 2, 3, 4):
            self.dup_tree.resizeColumnToContents(col)

    def _fill_categories(self, scanned) -> None:
        sizes: dict[str, int] = {}
        for entry in scanned.files:
            cat = category_for(entry.name)
            sizes[cat] = sizes.get(cat, 0) + entry.size
        rows = scanned.by_category().most_common()
        self.category_table.setRowCount(len(rows))
        for row, (cat, count) in enumerate(rows):
            for col, text in enumerate((cat, f"{count:n}", format_size(sizes[cat]))):
                self.category_table.setItem(row, col, QTableWidgetItem(text))

    def _fill_skipped(self, skipped) -> None:
        self.skipped_table.setRowCount(len(skipped))
        for row, item in enumerate(skipped):
            self.skipped_table.setItem(row, 0, QTableWidgetItem(item.path))
            self.skipped_table.setItem(row, 1, QTableWidgetItem(item.reason))
        self.skipped_table.resizeColumnToContents(1)

    def open_location(self, item: QTreeWidgetItem | None) -> None:
        path = item.data(0, PATH_ROLE) if item is not None else None
        if not path:
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def export_report(self) -> None:
        if self.result is None:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Salvar relatório", "relatorio_duplicados.csv", "Planilha CSV (*.csv)"
        )
        if not destination:
            return
        try:
            export_csv(self.result.duplicates, destination)
        except FileExistsError:
            QMessageBox.warning(self, "Arquivo existente", "Já existe um arquivo com esse nome. Escolha outro nome.")
            return
        except OSError as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))
            return
        self.status.setText(f"Relatório salvo em {destination}")

    def _set_running(self, running: bool) -> None:
        self.analyze_button.setEnabled(not running and bool(self.folder))
        self.strict_box.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        if not running:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)

    def stop(self) -> None:
        if self.worker is not None and self.thread is not None and self.thread.isRunning():
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(3000)
