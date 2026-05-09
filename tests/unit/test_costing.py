from __future__ import annotations

import pytest

from isa_cad.core.math_models.costing import (
    CHR_HEURISTICS,
    ConfidenceImpact,
    CostCalculator,
    EgressCostInput,
    ResourceCostInput,
    TCOInput,
)
from isa_cad.core.models.enums import CacheContext

calc = CostCalculator()


# ── CHR heuristic table ───────────────────────────────────────────────────────

def test_chr_heuristic_values():
    assert CHR_HEURISTICS[CacheContext.CDN]            == pytest.approx(0.85)
    assert CHR_HEURISTICS[CacheContext.INTERNAL_CACHE] == pytest.approx(0.70)
    assert CHR_HEURISTICS[CacheContext.UNKNOWN]        == pytest.approx(0.00)


# ── Egress cost: observed CHR ─────────────────────────────────────────────────

def test_egress_observed_chr_no_assumption():
    result = calc.compute_egress(EgressCostInput(
        monthly_gb=1000,
        egress_rate_per_gb=0.09,
        observed_chr=0.80,
    ))
    # billable = 1000 * (1 - 0.80) = 200 GB
    # cost = 200 * 0.09 = 18.0
    assert result.effective_chr == pytest.approx(0.80)
    assert result.billable_gb   == pytest.approx(200.0)
    assert result.egress_cost_usd == pytest.approx(18.0)
    assert result.chr_source    == "observed"
    assert result.is_assumption is False
    assert result.confidence_penalty == 0.0
    assert result.confidence_impact == ConfidenceImpact.HIGH
    assert result.assumptions == []


def test_egress_observed_chr_clamped():
    # observed_chr > 1.0 should be clamped to 1.0
    result = calc.compute_egress(EgressCostInput(
        monthly_gb=500,
        egress_rate_per_gb=0.10,
        observed_chr=1.5,
    ))
    assert result.effective_chr == pytest.approx(1.0)
    assert result.billable_gb   == pytest.approx(0.0)
    assert result.egress_cost_usd == pytest.approx(0.0)


# ── Egress cost: CDN heuristic ────────────────────────────────────────────────

def test_egress_cdn_heuristic_assumption():
    result = calc.compute_egress(EgressCostInput(
        monthly_gb=1000,
        egress_rate_per_gb=0.085,
        cache_context=CacheContext.CDN,
    ))
    # billable = 1000 * (1 - 0.85) = 150 GB
    # cost = 150 * 0.085 = 12.75
    assert result.effective_chr   == pytest.approx(0.85)
    assert result.billable_gb     == pytest.approx(150.0)
    assert result.egress_cost_usd == pytest.approx(12.75)
    assert result.chr_source      == "heuristic_cdn_default"
    assert result.is_assumption   is True
    assert result.confidence_penalty == pytest.approx(0.05)
    assert result.confidence_impact == ConfidenceImpact.MEDIUM
    assert len(result.assumptions) == 1
    assert "CDN" in result.assumptions[0]


# ── Egress cost: internal cache heuristic ────────────────────────────────────

def test_egress_internal_cache_heuristic():
    result = calc.compute_egress(EgressCostInput(
        monthly_gb=500,
        egress_rate_per_gb=0.01,
        cache_context=CacheContext.INTERNAL_CACHE,
    ))
    # billable = 500 * (1 - 0.70) = 150 GB
    assert result.effective_chr   == pytest.approx(0.70)
    assert result.billable_gb     == pytest.approx(150.0)
    assert result.is_assumption   is True
    assert result.confidence_penalty == pytest.approx(0.05)
    assert "read-heavy" in result.assumptions[0]


# ── Egress cost: unknown cache → conservative CHR=0.00 ───────────────────────

def test_egress_unknown_cache_conservative():
    result = calc.compute_egress(EgressCostInput(
        monthly_gb=1000,
        egress_rate_per_gb=0.09,
        cache_context=CacheContext.UNKNOWN,
    ))
    # CHR=0.00 → billable = 1000 * 1.0 = 1000 GB
    assert result.effective_chr   == pytest.approx(0.00)
    assert result.billable_gb     == pytest.approx(1000.0)
    assert result.egress_cost_usd == pytest.approx(90.0)
    assert result.confidence_impact == ConfidenceImpact.LOW
    assert result.confidence_penalty == pytest.approx(0.15)


def test_egress_no_context_defaults_to_unknown():
    result = calc.compute_egress(EgressCostInput(
        monthly_gb=200,
        egress_rate_per_gb=0.10,
    ))
    assert result.effective_chr == pytest.approx(0.00)
    assert result.chr_source    == "heuristic_unknown_conservative"


# ── Egress cost: inter-region ─────────────────────────────────────────────────

def test_egress_with_inter_region():
    result = calc.compute_egress(EgressCostInput(
        monthly_gb=1000,
        egress_rate_per_gb=0.09,
        observed_chr=0.85,
        inter_region_gb=100,
        inter_region_rate_per_gb=0.02,
    ))
    # egress = 1000 * 0.15 * 0.09 = 13.5
    # inter  = 100 * 0.02 = 2.0
    # total  = 15.5
    assert result.egress_cost_usd     == pytest.approx(13.5)
    assert result.inter_region_cost_usd == pytest.approx(2.0)
    assert result.total_cost_usd      == pytest.approx(15.5)
    assert any("Inter-region" in n for n in result.notes)


# ── TCO: resource costs ───────────────────────────────────────────────────────

def test_tco_resources_only():
    inp = TCOInput(resources=[
        ResourceCostInput("lambda-fn",   "compute", unit_price_usd=0.20,   quantity=500),
        ResourceCostInput("rds-db",      "db",      unit_price_usd=200.0,  quantity=1),
        ResourceCostInput("s3-storage",  "storage", unit_price_usd=0.023,  quantity=1000),
    ])
    result = calc.compute_tco(inp)
    # 0.20*500 + 200*1 + 0.023*1000 = 100 + 200 + 23 = 323
    assert result.resource_cost_usd == pytest.approx(323.0)
    assert result.total_usd         == pytest.approx(323.0)
    assert result.safety_buffer_applied is False
    assert result.egress_result is None


def test_tco_with_egress():
    inp = TCOInput(
        resources=[
            ResourceCostInput("api-gw", "compute", 50.0, 1),
        ],
        egress=EgressCostInput(
            monthly_gb=1000,
            egress_rate_per_gb=0.09,
            observed_chr=0.85,
        ),
        request_fees_usd=15.0,
    )
    result = calc.compute_tco(inp)
    # resource = 50, egress = 1000*0.15*0.09 = 13.5, requests = 15
    assert result.resource_cost_usd  == pytest.approx(50.0)
    assert result.egress_result is not None
    assert result.egress_result.egress_cost_usd == pytest.approx(13.5)
    assert result.request_fees_usd   == pytest.approx(15.0)
    assert result.subtotal_usd       == pytest.approx(78.5)
    assert result.total_usd          == pytest.approx(78.5)


def test_tco_safety_buffer_applied():
    inp = TCOInput(
        resources=[ResourceCostInput("svc", "compute", 1000.0, 1)],
        safety_buffer_multiplier=1.15,
    )
    result = calc.compute_tco(inp)
    assert result.safety_buffer_applied is True
    assert result.subtotal_usd == pytest.approx(1000.0)
    assert result.total_usd    == pytest.approx(1150.0)
    assert any("Safety buffer" in n for n in result.notes)


def test_tco_estimated_resource_adds_assumption():
    inp = TCOInput(resources=[
        ResourceCostInput("gpu-node", "compute", 500.0, 2, is_estimated=True),
    ])
    result = calc.compute_tco(inp)
    assert any("estimated" in a for a in result.assumptions)


def test_tco_resource_breakdown_structure():
    inp = TCOInput(resources=[
        ResourceCostInput("fn", "compute", unit_price_usd=0.10, quantity=100, unit="invocations"),
    ])
    result = calc.compute_tco(inp)
    assert len(result.resource_breakdown) == 1
    row = result.resource_breakdown[0]
    assert row["resource_id"]   == "fn"
    assert row["line_total"]    == pytest.approx(10.0)
    assert row["unit"]          == "invocations"


# ── TCO delta ────────────────────────────────────────────────────────────────

def test_tco_delta_saving():
    baseline = calc.compute_tco(TCOInput(resources=[
        ResourceCostInput("ecs-svc", "compute", 1200.0, 1)
    ]))
    proposed = calc.compute_tco(TCOInput(resources=[
        ResourceCostInput("lambda-fn", "compute", 850.0, 1)
    ]))
    delta = calc.tco_delta(baseline, proposed)
    assert delta["baseline_usd"] == pytest.approx(1200.0)
    assert delta["proposed_usd"] == pytest.approx(850.0)
    assert delta["delta_usd"]    == pytest.approx(-350.0)
    assert delta["delta_pct"]    == pytest.approx(-29.17, abs=0.1)
    assert delta["is_saving"]    is True


def test_tco_delta_cost_increase():
    baseline = calc.compute_tco(TCOInput(resources=[
        ResourceCostInput("svc-a", "compute", 500.0, 1)
    ]))
    proposed = calc.compute_tco(TCOInput(resources=[
        ResourceCostInput("svc-b", "compute", 750.0, 1)
    ]))
    delta = calc.tco_delta(baseline, proposed)
    assert delta["delta_usd"] == pytest.approx(250.0)
    assert delta["is_saving"] is False


def test_tco_delta_zero_baseline_no_division():
    baseline = calc.compute_tco(TCOInput(resources=[]))
    proposed = calc.compute_tco(TCOInput(resources=[
        ResourceCostInput("svc", "compute", 100.0, 1)
    ]))
    delta = calc.tco_delta(baseline, proposed)
    assert delta["delta_pct"] == 0.0   # no division by zero
