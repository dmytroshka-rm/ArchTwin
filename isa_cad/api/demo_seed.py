"""
Demo seed data — a realistic e-commerce architecture for testing.
Creates baseline graph + two sandbox layers for comparison.
"""

from __future__ import annotations

DEMO_BASELINE_REF = "baseline.main@sha256:a1b2c3"

# ── Components ─────────────────────────────────────────────────────────────────

DEMO_COMPONENTS = [
    {
        "id": "component.gateway.api-gw",
        "name": "API Gateway",
        "type": "gateway",
        "technology": "kong",
        "tier": "tier_1",
        "data_classification": "internal",
        "tags": ["ingress", "rate-limit"],
        "observed_metrics": {
            "p99_latency_ms": 12,
            "requests_per_second": 8500,
            "cache_hit_ratio": 0.85,
            "last_updated": "2026-05-09T10:00:00Z",
        },
    },
    {
        "id": "component.service.orders-api",
        "name": "Orders API",
        "type": "service",
        "technology": "fastapi",
        "tier": "tier_1",
        "data_classification": "confidential",
        "tags": ["domain-core", "orders"],
        "observed_metrics": {
            "p99_latency_ms": 85,
            "requests_per_second": 3200,
            "error_rate": 0.002,
            "last_updated": "2026-05-09T10:00:00Z",
        },
    },
    {
        "id": "component.service.payments-api",
        "name": "Payments API",
        "type": "service",
        "technology": "spring-boot",
        "tier": "tier_1",
        "data_classification": "restricted",
        "tags": ["domain-core", "pci"],
        "observed_metrics": {
            "p99_latency_ms": 120,
            "requests_per_second": 1800,
            "error_rate": 0.001,
            "last_updated": "2026-05-09T10:00:00Z",
        },
    },
    {
        "id": "component.service.inventory-svc",
        "name": "Inventory Service",
        "type": "service",
        "technology": "go",
        "tier": "standard",
        "data_classification": "internal",
        "tags": ["domain-support"],
        "observed_metrics": {
            "p99_latency_ms": 25,
            "requests_per_second": 5000,
            "last_updated": "2026-05-09T10:00:00Z",
        },
    },
    {
        "id": "component.data_store.orders-db",
        "name": "Orders DB",
        "type": "data_store",
        "technology": "postgresql",
        "tier": "tier_1",
        "data_classification": "confidential",
        "tags": ["rds", "multi-az"],
        "observed_metrics": {
            "p99_latency_ms": 8,
            "requests_per_second": 12000,
            "last_updated": "2026-05-09T10:00:00Z",
        },
    },
    {
        "id": "component.cache.redis-sessions",
        "name": "Redis Sessions",
        "type": "cache",
        "technology": "redis",
        "tier": "tier_1",
        "data_classification": "internal",
        "tags": ["elasticache"],
        "observed_metrics": {
            "p99_latency_ms": 2,
            "requests_per_second": 45000,
            "cache_hit_ratio": 0.92,
            "last_updated": "2026-05-09T10:00:00Z",
        },
    },
    {
        "id": "component.queue.order-events",
        "name": "Order Events",
        "type": "queue",
        "technology": "sqs",
        "tier": "standard",
        "data_classification": "internal",
        "tags": ["async", "fifo"],
    },
    {
        "id": "component.service.notification-svc",
        "name": "Notifications",
        "type": "service",
        "technology": "node",
        "tier": "auxiliary",
        "data_classification": "internal",
        "tags": ["email", "sms", "push"],
    },
    {
        "id": "component.external.stripe",
        "name": "Stripe",
        "type": "external_system",
        "technology": "stripe-api",
        "tier": "standard",
        "data_classification": "restricted",
        "tags": ["pci", "third-party"],
    },
]

# ── Relations ─────���────────────────────────────────────────────────────────────

DEMO_RELATIONS = [
    {
        "id": "rel.gw-orders",
        "source_id": "component.gateway.api-gw",
        "target_id": "component.service.orders-api",
        "type": "synchronous",
        "protocol": "HTTPS",
        "criticality": "high",
    },
    {
        "id": "rel.gw-payments",
        "source_id": "component.gateway.api-gw",
        "target_id": "component.service.payments-api",
        "type": "synchronous",
        "protocol": "HTTPS",
        "criticality": "high",
    },
    {
        "id": "rel.orders-db",
        "source_id": "component.service.orders-api",
        "target_id": "component.data_store.orders-db",
        "type": "data_access",
        "protocol": "PostgreSQL",
        "criticality": "high",
    },
    {
        "id": "rel.orders-redis",
        "source_id": "component.service.orders-api",
        "target_id": "component.cache.redis-sessions",
        "type": "data_access",
        "protocol": "Redis",
        "criticality": "medium",
    },
    {
        "id": "rel.orders-queue",
        "source_id": "component.service.orders-api",
        "target_id": "component.queue.order-events",
        "type": "asynchronous",
        "protocol": "SQS",
        "criticality": "medium",
    },
    {
        "id": "rel.orders-inventory",
        "source_id": "component.service.orders-api",
        "target_id": "component.service.inventory-svc",
        "type": "synchronous",
        "protocol": "gRPC",
        "criticality": "medium",
    },
    {
        "id": "rel.payments-stripe",
        "source_id": "component.service.payments-api",
        "target_id": "component.external.stripe",
        "type": "synchronous",
        "protocol": "HTTPS",
        "criticality": "high",
        "crosses_trust_boundary": True,
    },
    {
        "id": "rel.queue-notifications",
        "source_id": "component.queue.order-events",
        "target_id": "component.service.notification-svc",
        "type": "asynchronous",
        "protocol": "SQS",
        "criticality": "low",
    },
]

# ── Layout positions ─────────��─────────────────────────────────────────────────

DEMO_POSITIONS = {
    "component.gateway.api-gw":        {"x": 400, "y": 50},
    "component.service.orders-api":    {"x": 250, "y": 200},
    "component.service.payments-api":  {"x": 550, "y": 200},
    "component.service.inventory-svc": {"x": 100, "y": 350},
    "component.data_store.orders-db":  {"x": 250, "y": 400},
    "component.cache.redis-sessions":  {"x": 420, "y": 360},
    "component.queue.order-events":    {"x": 100, "y": 520},
    "component.service.notification-svc": {"x": 100, "y": 670},
    "component.external.stripe":       {"x": 620, "y": 370},
}
