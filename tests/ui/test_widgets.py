from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from pytestqt.qtbot import QtBot

from sbbn_toolbox.constants import PHASE_PLACEHOLDER_MESSAGE
from sbbn_toolbox.ui.main_window import MainWindow
from sbbn_toolbox.ui.pages.image_converter_page import ImageConverterPage
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.drop_zone import DropZone
from sbbn_toolbox.ui.widgets.toast import Toast


def test_action_button_exposes_variant_and_disabled_state(qtbot: QtBot) -> None:
    button = ActionButton("Action")
    qtbot.addWidget(button)

    assert button.property("variant") == "primary"
    assert button.focusPolicy() is Qt.FocusPolicy.StrongFocus
    button.setDisabled(True)
    assert not button.isEnabled()


def test_drop_zone_activates_with_keyboard(qtbot: QtBot) -> None:
    drop_zone = DropZone("Déposer", "Description", "Ajouter")
    qtbot.addWidget(drop_zone)

    with qtbot.waitSignal(drop_zone.selection_requested):
        qtbot.keyClick(drop_zone, Qt.Key.Key_Return)


def test_drop_zone_detects_but_does_not_load_drop(qtbot: QtBot) -> None:
    drop_zone = DropZone("Déposer", "Description", "Ajouter")
    qtbot.addWidget(drop_zone)
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile("document.pdf")])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    with qtbot.waitSignal(drop_zone.drop_detected):
        drop_zone.dropEvent(event)


def test_placeholder_action_requests_notification(qtbot: QtBot) -> None:
    page = ImageConverterPage()
    qtbot.addWidget(page)

    with qtbot.waitSignal(page.notification_requested) as blocker:
        drop_zone = page.findChild(DropZone)
        drop_zone.selection_requested.emit()

    assert blocker.args == [PHASE_PLACEHOLDER_MESSAGE]


def test_toast_displays_message(qtbot: QtBot) -> None:
    toast = Toast()
    qtbot.addWidget(toast)

    toast.show_message("Information", duration_ms=10_000)

    assert toast.isVisible()
    assert toast.accessibleName() == "Information"


def test_toast_uses_available_content_width(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.toast.show_message(
        "Le dossier de données a été mis à jour.",
        duration_ms=10_000,
    )

    parent = window.toast.parentWidget()
    assert parent is not None
    assert window.toast.x() == SPACING.lg
    assert parent.contentsRect().right() - window.toast.geometry().right() == SPACING.lg
