"""Load a case config (YAML) + constants into a flat, formula-friendly parameter object.

Keys mirror the workbook's named ranges (SECNH3, ElecOversize, BattEff, ...) so the
ported formulas in sizing.py / dispatch.py / economics.py read 1:1 against the Excel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _flatten_inputs(inputs: dict) -> dict[str, Any]:
    """Pull {section: {key: {value, unit}}} down to {key: value}."""
    flat: dict[str, Any] = {}
    for section in inputs.values():
        for key, spec in section.items():
            flat[key] = spec.get("value") if isinstance(spec, dict) else spec
    return flat


@dataclass
class Case:
    """All inputs + constants for one scenario, plus derived sizing (filled by sizing.py)."""

    raw: dict[str, Any]                      # flat S1 inputs by yaml key
    constants: dict[str, Any]                # from constants.yaml
    weather_file: str
    case_name: str
    derived: dict[str, float] = field(default_factory=dict)   # Pmax, Prated_Elec, ... (sizing)
    meta: dict[str, Any] = field(default_factory=dict)

    # --- convenience accessors by the workbook's named-range names ---------
    def __getitem__(self, key: str) -> Any:
        if key in self.derived:
            return self.derived[key]
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.derived:
            return self.derived[key]
        return self.raw.get(key, default)


def load_case(config_path: str | Path) -> Case:
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    # project root = the directory that holds config/ and data/ (one above the config file)
    project_root = config_path.parent.parent
    with config_path.open() as fh:
        cfg = yaml.safe_load(fh)

    flat = _flatten_inputs(cfg["inputs"])

    constants_path = config_path.parent / "constants.yaml"
    constants: dict[str, Any] = {}
    if constants_path.exists():
        with constants_path.open() as fh:
            constants = yaml.safe_load(fh)

    return Case(
        raw=flat,
        constants=constants,
        weather_file=cfg.get("weather_file"),
        case_name=cfg.get("case_name", config_path.stem),
        meta={"config_path": str(config_path), "review": cfg.get("_review_required"),
              "description": cfg.get("description", ""), "project_root": str(project_root)},
    )


def const_value(constants: dict, *path: str) -> Any:
    """Dig a nested constants.yaml entry and return its scalar `value`."""
    node: Any = constants
    for p in path:
        node = node[p]
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node
