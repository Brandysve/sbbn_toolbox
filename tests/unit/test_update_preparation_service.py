import hashlib
import io
import os
import stat
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest

import sbbn_toolbox.services.update_preparation_service as preparation_module
from sbbn_toolbox.services.update_preparation_service import (
    ARCHIVE_NAME,
    UpdatePreparationCancelled,
    UpdatePreparationError,
    UpdatePreparationService,
)
from sbbn_toolbox.services.update_service import (
    ReleaseAssets,
    SemanticVersion,
    UpdateCheckResult,
)

ARCHIVE_URL = f"https://github.com/Brandysve/sbbn_toolbox/releases/download/v1.2.0/{ARCHIVE_NAME}"
CHECKSUM_URL = f"{ARCHIVE_URL}.sha256"


class FakeResponse:
    def __init__(
        self,
        content: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        failure: BaseException | None = None,
        read_limit: int | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._content = content
        self._position = 0
        self._failure = failure
        self._read_limit = read_limit
        self.closed = False

    def read(self, amount: int = -1) -> bytes:
        if self._failure is not None and self._position > 0:
            raise self._failure
        effective_amount = amount
        if self._read_limit is not None:
            effective_amount = min(amount, self._read_limit)
        if effective_amount < 0:
            effective_amount = len(self._content)
        chunk = self._content[self._position : self._position + effective_amount]
        self._position += len(chunk)
        return chunk

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)

    def close(self) -> None:
        self.closed = True


def make_zip(
    entries: list[tuple[str, bytes, int | None]] | None = None,
) -> bytes:
    selected_entries = entries or [
        ("SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
        ("SBBN-Toolbox/runtime/python312.dll", b"runtime", None),
        ("SBBN-Toolbox/README.txt", b"readme", None),
        ("SBBN-Toolbox/config.json", b'{"dataPath": "data"}', None),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content, mode in selected_entries:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            if mode is not None:
                info.create_system = 3
                info.external_attr = mode << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def checksum_content(archive: bytes, *, name: str = ARCHIVE_NAME) -> bytes:
    return f"{hashlib.sha256(archive).hexdigest()}  {name}\n".encode()


def release(*, digest: str | None = None) -> UpdateCheckResult:
    return UpdateCheckResult(
        SemanticVersion.parse("1.1.0"),
        SemanticVersion.parse("1.2.0"),
        ReleaseAssets(ARCHIVE_URL, CHECKSUM_URL, digest),
        datetime(2026, 8, 4, tzinfo=UTC),
        release_notes="Notes",
    )


def transport_for(
    archive: bytes,
    *,
    checksum: bytes | None = None,
    archive_headers: dict[str, str] | None = None,
    archive_response: FakeResponse | None = None,
) -> Callable[[str], FakeResponse]:
    responses = {
        CHECKSUM_URL: FakeResponse(checksum or checksum_content(archive)),
        ARCHIVE_URL: archive_response
        or FakeResponse(
            archive,
            headers=(
                archive_headers
                if archive_headers is not None
                else {"Content-Length": str(len(archive))}
            ),
        ),
    }

    def transport(url: str) -> FakeResponse:
        return responses[url]

    return transport


def operation_directories(data_path: Path) -> list[Path]:
    staging = data_path / "updates" / "staging"
    return list(staging.iterdir()) if staging.exists() else []


def test_successful_download_and_preparation_preserves_staging(tmp_path: Path) -> None:
    archive = make_zip()
    service = UpdatePreparationService(transport=transport_for(archive))

    prepared = service.prepare(release(), tmp_path)

    assert prepared.archive_path.read_bytes() == archive
    assert prepared.checksum_path.read_bytes() == checksum_content(archive)
    assert (prepared.extracted_path / "SBBN-Toolbox/SBBN-Toolbox.exe").is_file()
    assert (prepared.extracted_path / "SBBN-Toolbox/runtime/python312.dll").is_file()
    assert (prepared.extracted_path / "SBBN-Toolbox/README.txt").is_file()
    assert not (prepared.extracted_path / "SBBN-Toolbox/config.json").exists()
    assert (prepared.staging_path / ".prepared.json").is_file()
    assert operation_directories(tmp_path) == [prepared.staging_path]


def test_progress_with_known_size(tmp_path: Path) -> None:
    archive = make_zip()
    progress: list[tuple[int, int | None, int | None]] = []

    UpdatePreparationService(transport=transport_for(archive)).prepare(
        release(), tmp_path, progress=lambda *values: progress.append(values)
    )

    assert progress
    assert progress[-1] == (len(archive), len(archive), 100)


def test_progress_with_unknown_size(tmp_path: Path) -> None:
    archive = make_zip()
    progress: list[tuple[int, int | None, int | None]] = []

    UpdatePreparationService(transport=transport_for(archive, archive_headers={})).prepare(
        release(), tmp_path, progress=lambda *values: progress.append(values)
    )

    assert progress[-1] == (len(archive), None, None)


def test_cancellation_cleans_operation(tmp_path: Path) -> None:
    archive = make_zip()
    cancelled = Event()

    def cancel_after_progress(_downloaded: int, _total: int | None, _percent: int | None) -> None:
        cancelled.set()

    with pytest.raises(UpdatePreparationCancelled):
        UpdatePreparationService(
            transport=transport_for(
                archive,
                archive_response=FakeResponse(
                    archive,
                    headers={"Content-Length": str(len(archive))},
                    read_limit=20,
                ),
            )
        ).prepare(release(), tmp_path, cancelled=cancelled, progress=cancel_after_progress)

    assert operation_directories(tmp_path) == []


@pytest.mark.parametrize("error", (TimeoutError("timeout"), OSError("interruption")))
def test_timeout_or_network_interruption_cleans_staging(
    tmp_path: Path, error: BaseException
) -> None:
    archive = make_zip()
    failing_response = FakeResponse(
        archive,
        headers={"Content-Length": str(len(archive))},
        failure=error,
        read_limit=20,
    )

    with pytest.raises(UpdatePreparationError, match="interrompue"):
        UpdatePreparationService(
            transport=transport_for(archive, archive_response=failing_response)
        ).prepare(release(), tmp_path)

    assert operation_directories(tmp_path) == []


def test_connection_timeout_is_reported(tmp_path: Path) -> None:
    def timeout(_url: str) -> FakeResponse:
        raise TimeoutError("connexion")

    with pytest.raises(UpdatePreparationError, match="inaccessible"):
        UpdatePreparationService(transport=timeout).prepare(release(), tmp_path)

    assert operation_directories(tmp_path) == []


def test_http_error_is_rejected(tmp_path: Path) -> None:
    archive = make_zip()
    responses = {
        CHECKSUM_URL: FakeResponse(status=503),
        ARCHIVE_URL: FakeResponse(archive),
    }

    with pytest.raises(UpdatePreparationError, match="503"):
        UpdatePreparationService(transport=lambda url: responses[url]).prepare(release(), tmp_path)


def test_redirect_to_forbidden_domain_is_rejected(tmp_path: Path) -> None:
    response = FakeResponse(status=302, headers={"Location": "https://evil.example/update.sha256"})

    with pytest.raises(UpdatePreparationError, match="domaine"):
        UpdatePreparationService(transport=lambda _url: response).prepare(release(), tmp_path)


def test_http_and_unapproved_initial_urls_are_rejected(tmp_path: Path) -> None:
    insecure = release()
    insecure = UpdateCheckResult(
        insecure.installed_version,
        insecure.latest_version,
        ReleaseAssets("http://github.com/update.zip", CHECKSUM_URL),
        insecure.checked_at,
    )

    with pytest.raises(UpdatePreparationError, match="domaine"):
        UpdatePreparationService(transport=lambda _url: FakeResponse()).prepare(insecure, tmp_path)


def test_correct_hash_is_case_insensitive(tmp_path: Path) -> None:
    archive = make_zip()
    checksum = (
        checksum_content(archive)
        .upper()
        .replace(ARCHIVE_NAME.upper().encode(), ARCHIVE_NAME.encode())
    )

    prepared = UpdatePreparationService(
        transport=transport_for(archive, checksum=checksum)
    ).prepare(release(), tmp_path)

    assert prepared.archive_path.exists()


def test_incorrect_hash_removes_zip_and_staging(tmp_path: Path) -> None:
    archive = make_zip()
    checksum = f"{'0' * 64}  {ARCHIVE_NAME}\n".encode()

    with pytest.raises(UpdatePreparationError, match="SHA-256"):
        UpdatePreparationService(transport=transport_for(archive, checksum=checksum)).prepare(
            release(), tmp_path
        )

    assert operation_directories(tmp_path) == []


@pytest.mark.parametrize(
    "checksum",
    (
        b"abc  SBBN-Toolbox-Windows-x64.zip\n",
        f"{'a' * 64}  other.zip\n".encode(),
        f"{'a' * 64}\n".encode(),
    ),
)
def test_malformed_checksum_or_wrong_name_is_rejected(tmp_path: Path, checksum: bytes) -> None:
    archive = make_zip()

    with pytest.raises(UpdatePreparationError, match="SHA-256"):
        UpdatePreparationService(transport=transport_for(archive, checksum=checksum)).prepare(
            release(), tmp_path
        )


def test_contradictory_github_digest_is_rejected(tmp_path: Path) -> None:
    archive = make_zip()

    with pytest.raises(UpdatePreparationError, match="digest GitHub"):
        UpdatePreparationService(transport=transport_for(archive)).prepare(
            release(digest="f" * 64), tmp_path
        )


def prepare_invalid_archive(tmp_path: Path, archive: bytes) -> None:
    UpdatePreparationService(transport=transport_for(archive)).prepare(release(), tmp_path)


@pytest.mark.parametrize(
    "entries",
    (
        [("Other/SBBN-Toolbox.exe", b"exe", None)],
        [
            ("SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
            ("SBBN-Toolbox/runtime/x", b"x", None),
            ("SBBN-Toolbox/README.txt", b"r", None),
            ("SBBN-Toolbox/../escape.txt", b"bad", None),
        ],
        [
            ("/SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
            ("SBBN-Toolbox/runtime/x", b"x", None),
            ("SBBN-Toolbox/README.txt", b"r", None),
        ],
        [
            ("SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
            ("SBBN-Toolbox/runtime/CON.txt", b"x", None),
            ("SBBN-Toolbox/README.txt", b"r", None),
        ],
        [
            ("SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
            ("SBBN-Toolbox/runtime/bad?.dll", b"x", None),
            ("SBBN-Toolbox/README.txt", b"r", None),
        ],
        [
            ("C:/SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
            ("SBBN-Toolbox/runtime/x", b"x", None),
            ("SBBN-Toolbox/README.txt", b"r", None),
        ],
    ),
)
def test_invalid_roots_paths_and_windows_names_are_rejected(
    tmp_path: Path, entries: list[tuple[str, bytes, int | None]]
) -> None:
    with pytest.raises(UpdatePreparationError):
        prepare_invalid_archive(tmp_path, make_zip(entries))

    assert operation_directories(tmp_path) == []


def test_duplicate_entry_is_rejected(tmp_path: Path) -> None:
    entries = [
        ("SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
        ("SBBN-Toolbox/runtime/x", b"x", None),
        ("SBBN-Toolbox/README.txt", b"r", None),
        ("SBBN-Toolbox/README.txt", b"duplicate", None),
    ]

    with pytest.warns(UserWarning, match="Duplicate name"):
        archive = make_zip(entries)
    with pytest.raises(UpdatePreparationError, match="dupliquée"):
        prepare_invalid_archive(tmp_path, archive)


def test_symbolic_link_is_rejected(tmp_path: Path) -> None:
    entries = [
        ("SBBN-Toolbox/SBBN-Toolbox.exe", b"exe", None),
        ("SBBN-Toolbox/runtime/x", b"target", stat.S_IFLNK | 0o777),
        ("SBBN-Toolbox/README.txt", b"r", None),
    ]

    with pytest.raises(UpdatePreparationError, match="lien"):
        prepare_invalid_archive(tmp_path, make_zip(entries))


def test_archive_total_size_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preparation_module, "MAX_TOTAL_UNCOMPRESSED_BYTES", 5)

    with pytest.raises(UpdatePreparationError, match="volumineuse"):
        prepare_invalid_archive(tmp_path, make_zip())


def test_archive_entry_count_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preparation_module, "MAX_ARCHIVE_ENTRIES", 2)

    with pytest.raises(UpdatePreparationError, match="trop de fichiers"):
        prepare_invalid_archive(tmp_path, make_zip())


def test_current_program_is_never_modified(tmp_path: Path) -> None:
    program = tmp_path / "programme"
    program.mkdir()
    executable = program / "SBBN-Toolbox.exe"
    executable.write_bytes(b"active-version")
    data_path = tmp_path / "data"
    data_path.mkdir()

    UpdatePreparationService(transport=transport_for(make_zip())).prepare(release(), data_path)

    assert executable.read_bytes() == b"active-version"
    assert set(program.iterdir()) == {executable}


def test_only_old_abandoned_stagings_are_cleaned(tmp_path: Path) -> None:
    staging_root = tmp_path / "updates/staging"
    staging_root.mkdir(parents=True)
    old_abandoned = staging_root / ("a" * 32)
    old_abandoned.mkdir()
    (old_abandoned / "partial").write_text("x")
    old_time = time.time() - preparation_module.ABANDONED_STAGING_AGE_SECONDS - 60
    os.utime(old_abandoned, (old_time, old_time))
    unrelated = staging_root / "ne-pas-supprimer"
    unrelated.mkdir()
    recent = staging_root / ("b" * 32)
    recent.mkdir()

    prepared = UpdatePreparationService(transport=transport_for(make_zip())).prepare(
        release(), tmp_path
    )

    assert not old_abandoned.exists()
    assert unrelated.exists()
    assert recent.exists()
    assert prepared.staging_path.exists()
