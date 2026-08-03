"""Écritures JSON atomiques limitées à leur fichier cible."""

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Écrire un objet JSON puis le remplacer atomiquement à destination."""
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.sbbn-partial-",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
