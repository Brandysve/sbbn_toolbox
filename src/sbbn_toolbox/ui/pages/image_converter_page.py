"""Structure visuelle du parcours images vers PDF."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sbbn_toolbox.constants import (
    ADD_IMAGES,
    CREATE_PDF,
    DROP_PLACEHOLDER_MESSAGE,
    IMAGES_DESCRIPTION,
    IMAGES_DROP_DESCRIPTION,
    IMAGES_DROP_TITLE,
    IMAGES_EMPTY_DESCRIPTION,
    IMAGES_EMPTY_TITLE,
    IMAGES_TITLE,
    PHASE_PLACEHOLDER_MESSAGE,
)
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.drop_zone import DropZone
from sbbn_toolbox.ui.widgets.empty_state import EmptyState
from sbbn_toolbox.ui.widgets.page_header import PageHeader


class ImageConverterPage(QWidget):
    """Page factice : aucune image n'est ouverte en Phase 1."""

    notification_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxxl, SPACING.xxl, SPACING.xxxl, SPACING.xxl)
        layout.setSpacing(SPACING.xl)

        layout.addWidget(PageHeader(IMAGES_TITLE, IMAGES_DESCRIPTION))

        drop_zone = DropZone(IMAGES_DROP_TITLE, IMAGES_DROP_DESCRIPTION, ADD_IMAGES)
        drop_zone.selection_requested.connect(
            lambda: self.notification_requested.emit(PHASE_PLACEHOLDER_MESSAGE)
        )
        drop_zone.drop_detected.connect(
            lambda: self.notification_requested.emit(DROP_PLACEHOLDER_MESSAGE)
        )
        layout.addWidget(drop_zone)
        layout.addWidget(EmptyState(IMAGES_EMPTY_TITLE, IMAGES_EMPTY_DESCRIPTION), stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()
        create_button = ActionButton(CREATE_PDF)
        create_button.setEnabled(False)
        create_button.setToolTip(IMAGES_EMPTY_TITLE)
        actions.addWidget(create_button)
        layout.addLayout(actions)
