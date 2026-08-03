"""Boutons cohérents du design system."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget


class ActionButton(QPushButton):
    """Bouton d'action primaire ou secondaire."""

    def __init__(
        self,
        text: str,
        *,
        variant: str = "primary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NavigationButton(QPushButton):
    """Bouton sélectionnable de la navigation principale."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("nav", True)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(text)
