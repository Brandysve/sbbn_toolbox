"""Modèle de présentation des paramètres et des mises à jour."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot

from sbbn_toolbox import __version__
from sbbn_toolbox.services.config_service import ConfigService
from sbbn_toolbox.services.update_preparation_service import (
    PreparedUpdate,
    UpdatePreparationCancelled,
    UpdatePreparationError,
    UpdatePreparationService,
)
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


class UpdateDownloadWorker(QObject):
    """Préparer la mise à jour hors du thread UI avec annulation coopérative."""

    progress_changed = Signal(int, object, object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        service: UpdatePreparationService,
        release: UpdateCheckResult,
        data_path: Path,
        cancellation: Event,
    ) -> None:
        super().__init__()
        self._service = service
        self._release = release
        self._data_path = data_path
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        """Télécharger et préparer, sans exposer de trace technique à l'interface."""
        try:
            prepared = self._service.prepare(
                self._release,
                self._data_path,
                cancelled=self._cancellation,
                progress=self.progress_changed.emit,
            )
            self.succeeded.emit(prepared)
        except UpdatePreparationCancelled:
            self.cancelled.emit()
        except UpdatePreparationError as error:
            self.failed.emit(str(error))


class SettingsViewModel(QObject):
    """Coordonner l'interface Paramètres et le service de configuration."""

    data_path_changed = Signal(str)
    update_check_started = Signal()
    update_check_succeeded = Signal(object)
    update_check_failed = Signal(bool)
    update_check_finished = Signal()
    update_download_started = Signal()
    update_download_progress = Signal(int, object, object)
    update_download_succeeded = Signal(object)
    update_download_failed = Signal(str)
    update_download_cancelled = Signal()
    update_download_finished = Signal()

    def __init__(
        self,
        service: ConfigService,
        update_service: UpdateService | None = None,
        preparation_service: UpdatePreparationService | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.update_service = update_service or UpdateService(__version__)
        self.preparation_service = preparation_service or UpdatePreparationService()
        self.current_data_path: Path | None = None
        self.latest_release: UpdateCheckResult | None = None
        self.prepared_update: PreparedUpdate | None = None
        self._update_thread: QThread | None = None
        self._update_worker: UpdateCheckWorker | None = None
        self._download_thread: QThread | None = None
        self._download_worker: UpdateDownloadWorker | None = None
        self._download_cancellation: Event | None = None

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
        self.latest_release = result
        self.update_check_succeeded.emit(result)

    @Slot()
    def _update_completed(self) -> None:
        self._update_thread = None
        self._update_worker = None
        self.update_check_finished.emit()

    def _update_failed(self, manual: bool) -> None:
        self.update_check_failed.emit(manual)

    def download_update(self) -> bool:
        """Démarrer la préparation de la release plus récente déjà validée."""
        release = self.latest_release
        if (
            self.current_data_path is None
            or release is None
            or not release.update_available
            or self._download_thread is not None
        ):
            return False
        thread = QThread(self)
        cancellation = Event()
        worker = UpdateDownloadWorker(
            self.preparation_service,
            release,
            self.current_data_path,
            cancellation,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(self.update_download_progress.emit)
        worker.succeeded.connect(self._download_succeeded)
        worker.failed.connect(self.update_download_failed.emit)
        worker.cancelled.connect(self.update_download_cancelled.emit)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._download_completed)
        self._download_thread = thread
        self._download_worker = worker
        self._download_cancellation = cancellation
        self.prepared_update = None
        self.update_download_started.emit()
        thread.start()
        return True

    def cancel_update_download(self) -> None:
        """Demander l'annulation au prochain point sûr."""
        if self._download_cancellation is not None:
            self._download_cancellation.set()

    @Slot(object)
    def _download_succeeded(self, prepared: PreparedUpdate) -> None:
        self.prepared_update = prepared
        self.update_download_succeeded.emit(prepared)

    @Slot()
    def _download_completed(self) -> None:
        self._download_thread = None
        self._download_worker = None
        self._download_cancellation = None
        self.update_download_finished.emit()

    def shutdown(self) -> None:
        """Attendre brièvement une vérification active avant fermeture."""
        if self._update_thread is not None and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait(6_000)
        if self._download_thread is not None and self._download_thread.isRunning():
            self.cancel_update_download()
            self._download_thread.quit()
            self._download_thread.wait(16_000)

    def _set_current(self, path: Path) -> Path:
        self.current_data_path = path
        self.data_path_changed.emit(str(path))
        return path
