import { useCallback, useRef, useState } from "react";
import { Mic, MicOff } from "lucide-react";

import { ChatMessages, type ChatMessage } from "@/components/ChatMessages";
import { ToolControlPanel } from "@/components/ToolControlPanel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiBaseUrl } from "@/config/site";
import { cn } from "@/lib/utils";

const SAMPLE_RATE = 16000;
const VAD_THRESHOLD = 0.015;
const SILENCE_MS = 700;
const MIN_SPEECH_MS = 300;

type Phase = "idle" | "disconnected" | "listening" | "thinking" | "speaking";

interface PlaybackItem {
  buffer: AudioBuffer;
  epoch: number;
}

function wsUrl(): string {
  const u = new URL(apiBaseUrl);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = "/ws/voice";
  return u.toString();
}

function floatTo16BitPCM(float32: Float32Array): Int16Array {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function arrayBufferToBase64(data: ArrayBufferView): string {
  const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function rms(samples: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    sum += samples[i] * samples[i];
  }
  return Math.sqrt(sum / samples.length);
}

function downsample(
  buffer: Float32Array,
  inputRate: number,
  outputRate: number,
): Float32Array {
  if (outputRate === inputRate) return buffer;
  const ratio = inputRate / outputRate;
  const newLen = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    result[i] = buffer[Math.round(i * ratio)];
  }
  return result;
}

const phaseColors: Record<string, string> = {
  listening: "bg-emerald-400",
  thinking: "bg-amber-400",
  speaking: "bg-violet-400",
};

export default function VoiceApp() {
  const [phase, setPhase] = useState<Phase>("disconnected");
  const [wsStatus, setWsStatus] = useState("off");
  const [interruptEnabled, setInterruptEnabled] = useState(false);
  const [latency, setLatency] = useState("—");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingAssistant, setStreamingAssistant] = useState("");
  const [error, setError] = useState("");
  const [sessionActive, setSessionActive] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const phaseRef = useRef<Phase>("disconnected");
  const speechStartTsRef = useRef(0);
  const lastVoiceTsRef = useRef(0);
  const isSpeakingRef = useRef(false);
  const latencyStartRef = useRef(0);
  const playbackQueueRef = useRef<PlaybackItem[]>([]);
  const isPlayingRef = useRef(false);
  const nextPlayTimeRef = useRef(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const playbackEpochRef = useRef(0);
  const interruptEnabledRef = useRef(false);
  const assistantBufferRef = useRef("");

  const setPhaseState = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const stopAllAudio = useCallback(() => {
    for (const source of activeSourcesRef.current) {
      try {
        source.stop(0);
      } catch {
        /* already stopped */
      }
    }
    activeSourcesRef.current = [];
    playbackQueueRef.current = [];
    isPlayingRef.current = false;
    nextPlayTimeRef.current = 0;
  }, []);

  const drainPlayback = useCallback(() => {
    const ctx = audioContextRef.current;
    if (!ctx || playbackQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }
    const item = playbackQueueRef.current.shift();
    if (!item || item.epoch !== playbackEpochRef.current) {
      drainPlayback();
      return;
    }
    isPlayingRef.current = true;
    const source = ctx.createBufferSource();
    source.buffer = item.buffer;
    source.connect(ctx.destination);
    activeSourcesRef.current.push(source);
    const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current);
    source.start(startAt);
    nextPlayTimeRef.current = startAt + item.buffer.duration;
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
      drainPlayback();
    };
  }, []);

  const playPcmChunk = useCallback(
    async (base64Audio: string, sampleRate: number, epoch: number) => {
      const ctx = audioContextRef.current;
      if (!ctx || epoch !== playbackEpochRef.current) return;
      const raw = atob(base64Audio);
      const bytes = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
      const int16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768;
      }
      const buffer = ctx.createBuffer(1, float32.length, sampleRate);
      buffer.copyToChannel(float32, 0);
      playbackQueueRef.current.push({ buffer, epoch });
      if (!isPlayingRef.current) drainPlayback();
    },
    [drainPlayback],
  );

  const addUserMessage = useCallback((text: string) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content: text },
    ]);
    setStreamingAssistant("");
  }, []);

  const finalizeAssistantMessage = useCallback((text: string) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant", content: text },
    ]);
    setStreamingAssistant("");
  }, []);

  const interruptAI = useCallback(() => {
    playbackEpochRef.current += 1;
    assistantBufferRef.current = "";
    setStreamingAssistant("");
    stopAllAudio();
    send({ type: "interrupt", data: {} });
    setPhaseState("listening");
  }, [send, setPhaseState, stopAllAudio]);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      const msg = JSON.parse(event.data as string);

      if (msg.type === "config") {
        const enabled = Boolean(msg.data.interrupt_enabled);
        interruptEnabledRef.current = enabled;
        setInterruptEnabled(enabled);
        return;
      }

      if (msg.type === "state") {
        setPhaseState((msg.data.phase as Phase) || "idle");
        return;
      }

      if (msg.type === "stt_final") {
        addUserMessage(msg.data.text || "");
        return;
      }

      if (msg.type === "llm_delta") {
        const next = assistantBufferRef.current + (msg.data.text || "");
        assistantBufferRef.current = next;
        setStreamingAssistant(next);
        return;
      }

      if (msg.type === "tts_audio") {
        if (assistantBufferRef.current.trim()) {
          finalizeAssistantMessage(assistantBufferRef.current.trim());
          assistantBufferRef.current = "";
        }
        if (latencyStartRef.current > 0) {
          const ms = Math.round(performance.now() - latencyStartRef.current);
          setLatency(`${ms} ms`);
          latencyStartRef.current = 0;
        }
        void playPcmChunk(
          msg.data.audio,
          msg.data.sample_rate || SAMPLE_RATE,
          playbackEpochRef.current,
        );
        return;
      }

      if (msg.type === "error") {
        const phaseLabel = msg.data.phase ? `[${msg.data.phase}] ` : "";
        const message = msg.data.message || "Unknown error";
        if (message.toLowerCase().includes("connection error")) {
          setError(
            `${phaseLabel}Workers unreachable. Ensure vLLM (:5001) and Kokoro (:5003) are running. (${message})`,
          );
        } else {
          setError(`${phaseLabel}${message}`);
        }
      }
    },
    [addUserMessage, finalizeAssistantMessage, playPcmChunk, setPhaseState],
  );

  const onAudioProcess = useCallback(
    (e: AudioProcessingEvent) => {
      const currentPhase = phaseRef.current;
      if (
        !interruptEnabledRef.current &&
        (currentPhase === "speaking" || currentPhase === "thinking")
      ) {
        return;
      }

      const ctx = audioContextRef.current;
      if (!ctx) return;

      const input = e.inputBuffer.getChannelData(0);
      const down = downsample(input, ctx.sampleRate, SAMPLE_RATE);
      const energy = rms(down);
      const now = performance.now();

      if (energy > VAD_THRESHOLD) {
        if (!isSpeakingRef.current) {
          isSpeakingRef.current = true;
          speechStartTsRef.current = now;
          if (
            interruptEnabledRef.current &&
            (currentPhase === "speaking" || currentPhase === "thinking")
          ) {
            interruptAI();
          }
          send({ type: "speech_start", data: {} });
        }
        lastVoiceTsRef.current = now;

        const pcm = floatTo16BitPCM(down);
        send({
          type: "audio_chunk",
          data: { audio: arrayBufferToBase64(pcm) },
        });
      } else if (isSpeakingRef.current && now - lastVoiceTsRef.current > SILENCE_MS) {
        if (now - speechStartTsRef.current >= MIN_SPEECH_MS) {
          latencyStartRef.current = performance.now();
          send({ type: "speech_end", data: {} });
        }
        isSpeakingRef.current = false;
      }
    },
    [interruptAI, send],
  );

  const startSession = async () => {
    setError("");
    setMessages([]);
    setStreamingAssistant("");
    assistantBufferRef.current = "";
    playbackEpochRef.current = 0;
    setLatency("—");

    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;
    ws.onopen = () => {
      setWsStatus("on");
      setPhaseState("listening");
    };
    ws.onclose = () => {
      setWsStatus("off");
      setPhaseState("disconnected");
    };
    ws.onerror = () => setError("WebSocket connection failed");
    ws.onmessage = handleMessage;

    const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaStreamRef.current = mediaStream;
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    const source = audioContext.createMediaStreamSource(mediaStream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;
    processor.onaudioprocess = onAudioProcess;
    source.connect(processor);
    processor.connect(audioContext.destination);

    setSessionActive(true);
  };

  const stopSession = () => {
    processorRef.current?.disconnect();
    processorRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    stopAllAudio();
    setSessionActive(false);
    setPhaseState("disconnected");
    setWsStatus("off");
  };

  return (
    <div className="space-y-4">
      <ToolControlPanel>
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "h-3 w-3 rounded-full bg-muted",
              phaseColors[phase] ?? "",
            )}
            aria-hidden
          />
          <span className="text-sm font-medium capitalize">{phase}</span>
        </div>

        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span>
            Latency: <strong className="text-foreground">{latency}</strong>
          </span>
          <span>
            WS: <strong className="text-foreground">{wsStatus}</strong>
          </span>
          <span className="flex items-center gap-2">
            Interrupt:
            <Badge variant="outline">{interruptEnabled ? "on" : "off"}</Badge>
          </span>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            className="flex-1 gap-2"
            disabled={sessionActive}
            onClick={() => startSession().catch((err) => setError(String(err)))}
          >
            <Mic className="h-4 w-4" aria-hidden />
            Start Session
          </Button>
          <Button
            className="flex-1 gap-2"
            variant="destructive"
            disabled={!sessionActive}
            onClick={stopSession}
          >
            <MicOff className="h-4 w-4" aria-hidden />
            Stop Session
          </Button>
        </div>
      </ToolControlPanel>

      <ChatMessages messages={messages} streamingAssistant={streamingAssistant} />

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
