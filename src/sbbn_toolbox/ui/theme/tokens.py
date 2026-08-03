"""Tokens du design system SBBN."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Colors:
    """Palette officielle de l'interface."""

    primary: str = "#361C3E"
    primary_hover: str = "#4B2754"
    primary_light: str = "#EDE3F0"
    background: str = "#FFFEF9"
    surface: str = "#F6F4F7"
    border: str = "#E6E2E9"
    text: str = "#1B1420"
    text_secondary: str = "#5C5563"
    success: str = "#277A50"
    error: str = "#B3261E"
    on_primary: str = "#FFFEF9"


@dataclass(frozen=True, slots=True)
class Spacing:
    """Échelle d'espacement indépendante de la résolution physique."""

    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32
    xxxl: int = 48


@dataclass(frozen=True, slots=True)
class Radii:
    """Rayons cohérents utilisés par les surfaces."""

    small: int = 8
    medium: int = 10
    large: int = 12


COLORS = Colors()
SPACING = Spacing()
RADII = Radii()
