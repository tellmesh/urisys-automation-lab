# Architecture

```txt
uri2flow YAML (flows/)
  ↓
urisys-automation-lab server :8099
  ↓
  stt:// / chat:// / webrtc://  (local mock packs)
  rdp:// / kvm:// / him:// / ocr:// / llm://  (urirdp-docker runtime)
  browser:// / shell://  (forward → :8795 or uri2run)
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

- `urirdp` — RDP + KVM/HIM/OCR/LLM
- `automation-lab` — web UI + `stt://` / `chat://` / `webrtc://`, forward execution to `urirdp`

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
