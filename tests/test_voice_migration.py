"""Consumer contract tests: no archived pack and no desktop/network side effects."""
import builtins
from pathlib import Path

import pytest

from urisys_lab.sessions import runners


@pytest.mark.parametrize("plan_ok", [True, False])
def test_session_plans_before_execution(monkeypatch, tmp_path, plan_ok):
    calls = []
    for name in ("write_meta", "_record_health", "_bootstrap_rdp", "copy_container_file", "docker_logs"):
        monkeypatch.setattr(runners, name, lambda *a, **k: None)
    monkeypatch.setattr(runners, "TELLMESH", tmp_path)
    monkeypatch.setattr(runners, "finalize_session", lambda directory, started, code, steps: code)

    def call(directory, steps, seq, name, uri, payload, ctx, **kwargs):
        calls.append((uri, payload, ctx))
        steps.append({"status": "pass"})
        if uri.startswith("llm://"):
            return {"ok": True, "result": {"ok": plan_ok, "uri": "kvm://local/task/command/click-text", "payload": {"text": "OK"}}}
        return {"ok": True, "result": {"clicked": True}}

    monkeypatch.setattr(runners, "_call_and_record", call)
    result = runners.session_automation_lab(tmp_path, use_existing=True)
    assert calls[1][0] == "llm://local/text/query/plan"
    assert result == (0 if plan_ok else 1)
    if plan_ok:
        assert len(calls) == 4
        assert calls[2][0] == calls[3][0] == "kvm://local/task/command/click-text"
        assert calls[2][1] == calls[3][1] == {"text": "OK"}
        assert calls[2][2]["dry_run"] is True
        assert calls[3][2] == {"approved": True, "dry_run": False, "allow_real": True}
    else:
        assert len(calls) == 2


def test_runtime_starts_without_urichat(monkeypatch, tmp_path):
    from server import automation_lab_server as server
    original_import = builtins.__import__

    def no_archived_pack(name, *args, **kwargs):
        assert name.split(".")[0] != "urichat", "archived pack imported"
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_archived_pack)
    monkeypatch.setattr(server, "LAB_ROOT", tmp_path)
    monkeypatch.setenv("URISYS_LAB_PACKS", "stt,message,webrtc")
    runtime = server.build_lab_runtime(str(tmp_path / "missing.json"))
    response = runtime.call("message://local/alert/command/send", {"text": "hello", "channel": "main"}, {"approved": True})
    assert response["ok"]
    assert response["result"]["channel"] == "main"
    assert not runtime.call("chat://local/uri/command/execute", {}, {"approved": True})["ok"]
