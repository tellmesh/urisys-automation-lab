"""Lab flow 09 structure tests."""

from __future__ import annotations

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
URISYS_PY = LAB.parent / "packages" / "python"
sys.path.insert(0, str(URISYS_PY))
sys.path.insert(0, str(LAB / "packages" / "python"))
sys.path.insert(0, str(LAB.parent / "urirdp-docker" / "packages" / "python"))


def test_flow_09_no_chat_bridge():
    import yaml

    flow = LAB / "flows" / "09_webrtc_video_chat_rdp.uri.flow.yaml"
    data = yaml.safe_load(flow.read_text(encoding="utf-8"))
    uris = [step["uri"] for step in data["do"]]
    assert all("chat://" not in uri for uri in uris)
    assert uris[-1] == "kvm://local/monitor/primary/query/screenshot"
    assert [step["id"] for step in data["do"]] == [
        "webrtc_start",
        "webrtc_send",
        "capture_desktop",
    ]
