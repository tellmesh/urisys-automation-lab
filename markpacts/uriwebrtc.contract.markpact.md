# uriwebrtc contract (deprecated location)

**Canonical pack:** [tellmesh/uriwebrtc](https://github.com/tellmesh/uriwebrtc)  
**Markpact:** `uriwebrtc/markpacts/uriwebrtc.markpact.md`  
**ifURI browser contract:** [if-uri/app/docs/WEBRTC.md](https://github.com/if-uri/app/blob/main/docs/WEBRTC.md)

This file is kept for historical links from `urisys-automation-lab`. Do not extend here.

## Scheme: `webrtc://`

### Routes (uriwebrtc >= 0.1.0)

```txt
webrtc://local/session/{session}/command/start
webrtc://local/session/{session}/data/command/send
webrtc://local/session/{session}/signal/command/post
webrtc://local/session/{session}/signal/query/inbox
```

### Role

- **Node pack** — session tracking, signal inbox mock, envelope capture (no execution).
- **Browser P2P** — ifURI `/api/webrtc/signal` + data channel `voice` / `voice-reply` (see WEBRTC.md).

### DataChannel envelope (node `data/command/send`)

```json
{
  "uri": "kvm://local/task/command/click-text",
  "payload": { "text": "OK" },
  "context": { "approved": true, "dry_run": true }
}
```

### Browser voice envelope (ifURI peer)

```json
{ "kind": "voice", "id": "v…", "text": "sprawdź health", "dry_run": false }
{ "kind": "voice-reply", "id": "v…", "ok": true, "text": "…" }
```
