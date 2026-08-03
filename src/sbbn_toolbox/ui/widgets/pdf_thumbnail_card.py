"""Carte visuelle d'une page PDF, sans logique documentaire."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.ui.theme.tokens import SPACING


class PdfThumbnailCard(QFrame):
    """Afficher la provenance, le numéro original et un aperçu en mémoire."""

    def __init__(
        self,
        page: PdfPageItem,
        parent: QWidget | None = None,
        *,
        page_count: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.page_identifier = page.identifier
        self.setProperty("card", True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMinimumWidth(234)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.sm)
        self.preview = QLabel("…")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(210, 297)
        layout.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignCenter)
        source = QLabel(page.source_display_name)
        source.setWordWrap(True)
        source.setToolTip(page.source_display_name)
        source.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(source)
        if page_count is None:
            details = f"Page {page.display_page_number} · Rotation {page.rotation}°"
        else:
            suffix = "page" if page_count == 1 else "pages"
            details = f"{page_count} {suffix}"
        self.details = QLabel(details)
        self.details.setProperty("role", "muted")
        self.details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.details)

    def set_page_count(self, page_count: int) -> None:
        suffix = "page" if page_count == 1 else "pages"
        self.details.setText(f"{page_count} {suffix}")

    def set_thumbnail(self, payload: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(payload):
            self.preview.setPixmap(
                pixmap.scaled(
                    self.preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.preview.setText("")
