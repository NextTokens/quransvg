"""Themes for the v4 colour mushaf.

The same contract as the v2 build, with nine tokens added for the recitation
rules. The starting values are the publisher's own palette 0, which is what the
printed tajweed masahif use; a theme is free to move them, and the night theme
has to, because that palette was chosen for white paper.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import stylesheet

THEME_DIR = Path(__file__).resolve().parents[2] / "themes-v4"

DEFAULT = "green-pink"


@dataclass(frozen=True)
class Theme:
    name: str
    title: str
    dark: bool
    colors: dict[str, str]

    def block(self) -> str:
        return stylesheet.theme_block(self.name, self.colors)


def path_for(name: str) -> Path:
    return THEME_DIR / f"{name}.json"


@lru_cache(maxsize=None)
def load(name: str) -> Theme:
    path = path_for(name)
    if not path.exists():
        raise FileNotFoundError(f"no theme {name!r} in {THEME_DIR}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Theme(
        name=name,
        title=data.get("title", name),
        dark=bool(data.get("dark", False)),
        colors=dict(data["colors"]),
    )


def names() -> list[str]:
    return sorted(p.stem for p in THEME_DIR.glob("*.json") if p.stem != "schema")
