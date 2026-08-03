"""Fenêtre principale et navigation de SBBN Toolbox."""

from enum import IntEnum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sbbn_toolbox.constants import (
    APPLICATION_NAME,
    APPLICATION_TAGLINE,
    LOCAL_PROCESSING_NOTE,
    NAV_HOME,
    NAV_IMAGES,
    NAV_PDF,
    NAV_SETTINGS,
)
from sbbn_toolbox.ui.pages.home_page import HomePage
from sbbn_toolbox.ui.pages.image_converter_page import ImageConverterPage
from sbbn_toolbox.ui.pages.pdf_merger_page import PdfMergerPage
from sbbn_toolbox.ui.pages.settings_page import SettingsPage
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import NavigationButton
from sbbn_toolbox.ui.widgets.toast import Toast
from sbbn_toolbox.viewmodels.settings_vm import SettingsViewModel


class Page(IntEnum):
    """Index stable des pages de navigation."""

    HOME = 0
    IMAGES = 1
    PDF = 2
    SETTINGS = 3


class MainWindow(QMainWindow):
    """Fenêtre racine moderne avec navigation latérale accessible."""

    def __init__(self, settings_viewmodel: SettingsViewModel | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APPLICATION_NAME)
        self.setMinimumSize(960, 640)
        self.resize(1180, 760)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = self._create_sidebar()
        root_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, SPACING.lg)
        content_layout.setSpacing(SPACING.sm)
        root_layout.addWidget(content, stretch=1)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        content_layout.addWidget(self.page_stack, stretch=1)

        self.home_page = HomePage()
        self.images_page = ImageConverterPage()
        self.pdf_page = PdfMergerPage()
        self.settings_page = SettingsPage(settings_viewmodel)
        for page in (self.home_page, self.images_page, self.pdf_page, self.settings_page):
            self.page_stack.addWidget(self._scrollable(page))

        self.toast = Toast()
        toast_layout = QHBoxLayout()
        toast_layout.setContentsMargins(SPACING.lg, 0, SPACING.lg, 0)
        toast_layout.addWidget(self.toast, alignment=Qt.AlignmentFlag.AlignBottom)
        content_layout.addLayout(toast_layout)

        self.home_page.images_requested.connect(lambda: self.navigate_to(Page.IMAGES))
        self.home_page.pdf_requested.connect(lambda: self.navigate_to(Page.PDF))
        self.images_page.notification_requested.connect(self.toast.show_message)
        self.pdf_page.notification_requested.connect(self.toast.show_message)
        self.settings_page.notification_requested.connect(self.toast.show_message)

        self.navigate_to(Page.HOME)

    def initialize_configuration(self) -> None:
        """Démarrer le parcours de configuration après affichage de la fenêtre."""
        self.settings_page.initialize_configuration()

    def _create_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(236)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(SPACING.lg, SPACING.xl, SPACING.lg, SPACING.xl)
        layout.setSpacing(SPACING.sm)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(SPACING.md)
        mark = QLabel("S")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(42, 42)
        brand_row.addWidget(mark)

        brand_labels = QVBoxLayout()
        brand_labels.setSpacing(0)
        name = QLabel(APPLICATION_NAME)
        name.setObjectName("brandName")
        brand_labels.addWidget(name)
        tagline = QLabel(APPLICATION_TAGLINE)
        tagline.setObjectName("brandTagline")
        tagline.setWordWrap(True)
        brand_labels.addWidget(tagline)
        brand_row.addLayout(brand_labels, stretch=1)
        layout.addLayout(brand_row)
        layout.addSpacing(SPACING.xl)

        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)
        navigation = (
            (Page.HOME, NAV_HOME),
            (Page.IMAGES, NAV_IMAGES),
            (Page.PDF, NAV_PDF),
            (Page.SETTINGS, NAV_SETTINGS),
        )
        self.navigation_buttons: dict[Page, NavigationButton] = {}
        for page, label in navigation:
            button = NavigationButton(label)
            button.clicked.connect(lambda checked=False, target=page: self.navigate_to(target))
            self.navigation_group.addButton(button, int(page))
            self.navigation_buttons[page] = button
            layout.addWidget(button)

        layout.addStretch()
        footer = QLabel(LOCAL_PROCESSING_NOTE)
        footer.setObjectName("sidebarFooter")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return sidebar

    def _scrollable(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    @property
    def current_page(self) -> Page:
        """Retourner la page actuellement affichée."""
        return Page(self.page_stack.currentIndex())

    def navigate_to(self, page: Page) -> None:
        """Afficher une page et synchroniser l'état actif de la navigation."""
        self.page_stack.setCurrentIndex(int(page))
        self.navigation_buttons[page].setChecked(True)
