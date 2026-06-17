"""Unit tests for urirdp_llm plan() handler."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB.parent / "urirdp-docker" / "packages" / "python"))

from urirdp_llm.handlers import plan  # noqa: E402


def test_plan_phrase_map_default():
    result = plan({"transcript": "kliknij OK"}, {"approved": True, "dry_run": False, "allow_real": True})
    assert result["ok"]
    assert result["uri"] == "kvm://local/task/command/click-text"
    assert result["payload"]["text"] == "OK"
    assert result["model"] == "phrase-map"


def test_plan_rejects_disallowed_scheme():
    result = plan(
        {"transcript": "otwórz przeglądarkę", "allowed_schemes": ["kvm"]},
        {"approved": True, "dry_run": False, "allow_real": True},
    )
    assert not result["ok"]
    assert "browser" in result["error"]


def test_plan_litellm_fallback_on_error():
    ctx = {
        "approved": True,
        "dry_run": False,
        "allow_real": True,
        "config": {"llm": {"driver": "litellm", "model": "gpt-4o-mini", "api_key": "test-key"}},
    }
    with patch("urirdp_llm.handlers._decide_litellm", side_effect=RuntimeError("offline")):
        result = plan({"transcript": "kliknij OK", "allowed_schemes": ["kvm"]}, ctx)
    assert result["ok"]
    assert result["model"] == "phrase-map"
    assert result["uri"] == "kvm://local/task/command/click-text"
