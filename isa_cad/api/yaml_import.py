"""
isa_cad/api/yaml_import.py
===========================
Parses user-provided YAML architecture descriptions into ISA-CAD components,
relations, and layout positions.

Supported YAML format:
----------------------
```yaml
name: "My System"
baseline_ref: "baseline.prod@v2.1"

components:
  - id: "component.service.orders-api"  # optional — auto-generated if missing
    name: "Orders API"
    type: "service"                      # service|data_store|cache|queue|gateway|external_system
    technology: "fastapi"                # optional
    tier: "tier_1"                       # tier_1|standard|auxiliary (default: standard)
    data_classification: "confidential"  # optional
    tags: ["domain-core"]                # optional
    metrics:                             # optional — observed metrics
      p99_latency_ms: 85
      requests_per_second: 3200
      cache_hit_ratio: 0.92
      error_rate: 0.002

relations:
  - source: "Orders API"          # can reference by name or id
    target: "Orders DB"
    type: "data_access"            # synchronous|asynchronous|data_access|streaming|batch|external
    protocol: "PostgreSQL"         # optional
    criticality: "high"            # high|medium|low (default: medium)
    crosses_trust_boundary: false  # optional
```
"""

from __future__ import annotations

import hashlib
from typing import Any

import yaml


def _make_id(comp_type: str, name: str) -> str:
    """Generate a stable component ID from type and name."""
    slug = name.lower().replace(" ", "-").replace("_", "-")
    # Remove non-alphanum except dash
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return f"component.{comp_type}.{slug}"


def _auto_layout(components: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Generate a simple grid layout for components."""
    positions: dict[str, dict[str, int]] = {}
    cols = 3
    x_gap = 250
    y_gap = 180
    x_start = 80
    y_start = 60

    # Group by tier for visual ordering
    tier_order = {"tier_1": 0, "standard": 1, "auxiliary": 2}
    sorted_comps = sorted(components, key=lambda c: (tier_order.get(c.get("tier", "standard"), 1), c.get("name", "")))

    for i, comp in enumerate(sorted_comps):
        col = i % cols
        row = i // cols
        positions[comp["id"]] = {
            "x": x_start + col * x_gap,
            "y": y_start + row * y_gap,
        }
    return positions


def parse_yaml_architecture(yaml_content: str) -> dict[str, Any]:
    """
    Parse YAML architecture description into ISA-CAD format.

    Returns:
        {
            "name": str,
            "baseline_ref": str,
            "components": [...],
            "relations": [...],
            "positions": {...},
            "warnings": [...],
        }
    """
    warnings: list[str] = []

    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return {"error": f"Invalid YAML: {e}", "components": [], "relations": [], "positions": {}, "warnings": []}

    if not isinstance(data, dict):
        return {"error": "YAML root must be a mapping (object)", "components": [], "relations": [], "positions": {}, "warnings": []}

    name = data.get("name", "Imported Architecture")
    baseline_ref = data.get("baseline_ref", f"baseline.import@sha256:{hashlib.sha256(yaml_content.encode()).hexdigest()[:12]}")

    # ── Parse components ──────────────────────────────────────────────────────

    raw_components = data.get("components", [])
    if not isinstance(raw_components, list):
        return {"error": "'components' must be a list", "components": [], "relations": [], "positions": {}, "warnings": []}

    components: list[dict[str, Any]] = []
    name_to_id: dict[str, str] = {}

    valid_types = {"system", "container", "component", "service", "data_store", "cache", "queue", "gateway", "external_system", "storage"}
    valid_tiers = {"tier_1", "standard", "auxiliary"}

    for i, raw in enumerate(raw_components):
        if not isinstance(raw, dict):
            warnings.append(f"Component #{i} is not a mapping — skipped")
            continue

        comp_name = raw.get("name", f"component-{i}")
        comp_type = raw.get("type", "service")

        if comp_type not in valid_types:
            warnings.append(f"Component '{comp_name}': unknown type '{comp_type}', defaulting to 'service'")
            comp_type = "service"

        tier = raw.get("tier", "standard")
        if tier not in valid_tiers:
            warnings.append(f"Component '{comp_name}': unknown tier '{tier}', defaulting to 'standard'")
            tier = "standard"

        comp_id = raw.get("id") or _make_id(comp_type, comp_name)
        name_to_id[comp_name] = comp_id
        name_to_id[comp_id] = comp_id  # also map id to itself

        comp: dict[str, Any] = {
            "id": comp_id,
            "name": comp_name,
            "type": comp_type,
            "tier": tier,
            "technology": raw.get("technology"),
            "data_classification": raw.get("data_classification"),
            "tags": raw.get("tags", []),
        }

        # Metrics
        metrics = raw.get("metrics") or raw.get("observed_metrics")
        if metrics and isinstance(metrics, dict):
            comp["observed_metrics"] = {
                "p99_latency_ms": metrics.get("p99_latency_ms"),
                "requests_per_second": metrics.get("requests_per_second") or metrics.get("rps"),
                "cache_hit_ratio": metrics.get("cache_hit_ratio") or metrics.get("chr"),
                "error_rate": metrics.get("error_rate"),
                "last_updated": metrics.get("last_updated"),
            }
            # Remove None values
            comp["observed_metrics"] = {k: v for k, v in comp["observed_metrics"].items() if v is not None}

        components.append(comp)

    # ── Parse relations ───────────────────────────────────────────────────────

    raw_relations = data.get("relations", [])
    if not isinstance(raw_relations, list):
        raw_relations = []

    relations: list[dict[str, Any]] = []
    valid_rel_types = {"synchronous", "asynchronous", "data_access", "streaming", "batch", "external"}

    for i, raw in enumerate(raw_relations):
        if not isinstance(raw, dict):
            warnings.append(f"Relation #{i} is not a mapping — skipped")
            continue

        source_ref = raw.get("source", raw.get("source_id", ""))
        target_ref = raw.get("target", raw.get("target_id", ""))

        # Resolve by name or id
        source_id = name_to_id.get(source_ref, source_ref)
        target_id = name_to_id.get(target_ref, target_ref)

        if not source_id or not target_id:
            warnings.append(f"Relation #{i}: missing source or target — skipped")
            continue

        if source_id not in name_to_id.values() and source_id not in [c["id"] for c in components]:
            warnings.append(f"Relation #{i}: source '{source_ref}' not found in components")
        if target_id not in name_to_id.values() and target_id not in [c["id"] for c in components]:
            warnings.append(f"Relation #{i}: target '{target_ref}' not found in components")

        rel_type = raw.get("type", "synchronous")
        if rel_type not in valid_rel_types:
            warnings.append(f"Relation #{i}: unknown type '{rel_type}', defaulting to 'synchronous'")
            rel_type = "synchronous"

        rel_id = raw.get("id", f"rel.{source_id.split('.')[-1]}-{target_id.split('.')[-1]}")

        relation: dict[str, Any] = {
            "id": rel_id,
            "source_id": source_id,
            "target_id": target_id,
            "type": rel_type,
            "protocol": raw.get("protocol"),
            "criticality": raw.get("criticality", "medium"),
            "crosses_trust_boundary": raw.get("crosses_trust_boundary", False),
            "crosses_bounded_context": raw.get("crosses_bounded_context", False),
        }
        relations.append(relation)

    # ── Auto-layout ───────────────────────────────────────────────────────────

    positions = _auto_layout(components)

    return {
        "name": name,
        "baseline_ref": baseline_ref,
        "components": components,
        "relations": relations,
        "positions": positions,
        "warnings": warnings,
    }
