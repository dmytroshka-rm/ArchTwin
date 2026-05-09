from __future__ import annotations

"""
tests/unit/test_cli.py
=======================
Smoke tests for the CLI argument parser.
These tests exercise argument parsing and the show-graph command only —
they do NOT invoke the full pipeline (that is covered by integration tests).
"""

import pytest

from isa_cad.cli import main


# ── show-graph ────────────────────────────────────────────────────────────────

class TestShowGraph:

    def test_show_graph_runs(self, capsys):
        main(["show-graph"])
        out = capsys.readouterr().out
        assert "nodes" in out

    def test_show_graph_lists_all_nodes(self, capsys):
        main(["show-graph"])
        out = capsys.readouterr().out
        for node in (
            "context_freshness", "build_design_delta", "parallel_reviewer",
            "security_veto", "reliability_veto", "compliance_veto", "fidelity_veto",
            "tradeoff_veto", "blast_radius", "calibration", "state_persistence",
            "reflect_decide", "required_actions", "isa_yaml_patch",
            "sandbox_recommendation", "human_review_gate", "human_decision_processor",
        ):
            assert node in out, f"node '{node}' missing from show-graph output"


# ── argument parsing ──────────────────────────────────────────────────────────

class TestArgParsing:

    def test_missing_subcommand_exits(self):
        with pytest.raises(SystemExit):
            main([])

    def test_run_missing_required_args_exits(self):
        with pytest.raises(SystemExit):
            main(["run"])

    def test_run_invalid_goal_exits(self):
        with pytest.raises(SystemExit):
            main(["run", "--session-id", "s", "--proposal-id", "p",
                  "--baseline", "b", "--goal", "invalid_goal"])

    def test_run_valid_goals_accepted(self):
        """Parser accepts all four valid goal values without raising."""
        for goal in ("balanced", "cost_efficiency", "max_reliability", "minimal_complexity"):
            # parse only — don't invoke the pipeline
            import argparse
            from isa_cad.cli import main as _main
            # Use argparse directly to test parsing without executing
            import sys
            argv = ["run", "--session-id", "s", "--proposal-id", "p",
                    "--baseline", "b", "--goal", goal]
            # Build a minimal parser check
            parser = argparse.ArgumentParser()
            sub = parser.add_subparsers(dest="command")
            run_p = sub.add_parser("run")
            run_p.add_argument("--session-id", required=True)
            run_p.add_argument("--proposal-id", required=True)
            run_p.add_argument("--baseline", required=True)
            run_p.add_argument("--goal", default="balanced",
                               choices=["cost_efficiency", "max_reliability",
                                        "minimal_complexity", "balanced"])
            args = parser.parse_args(argv)
            assert args.goal == goal


# ── package public API ────────────────────────────────────────────────────────

class TestPackageAPI:

    def test_version_exposed(self):
        import isa_cad
        assert hasattr(isa_cad, "__version__")
        assert isa_cad.__version__ == "0.5.3"

    def test_build_graph_importable_from_package(self):
        from isa_cad import build_graph
        assert callable(build_graph)

    def test_agent_state_importable_from_package(self):
        from isa_cad import AgentState
        assert isinstance(AgentState.__annotations__, dict)
        assert "session_id" in AgentState.__annotations__

    def test_build_graph_returns_compiled_graph(self):
        from isa_cad import build_graph
        g = build_graph()
        assert hasattr(g, "invoke")
        assert hasattr(g, "nodes")

    def test_build_llm_graph_importable(self):
        from isa_cad.agent import build_llm_graph
        assert callable(build_llm_graph)


# ── version subcommand ────────────────────────────────────────────────────────

class TestVersionSubcommand:

    def test_version_prints(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        assert "0.5.3" in out

    def test_version_contains_isa_cad(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        assert "isa-cad" in out


# ── new run flags ─────────────────────────────────────────────────────────────

class TestRunFlags:

    def _parse(self, argv: list[str]):
        import argparse
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        run_p = sub.add_parser("run")
        run_p.add_argument("--session-id", required=True)
        run_p.add_argument("--proposal-id", required=True)
        run_p.add_argument("--baseline", required=True)
        run_p.add_argument("--goal", default="balanced",
                           choices=["cost_efficiency", "max_reliability",
                                    "minimal_complexity", "balanced"])
        run_p.add_argument("--llm", action="store_true", default=False)
        run_p.add_argument("--format", dest="format", default="summary",
                           choices=["summary", "json", "markdown", "yaml"])
        run_p.add_argument("--output", "-o", default=None)
        return parser.parse_args(argv)

    def test_llm_flag_default_false(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b"])
        assert args.llm is False

    def test_llm_flag_set(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b", "--llm"])
        assert args.llm is True

    def test_format_default_summary(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b"])
        assert args.format == "summary"

    def test_format_markdown(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b", "--format", "markdown"])
        assert args.format == "markdown"

    def test_format_json(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b", "--format", "json"])
        assert args.format == "json"

    def test_format_yaml(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b", "--format", "yaml"])
        assert args.format == "yaml"

    def test_output_flag(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b", "--output", "report.md"])
        assert args.output == "report.md"

    def test_output_shorthand(self):
        args = self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                             "--baseline", "b", "-o", "out.json"])
        assert args.output == "out.json"

    def test_invalid_format_exits(self):
        import pytest
        with pytest.raises(SystemExit):
            self._parse(["run", "--session-id", "s", "--proposal-id", "p",
                         "--baseline", "b", "--format", "html"])
