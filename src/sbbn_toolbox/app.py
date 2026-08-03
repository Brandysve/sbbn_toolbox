"""Création de l'application Qt."""

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from sbbn_toolbox.constants import APPLICATION_NAME
from sbbn_toolbox.ui.main_window import MainWindow


def create_application(arguments: Sequence[str] | None = None) -> QApplication:
    """Créer ou réutiliser l'instance Qt de l'application."""
    application = QApplication.instance()
    if not isinstance(application, QApplication):
        application = QApplication(list(arguments) if arguments is not None else sys.argv)
    application.setApplicationName(APPLICATION_NAME)
    return application


def run(arguments: Sequence[str] | None = None) -> int:
    """Afficher la fenêtre principale et démarrer la boucle Qt."""
    application = create_application(arguments)
    window = MainWindow()
    window.show()
    return application.exec()
