"""Générer atomiquement les métadonnées Windows depuis pyproject.toml."""

import argparse
import os
import re
import tempfile
import tomllib
from pathlib import Path

VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def read_project_version(pyproject_path: Path) -> str:
    """Lire et valider la version stable déclarée par le projet."""
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project")
    version: object = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError("La version stable de pyproject.toml est invalide.")
    return version


def render_version_info(version: str) -> str:
    """Produire le format de ressource attendu par PyInstaller."""
    major, minor, patch = (int(part) for part in version.split("."))
    file_version = f"{version}.0"
    return f'''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "040C04B0",
        [
          StringStruct("CompanyName", "SBBN"),
          StringStruct("FileDescription", "SBBN Toolbox"),
          StringStruct("FileVersion", "{file_version}"),
          StringStruct("InternalName", "SBBN-Toolbox"),
          StringStruct("OriginalFilename", "SBBN-Toolbox.exe"),
          StringStruct("ProductName", "SBBN Toolbox"),
          StringStruct("ProductVersion", "{file_version}"),
        ],
      )
    ]),
    VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
  ],
)
'''


def write_version_info(pyproject_path: Path, output_path: Path) -> None:
    """Écrire le résultat sans jamais laisser de fichier partiel."""
    content = render_version_info(read_project_version(pyproject_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.sbbn-partial-",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    write_version_info(arguments.pyproject, arguments.output)


if __name__ == "__main__":
    main()
