from __future__ import annotations

import tempfile
from pathlib import Path

from isa_cad.state.canvas_state import CanvasSessionState
from isa_cad.state.session_store import SessionStore


def make_session(sid: str = "test-session-001") -> CanvasSessionState:
    return CanvasSessionState(session_id=sid, baseline_ref="baseline.prod")


def test_save_and_load(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    session = make_session()
    store.save(session)
    loaded = store.load("test-session-001")
    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.baseline_ref == session.baseline_ref


def test_load_nonexistent_returns_none(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    assert store.load("ghost-session") is None


def test_delete_existing(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    store.save(make_session())
    assert store.delete("test-session-001") is True
    assert store.load("test-session-001") is None


def test_delete_nonexistent(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    assert store.delete("ghost") is False


def test_list_sessions(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    store.save(make_session("session-a"))
    store.save(make_session("session-b"))
    ids = store.list_sessions()
    assert "session-a" in ids
    assert "session-b" in ids


def test_roundtrip_preserves_layers(tmp_path: Path):
    from isa_cad.state.canvas_state import SandboxLayer
    store = SessionStore(base_dir=tmp_path)
    session = make_session("layered-session")
    session.add_layer(SandboxLayer(id="layer-1", title="L1"))
    session.activate_layer("layer-1")
    session.assumptions = ["CDN CHR assumed = 0.85"]

    store.save(session)
    loaded = store.load("layered-session")

    assert loaded is not None
    assert loaded.get_layer("layer-1") is not None
    assert "layer-1" in loaded.active_layer_ids
    assert loaded.assumptions == ["CDN CHR assumed = 0.85"]
