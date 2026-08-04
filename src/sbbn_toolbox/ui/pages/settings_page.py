"""Écran de configuration du dossier de données."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from sbbn_toolbox.constants import (
    CHECK_FOR_UPDATES,
    CHOOSE_FOLDER,
    CHOOSE_OTHER_DATA,
    DATA_LOCATION_ERROR_TITLE,
    DATA_LOCATION_MIGRATED,
    DATA_LOCATION_RECOVERY,
    DATA_LOCATION_UPDATED,
    DATA_PATH_LABEL,
    DATA_PATH_PLACEHOLDER,
    DATA_SECTION_DESCRIPTION,
    DATA_SECTION_TITLE,
    FIRST_LAUNCH_MESSAGE,
    FIRST_LAUNCH_TITLE,
    INSTALLED_VERSION,
    INTERFACE_SECTION_DESCRIPTION,
    INTERFACE_SECTION_TITLE,
    MIGRATE_SETTINGS,
    SCALE_LABEL,
    SCALE_VALUE,
    SELECT_DATA_FOLDER,
    SETTINGS_DESCRIPTION,
    SETTINGS_TITLE,
    UPDATE_AVAILABLE,
    UPDATE_CHECK_UNAVAILABLE,
    UPDATE_CHECKING,
    UPDATE_STATUS_IDLE,
    UPDATE_UP_TO_DATE,
    USE_DEFAULT_DATA,
    USE_NEW_LOCATION,
    VERSION_SECTION_DESCRIPTION,
    VERSION_SECTION_TITLE,
)
from sbbn_toolbox.services.config_service import ConfigurationError
from sbbn_toolbox.services.update_service import UpdateCheckResult
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.page_header import PageHeader
from sbbn_toolbox.viewmodels.settings_vm import SettingsViewModel


class SettingsPage(QWidget):
    """Configurer et, au choix, migrer les préférences locales."""

    notification_requested = Signal(str)

    def __init__(
        self,
        viewmodel: SettingsViewModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.viewmodel = viewmodel
        self._selected_path: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxxl, SPACING.xxl, SPACING.xxxl, SPACING.xxl)
        layout.setSpacing(SPACING.xl)

        layout.addWidget(PageHeader(SETTINGS_TITLE, SETTINGS_DESCRIPTION))
        layout.addWidget(self._data_card())
        layout.addWidget(self._interface_card())
        layout.addWidget(self._version_card())
        layout.addStretch()
        if self.viewmodel is not None:
            self.viewmodel.data_path_changed.connect(self._set_current_path)
            self.viewmodel.update_check_started.connect(self._update_started)
            self.viewmodel.update_check_succeeded.connect(self._update_succeeded)
            self.viewmodel.update_check_failed.connect(self._update_failed)
            self.viewmodel.update_check_finished.connect(self._update_finished)

    def _data_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.md)

        title = QLabel(DATA_SECTION_TITLE)
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        description = QLabel(DATA_SECTION_DESCRIPTION)
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        layout.addWidget(description)
        label = QLabel(DATA_PATH_LABEL)
        label.setProperty("role", "muted")
        layout.addWidget(label)

        row = QHBoxLayout()
        self.path_field = QLineEdit(DATA_PATH_PLACEHOLDER)
        self.path_field.setObjectName("dataPathField")
        self.path_field.setReadOnly(True)
        row.addWidget(self.path_field, stretch=1)
        choose_button = ActionButton(CHOOSE_FOLDER, variant="secondary")
        choose_button.setObjectName("chooseDataFolderButton")
        choose_button.clicked.connect(self._choose_candidate)
        row.addWidget(choose_button)
        layout.addLayout(row)

        actions = QVBoxLayout()
        self.use_button = ActionButton(USE_NEW_LOCATION, variant="secondary")
        self.use_button.setObjectName("useDataLocationButton")
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self._use_selected_location)
        actions.addWidget(self.use_button)
        self.migrate_button = ActionButton(MIGRATE_SETTINGS)
        self.migrate_button.setObjectName("migrateSettingsButton")
        self.migrate_button.setEnabled(False)
        self.migrate_button.clicked.connect(self._migrate_selected_location)
        actions.addWidget(self.migrate_button)
        layout.addLayout(actions)
        return card

    def _interface_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.md)

        title = QLabel(INTERFACE_SECTION_TITLE)
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        description = QLabel(INTERFACE_SECTION_DESCRIPTION)
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        layout.addWidget(description)
        scale = QLabel(f"{SCALE_LABEL}  ·  {SCALE_VALUE}")
        scale.setProperty("role", "muted")
        scale.setWordWrap(True)
        layout.addWidget(scale)
        return card

    def _version_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.md)

        title = QLabel(VERSION_SECTION_TITLE)
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        description = QLabel(VERSION_SECTION_DESCRIPTION)
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        layout.addWidget(description)
        installed_version = self.viewmodel.installed_version if self.viewmodel else "—"
        self.version_label = QLabel(INSTALLED_VERSION.format(version=installed_version))
        self.version_label.setObjectName("installedVersionLabel")
        layout.addWidget(self.version_label)
        self.update_status = QLabel(UPDATE_STATUS_IDLE)
        self.update_status.setObjectName("updateStatusLabel")
        self.update_status.setProperty("role", "muted")
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        self.update_button = ActionButton(CHECK_FOR_UPDATES, variant="secondary")
        self.update_button.setObjectName("checkForUpdatesButton")
        self.update_button.setEnabled(self.viewmodel is not None)
        self.update_button.clicked.connect(self._check_manually)
        layout.addWidget(self.update_button)
        return card

    def initialize_configuration(self) -> None:
        """Charger la configuration ou ouvrir le parcours de premier lancement."""
        if self.viewmodel is None:
            return
        try:
            if self.viewmodel.load() is None:
                self._show_first_launch()
            else:
                self.viewmodel.check_for_updates(manual=False)
        except ConfigurationError:
            QMessageBox.warning(
                self,
                DATA_LOCATION_ERROR_TITLE,
                DATA_LOCATION_RECOVERY,
            )
            self._choose_recovery_location()

    def _show_first_launch(self) -> None:
        if self.viewmodel is None:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle(FIRST_LAUNCH_TITLE)
        dialog.setText(FIRST_LAUNCH_MESSAGE)
        default_button = dialog.addButton(USE_DEFAULT_DATA, QMessageBox.ButtonRole.AcceptRole)
        custom_button = dialog.addButton(CHOOSE_OTHER_DATA, QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        if dialog.clickedButton() is default_button:
            self._initialize_path(self.viewmodel.default_data_path)
        elif dialog.clickedButton() is custom_button:
            self._choose_recovery_location()

    def _choose_candidate(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, SELECT_DATA_FOLDER)
        if not selected:
            return
        self._selected_path = Path(selected)
        self.path_field.setText(selected)
        self.use_button.setEnabled(True)
        self.migrate_button.setEnabled(True)

    def _choose_recovery_location(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, SELECT_DATA_FOLDER)
        if selected:
            self._initialize_path(Path(selected))

    def _initialize_path(self, path: Path) -> None:
        if self.viewmodel is None:
            return
        try:
            self.viewmodel.initialize(path)
            self.notification_requested.emit(DATA_LOCATION_UPDATED)
            self.viewmodel.check_for_updates(manual=False)
        except ConfigurationError as error:
            self._show_error(str(error))

    def _use_selected_location(self) -> None:
        if self.viewmodel is None or self._selected_path is None:
            return
        try:
            self.viewmodel.use_new_location(self._selected_path)
            self._clear_selection()
            self.notification_requested.emit(DATA_LOCATION_UPDATED)
        except ConfigurationError as error:
            self._show_error(str(error))

    def _migrate_selected_location(self) -> None:
        if self.viewmodel is None or self._selected_path is None:
            return
        try:
            self.viewmodel.migrate_to(self._selected_path)
            self._clear_selection()
            self.notification_requested.emit(DATA_LOCATION_MIGRATED)
        except ConfigurationError as error:
            self._show_error(str(error))

    def _set_current_path(self, path: str) -> None:
        self.path_field.setText(path)

    def _check_manually(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.check_for_updates(manual=True)

    def _update_started(self) -> None:
        self.update_button.setEnabled(False)
        self.update_status.setText(UPDATE_CHECKING)

    def _update_succeeded(self, result: UpdateCheckResult) -> None:
        if result.update_available:
            self.update_status.setText(UPDATE_AVAILABLE.format(version=result.latest_version))
        else:
            self.update_status.setText(UPDATE_UP_TO_DATE)

    def _update_failed(self, manual: bool) -> None:
        if manual:
            self.update_status.setText(UPDATE_CHECK_UNAVAILABLE)
        else:
            self.update_status.setText(UPDATE_STATUS_IDLE)

    def _update_finished(self) -> None:
        self.update_button.setEnabled(self.viewmodel is not None)

    def _clear_selection(self) -> None:
        self._selected_path = None
        self.use_button.setEnabled(False)
        self.migrate_button.setEnabled(False)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, DATA_LOCATION_ERROR_TITLE, message)
