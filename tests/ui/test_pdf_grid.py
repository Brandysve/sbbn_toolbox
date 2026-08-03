from pathlib import Path

from pypdf import PdfWriter
from PySide6.QtCore import QModelIndex, Qt, QTimer
from PySide6.QtGui import QDrag
from pytestqt.qtbot import QtBot

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.services.preview_service import PreviewService
from sbbn_toolbox.ui.widgets.pdf_page_grid import PdfPageGrid
from sbbn_toolbox.ui.widgets.pdf_thumbnail_card import PdfThumbnailCard


def make_pages(count: int) -> list[PdfPageItem]:
    source = Path("/fixture/document.pdf")
    return [
        PdfPageItem(
            source_path=source,
            source_page_index=index,
            display_page_number=index + 1,
            source_display_name="document.pdf",
            width=100,
            height=200,
        )
        for index in range(count)
    ]


def test_grid_requests_visible_previews_first_and_lazily(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    grid.resize(700, 480)
    pages = make_pages(100)
    requests: list[tuple[str, int]] = []
    grid.preview_requested.connect(
        lambda identifier, priority: requests.append((identifier, priority))
    )

    grid.set_pages(pages)
    grid.show()
    qtbot.wait(20)

    assert requests
    assert len(requests) < len(pages)
    assert requests[0] == (pages[0].identifier, 2)
    assert any(priority == 1 for _, priority in requests)
    assert any(priority == 0 for _, priority in requests)


def test_grid_supports_multiple_selection(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    pages = make_pages(3)
    grid.set_pages(pages)
    grid.show()

    grid.item(0).setSelected(True)
    grid.item(1).setSelected(True)

    assert set(grid.selected_identifiers()) == {
        pages[0].identifier,
        pages[1].identifier,
    }
    assert grid.selectionMode() is grid.SelectionMode.ExtendedSelection
    assert grid.defaultDropAction() is Qt.DropAction.MoveAction


def test_cards_are_portrait_and_do_not_intercept_drag_events(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    grid.set_pages(make_pages(1))
    card = grid.itemWidget(grid.item(0))

    assert isinstance(card, PdfThumbnailCard)
    assert card.preview.height() > card.preview.width()
    assert card.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert grid.dragEnabled()
    assert grid.acceptDrops()
    assert not grid.showDropIndicator()


def test_internal_move_changes_order_and_emits_new_sequence(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    pages = make_pages(3)
    grid.set_pages(pages)

    with qtbot.waitSignal(grid.order_changed) as moved:
        changed = grid.model().moveRows(QModelIndex(), 0, 1, QModelIndex(), 3)

    assert changed
    assert grid.identifiers() == [
        pages[1].identifier,
        pages[2].identifier,
        pages[0].identifier,
    ]
    assert moved.args == [grid.identifiers()]


def test_explicit_drop_order_moves_selected_pages_across_sources(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    pages = make_pages(4)
    grid.set_pages(pages)

    with qtbot.waitSignal(grid.order_changed) as moved:
        changed = grid._apply_drop_order(
            [pages[0].identifier, pages[1].identifier],
            pages[3].identifier,
            True,
        )

    expected = [
        pages[2].identifier,
        pages[3].identifier,
        pages[0].identifier,
        pages[1].identifier,
    ]
    assert changed
    assert grid.identifiers() == expected
    assert moved.args == [expected]
    assert grid.selected_identifiers() == []
    assert grid.currentItem() is None


def test_drop_indicator_is_vertical_and_can_be_cleared(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    grid.resize(700, 480)
    grid.set_pages(make_pages(3))
    grid.show()
    qtbot.wait(10)
    first_rect = grid.visualItemRect(grid.item(0))

    grid._update_drop_indicator(first_rect.center())

    assert grid._drop_indicator is not None
    assert grid._drop_indicator.height() > grid._drop_indicator.width()

    grid._clear_drop_indicator()

    assert grid._drop_indicator is None


def test_finish_drag_removes_selection_focus_and_indicator(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    grid.resize(700, 480)
    grid.set_pages(make_pages(2))
    grid.show()
    qtbot.wait(10)
    grid.item(0).setSelected(True)
    grid.setCurrentRow(0)
    grid._update_drop_indicator(grid.visualItemRect(grid.item(1)).center())

    grid._finish_drag_visuals()

    assert grid.selected_identifiers() == []
    assert grid.currentItem() is None
    assert grid._drop_indicator is None


def test_completed_drop_reorders_after_native_drag_cleanup(qtbot: QtBot) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    pages = make_pages(3)
    grid.set_pages(pages)
    grid.item(0).setSelected(True)

    with qtbot.waitSignal(grid.order_changed) as moved:
        QTimer.singleShot(
            0,
            lambda: grid._complete_drop(
                [pages[0].identifier],
                pages[2].identifier,
                True,
            ),
        )

    expected = [pages[1].identifier, pages[2].identifier, pages[0].identifier]
    assert grid.identifiers() == expected
    assert moved.args == [expected]
    assert grid.selected_identifiers() == []


def test_custom_drag_does_not_let_qt_remove_the_source_row(
    qtbot: QtBot,
    monkeypatch,
) -> None:
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    pages = make_pages(3)
    grid.set_pages(pages)
    grid.item(0).setSelected(True)
    executed: list[Qt.DropAction] = []

    def execute_without_native_move(self, action: Qt.DropAction) -> Qt.DropAction:
        del self
        executed.append(action)
        return Qt.DropAction.MoveAction

    monkeypatch.setattr(QDrag, "exec", execute_without_native_move)

    grid.startDrag(Qt.DropAction.MoveAction)

    assert executed == [Qt.DropAction.MoveAction]
    assert grid.identifiers() == [page.identifier for page in pages]
    assert grid.count() == 3


def test_real_pdf_thumbnail_is_displayed(qtbot: QtBot, tmp_path: Path) -> None:
    source = tmp_path / "aperçu réel.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=500)
    with source.open("wb") as stream:
        writer.write(stream)
    page = list(PreviewService().iter_document_pages(source))[0]
    payload = PreviewService().render_thumbnail(page)
    grid = PdfPageGrid()
    qtbot.addWidget(grid)
    grid.set_pages([page])

    grid.set_thumbnail(page.identifier, payload)

    card = grid.itemWidget(grid.item(0))
    assert isinstance(card, PdfThumbnailCard)
    assert not card.preview.pixmap().isNull()
    assert card.preview.text() == ""
