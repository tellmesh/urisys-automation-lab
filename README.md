# urisys-automation-lab

10 przykładowych automatyzacji (TUI + GUI + STT + WebRTC) z lokalnym interfejsem web.

## Szybki start

### Docker (zalecane — jeden stack)

Wymaga checkout **tellmesh** workspace (`urisys/` obok `uri2flow/`, `uri3/`, `uri2ops/`).

```bash
cd urisys-automation-lab
bash scripts/docker-up.sh
bash scripts/docker-smoke.sh   # opcjonalnie
```

| Usługa | URL |
|--------|-----|
| Lab UI + STT/chat/WebRTC | http://127.0.0.1:8099 |
| urirdp URI API | http://127.0.0.1:8795/uri/call |
| RDP desktop | `127.0.0.1:3389` (user `urisys`) |

Zatrzymanie: `bash scripts/docker-down.sh` · logi: `bash scripts/docker-logs.sh`

### Lokalnie (bez Docker)

```bash
cd urisys-automation-lab
bash scripts/validate-flows.sh
bash scripts/run-lab.sh
```

## Stack

```txt
src/urisys_lab/           → test sessions, lenovo remote flows (moved from urisys)
flows/*.uri.flow.yaml     → uri2flow
server/                   → lab gateway :8099
../uristt, ../uriwebrtc, ../urimessage, ../urichat  → standalone voice packs
../urirdpedge/            → RDP/KVM stack CLI (optional `[rdp]` extra / dev)
web/                      → getUserMedia + Web Speech + WebRTC DataChannel
urirdp-docker :8795       → rdp/kvm/him/ocr/llm execution (Docker)
```

## Flow 08 (voice → KVM)

Standardized pipeline: **STT → llm plan → kvm execute** (legacy `chat://` deprecated — [CHAT-DEPRECATED.md](docs/CHAT-DEPRECATED.md))

```yaml
do:
  - id: stt_start
    uri: stt://local/session/main/command/start
  - id: stt_transcript
    uri: stt://local/session/main/query/transcript
    after: stt_start
  - id: map_voice
    uri: llm://local/text/query/plan
    after: stt_transcript
    payload:
      transcript_from: stt_transcript
  - id: execute_mapped
    uri: kvm://local/task/command/click-text
    after: map_voice
    if: map_voice.ok == true
    payload:
      payload_from: map_voice
```

NL log decision (host uri3): see [`uri3/examples/nl-log-decision.uri.flow.yaml`](../../uri3/examples/nl-log-decision.uri.flow.yaml)

## Powiązane

- [`tellmesh/examples/39_system_automations`](../../tellmesh/examples/39_system_automations/)
- [`urisys-node`](../urisys-node/) — jawnie zainstalowany slave runtime (:8790)
- [`uri2voice`](../../uri2voice/) — produkcyjny STT/TTS przez touri
- [`urirdp-docker`](../urirdp-docker/)

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [STT.md](docs/STT.md)
- [WEBRTC_CHAT.md](docs/WEBRTC_CHAT.md)
- [10_AUTOMATIONS.md](docs/10_AUTOMATIONS.md)

## Ekosystem TellMesh

Orchestrator: **[urisys](https://github.com/tellmesh/urisys)** · Mapa: **[MESH.md](https://github.com/tellmesh/urisys/blob/main/docs/MESH.md)** · Model: **[ECOSYSTEM.md](https://github.com/tellmesh/urisys/blob/main/../docs/ECOSYSTEM.md)**

| Pole | Wartość |
|------|---------|
| **Warstwa** | Lab / voice gateway |
| **Port** | 8099 |
| **Schemes** | stt, webrtc, message |
| **Orchestrator** | urisys |

Runtime edge: **`uri_control.edge`** w pakiecie **`uricore`** (legacy `urisysedge` usunięty 2026-06).
Router intencji: **`urirouter`** (`uri_router`) — resolve + HTTP/MQTT delegate.

<!-- end-ecosystem -->
