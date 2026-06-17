from __future__ import annotations

from typing import Any

_ROOMS: dict[str, dict[str, Any]] = {}


def _room_id(context: dict[str, Any]) -> str:
    params = context.get("params") or {}
    return params.get("session") or params.get("room") or "rdp-chat"


def session_start(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    room = payload.get("room") or _room_id(context)
    entry = {
        "room": room,
        "status": "ready",
        "signaling": "loopback",
        "data_channel": "uri-envelope",
    }
    _ROOMS[room] = entry
    return {"ok": True, "webrtc": entry, "note": "Browser WebRTC loopback; backend tracks session only."}


def data_send(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    room = payload.get("room") or _room_id(context)
    envelope = payload.get("envelope") or {}
    _ROOMS.setdefault(room, {"room": room, "status": "ready"})
    return {
        "ok": True,
        "room": room,
        "envelope": envelope,
        "received": True,
        "hint": "Forward envelope to chat://local/uri/command/execute for execution.",
    }
