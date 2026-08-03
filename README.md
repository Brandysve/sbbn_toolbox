# SBBN Toolbox

Application Windows locale et portable pour convertir des images en PDF et
réorganiser puis fusionner des pages PDF.

Le dépôt se trouve actuellement à la **Phase 1** : il fournit le design system,
les quatre écrans et leur navigation, sans logique de traitement de documents
ni configuration persistante.

## Prérequis de développement

- Python 3.12
- Windows, Linux ou macOS pour le développement (le livrable cible Windows x64)

## Installation

```bash
python -m venv .venv
```

Sous Windows :

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
```

Sous Linux ou macOS :

```bash
source .venv/bin/activate
python -m pip install -r requirements.lock
```

## Commandes

```bash
python -m sbbn_toolbox
ruff check .
ruff format --check .
mypy src
pytest
```
