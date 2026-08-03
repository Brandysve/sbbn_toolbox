"""Configuration portable et préférences autorisées de SBBN Toolbox."""

import json
import os
import stat
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from sbbn_toolbox.infrastructure.atomic_writer import atomic_write_json

SCHEMA_VERSION = 1
CONFIG_FILENAME = "config.json"
SETTINGS_FILENAME = "settings.json"
LOG_DIRECTORY_NAME = "logs"
LOG_FILENAME = "sbbn-toolbox.log"


class ConfigurationError(RuntimeError):
    """Erreur de configuration présentable sans détails techniques."""


class InvalidConfigurationError(ConfigurationError):
    """Le fichier de configuration ne respecte pas le schéma attendu."""


class DataDirectoryError(ConfigurationError):
    """Le dossier de données ne peut pas être utilisé en écriture."""


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Préférences persistantes strictement autorisées."""

    last_open_directory: str | None = None
    last_save_directory: str | None = None
    page_format: str = "original"
    margins_mm: int = 0
    interface: str = "automatic"

    def to_json(self) -> dict[str, object]:
        """Sérialiser les seules préférences autorisées."""
        return {
            "schemaVersion": SCHEMA_VERSION,
            "lastOpenDirectory": self.last_open_directory,
            "lastSaveDirectory": self.last_save_directory,
            "pageFormat": self.page_format,
            "marginsMm": self.margins_mm,
            "interface": self.interface,
        }

    @classmethod
    def from_json(cls, payload: object) -> "AppSettings":
        """Valider et filtrer un fichier de préférences."""
        if not isinstance(payload, dict):
            raise InvalidConfigurationError("Le fichier settings.json est invalide.")
        allowed = {
            "schemaVersion",
            "lastOpenDirectory",
            "lastSaveDirectory",
            "pageFormat",
            "marginsMm",
            "interface",
        }
        if set(payload) - allowed or payload.get("schemaVersion") != SCHEMA_VERSION:
            raise InvalidConfigurationError("Le fichier settings.json est invalide.")
        last_open = payload.get("lastOpenDirectory")
        last_save = payload.get("lastSaveDirectory")
        page_format = payload.get("pageFormat", "original")
        margins = payload.get("marginsMm", 0)
        interface = payload.get("interface", "automatic")
        if last_open is not None and not isinstance(last_open, str):
            raise InvalidConfigurationError("Le dernier dossier d’ouverture est invalide.")
        if last_save is not None and not isinstance(last_save, str):
            raise InvalidConfigurationError("Le dernier dossier d’enregistrement est invalide.")
        if not isinstance(page_format, str) or not isinstance(margins, int):
            raise InvalidConfigurationError("Les préférences de page sont invalides.")
        if not isinstance(interface, str):
            raise InvalidConfigurationError("Les préférences d’interface sont invalides.")
        return cls(last_open, last_save, page_format, margins, interface)


JsonWriter = Callable[[Path, Mapping[str, object]], None]


class ConfigService:
    """Gérer ``config.json`` et le dossier de données portable."""

    def __init__(
        self,
        program_dir: Path,
        *,
        json_writer: JsonWriter = atomic_write_json,
    ) -> None:
        self.program_dir = program_dir.resolve()
        self.config_path = self.program_dir / CONFIG_FILENAME
        self._write_json = json_writer

    @property
    def default_data_path(self) -> Path:
        """Dossier proposé au premier lancement."""
        return self.program_dir / "data"

    def load_data_path(self) -> Path | None:
        """Charger et valider le chemin configuré, ou signaler un premier lancement."""
        if not self.config_path.exists():
            return None
        payload = self._read_json(self.config_path, "Le fichier config.json est invalide.")
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schemaVersion", "dataPath"}
            or payload.get("schemaVersion") != SCHEMA_VERSION
            or not isinstance(payload.get("dataPath"), str)
            or not payload["dataPath"]
        ):
            raise InvalidConfigurationError("Le fichier config.json est invalide.")
        data_path = Path(payload["dataPath"])
        if not data_path.is_absolute():
            data_path = self.program_dir / data_path
            if not data_path.exists():
                return None
        self._prepare_data_directory(data_path, create_missing=True)
        return data_path

    def initialize(self, data_path: Path) -> Path:
        """Créer le dossier choisi et enregistrer sa configuration."""
        destination = data_path.resolve()
        self._prepare_data_directory(destination, create_missing=True)
        self._write_config(destination)
        return destination

    def use_new_location(self, data_path: Path) -> Path:
        """Utiliser un nouvel emplacement avec des préférences par défaut."""
        return self.initialize(data_path)

    def migrate_settings(self, current_path: Path, new_path: Path) -> Path:
        """Copier uniquement les préférences autorisées puis basculer la configuration."""
        source = current_path.resolve()
        destination = new_path.resolve()
        if source == destination:
            return source
        settings = self.read_settings(source)
        self._prepare_data_directory(destination, create_missing=True, settings=settings)
        if self.read_settings(destination) != settings:
            raise ConfigurationError("La validation des paramètres déplacés a échoué.")
        self._write_config(destination)
        source_settings = source / SETTINGS_FILENAME
        with suppress(OSError):
            source_settings.unlink(missing_ok=True)
        return destination

    def read_settings(self, data_path: Path) -> AppSettings:
        """Lire les préférences autorisées d'un dossier de données."""
        path = data_path / SETTINGS_FILENAME
        payload = self._read_json(path, "Le fichier settings.json est invalide.")
        return AppSettings.from_json(payload)

    def write_settings(self, data_path: Path, settings: AppSettings) -> None:
        """Écrire atomiquement les préférences autorisées."""
        self._ensure_writable_directory(data_path)
        try:
            self._write_json(data_path / SETTINGS_FILENAME, settings.to_json())
        except OSError as error:
            raise DataDirectoryError("Impossible d’écrire les paramètres.") from error

    def _write_config(self, data_path: Path) -> None:
        self._ensure_writable_directory(self.program_dir)
        try:
            self._write_json(
                self.config_path,
                {"schemaVersion": SCHEMA_VERSION, "dataPath": str(data_path)},
            )
        except OSError as error:
            raise ConfigurationError("Impossible d’écrire le fichier config.json.") from error

    def _prepare_data_directory(
        self,
        data_path: Path,
        *,
        create_missing: bool,
        settings: AppSettings | None = None,
    ) -> None:
        created_directories: list[Path] = []
        created_files: list[Path] = []
        try:
            if not data_path.exists() and create_missing:
                self._ensure_creatable(data_path)
                created_directories.extend(self._create_directory_chain(data_path))
            if not data_path.is_dir():
                raise DataDirectoryError("Le chemin de données n’est pas un dossier.")
            self._ensure_writable_directory(data_path)
            logs_path = data_path / LOG_DIRECTORY_NAME
            if not logs_path.exists():
                logs_path.mkdir()
                created_directories.append(logs_path)
            self._ensure_writable_directory(logs_path)
            settings_path = data_path / SETTINGS_FILENAME
            settings_existed = settings_path.exists()
            if settings is not None or not settings_existed:
                self._write_json(settings_path, (settings or AppSettings()).to_json())
                if not settings_path.exists():
                    raise DataDirectoryError("Impossible de créer le fichier settings.json.")
                if not settings_existed:
                    created_files.append(settings_path)
            else:
                self.read_settings(data_path)
            log_path = logs_path / LOG_FILENAME
            if not log_path.exists():
                log_path.touch()
                created_files.append(log_path)
        except (OSError, ConfigurationError) as error:
            self._clean_created_paths(created_files, created_directories)
            if isinstance(error, ConfigurationError):
                raise
            raise DataDirectoryError(
                "Le dossier de données est inaccessible ou en lecture seule."
            ) from error

    @staticmethod
    def _create_directory_chain(path: Path) -> list[Path]:
        missing: list[Path] = []
        candidate = path
        while not candidate.exists():
            missing.append(candidate)
            candidate = candidate.parent
        created: list[Path] = []
        for directory in reversed(missing):
            directory.mkdir()
            created.append(directory)
        return created

    @staticmethod
    def _clean_created_paths(files: list[Path], directories: list[Path]) -> None:
        for file_path in reversed(files):
            with suppress(OSError):
                file_path.unlink(missing_ok=True)
        for directory in reversed(directories):
            with suppress(OSError):
                directory.rmdir()

    @staticmethod
    def _ensure_creatable(path: Path) -> None:
        ancestor = path.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        ConfigService._ensure_writable_directory(ancestor)

    @staticmethod
    def _ensure_writable_directory(path: Path) -> None:
        try:
            mode = path.stat().st_mode
            if not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                raise DataDirectoryError("Le dossier est en lecture seule.")
            descriptor, probe_name = tempfile.mkstemp(dir=path, prefix=".sbbn-write-test-")
            os.close(descriptor)
            Path(probe_name).unlink()
        except OSError as error:
            raise DataDirectoryError(
                "Le dossier de données est inaccessible ou en lecture seule."
            ) from error

    @staticmethod
    def _read_json(path: Path, message: str) -> object:
        try:
            with path.open(encoding="utf-8") as stream:
                return json.load(stream)
        except (OSError, json.JSONDecodeError) as error:
            raise InvalidConfigurationError(message) from error
