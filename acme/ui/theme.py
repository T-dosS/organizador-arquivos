"""Identidade visual ACME: as mesmas cores do AutomacoesACME (painel/estilo.py)."""

from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, Qt, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

VERMELHO = "#A50008"
VERMELHO_ESCURO = "#6E0005"
TEXTO = "#1D1819"
TEXTO_2 = "#5F5759"
FUNDO = "#F5F4F4"
BORDA = "#E7E2E3"
VERDE = "#1E7F45"

STYLESHEET = f"""
QWidget {{ font-family: 'Segoe UI'; font-size: 10pt; color: {TEXTO}; }}
QDialog, QMessageBox, QFileDialog {{ background: #FFFFFF; }}
QMessageBox QLabel {{ color: {TEXTO}; background: transparent; }}
QMainWindow, QWidget#central {{ background: {FUNDO}; }}
#menu {{ background: {TEXTO}; border: none; outline: 0; }}
#menu::item {{ color: #FFFFFF; padding: 12px 18px; border-left: 4px solid transparent; }}
#menu::item:selected {{ background: #2E2627; border-left: 4px solid {VERMELHO}; }}
QLabel#marca {{ background: {TEXTO}; color: #FFFFFF; font-size: 13pt; font-weight: 700; padding: 18px; }}
QLabel#versao {{ background: {TEXTO}; color: #A39C9E; font-size: 8pt; padding: 10px 18px; }}
QComboBox {{ background: #FFFFFF; border: 1px solid {BORDA}; border-radius: 6px; padding: 5px 10px; }}
QLabel#title {{ font-size: 16pt; font-weight: 700; }}
QLabel#subtitle, QLabel#status, QLabel#indicatorDetail {{ color: {TEXTO_2}; }}
QLabel#indicatorCaption {{ color: {TEXTO_2}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#folder {{ background: #FFFFFF; border: 1px solid {BORDA}; border-radius: 6px; padding: 6px 10px; }}
QFrame#indicator {{ background: #FFFFFF; border: 1px solid {BORDA}; border-radius: 10px; }}
QFrame#indicator QLabel {{ background: transparent; }}
QLabel#indicatorValue {{ font-size: 14pt; font-weight: 700; }}
QPushButton {{ background: #FFFFFF; border: 1px solid {BORDA}; border-radius: 6px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {VERMELHO}; }}
QPushButton:disabled {{ color: #A39C9E; background: #F0EDEE; }}
QPushButton#primary {{ background: {VERMELHO}; color: #FFFFFF; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {VERMELHO_ESCURO}; }}
QPushButton#primary:disabled {{ background: #D9B3B5; }}
QProgressBar {{ background: {BORDA}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {VERMELHO}; border-radius: 3px; }}
QTabWidget::pane {{ border: 1px solid {BORDA}; border-radius: 6px; background: #FFFFFF; }}
QTabBar::tab {{ padding: 8px 16px; background: transparent; color: {TEXTO_2}; }}
QTabBar::tab:selected {{ color: {TEXTO}; border-bottom: 2px solid {VERMELHO}; font-weight: 600; }}
QTreeWidget, QTableWidget {{ background: #FFFFFF; alternate-background-color: {FUNDO}; border: none; }}
QHeaderView::section {{ background: {FUNDO}; border: none; border-bottom: 1px solid {BORDA}; padding: 6px; font-weight: 600; }}
"""


def preparar_aplicativo(app: QApplication) -> None:
    """Tema claro fixo e textos do Qt em português, como no AutomacoesACME.

    Sem isso, com o Windows no modo escuro, os diálogos ficam com texto escuro sobre fundo escuro.
    """
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:  # Qt anterior à 6.8
        pass
    app.setStyle("Fusion")
    paleta = QPalette()
    for papel, cor in ((QPalette.Window, FUNDO), (QPalette.WindowText, TEXTO), (QPalette.Base, "#FFFFFF"),
                       (QPalette.AlternateBase, FUNDO), (QPalette.Text, TEXTO), (QPalette.Button, "#FFFFFF"),
                       (QPalette.ButtonText, TEXTO), (QPalette.ToolTipBase, "#FFFFFF"), (QPalette.ToolTipText, TEXTO),
                       (QPalette.Highlight, VERMELHO), (QPalette.HighlightedText, "#FFFFFF"),
                       (QPalette.PlaceholderText, TEXTO_2)):
        paleta.setColor(papel, QColor(cor))
    app.setPalette(paleta)
    tradutor = QTranslator(app)
    if tradutor.load("qtbase_pt_BR", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tradutor)
    app.setStyleSheet(STYLESHEET)
