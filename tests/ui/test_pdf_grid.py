from pathlib import Path

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.ui.widgets.pdf_page_grid import PdfPageGrid


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
    assert requests[0][1] == 1
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
