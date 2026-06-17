"""Lab tests for message pack and flow 08 planning."""

from __future__ import annotations

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
URISYS_PY = LAB.parent / "packages" / "python"
sys.path.insert(0, str(URISYS_PY))
sys.path.insert(0, str(LAB / "packages" / "python"))
sys.path.insert(0, str(LAB / "server"))
sys.path.insert(0, str(LAB.parent / "urirdp-docker" / "packages" / "python"))

from urirdpedge.runtime import Runtime  # type: ignore

import uristt.routes as stt_routes
import urimessage.routes as message_routes
import urirdp_llm.routes as llm_routes


def _rt() -> Runtime:
    rt = Runtime(config={"chat": {"urisys_base_url": "http://127.0.0.1:8795"}})
    stt_routes.register(rt)
    message_routes.register(rt)
    llm_routes.register(rt)
    return rt


def test_message_alert_send():
    rt = _rt()
    res = rt.call(
        "message://local/alert/command/send",
        {"text": "critical error in logs", "severity": "critical", "approved": True},
        {"approved": True},
    )
    assert res["ok"]
    assert res["result"]["delivered"] is True
    assert res["result"]["severity"] == "critical"


def test_llm_plan_from_transcript():
    rt = _rt()
    res = rt.call(
        "llm://local/text/query/plan",
        {"transcript": "kliknij OK", "allowed_schemes": ["kvm"]},
        {"approved": True, "dry_run": False, "allow_real": True},
    )
    assert res["ok"]
    assert res["result"]["uri"] == "kvm://local/task/command/click-text"
    assert res["result"]["payload"]["text"] == "OK"


def test_flow_08_plan_expand():
    import yaml

    flow = LAB / "flows" / "08_voice_command_to_kvm.uri.flow.yaml"
    data = yaml.safe_load(flow.read_text(encoding="utf-8"))
    steps = data["do"]
    assert [step["id"] for step in steps] == [
        "stt_start",
        "stt_transcript",
        "map_voice",
        "execute_mapped",
    ]
    assert steps[2]["uri"] == "llm://local/text/query/plan"
    assert steps[2]["payload"]["transcript_from"] == "stt_transcript"
    assert steps[3]["payload"]["payload_from"] == "map_voice"
