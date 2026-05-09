from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from isa_cad.config.settings import settings
from isa_cad.core.models.checkpoint import Checkpoint, PartialReviewerOutput
from isa_cad.core.models.enums import OptimizationGoal
from isa_cad.state.canvas_state import CanvasSessionState


class CheckpointStore:
    """
    File-based store for Checkpoint objects.
    Persists checkpoints to disk so they survive process restarts.
    Each checkpoint is keyed by its id.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (settings.CHECKPOINT_DIR / "checkpoints")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, checkpoint_id: str) -> Path:
        safe = checkpoint_id.replace("/", "_").replace("\\", "_").replace(":", "-")
        return self._base_dir / f"{safe}.json"

    # ── persistence ──────────────────────────────────────────────────────────

    def save(self, checkpoint: Checkpoint) -> Path:
        """Persist a checkpoint to disk. Returns the file path."""
        path = self._path(checkpoint.id)
        path.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, checkpoint_id: str) -> Checkpoint | None:
        """Load a checkpoint by id. Returns None if not found."""
        path = self._path(checkpoint_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint.model_validate(data)

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint. Returns True if it existed."""
        path = self._path(checkpoint_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_checkpoints(self) -> list[str]:
        """Return all persisted checkpoint IDs."""
        return [p.stem for p in self._base_dir.glob("*.json")]

    def load_all_for_session(self, canvas_session_id: str) -> list[Checkpoint]:
        """Return all checkpoints for a given canvas session, sorted by saved_at."""
        results = []
        for cid in self.list_checkpoints():
            cp = self.load(cid)
            if cp and cp.canvas_session_id == canvas_session_id:
                results.append(cp)
        results.sort(key=lambda c: c.saved_at)
        return results

    # ── factory ──────────────────────────────────────────────────────────────

    @staticmethod
    def create_from_session(
        session: CanvasSessionState,
        pending_action: str,
        resume_node: str = "ContextAndFreshnessNode",
        partial_outputs: list[PartialReviewerOutput] | None = None,
    ) -> Checkpoint:
        """
        Build a Checkpoint from the current CanvasSessionState.
        Called by StatePersistenceNode before async refresh.
        """
        now = datetime.now(UTC)
        ts = now.strftime("%Y-%m-%d-%H%M%S") + f"-{now.microsecond:06d}"
        checkpoint_id = f"checkpoint.{session.session_id}.{ts}"

        return Checkpoint(
            id=checkpoint_id,
            canvas_session_id=session.session_id,
            baseline_ref=session.baseline_ref,
            sandbox_layer_ids=list(session.active_layer_ids),
            optimization_goal=session.optimization_goal,
            pending_action=pending_action,
            resume_node=resume_node,
            preserved_outputs=partial_outputs or [],
            assumptions=list(session.assumptions),
        )

    @staticmethod
    def restore_session(
        session: CanvasSessionState,
        checkpoint: Checkpoint,
    ) -> CanvasSessionState:
        """
        Restore session state from a checkpoint.
        Re-activates the layers that were active at checkpoint time.
        Does NOT overwrite the session's baseline_graph (that's fetched fresh).
        """
        session.optimization_goal = checkpoint.optimization_goal
        session.assumptions = list(checkpoint.assumptions)

        # Re-activate only layers that still exist in the session
        session.active_layer_ids = [
            lid for lid in checkpoint.sandbox_layer_ids
            if session.get_layer(lid) is not None
        ]

        # Restore partial outputs into session's partial_outputs dict
        for output in checkpoint.preserved_outputs:
            session.partial_outputs[output.node_name] = output.payload

        checkpoint.mark_resumed()
        return session
