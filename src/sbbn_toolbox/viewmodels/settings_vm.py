"""Modèle de présentation du dossier de données."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from sbbn_toolbox.services.config_service import ConfigService


class SettingsViewModel(QObject):
    """Coordonner l'interface Paramètres et le service de configuration."""

    data_path_changed = Signal(str)

    def __init__(self, service: ConfigService) -> None:
        super().__init__()
        self.service = service
        self.current_data_path: Path | None = None

    @property
    def default_data_path(self) -> Path:
        """Chemin proposé pour le premier lancement."""
        return self.service.default_data_path

    def load(self) -> Path | None:
        """Charger la configuration existante."""
        self.current_data_path = self.service.load_data_path()
        if self.current_data_path is not None:
            self.data_path_changed.emit(str(self.current_data_path))
        return self.current_data_path

    def initialize(self, path: Path) -> Path:
        """Finaliser le premier lancement."""
        return self._set_current(self.service.initialize(path))

    def use_new_location(self, path: Path) -> Path:
        """Changer d'emplacement sans migration."""
        return self._set_current(self.service.use_new_location(path))

    def migrate_to(self, path: Path) -> Path:
        """Déplacer les paramètres actuels vers un nouvel emplacement."""
        if self.current_data_path is None:
            return self.initialize(path)
        return self._set_current(self.service.migrate_settings(self.current_data_path, path))

    def _set_current(self, path: Path) -> Path:
        self.current_data_path = path
        self.data_path_changed.emit(str(path))
        return path
