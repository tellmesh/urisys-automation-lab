from __future__ import annotations

from typing import Any

_SESSIONS: dict[str, dict[str, Any]] = {}


def _session_id(context: dict[str, Any]) -> str:
    return (context.get("params") or {}).get("session", "main")


def session_start(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    sid = _session_id(context)
    entry = {
        "session": sid,
        "language": payload.get("language", "pl-PL"),
        "mode": payload.get("mode", "browser"),
        "status": "listening",
        "transcript": "",
    }
    _SESSIONS[sid] = entry
    return {"ok": True, "session": entry}


def session_transcript(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    sid = _session_id(context)
    session = _SESSIONS.setdefault(
        sid,
        {"session": sid, "language": "pl-PL", "mode": "browser", "status": "idle", "transcript": ""},
    )
    if payload.get("text"):
        session["transcript"] = str(payload["text"])
    if not session["transcript"]:
        session["transcript"] = payload.get("default_text") or "kliknij OK"
    return {
        "ok": True,
        "session": sid,
        "transcript": session["transcript"],
        "language": session.get("language", "pl-PL"),
        "engine": "mock-browser" if session.get("mode") == "browser" else "mock-local",
    }


def audio_transcribe(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    text = payload.get("text") or payload.get("transcript")
    if not text and payload.get("audio_b64"):
        text = "kliknij OK"
    if not text:
        text = "kliknij OK"
    return {
        "ok": True,
        "transcript": text,
        "language": payload.get("language", "pl-PL"),
        "engine": payload.get("engine", "mock"),
        "audio_received": bool(payload.get("audio_b64")),
    }
