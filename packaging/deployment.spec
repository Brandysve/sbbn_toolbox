# Paramètres de référence appliqués par scripts/build_windows.ps1.
# Le script reste la source exécutable afin de contrôler chaque échec PowerShell.
mode=standalone
python=CPython 3.12 x64
compiler=MSVC 2022+
plugin=pyside6
qt_plugins=platforms,styles,imageformats
console=disabled
deployment=true
output=SBBN-Toolbox-runtime.exe
portable_launcher=SBBN-Toolbox.exe
version=1.0.0.0
