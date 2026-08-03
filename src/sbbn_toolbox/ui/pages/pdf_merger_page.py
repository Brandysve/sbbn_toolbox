"""Structure visuelle du parcours de fusion PDF."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sbbn_toolbox.constants import (
    ADD_PDF,
    DROP_PLACEHOLDER_MESSAGE,
    MERGE_PDF,
    PDF_DESCRIPTION,
    PDF_DROP_DESCRIPTION,
    PDF_DROP_TITLE,
    PDF_EMPTY_DESCRIPTION,
    PDF_EMPTY_TITLE,
    PDF_TITLE,
    PHASE_PLACEHOLDER_MESSAGE,
)
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.drop_zone import DropZone
from sbbn_toolbox.ui.widgets.empty_state import EmptyState
from sbbn_toolbox.ui.widgets.page_header import PageHeader


class PdfMergerPage(QWidget):
    """Page factice : aucun PDF n'est ouvert en Phase 1."""

    notification_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxxl, SPACING.xxl, SPACING.xxxl, SPACING.xxl)
        layout.setSpacing(SPACING.xl)

        layout.addWidget(PageHeader(PDF_TITLE, PDF_DESCRIPTION))

        drop_zone = DropZone(PDF_DROP_TITLE, PDF_DROP_DESCRIPTION, ADD_PDF)
        drop_zone.selection_requested.connect(
            lambda: self.notification_requested.emit(PHASE_PLACEHOLDER_MESSAGE)
        )
        drop_zone.drop_detected.connect(
            lambda: self.notification_requested.emit(DROP_PLACEHOLDER_MESSAGE)
        )
        layout.addWidget(drop_zone)
        layout.addWidget(EmptyState(PDF_EMPTY_TITLE, PDF_EMPTY_DESCRIPTION), stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()
        merge_button = ActionButton(MERGE_PDF)
        merge_button.setEnabled(False)
        merge_button.setToolTip(PDF_EMPTY_TITLE)
        actions.addWidget(merge_button)
        layout.addLayout(actions)
