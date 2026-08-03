"""Création de l'application Qt."""

import sys
from collections.abc import Sequence

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from sbbn_toolbox.constants import APPLICATION_NAME
from sbbn_toolbox.infrastructure.paths import program_directory
from sbbn_toolbox.services.config_service import ConfigService
from sbbn_toolbox.ui.main_window import MainWindow
from sbbn_toolbox.ui.theme import load_stylesheet
from sbbn_toolbox.viewmodels.settings_vm import SettingsViewModel


def create_application(arguments: Sequence[str] | None = None) -> QApplication:
    """Créer ou réutiliser l'instance Qt de l'application."""
    application = QApplication.instance()
    if not isinstance(application, QApplication):
        application = QApplication(list(arguments) if arguments is not None else sys.argv)
    application.setApplicationName(APPLICATION_NAME)
    application.setStyle("Fusion")
    application.setStyleSheet(load_stylesheet())
    return application


def run(arguments: Sequence[str] | None = None) -> int:
    """Afficher la fenêtre principale et démarrer la boucle Qt."""
    effective_arguments = list(arguments) if arguments is not None else sys.argv
    smoke_test = "--smoke-test" in effective_arguments
    application = create_application(effective_arguments)
    settings_viewmodel = SettingsViewModel(ConfigService(program_directory()))
    window = MainWindow(settings_viewmodel)
    window.show()
    if smoke_test:

        def initialize_smoke_test() -> None:
            if settings_viewmodel.load() is None:
                settings_viewmodel.initialize(settings_viewmodel.default_data_path)
            QTimer.singleShot(250, window.close)

        QTimer.singleShot(0, initialize_smoke_test)
    else:
        QTimer.singleShot(0, window.initialize_configuration)
    return application.exec()
