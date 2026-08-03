"""Carte de vignette d'une image importée."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QTransform
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sbbn_toolbox.constants import REMOVE_IMAGE, ROTATE_IMAGE
from sbbn_toolbox.domain.image_item import ImageItem
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton


class ThumbnailCard(QFrame):
    """Afficher un aperçu et des actions textuelles accessibles."""

    rotate_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, item: ImageItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.md)

        preview = QLabel()
        pixmap = QPixmap(str(item.source_path))
        if item.rotation:
            pixmap = pixmap.transformed(QTransform().rotate(item.rotation))
        preview.setPixmap(
            pixmap.scaled(
                112,
                84,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        preview.setFixedSize(120, 92)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview)

        details = QVBoxLayout()
        name = QLabel(item.display_name)
        name.setWordWrap(True)
        name.setToolTip(item.display_name)
        details.addWidget(name)
        metadata = QLabel(f"{item.width} × {item.height} · {item.format} · {item.rotation}°")
        metadata.setProperty("role", "muted")
        details.addWidget(metadata)
        actions = QHBoxLayout()
        rotate = ActionButton(ROTATE_IMAGE, variant="secondary")
        rotate.clicked.connect(lambda: self.rotate_requested.emit(item.identifier))
        actions.addWidget(rotate)
        remove = ActionButton(REMOVE_IMAGE, variant="secondary")
        remove.clicked.connect(lambda: self.remove_requested.emit(item.identifier))
        actions.addWidget(remove)
        actions.addStretch()
        details.addLayout(actions)
        layout.addLayout(details, stretch=1)
