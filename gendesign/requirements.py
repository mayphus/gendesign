"""Load and check a requirements file.

Requirements are the measured input. Validation checks that the file has
the fields a later test can point at. It does not invent a fit dimension,
and feedback from a print does not rewrite this file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED = ("name", "units", "purpose", "constraints")


@dataclass
class Requirements:
    name: str
    units: str
    purpose: str
    constraints: dict
    raw: dict
    path: str | None = None
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def section(self, key: str) -> dict:
        value = self.raw.get(key) or {}
        return value if isinstance(value, dict) else {}


def validate_mapping(data: dict) -> list[str]:
    """Schema check. Returns a list of problems. Empty means usable."""
    if not isinstance(data, dict):
        return ["requirements must be a mapping"]
    errors = []
    for key in REQUIRED:
        if key not in data or data[key] in (None, "", {}):
            errors.append(f"missing {key}")
    units = str(data.get("units", "")).lower()
    if units and units not in {"mm", "millimetre", "millimetres", "millimeter", "millimeters"}:
        errors.append(f"units must be mm, got {data.get('units')!r}")
    constraints = data.get("constraints")
    if isinstance(constraints, dict):
        for key, value in constraints.items():
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float, str, list)):
                continue
            errors.append(f"constraint {key} is not a number, string, or list")
    elif constraints not in (None, {}):
        errors.append("constraints must be a mapping")
    return errors


def load_requirements(path) -> Requirements:
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}
    errors = validate_mapping(data)
    return Requirements(
        name=str(data.get("name") or ""),
        units=str(data.get("units") or ""),
        purpose=str(data.get("purpose") or "").strip(),
        constraints=data.get("constraints") if isinstance(data.get("constraints"), dict) else {},
        raw=data,
        path=str(path),
        errors=errors,
    )
