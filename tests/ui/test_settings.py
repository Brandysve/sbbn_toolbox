from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel
from pytestqt.qtbot import QtBot

from sbbn_toolbox.constants import DATA_LOCATION_UPDATED
from sbbn_toolbox.services.config_service import ConfigService
from sbbn_toolbox.services.update_service import ARCHIVE_NAME, CHECKSUM_NAME, UpdateService
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


def test_settings_page_displays_version_and_manual_update_result(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    config_service = ConfigService(program_dir)
    config_service.initialize(tmp_path / "données")
    release = {
        "tag_name": "v1.1.0",
        "html_url": "https://github.com/Brandysve/sbbn_toolbox/releases/tag/v1.1.0",
        "body": "Corrections et améliorations.",
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": ARCHIVE_NAME, "browser_download_url": "https://example.test/app.zip"},
            {"name": CHECKSUM_NAME, "browser_download_url": "https://example.test/app.sha256"},
        ],
    }
    viewmodel = SettingsViewModel(
        config_service,
        UpdateService("1.0.0", fetcher=lambda _url: release),
    )
    viewmodel.load()
    page = SettingsPage(viewmodel)
    qtbot.addWidget(page)

    assert viewmodel.installed_version in page.version_label.text()
    with qtbot.waitSignal(viewmodel.update_check_finished, timeout=2_000):
        qtbot.mouseClick(page.update_button, Qt.MouseButton.LeftButton)

    assert page.update_button.isEnabled()
    assert "1.1.0" in page.update_status.text()
    assert "disponible" in page.update_status.text()
    assert page.download_button.isEnabled()
    assert all(
        "Corrections et améliorations." not in label.text() for label in page.findChildren(QLabel)
    )
    assert page.findChild(type(page.download_button), "installUpdateButton") is None
    opened_urls: list[str] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    assert not page.whats_new_button.isHidden()
    qtbot.mouseClick(page.whats_new_button, Qt.MouseButton.LeftButton)
    assert opened_urls == ["https://github.com/Brandysve/sbbn_toolbox/releases/tag/v1.1.0"]

    viewmodel.update_download_started.emit()
    assert not page.cancel_download_button.isHidden()
    assert not page.download_button.isEnabled()
    viewmodel.update_download_progress.emit(512, 1_024, 50)
    assert page.update_status.text() == "512 / 1024 octets (50 %)"
    viewmodel.update_download_succeeded.emit(object())
    viewmodel.update_download_finished.emit()
    assert page.update_status.text() == "Mise à jour prête à être installée."
    assert page.cancel_download_button.isHidden()


def test_update_section_stays_compact_and_never_loads_readme_or_release_body(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    (program_dir / "README.txt").write_text("CONTENU README INTERDIT", encoding="utf-8")
    config_service = ConfigService(program_dir)
    config_service.initialize(tmp_path / "données")
    long_remote_body = "# Nouveautés\n<script>interdit()</script>\n" + ("texte " * 10_000)
    release = {
        "tag_name": "v1.1.0",
        "html_url": "https://github.com/Brandysve/sbbn_toolbox/releases/tag/v1.1.0",
        "body": long_remote_body,
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": ARCHIVE_NAME, "browser_download_url": "https://example.test/app.zip"},
            {"name": CHECKSUM_NAME, "browser_download_url": "https://example.test/app.sha256"},
        ],
    }
    viewmodel = SettingsViewModel(
        config_service,
        UpdateService("1.1.0", fetcher=lambda _url: release),
    )
    viewmodel.load()
    page = SettingsPage(viewmodel)
    qtbot.addWidget(page)
    card = page.findChild(QFrame, "versionUpdateCard")
    assert card is not None
    initial_height = card.sizeHint().height()

    with qtbot.waitSignal(viewmodel.update_check_finished, timeout=2_000):
        qtbot.mouseClick(page.update_button, Qt.MouseButton.LeftButton)

    displayed_text = "\n".join(label.text() for label in page.findChildren(QLabel))
    assert "CONTENU README INTERDIT" not in displayed_text
    assert "<script>" not in displayed_text
    assert "texte texte" not in displayed_text
    assert not page.download_button.isEnabled()
    assert page.whats_new_button.isHidden()
    assert card.sizeHint().height() == initial_height
    assert card.sizeHint().height() < 300
