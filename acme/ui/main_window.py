"""Janela principal: menu lateral à esquerda e as páginas à direita, como no AutomacoesACME."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from acme import APP_NAME, __version__
from acme.core.paths import PathNotAllowed, validate_root

from .duplicates_page import DuplicatesPage
from .history_page import HistoryPage
from .organize_page import OrganizePage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1240, 800)
        self.folder: str | None = None
        self.duplicates = DuplicatesPage()
        self.organize = OrganizePage()
        self.history = HistoryPage()
        self.organize.organized.connect(self.history.refresh)
        self._build()

    def _build(self) -> None:
        self.menu = QListWidget()
        self.menu.setObjectName("menu")
        self.menu.setFixedWidth(210)
        self.pages = QStackedWidget()
        for name, page in (("Duplicados exatos", self.duplicates), ("Organizar", self.organize),
                           ("Histórico", self.history)):
            self.menu.addItem(name)
            self.pages.addWidget(page)
        self.menu.currentRowChanged.connect(self._switch)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        brand = QLabel("ACME\nOrganizador")
        brand.setObjectName("marca")
        side_layout.addWidget(brand)
        side_layout.addWidget(self.menu, 1)
        version = QLabel(f"versão {__version__}")
        version.setObjectName("versao")
        side_layout.addWidget(version)

        right = QWidget()
        right.setObjectName("central")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 18, 24, 16)
        right_layout.setSpacing(14)
        folder_bar = QHBoxLayout()
        self.select_button = QPushButton("Selecionar pasta")
        self.select_button.clicked.connect(self.choose_folder)
        self.folder_label = QLabel("Nenhuma pasta selecionada")
        self.folder_label.setObjectName("folder")
        folder_bar.addWidget(self.select_button)
        folder_bar.addWidget(self.folder_label, 1)
        right_layout.addLayout(folder_bar)
        right_layout.addWidget(self.pages, 1)

        center = QWidget()
        layout = QHBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(side)
        layout.addWidget(right, 1)
        self.setCentralWidget(center)
        self.menu.setCurrentRow(0)

    def _switch(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if self.pages.currentWidget() is self.history:
            self.history.refresh()

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta")
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder: str) -> bool:
        try:
            self.folder = str(validate_root(folder))
        except PathNotAllowed as exc:
            QMessageBox.warning(self, "Pasta não permitida", str(exc))
            return False
        self.folder_label.setText(self.folder)
        self.duplicates.set_folder(self.folder)
        self.organize.set_folder(self.folder)
        return True

    def closeEvent(self, event) -> None:
        for page in (self.duplicates, self.organize, self.history):
            page.stop()
        super().closeEvent(event)
