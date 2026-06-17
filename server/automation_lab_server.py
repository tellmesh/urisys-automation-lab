from __future__ import annotations

import importlib
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = LAB_ROOT / "packages" / "python"
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

URIRDP_PACKAGES = LAB_ROOT.parent / "urirdp-docker" / "packages" / "python"
if URIRDP_PACKAGES.is_dir() and str(URIRDP_PACKAGES) not in sys.path:
    sys.path.insert(0, str(URIRDP_PACKAGES))

try:
    from labedge.runtime import Runtime, load_json
except ImportError:
    from urirdpedge.runtime import Runtime, load_json  # type: ignore


def build_lab_runtime(config_path: str | None = None) -> Runtime:
    config_file = config_path or os.environ.get(
        "URISYS_CONFIG",
        str(LAB_ROOT.parent / "urirdp-docker" / "config" / "rdp-kvm-profile.json"),
    )
    config = load_json(config_file) if Path(config_file).exists() else {}
    config.setdefault("chat", {})
    config["chat"]["urisys_base_url"] = os.environ.get("URISYS_RDP_URL", "http://127.0.0.1:8795")

    rt = Runtime(events_path=str(LAB_ROOT / "data" / "events.jsonl"), config=config)

    packs = os.environ.get("URISYS_LAB_PACKS", "rdp,kvm,him,ocr,llm,stt,chat,message,webrtc").split(",")
    packs = [p.strip() for p in packs if p.strip()]
    urirdp_available = URIRDP_PACKAGES.is_dir()
    if not urirdp_available:
        packs = [p for p in packs if p in {"stt", "chat", "message", "webrtc"}]
    if "rdp" in packs:
        import urirdp

        urirdp.register(rt)
    if "him" in packs:
        import urirdp_him

        urirdp_him.register(rt)
    if "ocr" in packs:
        import urirdp_ocr

        urirdp_ocr.register(rt)
    if "llm" in packs:
        import urirdp_llm

        urirdp_llm.register(rt)
    if "kvm" in packs:
        import urirdp_kvm

        urirdp_kvm.register(rt)
    if "stt" in packs:
        import uristt.routes as stt_routes

        stt_routes.register(rt)
    if "chat" in packs:
        import urichat.routes as chat_routes

        chat_routes.register(rt)
    if "message" in packs:
        import urimessage.routes as message_routes

        message_routes.register(rt)
    if "webrtc" in packs:
        import uriwebrtc.routes as webrtc_routes

        webrtc_routes.register(rt)
    return rt


def forward_uri_call(base_url: str, uri: str, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"uri": uri, "payload": payload, "context": context}).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/uri/call",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "uri": uri, "error": raw or str(exc)}


class LabHandler(BaseHTTPRequestHandler):
    runtime: Runtime
    static_root: Path
    forward_url: str
    forward_schemes: set[str]

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[lab] {self.address_string()} {fmt % args}")

    def _json(self, status: int, data: dict[str, Any]) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(body or "{}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            return self._json(200, {"ok": True, "service": "urisys-automation-lab"})
        if self.path == "/uri/routes":
            return self._json(200, {"ok": True, "routes": [r.pattern for r in self.runtime.routes]})

        rel = self.path.lstrip("/")
        if rel in ("", "index.html"):
            rel = "index.html"
        target = (self.static_root / rel).resolve()
        if not str(target).startswith(str(self.static_root.resolve())) or not target.is_file():
            return self._json(404, {"ok": False, "error": "not found"})
        content = target.read_bytes()
        ctype = "text/html" if target.suffix == ".html" else "application/javascript" if target.suffix == ".js" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if self.path == "/uri/call":
            req = self._read_json()
            uri = req.get("uri", "")
            payload = req.get("payload") or {}
            context = req.get("context") or {}
            context.setdefault("urisys_base_url", self.forward_url)

            scheme = uri.split("://", 1)[0] if "://" in uri else ""
            if scheme in self.forward_schemes:
                try:
                    forwarded = forward_uri_call(self.forward_url, uri, payload, context)
                    return self._json(200 if forwarded.get("ok") else 400, forwarded)
                except urllib.error.URLError as exc:
                    return self._json(502, {"ok": False, "error": str(exc), "forwarded_to": self.forward_url})

            result = self.runtime.call(uri, payload, context)
            if (
                not result.get("ok")
                and result.get("type") == "route_not_found"
                and scheme
                and scheme not in {"stt", "chat", "webrtc"}
            ):
                try:
                    forwarded = forward_uri_call(self.forward_url, uri, payload, context)
                    return self._json(200 if forwarded.get("ok") else 400, forwarded)
                except urllib.error.URLError as exc:
                    return self._json(502, {"ok": False, "error": str(exc), "forwarded_to": self.forward_url})
            return self._json(200 if result.get("ok") else 400, result)

        if self.path == "/api/stt/transcribe":
            req = self._read_json()
            result = self.runtime.call(
                "stt://local/audio/command/transcribe",
                req,
                {"approved": True, **(req.get("context") or {})},
            )
            return self._json(200 if result.get("ok") else 400, result)

        if self.path == "/uri/flow":
            from flow_runner import run_flow_file

            req = self._read_json()
            flow_path = req.get("path") or req.get("flow")
            if not flow_path:
                return self._json(400, {"ok": False, "error": "path or flow required"})
            context = req.get("context") or {}
            context.setdefault("approved", True)
            context.setdefault("urisys_base_url", self.forward_url)

            def _call(uri: str, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
                scheme = uri.split("://", 1)[0] if "://" in uri else ""
                if scheme in self.forward_schemes:
                    return forward_uri_call(self.forward_url, uri, payload, ctx)
                return self.runtime.call(uri, payload, ctx)

            try:
                result = run_flow_file(flow_path, call_uri=_call, context=context)
            except Exception as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            return self._json(200, result)

        return self._json(404, {"ok": False, "error": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8099) -> None:
    runtime = build_lab_runtime()
    forward_url = os.environ.get("URISYS_RDP_URL", "http://127.0.0.1:8795")
    forward_raw = os.environ.get(
        "URISYS_LAB_FORWARD_SCHEMES",
        "rdp,kvm,him,ocr,llm,browser,shell,http,https,env",
    )
    forward_schemes = {s.strip() for s in forward_raw.split(",") if s.strip()}

    handler = LabHandler
    handler.runtime = runtime
    handler.static_root = LAB_ROOT / "web"
    handler.forward_url = forward_url
    handler.forward_schemes = forward_schemes

    server = ThreadingHTTPServer((host, port), handler)
    print(f"urisys-automation-lab http://{host}:{port}")
    print(f"forward {sorted(forward_schemes)} -> {forward_url}")
    print("routes:")
    for route in runtime.routes:
        print(" -", route.pattern)
    server.serve_forever()


if __name__ == "__main__":
    serve(
        host=os.environ.get("URISYS_LAB_HOST", "127.0.0.1"),
        port=int(os.environ.get("URISYS_LAB_PORT", "8099")),
    )
