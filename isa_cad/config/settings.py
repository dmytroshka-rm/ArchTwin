from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── LLM provider ─────────────────────────────────────────────────────────
    # "anthropic" | "openai" — selects which LLM backs the reviewers.
    # Falls back automatically when only one API key is present.
    LLM_PROVIDER: str = os.getenv("ISA_CAD_LLM_PROVIDER", "anthropic")

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ISA_CAD_ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("ISA_CAD_OPENAI_MODEL", "gpt-4o")

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("ISA_CAD_LOG_LEVEL", "INFO")

    # Freshness thresholds
    DATA_FRESHNESS_MAX_AGE_HOURS: int = int(os.getenv("ISA_CAD_DATA_FRESHNESS_MAX_AGE_HOURS", "24"))
    PRICING_MAX_AGE_DAYS: int = int(os.getenv("ISA_CAD_PRICING_MAX_AGE_DAYS", "7"))
    STALE_DATA_DAYS: int = int(os.getenv("ISA_CAD_STALE_DATA_DAYS", "7"))

    # Calibration & Safety Buffer
    CALIBRATION_BUFFER_THRESHOLD: float = float(
        os.getenv("ISA_CAD_CALIBRATION_BUFFER_THRESHOLD", "0.20")
    )
    SAFETY_BUFFER_MULTIPLIER: float = float(
        os.getenv("ISA_CAD_SAFETY_BUFFER_MULTIPLIER", "1.15")
    )

    # Confidence
    MIN_CONFIDENCE: float = float(os.getenv("ISA_CAD_MIN_CONFIDENCE", "0.65"))

    # Checkpoints
    CHECKPOINT_DIR: Path = Path(os.getenv("ISA_CAD_CHECKPOINT_DIR", "./checkpoints"))

    # CHR heuristic defaults (Cache Hit Ratio)
    CHR_CDN_DEFAULT: float = 0.85        # CloudFront / Cloudflare
    CHR_INTERNAL_CACHE: float = 0.70     # Redis / Memcached
    CHR_UNKNOWN: float = 0.00            # conservative assumption

    # Tier criticality multipliers
    CRITICALITY_TIER_1: float = 2.0      # Shared DB, Identity Provider, Core API
    CRITICALITY_STANDARD: float = 1.0   # Domain API, worker, internal service
    CRITICALITY_AUXILIARY: float = 0.5  # Logging, metrics, monitoring


settings = Settings()
