import json
import os
import sys
import urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
URISYS_PY = LAB.parent / "packages" / "python"
sys.path.insert(0, str(URISYS_PY))
sys.path.insert(0, str(LAB / "packages" / "python"))
sys.path.insert(0, str(LAB.parent / "urirdp-docker" / "packages" / "python"))

from urirdpedge.runtime import Runtime  # type: ignore

import uristt.routes as stt_routes
import urichat.routes as chat_routes
import uriwebrtc.routes as webrtc_routes


def _rt() -> Runtime:
    rt = Runtime(config={"chat": {"urisys_base_url": "http://127.0.0.1:8795"}})
    stt_routes.register(rt)
    chat_routes.register(rt)
    webrtc_routes.register(rt)
    return rt


def test_stt_session_and_transcript():
    rt = _rt()
    start = rt.call(
        "stt://local/session/main/command/start",
        {"language": "pl-PL", "mode": "browser"},
        {"approved": True},
    )
    assert start["ok"]
    tx = rt.call("stt://local/session/main/query/transcript", {"text": "kliknij OK"}, {})
    assert tx["ok"]
    assert "OK" in tx["result"]["transcript"].upper()


def test_chat_uri_execute_dry_run():
    rt = _rt()
    res = rt.call(
        "chat://local/uri/command/execute",
        {"transcript": "kliknij OK", "dry_run": True, "approved": True},
        {"approved": True, "dry_run": True},
    )
    assert res["ok"]
    assert res["result"]["mode"] == "dry_run"
    assert "kvm://" in res["result"]["uri"]


def test_webrtc_data_send():
    rt = _rt()
    start = rt.call("webrtc://local/session/rdp-chat/command/start", {"room": "rdp-lab"}, {"approved": True})
    assert start["ok"]
    sent = rt.call(
        "webrtc://local/session/rdp-chat/data/command/send",
        {"envelope": {"uri": "rdp://local/display/query/status", "payload": {}}},
        {"approved": True},
    )
    assert sent["ok"]
    assert sent["result"]["envelope"]["uri"].startswith("rdp://")
