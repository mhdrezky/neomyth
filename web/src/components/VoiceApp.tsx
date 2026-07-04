import { useCallback, useEffect, useRef, useState } from "react";
import { History, Mic, MicOff, Trash2, X } from "lucide-react";

import { ChatMessages, type ChatMessage } from "@/components/ChatMessages";
import { ToolControlPanel } from "@/components/ToolControlPanel";
import { ToolHeader } from "@/components/ToolHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiBaseUrl } from "@/config/site";
import { cn } from "@/lib/utils";
import {
  deleteVoiceSession,
  getVoiceHistory,
  getVoiceSession,
  type VoiceHistoryItem,
} from "@/lib/voice-api";

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
  const [history, setHistory] = useState<VoiceHistoryItem[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [viewingTitle, setViewingTitle] = useState<string | null>(null);

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
      // Guard against a stray odd-length chunk so Int16Array never throws.
      const sampleCount = Math.floor(bytes.length / 2);
      if (sampleCount === 0) return;
      const int16 = new Int16Array(bytes.buffer, 0, sampleCount);
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

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await getVoiceHistory());
    } catch {
      /* API offline — keep whatever we had */
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const openHistoryItem = useCallback(async (item: VoiceHistoryItem) => {
    setHistoryOpen(false);
    setError("");
    try {
      const detail = await getVoiceSession(item.session_id);
      setMessages(
        detail.messages.map((m) => ({
          id: crypto.randomUUID(),
          role: m.role,
          content: m.content,
        })),
      );
      setStreamingAssistant("");
      setViewingTitle(detail.title);
    } catch (err) {
      setError(`Could not load conversation: ${String(err)}`);
    }
  }, []);

  const removeHistoryItem = useCallback(
    async (item: VoiceHistoryItem) => {
      try {
        await deleteVoiceSession(item.session_id);
        await loadHistory();
      } catch (err) {
        setError(`Could not delete conversation: ${String(err)}`);
      }
    },
    [loadHistory],
  );

  const closeHistoryView = useCallback(() => {
    setViewingTitle(null);
    setMessages([]);
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
        const nextPhase = (msg.data.phase as Phase) || "idle";
        // "listening" marks the end of a turn: finalize the streamed reply
        // even when it produced no TTS audio.
        if (nextPhase === "listening" && assistantBufferRef.current.trim()) {
          finalizeAssistantMessage(assistantBufferRef.current.trim());
          assistantBufferRef.current = "";
        }
        setPhaseState(nextPhase);
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
        if (latencyStartRef.current > 0) {
          const ms = Math.round(performance.now() - latencyStartRef.current);
          setLatency(`${ms} ms`);
          latencyStartRef.current = 0;
        }
        playPcmChunk(
          msg.data.audio,
          msg.data.sample_rate || SAMPLE_RATE,
          playbackEpochRef.current,
        ).catch((err) => {
          console.error("TTS playback failed", err);
          setError(`TTS playback failed: ${String(err)}`);
        });
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
    setViewingTitle(null);
    setHistoryOpen(false);
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

    const mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    mediaStreamRef.current = mediaStream;
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    // Autoplay policies can start the context suspended even after a click.
    await audioContext.resume();
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
    void loadHistory();
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ToolHeader
        title="Neo-Voice"
        subtitle="STT → LLM → TTS · WebSocket"
        icon={Mic}
        iconGradient="linear-gradient(135deg, #7c3aed, #a78bfa)"
        iconShadow="0 0 0 1px #5b21b6, 0 2px 8px rgba(124,58,237,.35)"
        statusLabel={`ws: ${wsStatus}`}
        statusActive={wsStatus === "on"}
      />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-6 py-8 pb-12">
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

      {viewingTitle && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/40 px-4 py-2 text-sm">
          <span className="truncate text-muted-foreground">
            Viewing history: <strong className="text-foreground">{viewingTitle}</strong>
          </span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 gap-1 px-2 text-xs"
            onClick={closeHistoryView}
          >
            <X className="h-3.5 w-3.5" aria-hidden />
            Close
          </Button>
        </div>
      )}

      <ChatMessages messages={messages} streamingAssistant={streamingAssistant} />

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
        </div>
      </div>

      {/* History floating tab */}
      {!historyOpen && (
        <button
          type="button"
          onClick={() => {
            void loadHistory();
            setHistoryOpen(true);
          }}
          className="fixed bottom-4 right-[18px] z-30 flex h-[38px] items-center gap-2 rounded-full border border-border bg-card px-[14px] text-muted-foreground shadow-lg transition-colors hover:text-foreground"
        >
          <History className="h-[14px] w-[14px]" aria-hidden />
          <span className="text-[12.5px] font-medium">History</span>
          <span className="rounded-[10px] border border-border bg-background px-[7px] py-[1px] text-[10px]">
            {history.length}
          </span>
        </button>
      )}

      {/* HISTORY DRAWER */}
      {historyOpen && (
        <div
          className="fixed inset-0 z-[39] bg-black/55 transition-opacity"
          onClick={() => setHistoryOpen(false)}
        />
      )}
      <div
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background shadow-2xl transition-transform duration-300"
        style={{
          transform: historyOpen ? "translateY(0)" : "translateY(110%)",
          transitionTimingFunction: "cubic-bezier(.4,0,.2,1)",
        }}
      >
        <div className="flex items-center justify-between border-b border-border px-[18px] py-[13px]">
          <div className="flex items-center gap-[10px]">
            <History className="h-4 w-4 text-primary" aria-hidden />
            <span className="text-[14px] font-semibold">Conversation history</span>
            <span className="rounded-full border border-border bg-muted px-2 py-[2px] text-[11px] text-muted-foreground">
              {history.length} conversations
            </span>
          </div>
          <button
            type="button"
            onClick={() => setHistoryOpen(false)}
            className="flex h-[30px] w-[30px] items-center justify-center rounded-[7px] border border-border bg-muted text-muted-foreground hover:text-foreground"
          >
            <X className="h-[15px] w-[15px]" aria-hidden />
          </button>
        </div>
        <div className="flex gap-3 overflow-x-auto px-[18px] py-4">
          {history.length === 0 ? (
            <div className="flex w-full items-center justify-center py-8 text-[13px] text-muted-foreground">
              No conversations yet. Start a voice session to create one.
            </div>
          ) : (
            history.map((h) => (
              <div
                key={h.session_id}
                onClick={() => void openHistoryItem(h)}
                className="group w-[232px] flex-none cursor-pointer rounded-[11px] border border-border bg-card p-[14px] transition-colors hover:border-primary/40"
              >
                <div className="mb-[11px] flex items-center justify-between gap-2">
                  <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <Mic className="h-[15px] w-[15px]" aria-hidden />
                  </div>
                  <button
                    type="button"
                    aria-label="Delete conversation"
                    onClick={(e) => {
                      e.stopPropagation();
                      void removeHistoryItem(h);
                    }}
                    className="flex h-[26px] w-[26px] items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/15 hover:text-destructive group-hover:opacity-100"
                  >
                    <Trash2 className="h-[13px] w-[13px]" aria-hidden />
                  </button>
                </div>
                <div className="truncate text-[12.5px] font-semibold">{h.title}</div>
                <div className="mt-[9px] flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>{new Date(h.created_at).toLocaleDateString()}</span>
                  <span>{h.message_count} messages</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
