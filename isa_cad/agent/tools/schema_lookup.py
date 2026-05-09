from __future__ import annotations

"""
isa_cad/agent/tools/schema_lookup.py
======================================
LangChain tool — validate a design-proposal dict against the isa.yaml
JSON Schema and return the validation report.

Used by reviewers and patch nodes to confirm that a proposed change
is schema-compliant before committing it to the isa.yaml output.
"""

import json
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from isa_cad.core.schema.validator import validate_isa_yaml


class _SchemaValidateInput(BaseModel):
    proposal_json: str = Field(
        ...,
        description=(
            "JSON string of a single design proposal dict to validate. "
            "Must be a dict, not a list. The tool wraps it automatically "
            "in {\"design_proposals\": [...]}"
        ),
    )


class SchemaValidationTool(BaseTool):
    """
    Validate a design proposal dict against the isa.yaml JSON Schema.

    Accepts a JSON-serialised dict representing a single design proposal
    and returns a validation report: ``valid``, ``errors`` list, and
    ``error_count``.
    """

    name: str = "schema_validation"
    description: str = (
        "Validate a design proposal dict against the isa.yaml JSON Schema. "
        "Pass a JSON string of the proposal object. "
        "Returns {valid, error_count, errors[]} — use this before "
        "writing any isa.yaml patch to ensure schema compliance."
    )
    args_schema: Type[BaseModel] = _SchemaValidateInput

    def _run(self, proposal_json: str) -> str:
        try:
            proposal: dict[str, Any] = json.loads(proposal_json)
        except json.JSONDecodeError as exc:
            return json.dumps({
                "valid":       False,
                "error_count": 1,
                "errors":      [f"Invalid JSON input: {exc}"],
            })

        if not isinstance(proposal, dict):
            return json.dumps({
                "valid":       False,
                "error_count": 1,
                "errors":      ["Input must be a JSON object (dict), not a list or scalar."],
            })

        result = validate_isa_yaml({"design_proposals": [proposal]})
        return json.dumps({
            "valid":       result.valid,
            "error_count": len(result.errors),
            "errors":      result.errors,
        })
