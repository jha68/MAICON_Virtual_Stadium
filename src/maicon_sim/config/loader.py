"""Load local JSON/YAML contracts without fetching schema identifiers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from importlib.resources import files
import copy
import hashlib
import json
import math
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ConfigError(ValueError):
    """An actionable configuration error; CLI maps this to exit status 2."""


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _finite(value: Any, name: str, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigError(f"{name}:{path}: non-finite number; use a finite SI value")
    if isinstance(value, dict):
        for k, v in value.items():
            _finite(v, name, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _finite(v, name, f"{path}[{i}]")


def read_data(path: str | Path) -> dict:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeError) as exc:
        raise ConfigError(f"{path}:$: unable to read YAML/JSON; check the file and syntax") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}:$: expected an object; use a key/value YAML mapping")
    _finite(data, str(path))
    return data


def validate_schema(data: dict, schema_name: str, filename: str = "configuration") -> None:
    try:
        schema = json.loads(files("maicon_sim").joinpath("resources", "schemas",
                                                        schema_name + ".schema.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{filename}:$: packaged schema {schema_name!r} unavailable") from exc
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(data),
                    key=lambda e: "/".join(str(p) for p in e.path))
    if errors:
        e = errors[0]
        location = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.path)
        message = e.message
        def redact_codes(node):
            nonlocal message
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "mission_code" and isinstance(value, str) and value:
                        message = message.replace(value, "[REDACTED]")
                    else:
                        redact_codes(value)
            elif isinstance(node, list):
                for value in node:
                    redact_codes(value)
        redact_codes(data)
        raise ConfigError(f"{filename}:{location}: {message}; follow the matching examples/schema")


@dataclass
class LoadedConfig:
    scenario: dict
    rules: dict
    arena: dict
    assets: dict
    sensors: dict
    path: Path
    hashes: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def sensor_profile(self) -> dict:
        return self.sensors

    def public_map_prior(self) -> dict:
        return copy.deepcopy({k: self.arena[k] for k in
                              ("arena_id", "bounds", "sectors", "bases", "nominal_starts")})


def load_scenario(path: str | Path, backend: str | None = None) -> LoadedConfig:
    from .semantic_validation import validate_semantics
    path = Path(path).resolve()
    scenario = read_data(path)
    validate_schema(scenario, "scenario", str(path))
    values = {}
    refs = {"rules": "rules", "arena": "arena", "assets": "assets",
            "sensor_profile": "sensors"}
    for prefix, field_name in refs.items():
        ref = Path(scenario[prefix + "_file"])
        if ref.is_absolute():
            raise ConfigError(f"{path}:$.{prefix}_file: absolute paths are not portable; use a relative path")
        location = path.parent / ref
        data = read_data(location)
        validate_schema(data, prefix, str(location))
        values[field_name] = data
    source_hash = canonical_hash(scenario)
    result = LoadedConfig(scenario=copy.deepcopy(scenario), path=path, **values)
    result.warnings = validate_semantics(result, backend or scenario["default_backend"])
    result.hashes = {
        "scenario_hash": canonical_hash(result.scenario),
        "source_scenario_hash": source_hash,
        "rule_profile_hash": canonical_hash(result.rules),
        "arena_hash": canonical_hash(result.arena),
        "asset_manifest_hash": canonical_hash(result.assets),
        "sensor_profile_hash": canonical_hash(result.sensors),
    }
    return result
