/**
 * Neomyth Voice client — mic capture, energy VAD, WebSocket, playback, interrupt.
 */
(() => {
  const SAMPLE_RATE = 16000;
  const VAD_THRESHOLD = 0.015;
  const SILENCE_MS = 700;
  const MIN_SPEECH_MS = 300;

  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const phaseDot = document.getElementById("phaseDot");
  const phaseLabel = document.getElementById("phaseLabel");
  const latencyEl = document.getElementById("latency");
  const wsStatusEl = document.getElementById("wsStatus");
  const transcriptEl = document.getElementById("transcript");
  const errorEl = document.getElementById("error");

  let ws = null;
  let audioContext = null;
  let mediaStream = null;
  let processor = null;
  let phase = "idle";
  let speechStartTs = 0;
  let lastVoiceTs = 0;
  let isSpeaking = false;
  let latencyStart = 0;
  let playbackQueue = [];
  let isPlaying = false;
  let nextPlayTime = 0;
  let activeSources = [];
  let playbackEpoch = 0;
  let interruptEnabled =
    typeof window !== "undefined" &&
    window.NEOMYTH_VOICE &&
    window.NEOMYTH_VOICE.interruptEnabled === true;

  let assistantBuffer = "";

  function setPhase(next) {
    phase = next;
    phaseDot.className = "dot";
    if (next !== "idle" && next !== "disconnected") {
      phaseDot.classList.add(next);
    }
    phaseLabel.textContent = next.charAt(0).toUpperCase() + next.slice(1);
  }

  function logLine(prefix, text) {
    transcriptEl.textContent += `${prefix}: ${text}\n`;
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  }

  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws/voice`;
  }

  function send(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }

  function floatTo16BitPCM(float32) {
    const out = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  function rms(samples) {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i];
    }
    return Math.sqrt(sum / samples.length);
  }

  function downsample(buffer, inputRate, outputRate) {
    if (outputRate === inputRate) return buffer;
    const ratio = inputRate / outputRate;
    const newLen = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) {
      result[i] = buffer[Math.round(i * ratio)];
    }
    return result;
  }

  function stopAllAudio() {
    for (const source of activeSources) {
      try {
        source.stop(0);
      } catch (_) {
        /* already stopped */
      }
    }
    activeSources = [];
    playbackQueue = [];
    isPlaying = false;
    nextPlayTime = 0;
  }

  function interruptAI() {
    playbackEpoch += 1;
    assistantBuffer = "";
    stopAllAudio();
    send({ type: "interrupt", data: {} });
    setPhase("listening");
  }

  async function playPcmChunk(base64Audio, sampleRate, epoch) {
    if (!audioContext || epoch !== playbackEpoch) return;
    const raw = atob(base64Audio);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    const int16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }
    const buffer = audioContext.createBuffer(1, float32.length, sampleRate);
    buffer.copyToChannel(float32, 0);
    playbackQueue.push({ buffer, epoch });
    if (!isPlaying) drainPlayback();
  }

  function drainPlayback() {
    if (!audioContext || playbackQueue.length === 0) {
      isPlaying = false;
      return;
    }
    const item = playbackQueue.shift();
    if (!item || item.epoch !== playbackEpoch) {
      drainPlayback();
      return;
    }
    isPlaying = true;
    const source = audioContext.createBufferSource();
    source.buffer = item.buffer;
    source.connect(audioContext.destination);
    activeSources.push(source);
    const startAt = Math.max(audioContext.currentTime, nextPlayTime);
    source.start(startAt);
    nextPlayTime = startAt + item.buffer.duration;
    source.onended = () => {
      activeSources = activeSources.filter((s) => s !== source);
      drainPlayback();
    };
  }

  function onAudioProcess(e) {
    if (
      !interruptEnabled &&
      (phase === "speaking" || phase === "thinking")
    ) {
      return;
    }

    const input = e.inputBuffer.getChannelData(0);
    const down = downsample(input, audioContext.sampleRate, SAMPLE_RATE);
    const energy = rms(down);
    const now = performance.now();

    if (energy > VAD_THRESHOLD) {
      if (!isSpeaking) {
        isSpeaking = true;
        speechStartTs = now;
        if (interruptEnabled && (phase === "speaking" || phase === "thinking")) {
          interruptAI();
        }
        send({ type: "speech_start", data: {} });
      }
      lastVoiceTs = now;

      const pcm = floatTo16BitPCM(down);
      send({
        type: "audio_chunk",
        data: { audio: arrayBufferToBase64(pcm.buffer) },
      });
    } else if (isSpeaking && now - lastVoiceTs > SILENCE_MS) {
      if (now - speechStartTs >= MIN_SPEECH_MS) {
        latencyStart = performance.now();
        send({ type: "speech_end", data: {} });
      }
      isSpeaking = false;
    }
  }

  function handleMessage(event) {
    const msg = JSON.parse(event.data);

    if (msg.type === "config") {
      interruptEnabled = Boolean(msg.data.interrupt_enabled);
      const el = document.getElementById("interruptStatus");
      if (el) el.textContent = interruptEnabled ? "on" : "off";
      return;
    }

    if (msg.type === "state") {
      setPhase(msg.data.phase || "idle");
      return;
    }

    if (msg.type === "stt_final") {
      logLine("You", msg.data.text || "");
      return;
    }

    if (msg.type === "llm_delta") {
      assistantBuffer += msg.data.text || "";
      return;
    }

    if (msg.type === "tts_audio") {
      if (assistantBuffer.trim()) {
        logLine("AI", assistantBuffer.trim());
        assistantBuffer = "";
      }
      if (latencyStart > 0) {
        const ms = Math.round(performance.now() - latencyStart);
        latencyEl.textContent = `${ms} ms`;
        latencyStart = 0;
      }
      playPcmChunk(
        msg.data.audio,
        msg.data.sample_rate || SAMPLE_RATE,
        playbackEpoch,
      );
      return;
    }

    if (msg.type === "error") {
      const phaseLabel = msg.data.phase ? `[${msg.data.phase}] ` : "";
      const message = msg.data.message || "Unknown error";
      if (message.toLowerCase().includes("connection error")) {
        errorEl.textContent =
          `${phaseLabel}Worker tidak terjangkau. Pastikan vLLM (:5001) dan Kokoro (:5003) sudah running. (${message})`;
      } else {
        errorEl.textContent = `${phaseLabel}${message}`;
      }
    }
  }

  async function startSession() {
    errorEl.textContent = "";
    transcriptEl.textContent = "";
    assistantBuffer = "";
    playbackEpoch = 0;
    latencyEl.textContent = "—";

    ws = new WebSocket(wsUrl());
    ws.onopen = () => {
      wsStatusEl.textContent = "on";
      setPhase("listening");
    };
    ws.onclose = () => {
      wsStatusEl.textContent = "off";
      setPhase("disconnected");
    };
    ws.onerror = () => {
      errorEl.textContent = "WebSocket connection failed";
    };
    ws.onmessage = handleMessage;

    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = onAudioProcess;
    source.connect(processor);
    processor.connect(audioContext.destination);

    startBtn.disabled = true;
    stopBtn.disabled = false;
  }

  function stopSession() {
    if (processor) {
      processor.disconnect();
      processor = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    stopAllAudio();
    startBtn.disabled = false;
    stopBtn.disabled = true;
    setPhase("disconnected");
    wsStatusEl.textContent = "off";
  }

  startBtn.addEventListener("click", () => {
    startSession().catch((err) => {
      errorEl.textContent = err.message || String(err);
    });
  });
  stopBtn.addEventListener("click", stopSession);
})();
