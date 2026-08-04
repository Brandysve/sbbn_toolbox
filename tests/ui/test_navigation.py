import os
import subprocess
import sys

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QWidget,
)
from pytestqt.qtbot import QtBot

from sbbn_toolbox.constants import APPLICATION_NAME
from sbbn_toolbox.ui.main_window import MainWindow, Page


def test_main_window_starts_on_home(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == APPLICATION_NAME
    assert window.current_page is Page.HOME
    assert window.navigation_buttons[Page.HOME].isChecked()


def test_sidebar_and_home_cards_navigate(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.navigation_buttons[Page.SETTINGS], Qt.MouseButton.LeftButton)
    assert window.current_page is Page.SETTINGS
    assert window.navigation_buttons[Page.SETTINGS].isChecked()

    window.navigate_to(Page.HOME)
    window.home_page.images_requested.emit()
    assert window.current_page is Page.IMAGES

    window.navigate_to(Page.HOME)
    window.home_page.pdf_requested.emit()
    assert window.current_page is Page.PDF


def test_navigation_is_keyboard_accessible(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    button = window.navigation_buttons[Page.IMAGES]
    button.setFocus()

    qtbot.keyClick(button, Qt.Key.Key_Space)

    assert window.current_page is Page.IMAGES
    assert button.accessibleName()


WINDOW_SIZES = ((960, 640), (1080, 700), (1440, 900))


def _assert_layout_items_do_not_overlap(layout: QLayout) -> None:
    widget_rects: list[QRect] = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None and widget.isVisible():
            widget_rects.append(widget.geometry())
        if child_layout is not None:
            _assert_layout_items_do_not_overlap(child_layout)

    for index, first in enumerate(widget_rects):
        for second in widget_rects[index + 1 :]:
            assert not first.intersects(second)


def _assert_widget_inside_page(widget: QWidget, page: QWidget) -> None:
    top_left = widget.mapTo(page, widget.rect().topLeft())
    widget_rect = QRect(top_left, widget.size())
    assert page.rect().contains(widget_rect)


@pytest.mark.parametrize(("width", "height"), WINDOW_SIZES)
def test_all_pages_remain_usable_when_resized(
    qtbot: QtBot,
    qapp: QApplication,
    width: int,
    height: int,
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(width, height)
    window.show()
    qapp.processEvents()

    assert window.size() == window.size().expandedTo(window.minimumSize())
    for page in Page:
        window.navigate_to(page)
        qapp.processEvents()
        scroll = window.page_stack.currentWidget()
        assert isinstance(scroll, QScrollArea)
        page_widget = scroll.widget()
        assert page_widget is not None
        assert scroll.horizontalScrollBar().maximum() == 0
        if page not in {Page.IMAGES, Page.PDF, Page.SETTINGS}:
            assert scroll.verticalScrollBar().maximum() == 0
        assert page_widget.minimumSizeHint().width() <= scroll.viewport().width()
        if page not in {Page.IMAGES, Page.PDF, Page.SETTINGS}:
            assert page_widget.minimumSizeHint().height() <= scroll.viewport().height()

        buttons = page_widget.findChildren(QPushButton)
        assert buttons
        line_edits = [
            field
            for field in page_widget.findChildren(QLineEdit)
            if not isinstance(field.parentWidget(), QSpinBox)
        ]
        controls: list[QWidget] = [*buttons, *line_edits]
        for control in controls:
            if control.isHidden():
                continue
            assert control.isVisible()
            assert control.width() >= control.minimumSizeHint().width()
            assert control.height() >= control.minimumSizeHint().height()
            _assert_widget_inside_page(control, page_widget)

        layout = page_widget.layout()
        assert layout is not None
        _assert_layout_items_do_not_overlap(layout)


@pytest.mark.parametrize("scale_factor", (1.0, 1.25, 1.5))
def test_qt_layouts_with_simulated_scale_factor(scale_factor: float) -> None:
    script = """
import sys

from PySide6.QtWidgets import QPushButton, QScrollArea

from sbbn_toolbox.app import create_application
from sbbn_toolbox.ui.main_window import MainWindow, Page

application = create_application([])
window = MainWindow()
window.resize(window.minimumSize())
window.show()
application.processEvents()
device_scale = window.devicePixelRatio()
if sys.platform == "win32":
    # QT_SCALE_FACTOR multiplie la mise à l'échelle Windows native.
    assert device_scale + 0.01 >= SCALE_FACTOR
else:
    assert abs(device_scale - SCALE_FACTOR) < 0.01
for page in Page:
    window.navigate_to(page)
    application.processEvents()
    scroll = window.page_stack.currentWidget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.horizontalScrollBar().maximum() == 0
    if page not in {Page.IMAGES, Page.PDF, Page.SETTINGS}:
        assert scroll.verticalScrollBar().maximum() == 0
    page_widget = scroll.widget()
    assert page_widget is not None
    buttons = page_widget.findChildren(QPushButton)
    assert buttons
    assert all(
            button.isVisible()
            or button.objectName()
            in {
                "addMorePdfButton",
                "cancelConversionButton",
                "cancelPdfOperationButton",
                "cancelUpdateDownloadButton",
            }
        for button in buttons
    )
print("dpi-layout-ok")
""".replace("SCALE_FACTOR", str(scale_factor))
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    environment["QT_SCALE_FACTOR"] = str(scale_factor)
    environment["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert "dpi-layout-ok" in result.stdout
