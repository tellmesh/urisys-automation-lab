# uristt contract (MVP)

Scheme: `stt://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: uristt.contract
  version: 0.1.0
scheme: stt
commands:
  - id: stt.session.start
    pattern: stt://local/session/{session}/command/start
    side_effects: true
    requires_approval: true
  - id: stt.audio.transcribe
    pattern: stt://local/audio/command/transcribe
    side_effects: true
    requires_approval: true
queries:
  - id: stt.session.transcript
    pattern: stt://local/session/{session}/query/transcript
```

## Routes

```txt
stt://local/session/{session}/command/start
stt://local/session/{session}/query/transcript
stt://local/audio/command/transcribe
```

## Engines (planned)

| Engine | Use case |
|--------|----------|
| browser Web Speech API | demo / quick tests |
| Vosk | offline CPU / RPi |
| whisper.cpp | local C++ inference |
| faster-whisper | PC/GPU quality |

## Pipeline

```txt
getUserMedia / MediaRecorder
  → stt://local/audio/command/transcribe
  → transcript
  → chat://local/uri/command/execute
```
