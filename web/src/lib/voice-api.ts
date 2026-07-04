import { apiBaseUrl } from "@/config/site";

const BASE = `${apiBaseUrl}/voice`;

export interface VoiceHistoryItem {
  session_id: string;
  title: string;
  created_at: string;
  last_activity_at: string;
  message_count: number;
}

export interface VoiceSessionMessage {
  role: "user" | "assistant";
  content: string;
}

export interface VoiceSessionDetail {
  session_id: string;
  title: string;
  created_at: string;
  messages: VoiceSessionMessage[];
}

export async function getVoiceHistory(
  limit = 20,
  offset = 0,
): Promise<VoiceHistoryItem[]> {
  const res = await fetch(`${BASE}/history?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error(`History failed: ${res.status}`);
  return res.json();
}

export async function getVoiceSession(
  sessionId: string,
): Promise<VoiceSessionDetail> {
  const res = await fetch(`${BASE}/history/${sessionId}`);
  if (!res.ok) throw new Error(`Get session failed: ${res.status}`);
  return res.json();
}

export async function deleteVoiceSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/history/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}
