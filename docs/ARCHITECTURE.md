# Architecture

```txt
uri2flow YAML (flows/)
  ↓
urisys-automation-lab server :8099
  ↓
  stt:// / webrtc:// / message://  (standalone packs: uristt, uriwebrtc, urimessage)
  rdp:// / kvm:// / him:// / ocr:// / llm://  (urirdpedge → urirdp-docker :8795)
  browser:// / shell:// / env://  (forward → :8795 or local when packs loaded)
```

## Transport

| Service | URL |
|---------|-----|
| Lab UI + URI gateway | `http://127.0.0.1:8099` |
| urirdp-docker | `http://127.0.0.1:8795/uri/call` |

### Docker Compose

```bash
cd urisys-automation-lab
docker compose -f docker-compose.lab.yml up --build -d
```

Services:

- `urirdp` — RDP + KVM/HIM/OCR/LLM (`urirdpedge` / `urisys-rdp`)
- `automation-lab` — web UI + `stt://` / `webrtc://` / `message://`, forward execution to `urirdp`

## Principle

- **uri2flow** — compile only
- **webrtc://** — media + data transport
- **stt://** — speech → text
- **chat://** — text → URI mapping / forward
- **kvm/him/ocr/llm/rdp** — execution

## Related

- `tellmesh/examples/39_system_automations/` — uri3 smoke flows
- `uri2voice/` + `examples/21_touri_voice/` — touri STT/TTS
- `urirdp-docker/` — RDP + KVM stack
