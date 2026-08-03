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

Les tests Qt automatisés s'exécutent avec la plateforme hors écran et simulent
notamment les facteurs d'échelle 125 % et 150 %. La validation DPI Windows
native sera effectuée en Phase 6 sur l'exécutable compilé, sur Windows 10 et 11.

Pour lancer manuellement l'application avec une échelle simulée sous Linux ou
macOS :

```bash
QT_SCALE_FACTOR=1.25 python -m sbbn_toolbox
QT_SCALE_FACTOR=1.5 python -m sbbn_toolbox
```

Sous PowerShell :

```powershell
$env:QT_SCALE_FACTOR = "1.25"; python -m sbbn_toolbox
$env:QT_SCALE_FACTOR = "1.5"; python -m sbbn_toolbox
Remove-Item Env:QT_SCALE_FACTOR
```
