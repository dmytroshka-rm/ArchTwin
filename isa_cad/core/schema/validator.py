from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

_SCHEMA_PATH = Path(__file__).parent / "isa_yaml_schema.json"
_SCHEMA: dict | None = None


def _load_schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


def validate_isa_yaml(data: dict) -> ValidationResult:
    """
    Validate a parsed isa.yaml dict against the ISA-CAD JSON Schema.
    Returns a ValidationResult with all errors collected (not fail-fast).
    """
    schema = _load_schema()
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    if not errors:
        return ValidationResult(valid=True)

    messages = [_format_error(e) for e in errors]
    return ValidationResult(valid=False, errors=messages)


def validate_isa_yaml_file(path: str | Path) -> ValidationResult:
    """Load and validate an isa.yaml file from disk."""
    path = Path(path)
    if not path.exists():
        return ValidationResult(valid=False, errors=[f"File not found: {path}"])

    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return ValidationResult(valid=False, errors=[f"YAML parse error: {e}"])

    if not isinstance(data, dict):
        return ValidationResult(valid=False, errors=["Root element must be a YAML mapping (dict)"])

    return validate_isa_yaml(data)


def _format_error(error: jsonschema.ValidationError) -> str:
    path = " → ".join(str(p) for p in error.absolute_path) or "root"
    return f"[{path}] {error.message}"
