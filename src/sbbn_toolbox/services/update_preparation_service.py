"""Téléchargement et préparation sécurisés d'une mise à jour portable."""

import hashlib
import http.client
import re
import secrets
import shutil
import stat
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import Event
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

from sbbn_toolbox.infrastructure.atomic_writer import atomic_write_json
from sbbn_toolbox.services.update_service import ARCHIVE_NAME, UpdateCheckResult

UPDATES_DIRECTORY = "updates"
STAGING_DIRECTORY = "staging"
OPERATION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
CHECKSUM_LINE_PATTERN = re.compile(rf"^([0-9a-fA-F]{{64}})[ \t]+\*?{re.escape(ARCHIVE_NAME)}$")
ALLOWED_GITHUB_HOSTS = frozenset(
    {
        "api.github.com",
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 5
CONNECTION_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 15.0
DOWNLOAD_CHUNK_SIZE = 256 * 1024
MAX_ARCHIVE_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_CHECKSUM_BYTES = 4 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRY_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000
ABANDONED_STAGING_AGE_SECONDS = 7 * 24 * 60 * 60
WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*')
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class UpdatePreparationError(RuntimeError):
    """La mise à jour n'a pas pu être préparée en sécurité."""


class UpdatePreparationCancelled(UpdatePreparationError):
    """L'utilisateur a annulé la préparation."""


class ResponseStream(Protocol):
    """Réponse minimale requise, injectable dans les tests."""

    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def close(self) -> None: ...


Transport = Callable[[str], ResponseStream]
ProgressCallback = Callable[[int, int | None, int | None], None]


class _HttpsResponse:
    def __init__(
        self,
        connection: http.client.HTTPSConnection,
        response: http.client.HTTPResponse,
    ) -> None:
        self._connection = connection
        self._response = response
        self.status = response.status

    def read(self, amount: int = -1) -> bytes:
        return self._response.read(amount)

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._response.getheader(name, default)

    def close(self) -> None:
        self._response.close()
        self._connection.close()


@dataclass(frozen=True, slots=True)
class PreparedUpdate:
    """Staging complet et validé, sans action sur l'application active."""

    operation_id: str
    staging_path: Path
    archive_path: Path
    checksum_path: Path
    extracted_path: Path
    version: str


@dataclass(frozen=True, slots=True)
class _ValidatedEntry:
    info: zipfile.ZipInfo
    relative_path: PurePosixPath
    is_directory: bool
    skip: bool = False


class UpdatePreparationService:
    """Préparer une archive complète dans le dossier data, sans l'installer."""

    def __init__(self, *, transport: Transport | None = None) -> None:
        self._transport = transport or self._open_https_once

    def prepare(
        self,
        release: UpdateCheckResult,
        data_path: Path,
        *,
        cancelled: Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> PreparedUpdate:
        """Télécharger, vérifier puis extraire une release dans un staging isolé."""
        cancellation = cancelled or Event()
        callback = progress or (lambda _downloaded, _total, _percentage: None)
        try:
            staging_root = self._prepare_staging_root(data_path)
            self._cleanup_abandoned_stagings(staging_root)
            operation_id, operation_path = self._create_operation(staging_root)
        except UpdatePreparationError:
            raise
        except OSError as error:
            raise UpdatePreparationError(
                "Le dossier de préparation de la mise à jour est inaccessible."
            ) from error
        archive_path = operation_path / "update.zip"
        checksum_path = operation_path / "update.sha256"
        extracted_path = operation_path / "extracted"

        try:
            self._raise_if_cancelled(cancellation)
            self._validate_https_url(release.assets.archive_url)
            self._validate_https_url(release.assets.checksum_url)
            self._download(
                release.assets.checksum_url,
                checksum_path,
                cancellation,
                max_bytes=MAX_CHECKSUM_BYTES,
            )
            expected_hash = self._read_checksum(checksum_path)
            actual_hash = self._download(
                release.assets.archive_url,
                archive_path,
                cancellation,
                max_bytes=MAX_ARCHIVE_DOWNLOAD_BYTES,
                progress=callback,
                calculate_sha256=True,
            )
            if actual_hash is None or actual_hash.lower() != expected_hash.lower():
                archive_path.unlink(missing_ok=True)
                raise UpdatePreparationError("Le SHA-256 de la mise à jour ne correspond pas.")
            github_digest = release.assets.archive_digest
            if github_digest is not None and actual_hash.lower() != github_digest.lower():
                archive_path.unlink(missing_ok=True)
                raise UpdatePreparationError("Le digest GitHub de la mise à jour est invalide.")

            entries = self._validate_archive(archive_path, extracted_path)
            self._extract_archive(archive_path, extracted_path, entries, cancellation)
            atomic_write_json(
                operation_path / ".prepared.json",
                {
                    "schemaVersion": 1,
                    "version": str(release.latest_version),
                    "archive": "update.zip",
                    "checksum": "update.sha256",
                    "extracted": "extracted",
                    "configPolicy": "preserve-existing",
                },
            )
            return PreparedUpdate(
                operation_id,
                operation_path,
                archive_path,
                checksum_path,
                extracted_path,
                str(release.latest_version),
            )
        except Exception as error:
            self._safe_remove_operation(operation_path, staging_root)
            if isinstance(error, UpdatePreparationError):
                raise
            raise UpdatePreparationError("La préparation de la mise à jour a échoué.") from error

    def _download(
        self,
        url: str,
        destination: Path,
        cancelled: Event,
        *,
        max_bytes: int,
        progress: ProgressCallback | None = None,
        calculate_sha256: bool = False,
    ) -> str | None:
        response = self._open_response(url)
        digest = hashlib.sha256() if calculate_sha256 else None
        downloaded = 0
        try:
            if response.status != 200:
                raise UpdatePreparationError(
                    f"Le serveur de mise à jour a répondu avec le code {response.status}."
                )
            total = self._content_length(response.getheader("Content-Length"), max_bytes)
            with destination.open("xb") as stream:
                while True:
                    self._raise_if_cancelled(cancelled)
                    try:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    except (OSError, TimeoutError) as error:
                        raise UpdatePreparationError(
                            "La connexion a été interrompue pendant le téléchargement."
                        ) from error
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise UpdatePreparationError(
                            "Le téléchargement dépasse la taille autorisée."
                        )
                    stream.write(chunk)
                    if digest is not None:
                        digest.update(chunk)
                    if progress is not None:
                        percentage = min(100, downloaded * 100 // total) if total else None
                        progress(downloaded, total, percentage)
                stream.flush()
            if total is not None and downloaded != total:
                raise UpdatePreparationError("Le téléchargement est incomplet.")
            if progress is not None and downloaded == 0:
                progress(0, total, 100 if total == 0 else None)
            return digest.hexdigest() if digest is not None else None
        finally:
            response.close()

    def _open_response(self, url: str) -> ResponseStream:
        current_url = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            self._validate_https_url(current_url)
            try:
                response = self._transport(current_url)
            except (OSError, TimeoutError) as error:
                raise UpdatePreparationError(
                    "Le serveur de mise à jour est inaccessible."
                ) from error
            if response.status not in REDIRECT_STATUSES:
                return response
            location = response.getheader("Location")
            response.close()
            if redirect_count == MAX_REDIRECTS or not location:
                raise UpdatePreparationError("La redirection de téléchargement est invalide.")
            current_url = urljoin(current_url, location)
        raise UpdatePreparationError("Trop de redirections de téléchargement.")

    @staticmethod
    def _validate_https_url(url: str) -> None:
        parsed = urlsplit(url)
        try:
            port = parsed.port
        except ValueError as error:
            raise UpdatePreparationError("L’URL de téléchargement est invalide.") from error
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() not in ALLOWED_GITHUB_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise UpdatePreparationError("Le domaine de téléchargement n’est pas autorisé.")

    @staticmethod
    def _open_https_once(url: str) -> ResponseStream:
        parsed = urlsplit(url)
        if parsed.hostname is None:
            raise UpdatePreparationError("L’URL de téléchargement est invalide.")
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            port=parsed.port or 443,
            timeout=CONNECTION_TIMEOUT_SECONDS,
        )
        target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        try:
            connection.request(
                "GET",
                target,
                headers={"User-Agent": "SBBN-Toolbox", "Accept": "application/octet-stream"},
            )
            response = connection.getresponse()
            if connection.sock is not None:
                connection.sock.settimeout(READ_TIMEOUT_SECONDS)
            return _HttpsResponse(connection, response)
        except BaseException:
            connection.close()
            raise

    @staticmethod
    def _content_length(value: str | None, maximum: int) -> int | None:
        if value is None:
            return None
        if not value.isascii() or not value.isdigit():
            raise UpdatePreparationError("La taille annoncée du téléchargement est invalide.")
        length = int(value)
        if length > maximum:
            raise UpdatePreparationError("Le téléchargement dépasse la taille autorisée.")
        return length

    @staticmethod
    def _read_checksum(path: Path) -> str:
        try:
            content = path.read_bytes().decode("ascii").strip("\r\n")
        except (OSError, UnicodeDecodeError) as error:
            raise UpdatePreparationError("Le fichier SHA-256 est invalide.") from error
        match = CHECKSUM_LINE_PATTERN.fullmatch(content)
        if match is None or SHA256_PATTERN.fullmatch(match.group(1)) is None:
            raise UpdatePreparationError("Le fichier SHA-256 est invalide.")
        return match.group(1).lower()

    def _validate_archive(
        self,
        archive_path: Path,
        extracted_path: Path,
    ) -> list[_ValidatedEntry]:
        validated: list[_ValidatedEntry] = []
        normalized_names: set[str] = set()
        total_size = 0
        has_executable = False
        has_readme = False
        has_runtime = False
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise UpdatePreparationError("L’archive contient trop de fichiers.")
            for info in infos:
                entry = self._validate_entry(info, extracted_path)
                key = entry.relative_path.as_posix().casefold()
                if key in normalized_names:
                    raise UpdatePreparationError("L’archive contient une entrée dupliquée.")
                normalized_names.add(key)
                total_size += info.file_size
                if info.file_size > MAX_ENTRY_UNCOMPRESSED_BYTES:
                    raise UpdatePreparationError("Un fichier de l’archive est trop volumineux.")
                if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise UpdatePreparationError("L’archive décompressée est trop volumineuse.")
                if info.file_size > DOWNLOAD_CHUNK_SIZE and (
                    info.compress_size == 0
                    or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise UpdatePreparationError(
                        "L’archive présente un taux de compression anormal."
                    )
                name = entry.relative_path.as_posix()
                has_executable |= name == "SBBN-Toolbox/SBBN-Toolbox.exe"
                has_readme |= name == "SBBN-Toolbox/README.txt"
                has_runtime |= name == "SBBN-Toolbox/runtime" or name.startswith(
                    "SBBN-Toolbox/runtime/"
                )
                validated.append(entry)
        if not has_executable or not has_readme or not has_runtime:
            raise UpdatePreparationError("La structure de l’archive de mise à jour est invalide.")
        return validated

    def _validate_entry(self, info: zipfile.ZipInfo, extracted_path: Path) -> _ValidatedEntry:
        original_name = info.orig_filename
        normalized_name = original_name.replace("\\", "/")
        if (
            not normalized_name
            or "\x00" in original_name
            or normalized_name.startswith("/")
            or re.match(r"^[A-Za-z]:", normalized_name)
        ):
            raise UpdatePreparationError("L’archive contient un chemin absolu.")
        parts = PurePosixPath(normalized_name).parts
        if (
            not parts
            or parts[0] != "SBBN-Toolbox"
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise UpdatePreparationError("La racine de l’archive est invalide.")
        for component in parts:
            self._validate_windows_component(component)
        relative_path = PurePosixPath(*parts)
        destination = (extracted_path / Path(*parts)).resolve(strict=False)
        extracted_root = extracted_path.resolve(strict=False)
        if not destination.is_relative_to(extracted_root):
            raise UpdatePreparationError("Un chemin de l’archive sort du dossier autorisé.")

        unix_mode = info.external_attr >> 16
        file_type = stat.S_IFMT(unix_mode)
        is_directory = info.is_dir() or normalized_name.endswith("/")
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR} or (
            is_directory and file_type == stat.S_IFREG
        ):
            raise UpdatePreparationError("L’archive contient un lien ou fichier spécial.")
        if info.flag_bits & 0x1:
            raise UpdatePreparationError("L’archive contient un fichier chiffré.")
        skip = relative_path.as_posix().casefold() == "sbbn-toolbox/config.json".casefold()
        return _ValidatedEntry(info, relative_path, is_directory, skip)

    @staticmethod
    def _validate_windows_component(component: str) -> None:
        if (
            len(component) > 255
            or component.endswith((" ", "."))
            or any(character in WINDOWS_FORBIDDEN_CHARACTERS for character in component)
            or any(ord(character) < 32 for character in component)
            or component.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
        ):
            raise UpdatePreparationError("L’archive contient un nom incompatible avec Windows.")

    def _extract_archive(
        self,
        archive_path: Path,
        extracted_path: Path,
        entries: list[_ValidatedEntry],
        cancelled: Event,
    ) -> None:
        extracted_path.mkdir()
        extracted_root = extracted_path.resolve(strict=True)
        with zipfile.ZipFile(archive_path) as archive:
            for entry in entries:
                self._raise_if_cancelled(cancelled)
                if entry.skip:
                    continue
                destination = extracted_path / Path(*entry.relative_path.parts)
                resolved_destination = destination.resolve(strict=False)
                if not resolved_destination.is_relative_to(extracted_root):
                    raise UpdatePreparationError("Un chemin d’extraction sort du dossier autorisé.")
                if entry.is_directory:
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry.info) as source, destination.open("xb") as output:
                    while chunk := source.read(DOWNLOAD_CHUNK_SIZE):
                        self._raise_if_cancelled(cancelled)
                        output.write(chunk)

    @staticmethod
    def _raise_if_cancelled(cancelled: Event) -> None:
        if cancelled.is_set():
            raise UpdatePreparationCancelled("La préparation de la mise à jour a été annulée.")

    @staticmethod
    def _prepare_staging_root(data_path: Path) -> Path:
        data_root = data_path.resolve(strict=True)
        updates_root = data_root / UPDATES_DIRECTORY
        if updates_root.is_symlink():
            raise UpdatePreparationError("Le dossier de mises à jour n’est pas autorisé.")
        updates_root.mkdir(exist_ok=True)
        staging_root = updates_root / STAGING_DIRECTORY
        if staging_root.is_symlink():
            raise UpdatePreparationError("Le dossier de staging n’est pas autorisé.")
        staging_root.mkdir(exist_ok=True)
        resolved_staging = staging_root.resolve(strict=True)
        if resolved_staging.parent != updates_root.resolve(strict=True):
            raise UpdatePreparationError("Le dossier de staging n’est pas autorisé.")
        return resolved_staging

    @staticmethod
    def _create_operation(staging_root: Path) -> tuple[str, Path]:
        for _attempt in range(5):
            operation_id = secrets.token_hex(16)
            operation_path = staging_root / operation_id
            try:
                operation_path.mkdir()
            except FileExistsError:
                continue
            return operation_id, operation_path
        raise UpdatePreparationError("Impossible de créer un staging unique.")

    def _cleanup_abandoned_stagings(self, staging_root: Path) -> None:
        cutoff = time.time() - ABANDONED_STAGING_AGE_SECONDS
        for candidate in staging_root.iterdir():
            if (
                OPERATION_ID_PATTERN.fullmatch(candidate.name) is None
                or (candidate / ".prepared.json").is_file()
            ):
                continue
            try:
                if candidate.stat(follow_symlinks=False).st_mtime < cutoff:
                    self._safe_remove_operation(candidate, staging_root)
            except OSError:
                continue

    @staticmethod
    def _safe_remove_operation(operation_path: Path, staging_root: Path) -> None:
        resolved_root = staging_root.resolve(strict=True)
        if OPERATION_ID_PATTERN.fullmatch(operation_path.name) is None:
            raise UpdatePreparationError("Refus de nettoyer un staging non contrôlé.")
        if operation_path.is_symlink():
            operation_path.unlink(missing_ok=True)
            return
        resolved_operation = operation_path.resolve(strict=False)
        if resolved_operation.parent != resolved_root:
            raise UpdatePreparationError("Refus de nettoyer un staging non contrôlé.")
        if operation_path.exists():
            shutil.rmtree(operation_path)
