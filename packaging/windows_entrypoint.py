"""Point d’entrée exclusivement destiné au packaging Windows PyInstaller."""

from sbbn_toolbox.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
