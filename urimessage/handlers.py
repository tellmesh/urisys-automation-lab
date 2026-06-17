from __future__ import annotations

from typing import Any


def alert_send(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "")
    channel = str(payload.get("channel") or "alert")
    severity = str(payload.get("severity") or "info")
    return {
        "ok": True,
        "text": text,
        "channel": channel,
        "severity": severity,
        "delivered": bool(text),
        "echo": True,
    }
