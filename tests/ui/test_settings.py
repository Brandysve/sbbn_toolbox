from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from pytestqt.qtbot import QtBot

from sbbn_toolbox.constants import DATA_LOCATION_UPDATED
from sbbn_toolbox.services.config_service import ConfigService
from sbbn_toolbox.ui.pages.settings_page import SettingsPage
from sbbn_toolbox.viewmodels.settings_vm import SettingsViewModel


def test_settings_page_exposes_distinct_location_actions(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    destination = tmp_path / "Données personnalisées"
    destination.mkdir()
    viewmodel = SettingsViewModel(ConfigService(program_dir))
    page = SettingsPage(viewmodel)
    qtbot.addWidget(page)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args: str(destination),
    )

    choose_button = page.findChild(type(page.use_button), "chooseDataFolderButton")
    assert choose_button is not None
    assert page.use_button.text() != page.migrate_button.text()
    assert not page.use_button.isEnabled()
    assert not page.migrate_button.isEnabled()

    qtbot.mouseClick(choose_button, Qt.MouseButton.LeftButton)

    assert page.use_button.isEnabled()
    assert page.migrate_button.isEnabled()

    with qtbot.waitSignal(page.notification_requested) as notification:
        qtbot.mouseClick(page.use_button, Qt.MouseButton.LeftButton)

    assert notification.args == [DATA_LOCATION_UPDATED]
    assert viewmodel.current_data_path == destination
    assert page.path_field.text() == str(destination)
