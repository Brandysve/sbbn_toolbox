"""Détection sûre des releases stables de SBBN Toolbox."""

import json
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import total_ordering
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sbbn_toolbox.infrastructure.atomic_writer import atomic_write_json

REPOSITORY = "Brandysve/sbbn_toolbox"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
ARCHIVE_NAME = "SBBN-Toolbox-Windows-x64.zip"
CHECKSUM_NAME = f"{ARCHIVE_NAME}.sha256"
CACHE_FILENAME = "update-check.json"
CHECK_INTERVAL = timedelta(hours=24)
NETWORK_TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 1_000_000
SEMVER_PATTERN = re.compile(
    r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class UpdateCheckError(RuntimeError):
    """La vérification distante n'a pas pu aboutir."""


@total_ordering
@dataclass(frozen=True, slots=True)
class SemanticVersion:
    """Version SemVer comparable, avec préversions ordonnées selon la spécification."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        """Analyser une version ou un tag Git préfixé par ``v``."""
        match = SEMVER_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError("Version SemVer invalide.")
        prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
        if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in prerelease):
            raise ValueError("Version SemVer invalide.")
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{'.'.join(self.prerelease)}" if self.prerelease else base

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        own_core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if own_core != other_core:
            return own_core < other_core
        if not self.prerelease:
            return False
        if not other.prerelease:
            return True
        for own_part, other_part in zip(self.prerelease, other.prerelease, strict=False):
            if own_part == other_part:
                continue
            own_numeric = own_part.isdigit()
            other_numeric = other_part.isdigit()
            if own_numeric and other_numeric:
                return int(own_part) < int(other_part)
            if own_numeric != other_numeric:
                return own_numeric
            return own_part < other_part
        return len(self.prerelease) < len(other.prerelease)


@dataclass(frozen=True, slots=True)
class ReleaseAssets:
    """URLs des deux assets exigés pour une future mise à jour."""

    archive_url: str
    checksum_url: str
    archive_digest: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    """Résultat exploitable par l'interface, issu du réseau ou du cache."""

    installed_version: SemanticVersion
    latest_version: SemanticVersion
    assets: ReleaseAssets
    checked_at: datetime
    release_notes: str = ""
    from_cache: bool = False

    @property
    def update_available(self) -> bool:
        """Indiquer si la release stable est plus récente que l'installation."""
        return self.installed_version < self.latest_version


@dataclass(frozen=True, slots=True)
class _UpdateCache:
    last_attempt_at: datetime
    result: UpdateCheckResult | None


Fetcher = Callable[[str], object]


class UpdateService:
    """Consulter au plus quotidiennement la dernière release stable publique."""

    def __init__(self, installed_version: str, *, fetcher: Fetcher | None = None) -> None:
        self.installed_version = SemanticVersion.parse(installed_version)
        self._fetcher = fetcher or self._fetch_latest_release

    def check(
        self,
        data_path: Path,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> UpdateCheckResult:
        """Vérifier la release stable, sauf cache automatique encore valide."""
        checked_at = (now or datetime.now(UTC)).astimezone(UTC)
        cache_path = data_path / CACHE_FILENAME
        cached = self._read_cache(cache_path)
        if not force and cached is not None:
            age = checked_at - cached.last_attempt_at
            if timedelta(0) <= age < CHECK_INTERVAL:
                if cached.result is None:
                    raise UpdateCheckError("La vérification des mises à jour est indisponible.")
                return UpdateCheckResult(
                    self.installed_version,
                    cached.result.latest_version,
                    cached.result.assets,
                    cached.result.checked_at,
                    release_notes=cached.result.release_notes,
                    from_cache=True,
                )

        try:
            release = self._parse_release(self._fetcher(LATEST_RELEASE_URL), checked_at)
            atomic_write_json(cache_path, self._cache_payload(release))
            return release
        except (
            HTTPError,
            OSError,
            TimeoutError,
            URLError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            with suppress(OSError):
                atomic_write_json(cache_path, self._failed_cache_payload(checked_at, cached))
            raise UpdateCheckError("La vérification des mises à jour est indisponible.") from error

    def _parse_release(self, payload: object, checked_at: datetime) -> UpdateCheckResult:
        if not isinstance(payload, dict) or payload.get("draft") is not False:
            raise ValueError("Release GitHub invalide.")
        if payload.get("prerelease") is not False:
            raise ValueError("Les prereleases ne sont pas proposées automatiquement.")
        tag_name = payload.get("tag_name")
        assets_payload = payload.get("assets")
        if not isinstance(tag_name, str) or not isinstance(assets_payload, list):
            raise ValueError("Release GitHub invalide.")
        latest_version = SemanticVersion.parse(tag_name)
        if latest_version.prerelease:
            raise ValueError("Les prereleases ne sont pas proposées automatiquement.")

        urls: dict[str, str] = {}
        archive_digest: str | None = None
        for asset in assets_payload:
            if not isinstance(asset, dict):
                continue
            name = asset.get("name")
            url = asset.get("browser_download_url")
            if name in {ARCHIVE_NAME, CHECKSUM_NAME} and isinstance(url, str):
                urls[name] = url
                if name == ARCHIVE_NAME:
                    digest = asset.get("digest")
                    if digest is not None:
                        if (
                            not isinstance(digest, str)
                            or re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) is None
                        ):
                            raise ValueError("Digest GitHub invalide.")
                        archive_digest = digest.removeprefix("sha256:").lower()
        if set(urls) != {ARCHIVE_NAME, CHECKSUM_NAME}:
            raise ValueError("Les assets attendus sont absents.")
        notes = payload.get("body", "")
        if not isinstance(notes, str):
            raise ValueError("Notes de release invalides.")
        assets = ReleaseAssets(urls[ARCHIVE_NAME], urls[CHECKSUM_NAME], archive_digest)
        return UpdateCheckResult(
            self.installed_version,
            latest_version,
            assets,
            checked_at,
            release_notes=notes,
        )

    def _read_cache(self, path: Path) -> _UpdateCache | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != {
                "schemaVersion",
                "lastAttemptAt",
                "checkedAt",
                "latestVersion",
                "archiveUrl",
                "checksumUrl",
                "archiveDigest",
                "releaseNotes",
            }:
                return None
            if payload["schemaVersion"] != 1:
                return None
            last_attempt_at = datetime.fromisoformat(str(payload["lastAttemptAt"]))
            if last_attempt_at.tzinfo is None:
                return None
            optional_values = (
                payload["checkedAt"],
                payload["latestVersion"],
                payload["archiveUrl"],
                payload["checksumUrl"],
                payload["releaseNotes"],
            )
            if all(value is None for value in optional_values):
                return _UpdateCache(last_attempt_at.astimezone(UTC), None)
            if any(value is None for value in optional_values):
                return None
            checked_at = datetime.fromisoformat(str(payload["checkedAt"]))
            if checked_at.tzinfo is None:
                return None
            latest = SemanticVersion.parse(str(payload["latestVersion"]))
            archive_url = payload["archiveUrl"]
            checksum_url = payload["checksumUrl"]
            archive_digest = payload["archiveDigest"]
            release_notes = payload["releaseNotes"]
            if (
                not isinstance(archive_url, str)
                or not isinstance(checksum_url, str)
                or not isinstance(release_notes, str)
                or (
                    archive_digest is not None
                    and (
                        not isinstance(archive_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", archive_digest) is None
                    )
                )
            ):
                return None
            return _UpdateCache(
                last_attempt_at.astimezone(UTC),
                UpdateCheckResult(
                    self.installed_version,
                    latest,
                    ReleaseAssets(archive_url, checksum_url, archive_digest),
                    checked_at.astimezone(UTC),
                    release_notes=release_notes,
                    from_cache=True,
                ),
            )
        except (OSError, ValueError, json.JSONDecodeError, KeyError):
            return None

    @staticmethod
    def _cache_payload(result: UpdateCheckResult) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "lastAttemptAt": result.checked_at.isoformat(),
            "checkedAt": result.checked_at.isoformat(),
            "latestVersion": str(result.latest_version),
            "archiveUrl": result.assets.archive_url,
            "checksumUrl": result.assets.checksum_url,
            "archiveDigest": result.assets.archive_digest,
            "releaseNotes": result.release_notes,
        }

    @staticmethod
    def _failed_cache_payload(
        attempted_at: datetime,
        cached: _UpdateCache | None,
    ) -> dict[str, object]:
        result = cached.result if cached is not None else None
        return {
            "schemaVersion": 1,
            "lastAttemptAt": attempted_at.isoformat(),
            "checkedAt": result.checked_at.isoformat() if result else None,
            "latestVersion": str(result.latest_version) if result else None,
            "archiveUrl": result.assets.archive_url if result else None,
            "checksumUrl": result.assets.checksum_url if result else None,
            "archiveDigest": result.assets.archive_digest if result else None,
            "releaseNotes": result.release_notes if result else None,
        }

    @staticmethod
    def _fetch_latest_release(url: str) -> Any:
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "SBBN-Toolbox",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:  # noqa: S310
            content = response.read(MAX_RESPONSE_BYTES + 1)
        if len(content) > MAX_RESPONSE_BYTES:
            raise ValueError("Réponse GitHub trop volumineuse.")
        return json.loads(content)
