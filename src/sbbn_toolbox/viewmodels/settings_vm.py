"""Modèle de présentation des paramètres et des mises à jour."""

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from sbbn_toolbox import __version__
from sbbn_toolbox.services.config_service import ConfigService
from sbbn_toolbox.services.update_service import UpdateCheckError, UpdateCheckResult, UpdateService


class UpdateCheckWorker(QObject):
    """Exécuter une vérification réseau sans bloquer le thread UI."""

    succeeded = Signal(object)
    failed = Signal()

    def __init__(self, service: UpdateService, data_path: Path, *, force: bool) -> None:
        super().__init__()
        self._service = service
        self._data_path = data_path
        self._force = force

    @Slot()
    def run(self) -> None:
        """Effectuer la vérification et masquer les détails d'erreur réseau."""
        try:
            self.succeeded.emit(self._service.check(self._data_path, force=self._force))
        except UpdateCheckError:
            self.failed.emit()


class SettingsViewModel(QObject):
    """Coordonner l'interface Paramètres et le service de configuration."""

    data_path_changed = Signal(str)
    update_check_started = Signal()
    update_check_succeeded = Signal(object)
    update_check_failed = Signal(bool)
    update_check_finished = Signal()

    def __init__(
        self,
        service: ConfigService,
        update_service: UpdateService | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.update_service = update_service or UpdateService(__version__)
        self.current_data_path: Path | None = None
        self._update_thread: QThread | None = None
        self._update_worker: UpdateCheckWorker | None = None

    @property
    def installed_version(self) -> str:
        """Version issue des métadonnées générées depuis ``pyproject.toml``."""
        return __version__

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

    def check_for_updates(self, *, manual: bool) -> bool:
        """Démarrer une vérification asynchrone si la configuration est prête."""
        if self.current_data_path is None or self._update_thread is not None:
            return False
        thread = QThread(self)
        worker = UpdateCheckWorker(
            self.update_service,
            self.current_data_path,
            force=manual,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._update_succeeded)
        worker.failed.connect(lambda: self._update_failed(manual))
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._update_completed)
        self._update_thread = thread
        self._update_worker = worker
        self.update_check_started.emit()
        thread.start()
        return True

    @Slot(object)
    def _update_succeeded(self, result: UpdateCheckResult) -> None:
        self.update_check_succeeded.emit(result)

    @Slot()
    def _update_completed(self) -> None:
        self._update_thread = None
        self._update_worker = None
        self.update_check_finished.emit()

    def _update_failed(self, manual: bool) -> None:
        self.update_check_failed.emit(manual)

    def shutdown(self) -> None:
        """Attendre brièvement une vérification active avant fermeture."""
        if self._update_thread is not None and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait(6_000)

    def _set_current(self, path: Path) -> Path:
        self.current_data_path = path
        self.data_path_changed.emit(str(path))
        return path
