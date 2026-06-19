import base64
import json
from pathlib import Path

from urisys_lab.core import backfill_session_images, extract_step_screenshots

_PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a4944454154789c636000000200015d0b2a0000000049454e44ae426082"
    )
    * 3
).decode("ascii")


def test_extract_nested_forward_result(tmp_path: Path):
    step = {
        "id": "screen_feed",
        "response": {
            "ok": True,
            "result": {
                "ok": True,
                "result": {"mime": "image/png", "base64": _PNG, "width": 1, "height": 1},
            },
            "event": {
                "result": {"mime": "image/png", "base64": _PNG, "width": 1, "height": 1},
            },
        },
    }
    saved = extract_step_screenshots(step, session_dir=tmp_path, flow_id="flow08")
    assert saved == ["screenshots/flow08__screen_feed.png"]
    assert (tmp_path / saved[0]).is_file()
    assert "base64" not in json.dumps(step)


def test_skip_text_plain_mock_screenshot(tmp_path: Path):
    step = {
        "id": "kvm_screenshot",
        "response": {
            "ok": True,
            "result": {
                "mime": "text/plain",
                "base64": base64.b64encode(b"Mock screenshot with buttons").decode("ascii"),
            },
        },
    }
    assert extract_step_screenshots(step, session_dir=tmp_path, flow_id="upgrade") == []


def test_backfill_from_responses_dir(tmp_path: Path):
    responses = tmp_path / "responses"
    responses.mkdir(parents=True)
    (responses / "flow__frame.json").write_text(
        json.dumps(
            {
                "id": "frame",
                "response": {"ok": True, "result": {"mime": "image/png", "base64": _PNG}},
            }
        ),
        encoding="utf-8",
    )
    saved = backfill_session_images(tmp_path)
    assert saved == ["screenshots/flow__frame.png"]
