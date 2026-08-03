from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox
from pytestqt.qtbot import QtBot

from sbbn_toolbox.ui.main_window import MainWindow
from sbbn_toolbox.ui.pages.image_converter_page import ImageConverterPage
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.drop_zone import DropZone
from sbbn_toolbox.ui.widgets.thumbnail_card import ThumbnailCard
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

    with (
        qtbot.waitSignal(drop_zone.drop_detected),
        qtbot.waitSignal(drop_zone.files_dropped) as dropped,
    ):
        drop_zone.dropEvent(event)

    assert dropped.args == [["document.pdf"]]


def test_image_selection_imports_a_valid_file(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "image sélectionnée.png"
    Image.new("RGB", (40, 30), "purple").save(source)
    page = ImageConverterPage()
    qtbot.addWidget(page)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *args: ([str(source)], ""),
    )

    drop_zone = page.findChild(DropZone)
    drop_zone.selection_requested.emit()

    assert len(page.viewmodel.items) == 1
    assert page.grid.count() == 1
    assert page.create_button.isEnabled()


def test_image_keyboard_shortcuts_select_and_remove_all(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    sources = [tmp_path / "première image.png", tmp_path / "deuxième image.png"]
    for source in sources:
        Image.new("RGB", (40, 30), "purple").save(source)
    page = ImageConverterPage()
    qtbot.addWidget(page)
    page.viewmodel.import_files(sources)
    page.show()
    page.grid.setFocus()

    qtbot.keyClick(page.grid, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)

    assert len(page.grid.selectedItems()) == 2
    qtbot.keyClick(page.grid, Qt.Key.Key_Delete)
    assert page.viewmodel.items == []


def test_long_image_name_is_available_as_tooltip(qtbot: QtBot, tmp_path: Path) -> None:
    source = tmp_path / ("nom très long avec accents " * 5 + ".png")
    Image.new("RGB", (40, 30), "purple").save(source)
    page = ImageConverterPage()
    qtbot.addWidget(page)
    page.viewmodel.import_files([source])
    card = page.grid.itemWidget(page.grid.item(0))

    assert isinstance(card, ThumbnailCard)
    assert any(label.toolTip() == source.name for label in card.findChildren(QLabel))


def test_main_window_confirms_before_discarding_unexported_selection(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "non exportée.png"
    Image.new("RGB", (40, 30), "purple").save(source)
    window = MainWindow()
    qtbot.addWidget(window)
    window.images_page.viewmodel.import_files([source])
    window.show()
    answers = iter([QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(QMessageBox, "question", lambda *args: next(answers))

    assert not window.close()
    assert window.isVisible()
    assert window.close()


def test_image_actions_are_restored_after_long_operation(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = tmp_path / "état interface.png"
    Image.new("RGB", (40, 30), "purple").save(source)
    page = ImageConverterPage()
    qtbot.addWidget(page)
    page.viewmodel.import_files([source])
    page.show()

    page._set_busy(True)

    assert not page.grid.isEnabled()
    assert not page.create_button.isEnabled()
    assert page.cancel_button.isVisible()
    assert page.progress.isVisible()

    page._set_busy(False)

    assert page.grid.isEnabled()
    assert page.create_button.isEnabled()
    assert page.cancel_button.isHidden()
    assert page.progress.isHidden()


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
