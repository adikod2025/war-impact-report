"""Configuration injection - one loading path, no magic numbers in modules.

Pitfall 5 (*Policy & Configuration Sprawl*) is caused by constants scattered
across modules. The control is a single loading path used by every component.
Precedence, lowest to highest:

1. ``apexforge/config/default.yaml`` (committed, reviewed, versioned)
2. an explicit override file or dict passed to :func:`load_config`
3. ``APEXFORGE_``-prefixed environment variables

Environment overrides use ``__`` for nesting, so ``APEXFORGE_EDGE__MAX_SPEED``
sets ``edge.max_speed``.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

__all__ = ["Config", "load_config", "DEFAULT_CONFIG_PATH", "ConfigError"]

DEFAULT_CONFIG_PATH = Path(__file__).with_name("default.yaml")

ENV_PREFIX = "APEXFORGE_"
NEST_SEP = "__"


class ConfigError(ValueError):
    """Raised when configuration is malformed or a required key is absent."""


def _deep_merge(base: Dict[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _coerce(raw: str) -> Any:
    """Interpret an environment string as YAML scalar (int/float/bool/str)."""
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def _env_overlay(environ: Mapping[str, str]) -> Dict[str, Any]:
    overlay: Dict[str, Any] = {}
    for key, raw in environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        path = key[len(ENV_PREFIX) :].lower().split(NEST_SEP)
        cursor = overlay
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
            if not isinstance(cursor, dict):  # pragma: no cover - defensive
                raise ConfigError(f"env override {key} collides with a scalar")
        cursor[path[-1]] = _coerce(raw)
    return overlay


class Config:
    """Immutable-by-convention configuration view with dotted lookup."""

    def __init__(self, data: Dict[str, Any]):
        self._data = copy.deepcopy(data)

    def get(self, dotted: str, default: Any = None) -> Any:
        cursor: Any = self._data
        for part in dotted.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return default
            cursor = cursor[part]
        return copy.deepcopy(cursor) if isinstance(cursor, (dict, list)) else cursor

    def require(self, dotted: str) -> Any:
        """Fetch a key that must exist. Absence is a startup failure."""
        sentinel = object()
        value = self.get(dotted, sentinel)
        if value is sentinel:
            raise ConfigError(f"required configuration key {dotted!r} is absent")
        return value

    def section(self, name: str) -> Dict[str, Any]:
        value = self.get(name, {})
        if not isinstance(value, dict):
            raise ConfigError(f"configuration section {name!r} is not a mapping")
        return value

    def as_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Config(sections={sorted(self._data)})"


def load_config(
    overrides: Optional[Mapping[str, Any]] = None,
    *,
    path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Config:
    """Load configuration through the single sanctioned path.

    Parameters
    ----------
    overrides:
        Explicit overlay, applied above the file and below the environment.
    path:
        Alternative base file. Defaults to the committed ``default.yaml``.
    environ:
        Environment mapping to read ``APEXFORGE_*`` overrides from. Defaults to
        ``os.environ``. Injectable so tests never mutate real process state.
    """
    base_path = path or DEFAULT_CONFIG_PATH
    try:
        with open(base_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {base_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"configuration file {base_path} is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"configuration root of {base_path} must be a mapping")

    if overrides:
        data = _deep_merge(data, overrides)

    data = _deep_merge(data, _env_overlay(os.environ if environ is None else environ))
    return Config(data)
