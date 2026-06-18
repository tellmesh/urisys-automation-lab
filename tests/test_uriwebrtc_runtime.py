from __future__ import annotations

from urisysedge.runtime import Runtime

import uriwebrtc


def test_webrtc_session_and_signal():
    rt = Runtime()
    uriwebrtc.register(rt)
    start = rt.call(
        "webrtc://local/session/rdp-chat/command/start",
        {"room": "rdp-chat"},
        {"approved": True, "params": {"session": "rdp-chat"}},
    )
    assert start["ok"]
    posted = rt.call(
        "webrtc://local/session/rdp-chat/signal/command/post",
        {"from": "peer-a", "type": "offer", "data": {"sdp": "v=0"}},
        {"approved": True, "params": {"session": "rdp-chat"}},
    )
    assert posted["ok"]
    inbox = rt.call(
        "webrtc://local/session/rdp-chat/signal/query/inbox",
        {"since": 0},
        {"params": {"session": "rdp-chat"}},
    )
    assert inbox["ok"]
    assert len(inbox["result"]["signals"]) == 1
