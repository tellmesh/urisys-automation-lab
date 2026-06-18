from __future__ import annotations

from urisysedge.runtime import Runtime

import uristt.routes as uristt


def test_stt_and_tts_mock():
    rt = Runtime()
    uristt.register(rt)
    start = rt.call(
        "stt://local/session/main/command/start",
        {"language": "pl-PL"},
        {"approved": True, "params": {"session": "main"}},
    )
    assert start["ok"]
    tx = rt.call(
        "stt://local/session/main/query/transcript",
        {"text": "kliknij OK"},
        {"params": {"session": "main"}},
    )
    assert tx["ok"]
    speak = rt.call(
        "tts://local/session/main/command/speak",
        {"text": "hello"},
        {"approved": True, "params": {"session": "main"}},
    )
    assert speak["ok"]
