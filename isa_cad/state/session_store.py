from __future__ import annotations

import json
from pathlib import Path

from isa_cad.config.settings import settings
from isa_cad.state.canvas_state import CanvasSessionState


class SessionStore:
    """
    File-based store for CanvasSessionState.
    Persists sessions to disk so they survive process restarts
    and can be resumed after async Observed Graph refresh.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (settings.CHECKPOINT_DIR / "sessions")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self._base_dir / f"{safe_id}.json"

    def save(self, state: CanvasSessionState) -> Path:
        """Persist a session to disk. Returns the file path."""
        path = self._path(state.session_id)
        path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path

    def load(self, session_id: str) -> CanvasSessionState | None:
        """Load a session from disk. Returns None if not found."""
        path = self._path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return CanvasSessionState.model_validate(data)

    def delete(self, session_id: str) -> bool:
        """Delete a persisted session. Returns True if it existed."""
        path = self._path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_sessions(self) -> list[str]:
        """Return all persisted session IDs."""
        return [p.stem for p in self._base_dir.glob("*.json")]
