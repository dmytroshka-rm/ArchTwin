from __future__ import annotations

"""
isa_cad/output/formatters/yaml_fmt.py
=======================================
YAML formatter — serialises the Decision-Grade Output Contract to YAML.

Produces the same logical document as JsonFormatter but in YAML format,
which is easier to diff in PR reviews and to paste into isa.yaml files.
"""

from typing import Any

import yaml

from .base import FormattedOutput, _fo
from .json_fmt import JsonFormatter


class YamlFormatter:
    """Formats the pipeline AgentState as a YAML document."""

    media_type = "application/yaml"

    def __init__(self, default_flow_style: bool = False) -> None:
        self._flow = default_flow_style
        # Reuse the JSON formatter's document builder
        self._json = JsonFormatter()

    def format(self, state: dict[str, Any]) -> FormattedOutput:  # noqa: A003
        fo = _fo(state)
        # Build the same document as the JSON formatter
        doc = self._json._build_doc(fo, state)
        doc["meta"]["formatter"] = "YamlFormatter"

        content = yaml.dump(
            doc,
            allow_unicode=True,
            default_flow_style=self._flow,
            sort_keys=False,
        )

        return FormattedOutput(
            content=content,
            media_type=self.media_type,
            metadata={
                "proposal_id": fo.get("proposal_id"),
                "decision":    fo.get("decision"),
                "score":       fo.get("recommendation_score"),
            },
        )
