from __future__ import annotations

from pathlib import Path

import yaml

from isa_cad.core.models.proposal import DesignProposal
from isa_cad.core.schema.validator import ValidationResult, validate_isa_yaml


def proposal_to_dict(proposal: DesignProposal) -> dict:
    """Convert a DesignProposal to an isa.yaml-compatible dict."""
    data = proposal.model_dump(exclude_none=True, mode="json")

    # Wrap into top-level structure
    return {"design_proposals": [data]}


def proposals_to_dict(proposals: list[DesignProposal]) -> dict:
    """Convert multiple DesignProposals to a single isa.yaml-compatible dict."""
    items = [p.model_dump(exclude_none=True, mode="json") for p in proposals]
    return {"design_proposals": items}


def dump_isa_yaml(proposals: list[DesignProposal], path: str | Path) -> ValidationResult:
    """
    Serialize DesignProposals to an isa.yaml file.
    Validates before writing — raises if invalid.
    """
    data = proposals_to_dict(proposals)
    result = validate_isa_yaml(data)
    if not result:
        return result

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    return result


def load_isa_yaml(path: str | Path) -> tuple[dict, ValidationResult]:
    """
    Load an isa.yaml file and validate it.
    Returns (parsed_dict, ValidationResult).
    """
    path = Path(path)
    if not path.exists():
        return {}, ValidationResult(valid=False, errors=[f"File not found: {path}"])

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    result = validate_isa_yaml(data)
    return data, result
