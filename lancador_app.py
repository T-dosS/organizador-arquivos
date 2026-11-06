"""Ponto de entrada do executável OrganizadorACME.exe."""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from acme import APP_NAME
from acme.ui.main_window import MainWindow
from acme.ui.theme import preparar_aplicativo


def pasta_recursos() -> Path:
    # No executável o PyInstaller extrai os dados em sys._MEIPASS; no VS Code, ao lado deste arquivo.
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "recursos"


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    preparar_aplicativo(app)
    icone = pasta_recursos() / "icone.ico"
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
