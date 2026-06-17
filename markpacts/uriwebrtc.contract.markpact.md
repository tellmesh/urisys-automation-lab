# uriwebrtc contract (MVP)

Scheme: `webrtc://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: uriwebrtc.contract
  version: 0.1.0
scheme: webrtc
commands:
  - id: webrtc.session.start
    pattern: webrtc://local/session/{session}/command/start
    side_effects: true
    requires_approval: true
  - id: webrtc.data.send
    pattern: webrtc://local/session/{session}/data/command/send
    side_effects: true
    requires_approval: true
```

## Routes

```txt
webrtc://local/session/{session}/command/start
webrtc://local/session/{session}/data/command/send
```

## Role

Transport only — media + DataChannel URI envelopes.

Execution stays in `kvm://`, `him://`, `rdp://`, etc.

## DataChannel envelope

```json
{
  "uri": "kvm://local/task/command/click-text",
  "payload": { "text": "OK" },
  "context": { "approved": true, "dry_run": true }
}
```

Signaling (future): `signaling://local/room/{id}/…`
