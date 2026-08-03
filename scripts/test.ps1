$ErrorActionPreference = "Stop"
ruff check .
ruff format --check .
mypy src
pytest
