import json
import stat
from collections.abc import Mapping
from pathlib import Path

import pytest

from sbbn_toolbox.infrastructure.atomic_writer import atomic_write_json
from sbbn_toolbox.services.config_service import (
    AppSettings,
    ConfigService,
    ConfigurationError,
    DataDirectoryError,
    InvalidConfigurationError,
)


def read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def assert_data_layout(path: Path) -> None:
    assert (path / "settings.json").is_file()
    assert (path / "logs" / "sbbn-toolbox.log").is_file()


def test_first_launch_has_no_configuration(tmp_path: Path) -> None:
    service = ConfigService(tmp_path / "programme")
    service.program_dir.mkdir()

    assert service.load_data_path() is None
    assert not service.config_path.exists()


def test_first_launch_can_use_default_data_directory(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    service = ConfigService(program_dir)

    selected = service.initialize(service.default_data_path)

    assert selected == program_dir / "data"
    assert read_json(service.config_path) == {
        "schemaVersion": 1,
        "dataPath": str(program_dir / "data"),
    }
    assert_data_layout(selected)


def test_first_launch_can_use_custom_unicode_directory(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme avec espaces"
    program_dir.mkdir()
    selected_path = tmp_path / "Données été 你好"
    service = ConfigService(program_dir)

    selected = service.initialize(selected_path)

    assert selected == selected_path
    assert read_json(service.config_path)["dataPath"] == str(selected_path)  # type: ignore[index]
    assert "Données été 你好" in service.config_path.read_text(encoding="utf-8")
    assert_data_layout(selected_path)


def test_restart_loads_existing_configuration(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    data_path = tmp_path / "données"
    ConfigService(program_dir).initialize(data_path)

    restarted_service = ConfigService(program_dir)

    assert restarted_service.load_data_path() == data_path
    assert restarted_service.read_settings(data_path) == AppSettings()


def test_missing_configured_directory_is_created(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    missing_path = tmp_path / "absent" / "données"
    atomic_write_json(
        program_dir / "config.json",
        {"schemaVersion": 1, "dataPath": str(missing_path)},
    )

    loaded = ConfigService(program_dir).load_data_path()

    assert loaded == missing_path
    assert_data_layout(missing_path)


def test_read_only_directory_is_rejected(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    read_only_path = tmp_path / "lecture-seule"
    read_only_path.mkdir()
    read_only_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(DataDirectoryError, match="lecture seule"):
            ConfigService(program_dir).initialize(read_only_path)
    finally:
        read_only_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    assert not (program_dir / "config.json").exists()


@pytest.mark.parametrize(
    "payload",
    (
        "{invalid",
        '{"schemaVersion": 1, "dataPath": "/tmp", "history": []}',
        '{"schemaVersion": 2, "dataPath": "/tmp"}',
    ),
)
def test_invalid_config_json_is_rejected(tmp_path: Path, payload: str) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    (program_dir / "config.json").write_text(payload, encoding="utf-8")

    with pytest.raises(InvalidConfigurationError):
        ConfigService(program_dir).load_data_path()


def test_change_location_without_migration_uses_default_settings(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    old_path = tmp_path / "ancien"
    new_path = tmp_path / "nouveau"
    service = ConfigService(program_dir)
    service.initialize(old_path)
    old_settings = AppSettings(page_format="A4", margins_mm=12, interface="compact")
    service.write_settings(old_path, old_settings)

    service.use_new_location(new_path)

    assert service.load_data_path() == new_path
    assert service.read_settings(new_path) == AppSettings()
    assert service.read_settings(old_path) == old_settings


def test_change_location_with_migration_copies_allowed_settings(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    old_path = tmp_path / "ancien"
    new_path = tmp_path / "nouveau"
    service = ConfigService(program_dir)
    service.initialize(old_path)
    settings = AppSettings(
        last_open_directory="D:/Dossiers",
        last_save_directory="D:/Sorties",
        page_format="A4",
        margins_mm=10,
        interface="comfortable",
    )
    service.write_settings(old_path, settings)

    service.migrate_settings(old_path, new_path)

    assert service.load_data_path() == new_path
    assert service.read_settings(new_path) == settings
    assert not (old_path / "settings.json").exists()
    assert (old_path / "logs" / "sbbn-toolbox.log").exists()


def test_migration_failure_keeps_old_configuration_and_settings(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    old_path = tmp_path / "ancien"
    new_path = tmp_path / "nouveau"
    regular_service = ConfigService(program_dir)
    regular_service.initialize(old_path)
    settings = AppSettings(page_format="A4")
    regular_service.write_settings(old_path, settings)

    def fail_config_write(path: Path, payload: Mapping[str, object]) -> None:
        if path.name == "config.json":
            raise OSError("échec simulé")
        atomic_write_json(path, payload)

    failing_service = ConfigService(program_dir, json_writer=fail_config_write)

    with pytest.raises(ConfigurationError, match="config.json"):
        failing_service.migrate_settings(old_path, new_path)

    assert regular_service.load_data_path() == old_path
    assert regular_service.read_settings(old_path) == settings


def test_invalid_settings_json_is_rejected(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    data_path = tmp_path / "données"
    service = ConfigService(program_dir)
    service.initialize(data_path)
    (data_path / "settings.json").write_text('{"recentDocuments": ["secret.pdf"]}')

    with pytest.raises(InvalidConfigurationError):
        service.read_settings(data_path)


def test_persistent_files_contain_no_documentary_data(tmp_path: Path) -> None:
    program_dir = tmp_path / "programme"
    program_dir.mkdir()
    data_path = tmp_path / "données"
    service = ConfigService(program_dir)
    service.initialize(data_path)

    config_payload = read_json(service.config_path)
    settings_payload = read_json(data_path / "settings.json")
    log_content = (data_path / "logs" / "sbbn-toolbox.log").read_text(encoding="utf-8")

    assert isinstance(config_payload, dict)
    assert set(config_payload) == {"schemaVersion", "dataPath"}
    assert isinstance(settings_payload, dict)
    assert set(settings_payload) == {
        "schemaVersion",
        "lastOpenDirectory",
        "lastSaveDirectory",
        "pageFormat",
        "marginsMm",
        "interface",
    }
    serialized = json.dumps([config_payload, settings_payload, log_content]).lower()
    assert "document" not in serialized
    assert "history" not in serialized
    assert "recent" not in serialized
    assert ".pdf" not in serialized


def test_packaged_relative_default_prompts_until_data_is_initialized(tmp_path: Path) -> None:
    program_dir = tmp_path / "SBBN-Toolbox"
    program_dir.mkdir()
    service = ConfigService(program_dir)
    service.config_path.write_text(
        '{"schemaVersion": 1, "dataPath": "data"}',
        encoding="utf-8",
    )

    assert service.load_data_path() is None

    initialized = service.initialize(service.default_data_path)

    assert initialized == program_dir / "data"
    assert service.load_data_path() == initialized


def test_packaged_relative_data_path_is_resolved_from_program_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_dir = tmp_path / "SBBN-Toolbox"
    program_dir.mkdir()
    service = ConfigService(program_dir)
    service.initialize(program_dir / "data")
    service.config_path.write_text(
        '{"schemaVersion": 1, "dataPath": "data"}',
        encoding="utf-8",
    )
    unrelated_working_directory = tmp_path / "ailleurs"
    unrelated_working_directory.mkdir()
    monkeypatch.chdir(unrelated_working_directory)

    assert service.load_data_path() == program_dir / "data"
