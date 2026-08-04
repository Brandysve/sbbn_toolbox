from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread
from pytestqt.qtbot import QtBot

from sbbn_toolbox.services.config_service import ConfigService
from sbbn_toolbox.services.update_preparation_service import (
    PreparedUpdate,
    ProgressCallback,
    UpdatePreparationService,
)
from sbbn_toolbox.services.update_service import (
    ARCHIVE_NAME,
    CHECKSUM_NAME,
    UpdateCheckResult,
    UpdateService,
)
from sbbn_toolbox.viewmodels.settings_vm import SettingsViewModel


def stable_release() -> dict[str, object]:
    return {
        "tag_name": "v1.1.0",
        "html_url": "https://github.com/Brandysve/sbbn_toolbox/releases/tag/v1.1.0",
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": ARCHIVE_NAME, "browser_download_url": "https://example.test/app.zip"},
            {"name": CHECKSUM_NAME, "browser_download_url": "https://example.test/app.sha256"},
        ],
    }


def test_update_check_runs_outside_ui_thread(qtbot: QtBot, tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    config_service = ConfigService(program_dir)
    data_path = config_service.initialize(tmp_path / "données")
    calling_threads: list[QThread] = []

    def fetch(_url: str) -> object:
        calling_threads.append(QThread.currentThread())
        return stable_release()

    viewmodel = SettingsViewModel(
        config_service,
        UpdateService("1.0.0", fetcher=fetch),
    )
    viewmodel.load()
    results: list[object] = []
    viewmodel.update_check_succeeded.connect(results.append)

    with qtbot.waitSignals(
        [viewmodel.update_check_succeeded, viewmodel.update_check_finished],
        timeout=2_000,
    ):
        assert viewmodel.check_for_updates(manual=False)

    result = results[0]
    assert result.update_available
    assert calling_threads
    assert calling_threads[0] is not viewmodel.thread()
    assert (data_path / "update-check.json").is_file()


def test_manual_network_failure_is_reported_without_details(qtbot: QtBot, tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    config_service = ConfigService(program_dir)
    config_service.initialize(tmp_path / "données")

    def fail(_url: str) -> object:
        raise OSError("détail réseau sensible")

    viewmodel = SettingsViewModel(
        config_service,
        UpdateService("1.0.0", fetcher=fail),
    )
    viewmodel.load()

    with qtbot.waitSignal(viewmodel.update_check_failed, timeout=2_000) as failure:
        assert viewmodel.check_for_updates(manual=True)

    assert failure.args == [True]
    with qtbot.waitSignal(viewmodel.update_check_finished, timeout=2_000):
        pass


class RecordingPreparationService(UpdatePreparationService):
    def __init__(self) -> None:
        super().__init__()
        self.calling_threads: list[QThread] = []

    def prepare(
        self,
        release: UpdateCheckResult,
        data_path: Path,
        *,
        cancelled: Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> PreparedUpdate:
        self.calling_threads.append(QThread.currentThread())
        if progress is not None:
            progress(50, 100, 50)
        staging = data_path / "updates/staging" / ("a" * 32)
        extracted = staging / "extracted"
        extracted.mkdir(parents=True)
        return PreparedUpdate(
            "a" * 32,
            staging,
            staging / "update.zip",
            staging / "update.sha256",
            extracted,
            str(release.latest_version),
        )


def test_update_download_runs_outside_ui_thread(qtbot: QtBot, tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    config_service = ConfigService(program_dir)
    config_service.initialize(tmp_path / "données")
    preparation_service = RecordingPreparationService()
    update_service = UpdateService("1.0.0", fetcher=lambda _url: stable_release())
    viewmodel = SettingsViewModel(config_service, update_service, preparation_service)
    viewmodel.load()
    with qtbot.waitSignal(viewmodel.update_check_finished, timeout=2_000):
        viewmodel.check_for_updates(manual=True)

    progress: list[tuple[int, int | None, int | None]] = []
    viewmodel.update_download_progress.connect(lambda *values: progress.append(values))
    with qtbot.waitSignals(
        [viewmodel.update_download_succeeded, viewmodel.update_download_finished],
        timeout=2_000,
    ):
        assert viewmodel.download_update()

    assert progress == [(50, 100, 50)]
    assert preparation_service.calling_threads[0] is not viewmodel.thread()
    assert viewmodel.prepared_update is not None
