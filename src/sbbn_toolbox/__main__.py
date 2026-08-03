"""Point d'entrée de ``python -m sbbn_toolbox``."""

from sbbn_toolbox.app import run


def main() -> int:
    """Lancer SBBN Toolbox."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
