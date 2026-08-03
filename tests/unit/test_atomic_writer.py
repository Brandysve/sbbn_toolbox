import json
from pathlib import Path

import pytest

from sbbn_toolbox.infrastructure import atomic_writer


def test_atomic_json_write_replaces_target_without_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text('{"old": true}', encoding="utf-8")

    atomic_writer.atomic_write_json(target, {"schemaVersion": 1})

    assert json.loads(target.read_text(encoding="utf-8")) == {"schemaVersion": 1}
    assert not list(tmp_path.glob(".config.json.sbbn-partial-*"))


def test_atomic_json_write_preserves_target_and_cleans_partial_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "settings.json"
    original_content = '{"schemaVersion": 1, "pageFormat": "original"}'
    target.write_text(original_content, encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError(f"échec simulé pour {source.name} vers {destination.name}")

    monkeypatch.setattr(atomic_writer.os, "replace", fail_replace)

    with pytest.raises(OSError, match="échec simulé"):
        atomic_writer.atomic_write_json(target, {"schemaVersion": 1, "pageFormat": "A4"})

    assert target.read_text(encoding="utf-8") == original_content
    assert not list(tmp_path.glob(".settings.json.sbbn-partial-*"))
