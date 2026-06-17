import urichat
import uristt
import uriwebrtc
from urisysedge.runtime import Runtime


def _rt() -> Runtime:
    rt = Runtime(config={"chat": {"urisys_base_url": "http://127.0.0.1:8795"}})
    uristt.register(rt)
    urichat.register(rt)
    uriwebrtc.register(rt)
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


def test_webrtc_signal_relay():
    rt = _rt()
    posted = rt.call(
        "webrtc://local/session/room-a/signal/command/post",
        {"room": "room-a", "from": "http://a", "type": "offer", "data": {"type": "offer", "sdp": "v=0"}},
        {"approved": True},
    )
    assert posted["ok"]
    inbox = rt.call("webrtc://local/session/room-a/signal/query/inbox", {"room": "room-a", "since": 0}, {})
    assert inbox["ok"]
    assert len(inbox["result"]["signals"]) == 1
