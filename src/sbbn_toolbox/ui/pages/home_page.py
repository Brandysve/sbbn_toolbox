"""Page d'accueil."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sbbn_toolbox.constants import (
    HOME_DESCRIPTION,
    HOME_EYEBROW,
    HOME_IMAGES_DESCRIPTION,
    HOME_PDF_DESCRIPTION,
    HOME_TITLE,
    LOCAL_PROCESSING_NOTE,
    NAV_IMAGES,
    NAV_PDF,
)
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.card import FeatureCard


class HomePage(QWidget):
    """Oriente vers les deux parcours principaux."""

    images_requested = Signal()
    pdf_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homePage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxxl, SPACING.xxxl, SPACING.xxxl, SPACING.xxl)
        layout.setSpacing(SPACING.lg)

        eyebrow = QLabel(HOME_EYEBROW)
        eyebrow.setProperty("role", "eyebrow")
        layout.addWidget(eyebrow)

        title = QLabel(HOME_TITLE)
        title.setProperty("role", "pageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        description = QLabel(HOME_DESCRIPTION)
        description.setProperty("role", "description")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(SPACING.lg)

        cards = QHBoxLayout()
        cards.setSpacing(SPACING.xl)
        images_card = FeatureCard("I", NAV_IMAGES, HOME_IMAGES_DESCRIPTION)
        images_card.activated.connect(self.images_requested)
        cards.addWidget(images_card)
        pdf_card = FeatureCard("P", NAV_PDF, HOME_PDF_DESCRIPTION)
        pdf_card.activated.connect(self.pdf_requested)
        cards.addWidget(pdf_card)
        layout.addLayout(cards, stretch=1)

        note = QLabel(LOCAL_PROCESSING_NOTE)
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
