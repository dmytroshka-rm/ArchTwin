from __future__ import annotations

"""
isa_cad/cli.py
==============
Command-line interface for the ISA-CAD agent pipeline.

Usage examples
--------------
Run full pipeline (rule-based reviewers, JSON output):
    python -m isa_cad.cli run \\
        --session-id  s-123 \\
        --proposal-id p-456 \\
        --baseline    arch.prod \\
        --goal        balanced

Run with LLM-backed reviewers (Claude by default):
    python -m isa_cad.cli run --llm \\
        --session-id s-123 --proposal-id p-456 --baseline arch.prod

Run with Markdown output format:
    python -m isa_cad.cli run --format markdown \\
        --session-id s-123 --proposal-id p-456 --baseline arch.prod

Save report to file:
    python -m isa_cad.cli run --format yaml --output report.yaml \\
        --session-id s-123 --proposal-id p-456 --baseline arch.prod

Print graph topology:
    python -m isa_cad.cli show-graph

All options:
    python -m isa_cad.cli run --help
"""

import argparse
import json
import sys
from typing import Any


# ── run ───────────────────────────────────────────────────────────────────────

def _run(args: argparse.Namespace) -> None:
    """Invoke the compiled LangGraph pipeline and render the final output."""
    from isa_cad.core.logging import configure_logging
    configure_logging()

    from isa_cad.agent.graph import build_graph, build_llm_graph
    from isa_cad.core.models.enums import OptimizationGoal

    goal_values = [g.value for g in OptimizationGoal]
    if args.goal not in goal_values:
        print(f"[error] --goal must be one of: {', '.join(goal_values)}", file=sys.stderr)
        sys.exit(1)

    initial_state: dict[str, Any] = {
        "session_id":        args.session_id,
        "proposal_id":       args.proposal_id,
        "baseline_ref":      args.baseline,
        "optimization_goal": OptimizationGoal(args.goal),
    }
    if args.source_component:
        initial_state["source_component_id"] = args.source_component

    mode = "LLM" if args.llm else "rule-based"
    print(f"[isa-cad] pipeline={mode}  session={args.session_id}  goal={args.goal}")

    graph = build_llm_graph() if args.llm else build_graph()
    final_state: dict[str, Any] = graph.invoke(initial_state)

    output = _format_output(final_state, args.format)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"[isa-cad] report saved to {args.output}")
    else:
        print(output)


def _format_output(state: dict[str, Any], fmt: str) -> str:
    """Render final_state using the requested formatter."""
    if fmt == "markdown":
        from isa_cad.output import MarkdownFormatter
        return MarkdownFormatter().format(state).content

    if fmt == "yaml":
        from isa_cad.output import YamlFormatter
        return YamlFormatter().format(state).content

    if fmt == "json":
        from isa_cad.output import JsonFormatter
        return JsonFormatter().format(state).content

    # default: compact summary
    return _compact_summary(state)


def _compact_summary(state: dict[str, Any]) -> str:
    fo: dict[str, Any] = state.get("final_output") or {}
    lines: list[str] = [
        "",
        "-- final_output -----------------------------------------",
        json.dumps(fo, indent=2, default=str),
    ]

    hrr: dict[str, Any] = state.get("human_review_request") or {}
    if hrr.get("required"):
        level = hrr.get("escalation_level", "info").upper()
        lines.append(f"\n[HUMAN REVIEW REQUIRED -- {level}]")
        for reason in hrr.get("reasons", []):
            lines.append(f"  - {reason}")
        options = hrr.get("options", [])
        if options:
            lines.append(f"  Options: {', '.join(options)}")

    recs: list[dict[str, Any]] = state.get("recommendations") or []
    if recs:
        lines.append(f"\n-- recommendations ({len(recs)}) ---------------------------------")
        for rec in recs:
            score = rec.get("goal_alignment", 0.0)
            lines.append(f"  [{score:.2f}] {rec.get('title', '?')} -- {rec.get('rationale', '')}")

    lines.append("")
    return "\n".join(lines)


# ── show-graph ────────────────────────────────────────────────────────────────

def _show_graph(_args: argparse.Namespace) -> None:
    """Print the pipeline graph topology."""
    from isa_cad.agent.graph import build_graph
    graph = build_graph()

    print("-- nodes -------------------------------------------------")
    for node in sorted(graph.nodes):
        print(f"  {node}")

    try:
        raw = graph.graph
        print("\n-- edges -------------------------------------------------")
        for src, dst, *_ in raw.edges():
            print(f"  {src} -> {dst}")
    except AttributeError:
        print("\n[info] edge inspection not available on this LangGraph version")


# ── version ───────────────────────────────────────────────────────────────────

def _version(_args: argparse.Namespace) -> None:
    import isa_cad
    print(f"isa-cad {isa_cad.__version__}")


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isa-cad",
        description="ISA-CAD -- Intelligent System Architecture CAD Agent",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── run ──────────────────────────────────────────────────────────────────
    run_p = sub.add_parser("run", help="Execute the full ISA-CAD pipeline")
    run_p.add_argument("--session-id",  required=True,
                       help="Canvas session identifier")
    run_p.add_argument("--proposal-id", required=True,
                       help="Design proposal identifier")
    run_p.add_argument("--baseline",    required=True,
                       help="Baseline architecture reference (e.g. arch.prod)")
    run_p.add_argument(
        "--goal",
        default="balanced",
        choices=["cost_efficiency", "max_reliability", "minimal_complexity", "balanced"],
        help="Optimization goal (default: balanced)",
    )
    run_p.add_argument("--source-component", default=None,
                       help="Source component ID for design delta (optional)")
    run_p.add_argument(
        "--llm",
        action="store_true",
        default=False,
        help="Use LLM-backed reviewers (requires ANTHROPIC_API_KEY or OPENAI_API_KEY)",
    )
    run_p.add_argument(
        "--format",
        dest="format",
        default="summary",
        choices=["summary", "json", "markdown", "yaml"],
        help="Output format (default: summary)",
    )
    run_p.add_argument(
        "--output", "-o",
        default=None,
        metavar="FILE",
        help="Save output to file instead of stdout",
    )
    run_p.set_defaults(func=_run)

    # ── show-graph ────────────────────────────────────────────────────────────
    sg_p = sub.add_parser("show-graph", help="Print pipeline graph topology")
    sg_p.set_defaults(func=_show_graph)

    # ── version ───────────────────────────────────────────────────────────────
    ver_p = sub.add_parser("version", help="Print version and exit")
    ver_p.set_defaults(func=_version)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
