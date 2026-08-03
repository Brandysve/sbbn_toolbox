from PySide6.QtWidgets import QApplication, QLabel

from sbbn_toolbox.app import create_application
from sbbn_toolbox.constants import APPLICATION_NAME, INITIAL_MESSAGE
from sbbn_toolbox.ui.main_window import MainWindow


def test_create_application_sets_name(qapp: QApplication) -> None:
    application = create_application([])

    assert application is qapp
    assert application.applicationName() == APPLICATION_NAME


def test_main_window_is_minimal(qapp: QApplication) -> None:
    window = MainWindow()

    assert window.windowTitle() == APPLICATION_NAME
    assert isinstance(window.centralWidget(), QLabel)
    assert window.centralWidget().text() == INITIAL_MESSAGE
