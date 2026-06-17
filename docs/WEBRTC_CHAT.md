# WebRTC + chat

Lab UI (`web/index.html`):

1. `getUserMedia` — camera/mic
2. `RTCPeerConnection` loopback — local demo
3. `RTCDataChannel` — URI JSON envelopes
4. `POST /uri/call` — execution via urisys

Flow 09: `flows/09_webrtc_video_chat_rdp.uri.flow.yaml`.

`webrtc://` does not execute automation — it tracks sessions and accepts envelopes.
