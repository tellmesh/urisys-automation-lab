"""Unit tests for urillm text_plan() handler."""

from __future__ import annotations

from unittest.mock import patch

from urillm.handlers import text_plan


def test_plan_phrase_map_default():
    result = text_plan({"transcript": "kliknij OK"}, {"approved": True, "dry_run": False, "allow_real": True})
    assert result["ok"]
    assert result["uri"] == "kvm://local/task/command/click-text"
    assert result["payload"]["text"] == "OK"
    assert result["model"] == "phrase-map"


def test_plan_rejects_disallowed_scheme():
    result = text_plan(
        {"transcript": "move mouse", "allowed_schemes": ["kvm"]},
        {"approved": True, "dry_run": False, "allow_real": True},
    )
    assert not result["ok"]
    assert "him" in result["error"]


def test_plan_litellm_fallback_on_error():
    ctx = {
        "approved": True,
        "dry_run": False,
        "allow_real": True,
        "config": {"llm": {"driver": "litellm", "model": "gpt-4o-mini", "api_key": "test-key"}},
    }
    with patch("urillm.handlers.litellm_chat", side_effect=RuntimeError("offline")):
        result = text_plan({"transcript": "kliknij OK", "allowed_schemes": ["kvm"]}, ctx)
    assert result["ok"]
    assert result["model"] == "phrase-map"
    assert result["uri"] == "kvm://local/task/command/click-text"
