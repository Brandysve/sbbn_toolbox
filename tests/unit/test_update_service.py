import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sbbn_toolbox.services.update_service import (
    ARCHIVE_NAME,
    CHECKSUM_NAME,
    LATEST_RELEASE_URL,
    SemanticVersion,
    UpdateCheckError,
    UpdateService,
)


def release_payload(version: str = "v1.1.0") -> dict[str, object]:
    return {
        "tag_name": version,
        "html_url": f"https://github.com/Brandysve/sbbn_toolbox/releases/tag/{version}",
        "body": "Notes de la version stable.",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": ARCHIVE_NAME,
                "browser_download_url": f"https://example.test/{ARCHIVE_NAME}",
                "digest": f"sha256:{'a' * 64}",
            },
            {
                "name": CHECKSUM_NAME,
                "browser_download_url": f"https://example.test/{CHECKSUM_NAME}",
            },
        ],
    }


@pytest.mark.parametrize(
    ("older", "newer"),
    (
        ("1.0.0", "1.0.1"),
        ("1.9.9", "2.0.0"),
        ("1.0.0-alpha", "1.0.0"),
        ("1.0.0-alpha.1", "1.0.0-alpha.beta"),
        ("1.0.0-beta.2", "1.0.0-beta.11"),
    ),
)
def test_semver_orders_versions(older: str, newer: str) -> None:
    assert SemanticVersion.parse(older) < SemanticVersion.parse(newer)
    assert not SemanticVersion.parse(newer) < SemanticVersion.parse(older)


@pytest.mark.parametrize("value", ("1", "1.0", "01.0.0", "1.0.0-01", "version-1.0.0"))
def test_semver_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        SemanticVersion.parse(value)


def test_stable_release_identifies_zip_and_checksum(tmp_path: Path) -> None:
    requested_urls: list[str] = []

    def fetch(url: str) -> object:
        requested_urls.append(url)
        return release_payload()

    checked_at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    result = UpdateService("1.0.0", fetcher=fetch).check(tmp_path, now=checked_at)

    assert requested_urls == [LATEST_RELEASE_URL]
    assert result.update_available
    assert str(result.latest_version) == "1.1.0"
    assert result.assets.archive_url.endswith(ARCHIVE_NAME)
    assert result.assets.checksum_url.endswith(CHECKSUM_NAME)
    assert result.assets.archive_digest == "a" * 64
    assert result.release_url.endswith("/releases/tag/v1.1.0")
    assert not result.from_cache
    assert json.loads((tmp_path / "update-check.json").read_text(encoding="utf-8")) == {
        "schemaVersion": 1,
        "lastAttemptAt": checked_at.isoformat(),
        "checkedAt": checked_at.isoformat(),
        "latestVersion": "1.1.0",
        "archiveUrl": f"https://example.test/{ARCHIVE_NAME}",
        "checksumUrl": f"https://example.test/{CHECKSUM_NAME}",
        "archiveDigest": "a" * 64,
        "releaseUrl": "https://github.com/Brandysve/sbbn_toolbox/releases/tag/v1.1.0",
    }


def test_automatic_check_uses_cache_for_24_hours(tmp_path: Path) -> None:
    calls = 0

    def fetch(_url: str) -> object:
        nonlocal calls
        calls += 1
        return release_payload()

    service = UpdateService("1.0.0", fetcher=fetch)
    first_check = datetime(2026, 8, 4, 10, tzinfo=UTC)

    service.check(tmp_path, now=first_check)
    cached = service.check(tmp_path, now=first_check + timedelta(hours=23, minutes=59))
    refreshed = service.check(tmp_path, now=first_check + timedelta(hours=24))

    assert calls == 2
    assert cached.from_cache
    assert not refreshed.from_cache


def test_manual_check_bypasses_recent_cache(tmp_path: Path) -> None:
    versions = iter((release_payload("v1.1.0"), release_payload("v1.2.0")))
    service = UpdateService("1.0.0", fetcher=lambda _url: next(versions))
    now = datetime(2026, 8, 4, 10, tzinfo=UTC)

    service.check(tmp_path, now=now)
    result = service.check(tmp_path, force=True, now=now + timedelta(minutes=1))

    assert str(result.latest_version) == "1.2.0"
    assert not result.from_cache


@pytest.mark.parametrize(
    "payload",
    (
        {**release_payload(), "prerelease": True},
        {**release_payload(), "draft": True},
        release_payload("v1.1.0-rc.1"),
        {**release_payload(), "assets": []},
    ),
)
def test_invalid_or_unstable_release_is_rejected_silently(tmp_path: Path, payload: object) -> None:
    service = UpdateService("1.0.0", fetcher=lambda _url: payload)

    with pytest.raises(UpdateCheckError, match="indisponible"):
        service.check(tmp_path)

    cache = json.loads((tmp_path / "update-check.json").read_text(encoding="utf-8"))
    assert cache["latestVersion"] is None


def test_network_failure_does_not_modify_existing_cache(tmp_path: Path) -> None:
    now = datetime(2026, 8, 4, 10, tzinfo=UTC)
    UpdateService("1.0.0", fetcher=lambda _url: release_payload()).check(tmp_path, now=now)
    cache_path = tmp_path / "update-check.json"

    def fail(_url: str) -> object:
        raise OSError("hors ligne")

    with pytest.raises(UpdateCheckError):
        UpdateService("1.0.0", fetcher=fail).check(
            tmp_path,
            force=True,
            now=now + timedelta(minutes=1),
        )

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache["latestVersion"] == "1.1.0"
    assert cache["lastAttemptAt"] == (now + timedelta(minutes=1)).isoformat()


def test_failed_automatic_attempt_is_not_repeated_within_24_hours(tmp_path: Path) -> None:
    calls = 0

    def fail(_url: str) -> object:
        nonlocal calls
        calls += 1
        raise OSError("hors ligne")

    service = UpdateService("1.0.0", fetcher=fail)
    now = datetime(2026, 8, 4, 10, tzinfo=UTC)

    with pytest.raises(UpdateCheckError):
        service.check(tmp_path, now=now)
    with pytest.raises(UpdateCheckError):
        service.check(tmp_path, now=now + timedelta(hours=23))

    assert calls == 1


@pytest.mark.parametrize(
    "url",
    (
        "http://github.com/Brandysve/sbbn_toolbox/releases/tag/v1.1.0",
        "https://evil.example/Brandysve/sbbn_toolbox/releases/tag/v1.1.0",
        "https://github.com/another/repository/releases/tag/v1.1.0",
        "https://github.com/Brandysve/sbbn_toolbox/releases/tag/v9.9.9",
    ),
)
def test_unexpected_release_page_url_is_rejected(tmp_path: Path, url: str) -> None:
    payload = {**release_payload(), "html_url": url}

    with pytest.raises(UpdateCheckError):
        UpdateService("1.0.0", fetcher=lambda _url: payload).check(tmp_path)
