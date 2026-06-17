# STT

## Demo (browser)

```txt
getUserMedia → Web Speech API → transcript → chat://local/uri/command/execute
```

## Stable local

```txt
MediaRecorder chunks
  → POST /api/stt/transcribe
  → stt://local/audio/command/transcribe
  → Vosk / whisper.cpp / faster-whisper (future)
```

## Flow 08

See `flows/08_voice_command_to_kvm.uri.flow.yaml`.
