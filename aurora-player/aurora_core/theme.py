"""Material-inspired palettes and contrast checks without Qt dependencies."""

import colorsys
from typing import Dict


def _hsl(hue: int, saturation: float, lightness: float) -> str:
    red, green, blue = colorsys.hls_to_rgb((hue % 360) / 360.0, lightness / 100.0, saturation)
    return "#{:02X}{:02X}{:02X}".format(round(red * 255), round(green * 255), round(blue * 255))


def _rgb(color: str):
    value = color.lstrip("#")
    if len(value) != 6:
        raise ValueError("expected #RRGGBB")
    return tuple(int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4))


def _linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    red, green, blue = (_linear(channel) for channel in _rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    light = max(relative_luminance(first), relative_luminance(second))
    dark = min(relative_luminance(first), relative_luminance(second))
    return (light + 0.05) / (dark + 0.05)


def make_palette(hue: int, mode: str = "dark") -> Dict[str, str]:
    """Build a compact M3-like palette with readable foreground roles."""

    light = mode == "light"
    if light:
        palette = {
            "primary": _hsl(hue, 0.78, 40),
            "on_primary": "#FFFFFF",
            "primary_container": _hsl(hue, 0.70, 90),
            "on_primary_container": _hsl(hue, 0.55, 18),
            "secondary": _hsl(hue, 0.35, 35),
            "on_secondary": "#FFFFFF",
            "secondary_container": _hsl(hue, 0.25, 90),
            "on_secondary_container": _hsl(hue, 0.35, 18),
            "tertiary": _hsl(hue + 60, 0.45, 35),
            "on_tertiary": "#FFFFFF",
            "tertiary_container": _hsl(hue + 60, 0.35, 90),
            "on_tertiary_container": _hsl(hue + 60, 0.30, 18),
            "surface": _hsl(hue, 0.10, 98),
            "surface_dim": _hsl(hue, 0.08, 90),
            "surface_bright": "#FFFFFF",
            "surface_container_lowest": "#FFFFFF",
            "surface_container_low": _hsl(hue, 0.08, 96),
            "surface_container": _hsl(hue, 0.08, 94),
            "surface_container_high": _hsl(hue, 0.07, 92),
            "surface_container_highest": _hsl(hue, 0.06, 90),
            "on_surface": _hsl(hue, 0.08, 10),
            "on_surface_variant": _hsl(hue, 0.10, 30),
            "outline": _hsl(hue, 0.06, 45),
            "outline_variant": _hsl(hue, 0.08, 75),
            "inverse_surface": _hsl(hue, 0.08, 20),
            "inverse_on_surface": _hsl(hue, 0.08, 95),
            "inverse_primary": _hsl(hue, 0.75, 80),
        }
    else:
        palette = {
            "primary": _hsl(hue, 0.90, 84),
            "on_primary": _hsl(hue, 0.55, 20),
            "primary_container": _hsl(hue, 0.42, 30),
            "on_primary_container": _hsl(hue, 0.92, 92),
            "secondary": _hsl(hue, 0.26, 82),
            "on_secondary": _hsl(hue, 0.19, 18),
            "secondary_container": _hsl(hue, 0.15, 28),
            "on_secondary_container": _hsl(hue, 0.30, 90),
            "tertiary": _hsl(hue + 60, 0.45, 80),
            "on_tertiary": _hsl(hue + 60, 0.30, 18),
            "tertiary_container": _hsl(hue + 60, 0.24, 31),
            "on_tertiary_container": _hsl(hue + 60, 0.60, 92),
            "surface": _hsl(hue, 0.10, 8),
            "surface_dim": _hsl(hue, 0.10, 8),
            "surface_bright": _hsl(hue, 0.06, 23),
            "surface_container_lowest": _hsl(hue, 0.12, 5),
            "surface_container_low": _hsl(hue, 0.09, 11),
            "surface_container": _hsl(hue, 0.08, 12),
            "surface_container_high": _hsl(hue, 0.07, 17),
            "surface_container_highest": _hsl(hue, 0.06, 21),
            "on_surface": _hsl(hue, 0.08, 92),
            "on_surface_variant": _hsl(hue, 0.10, 79),
            "outline": _hsl(hue, 0.05, 58),
            "outline_variant": _hsl(hue, 0.07, 29),
            "inverse_surface": _hsl(hue, 0.08, 92),
            "inverse_on_surface": _hsl(hue, 0.06, 19),
            "inverse_primary": _hsl(hue, 0.50, 56),
        }
    palette.update(
        {
            "error": "#BA1A1A" if light else "#FFB4AB",
            "on_error": "#FFFFFF" if light else "#690005",
            "error_container": "#FFDAD6" if light else "#93000A",
            "on_error_container": "#410002" if light else "#FFDAD6",
        }
    )
    return palette


def validate_palette_contrast(palette: Dict[str, str]) -> bool:
    pairs = (
        ("on_surface", "surface"),
        ("on_primary", "primary"),
        ("on_primary_container", "primary_container"),
        ("on_secondary_container", "secondary_container"),
        ("on_error", "error"),
    )
    return all(contrast_ratio(palette[foreground], palette[background]) >= 4.5 for foreground, background in pairs)
