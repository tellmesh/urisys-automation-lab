const logEl = document.getElementById("log");
const transcriptEl = document.getElementById("transcript");
const uriEl = document.getElementById("uri");
const payloadEl = document.getElementById("payload");

let localStream = null;
let pc = null;
let dataChannel = null;

function log(msg, obj) {
  const line = obj ? `${msg}\n${JSON.stringify(obj, null, 2)}` : msg;
  logEl.textContent = `${line}\n\n${logEl.textContent}`.slice(0, 8000);
}

async function uriCall(uri, payload, context = {}) {
  const res = await fetch("/uri/call", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uri, payload, context }),
  });
  const data = await res.json();
  log(`POST ${uri}`, data);
  return data;
}

document.getElementById("btnMedia").onclick = async () => {
  try {
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    document.getElementById("localVideo").srcObject = localStream;
    log("getUserMedia OK");
  } catch (err) {
    log("getUserMedia failed", { error: String(err) });
  }
};

document.getElementById("btnWebRTC").onclick = async () => {
  pc = new RTCPeerConnection();
  dataChannel = pc.createDataChannel("uri");
  dataChannel.onopen = () => log("DataChannel open");
  dataChannel.onmessage = (ev) => log("DataChannel message", JSON.parse(ev.data));

  pc.ontrack = (ev) => {
    document.getElementById("remoteVideo").srcObject = ev.streams[0];
  };

  if (localStream) {
    localStream.getTracks().forEach((t) => pc.addTrack(t, localStream));
  }

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await pc.setRemoteDescription(offer);
  const answer = await pc.createAnswer();
  await pc.setRemoteDescription(offer);
  await pc.setLocalDescription(answer);
  await pc.setRemoteDescription(answer);
  log("WebRTC loopback ready");
};

document.getElementById("btnListen").onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    log("SpeechRecognition unavailable — use stt:// backend");
    return;
  }
  const rec = new SR();
  rec.lang = "pl-PL";
  rec.interimResults = false;
  rec.onresult = (ev) => {
    const text = ev.results[0][0].transcript;
    transcriptEl.value = text;
    log("Web Speech transcript", { text });
  };
  rec.onerror = (ev) => log("SpeechRecognition error", { error: ev.error });
  rec.start();
  log("Listening…");
};

document.getElementById("btnSttBackend").onclick = async () => {
  const text = transcriptEl.value.trim();
  await fetch("/api/stt/transcribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language: "pl-PL" }),
  })
    .then((r) => r.json())
    .then((data) => log("stt:// backend", data));
};

document.getElementById("btnCall").onclick = async () => {
  let payload = {};
  try {
    payload = JSON.parse(payloadEl.value || "{}");
  } catch (err) {
    log("Invalid JSON payload", { error: String(err) });
    return;
  }
  await uriCall(uriEl.value, payload, {
    approved: document.getElementById("approved").checked,
    dry_run: document.getElementById("dryRun").checked,
  });
};

document.getElementById("btnChatExecute").onclick = async () => {
  const text = transcriptEl.value.trim() || "kliknij OK";
  await uriCall("chat://local/uri/command/execute", {
    transcript: text,
    approved: document.getElementById("approved").checked,
    dry_run: document.getElementById("dryRun").checked,
  });
};

document.getElementById("btnSendEnvelope").onclick = async () => {
  const envelope = {
    uri: uriEl.value,
    payload: JSON.parse(payloadEl.value || "{}"),
    context: {
      approved: document.getElementById("approved").checked,
      dry_run: document.getElementById("dryRun").checked,
    },
  };
  if (dataChannel && dataChannel.readyState === "open") {
    dataChannel.send(JSON.stringify(envelope));
    log("Sent DataChannel envelope", envelope);
  } else {
    await uriCall("webrtc://local/session/rdp-chat/data/command/send", {
      room: "rdp-lab",
      envelope,
    });
  }
};
