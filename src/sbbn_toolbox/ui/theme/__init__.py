"""Chargement du thème SBBN."""

from pathlib import Path

from sbbn_toolbox.ui.theme.tokens import COLORS, RADII, SPACING


def load_stylesheet() -> str:
    """Charger la feuille QSS et y injecter les tokens officiels."""
    stylesheet_path = Path(__file__).with_name("stylesheet.qss")
    stylesheet = stylesheet_path.read_text(encoding="utf-8")
    replacements = {
        "@primary": COLORS.primary,
        "@primary-hover": COLORS.primary_hover,
        "@primary-light": COLORS.primary_light,
        "@background": COLORS.background,
        "@surface": COLORS.surface,
        "@border": COLORS.border,
        "@text": COLORS.text,
        "@text-secondary": COLORS.text_secondary,
        "@success": COLORS.success,
        "@error": COLORS.error,
        "@on-primary": COLORS.on_primary,
        "@disabled": COLORS.text_secondary,
        "@radius-small": f"{RADII.small}px",
        "@radius-medium": f"{RADII.medium}px",
        "@radius-large": f"{RADII.large}px",
        "@spacing-extra-small": f"{SPACING.xs}px",
        "@spacing-small": f"{SPACING.sm}px",
    }
    for token, value in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        stylesheet = stylesheet.replace(token, value)
    return stylesheet
