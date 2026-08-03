"""Fenêtre minimale de la Phase 0."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

from sbbn_toolbox.constants import APPLICATION_NAME, INITIAL_MESSAGE


class MainWindow(QMainWindow):
    """Fenêtre racine minimale, sans fonctionnalités de la Phase 1."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APPLICATION_NAME)
        self.resize(720, 480)

        message = QLabel(INITIAL_MESSAGE)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(message)
