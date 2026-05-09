from __future__ import annotations

from pathlib import Path

import pytest

from isa_cad.core.schema import validate_isa_yaml, validate_isa_yaml_file

FIXTURES = Path(__file__).parent.parent.parent / "isa_cad" / "core" / "schema" / "fixtures"


def test_valid_proposal_passes():
    result = validate_isa_yaml_file(FIXTURES / "valid_proposal.yaml")
    assert result.valid, f"Expected valid, got errors: {result.errors}"


def test_invalid_proposal_fails():
    result = validate_isa_yaml_file(FIXTURES / "invalid_proposal.yaml")
    assert not result.valid
    assert len(result.errors) > 0


def test_invalid_proposal_catches_specific_errors():
    result = validate_isa_yaml_file(FIXTURES / "invalid_proposal.yaml")
    joined = " ".join(result.errors)
    # base_confidence > 1.0
    assert "1.5" in joined or "maximum" in joined
    # unknown status enum
    assert "unknown_status" in joined or "status" in joined


def test_missing_required_fields():
    result = validate_isa_yaml({"design_proposals": [{"title": "No ID"}]})
    assert not result.valid
    assert any("id" in e for e in result.errors)


def test_empty_proposals_fails():
    result = validate_isa_yaml({"design_proposals": []})
    assert not result.valid


def test_minimal_valid_proposal():
    result = validate_isa_yaml({
        "design_proposals": [{
            "id": "proposal.minimal",
            "title": "Minimal",
            "status": "sandbox_layer",
            "optimization_goal": "balanced",
            "baseline_ref": "baseline.prod",
        }]
    })
    assert result.valid, f"Errors: {result.errors}"


def test_file_not_found():
    result = validate_isa_yaml_file("/nonexistent/path/isa.yaml")
    assert not result.valid
    assert "not found" in result.errors[0].lower()
