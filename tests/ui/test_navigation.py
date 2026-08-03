from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea
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


def test_layout_fits_minimum_logical_width(qtbot: QtBot, qapp: QApplication) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(window.minimumSize())
    window.show()
    qapp.processEvents()

    assert window.size().width() >= 960
    for index in range(window.page_stack.count()):
        scroll = window.page_stack.widget(index)
        assert isinstance(scroll, QScrollArea)
        assert scroll.widget().minimumSizeHint().width() <= scroll.viewport().width()
