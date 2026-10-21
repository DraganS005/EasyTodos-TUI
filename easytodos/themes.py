"""Theme catalog for the Textual interface."""

from __future__ import annotations

from dataclasses import dataclass

from textual.theme import BUILTIN_THEMES, Theme

from .model import DEFAULT_THEME


@dataclass(frozen=True)
class ThemeSelection:
    """A confirmed theme and transparent-background choice."""

    theme: str
    transparent: bool


@dataclass(frozen=True)
class ThemeChoice:
    """A selectable color theme with a friendly label."""

    id: str
    label: str
    theme: Theme

    @property
    def dark(self) -> bool:
        return self.theme.dark

    @property
    def swatch_primary(self) -> str:
        return self.theme.primary

    @property
    def swatch_background(self) -> str:
        return (
            self.theme.background
            or self.theme.surface
            or self.theme.panel
            or ("#1e1e1e" if self.theme.dark else "#f5f5f5")
        )


CUSTOM_THEMES: tuple[Theme, ...] = (
    Theme(
        name="default",
        primary="#5f6b7a",
        secondary="#8794a5",
        accent="#91a4bd",
        warning="#d2b36c",
        error="#cf7f7f",
        success="#8fbc8f",
        foreground="#d7dae0",
        background="#181a1f",
        surface="#1e2127",
        panel="#272b33",
        dark=True,
    ),
    Theme(
        name="everforest-dark",
        primary="#a7c080",
        secondary="#7fbbb3",
        accent="#d699b6",
        warning="#dbbc7f",
        error="#e67e80",
        success="#a7c080",
        foreground="#d3c6aa",
        background="#2d353b",
        surface="#343f44",
        panel="#3d484d",
        dark=True,
    ),
    Theme(
        name="kanagawa",
        primary="#7e9cd8",
        secondary="#957fb8",
        accent="#e6c384",
        warning="#e6c384",
        error="#e46876",
        success="#98bb6c",
        foreground="#dcd7ba",
        background="#1f1f28",
        surface="#2a2a37",
        panel="#363646",
        dark=True,
    ),
    Theme(
        name="ayu-mirage",
        primary="#73d0ff",
        secondary="#ffcc66",
        accent="#d4bfff",
        warning="#ffd580",
        error="#f28779",
        success="#bae67e",
        foreground="#cbccc6",
        background="#1f2430",
        surface="#232834",
        panel="#2d3343",
        dark=True,
    ),
    Theme(
        name="github-dark",
        primary="#58a6ff",
        secondary="#1f6feb",
        accent="#f78166",
        warning="#d29922",
        error="#f85149",
        success="#3fb950",
        foreground="#c9d1d9",
        background="#0d1117",
        surface="#161b22",
        panel="#21262d",
        dark=True,
    ),
    Theme(
        name="github-light",
        primary="#0969da",
        secondary="#218bff",
        accent="#8250df",
        warning="#9a6700",
        error="#cf222e",
        success="#1a7f37",
        foreground="#24292f",
        background="#ffffff",
        surface="#f6f8fa",
        panel="#eaeef2",
        dark=False,
    ),
)

# The app default first, then Textual's base themes, then the rest
# alphabetically by label.
_THEME_LABELS: tuple[tuple[str, str], ...] = (
    ("default", "Default"),
    ("textual-dark", "Textual Dark"),
    ("textual-light", "Textual Light"),
    ("atom-one-dark", "Atom One Dark"),
    ("atom-one-light", "Atom One Light"),
    ("ayu-mirage", "Ayu Mirage"),
    ("catppuccin-frappe", "Catppuccin Frappe"),
    ("catppuccin-latte", "Catppuccin Latte"),
    ("catppuccin-macchiato", "Catppuccin Macchiato"),
    ("catppuccin-mocha", "Catppuccin Mocha"),
    ("dracula", "Dracula"),
    ("everforest-dark", "Everforest Dark"),
    ("flexoki", "Flexoki"),
    ("github-dark", "GitHub Dark"),
    ("github-light", "GitHub Light"),
    ("gruvbox", "Gruvbox Dark"),
    ("kanagawa", "Kanagawa"),
    ("monokai", "Monokai"),
    ("nord", "Nord"),
    ("rose-pine", "Rose Pine"),
    ("rose-pine-dawn", "Rose Pine Dawn"),
    ("rose-pine-moon", "Rose Pine Moon"),
    ("solarized-dark", "Solarized Dark"),
    ("solarized-light", "Solarized Light"),
    ("tokyo-night", "Tokyo Night"),
)

_CUSTOM_BY_ID = {theme.name: theme for theme in CUSTOM_THEMES}


def _theme(theme_id: str) -> Theme:
    return _CUSTOM_BY_ID.get(theme_id) or BUILTIN_THEMES[theme_id]


THEME_CHOICES: tuple[ThemeChoice, ...] = tuple(
    ThemeChoice(theme_id, label, _theme(theme_id))
    for theme_id, label in _THEME_LABELS
)
THEME_IDS = frozenset(choice.id for choice in THEME_CHOICES)
THEME_BY_ID = {choice.id: choice for choice in THEME_CHOICES}

assert len(THEME_CHOICES) == 25
assert DEFAULT_THEME in THEME_IDS


def get_theme_choice(theme_id: str) -> ThemeChoice | None:
    """Return a catalog entry, or ``None`` for an unknown theme id."""
    return THEME_BY_ID.get(theme_id)
