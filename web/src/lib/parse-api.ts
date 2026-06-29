import { apiBaseUrl } from "@/config/site";

const BASE = `${apiBaseUrl}/parse`;

export interface UploadResult {
  id: string;
  filename: string;
  size_bytes: number;
  doc_type: string;
}

export interface StartJobResult {
  job_id: string;
  document_id: string;
  status: string;
}

export interface SectionResult {
  id: string;
  page_number: number;
  label: string;
  region: string;
  rect: { top: number; left: number; width: number; height: number };
  markdown: string;
  json_data: Record<string, unknown> | null;
  confidence: number | null;
  sort_order: number;
}

export interface JobResult {
  job_id: string;
  document_id: string;
  status: string;
  error_msg: string | null;
  markdown_output: string | null;
  json_output: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  sections: SectionResult[];
}

export interface HistoryItem {
  job_id: string;
  filename: string;
  doc_type: string;
  status: string;
  created_at: string;
  section_count: number;
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function startJob(
  documentId: string,
  schemaText?: string,
): Promise<StartJobResult> {
  const res = await fetch(`${BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: documentId,
      schema_text: schemaText ?? null,
    }),
  });
  if (!res.ok) throw new Error(`Start job failed: ${res.status}`);
  return res.json();
}

export function pageImageUrl(documentId: string, pageNumber: number): string {
  return `${BASE}/documents/${documentId}/pages/${pageNumber}`;
}

export async function getJob(jobId: string): Promise<JobResult> {
  const res = await fetch(`${BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Get job failed: ${res.status}`);
  return res.json();
}

export async function getHistory(
  limit = 20,
  offset = 0,
): Promise<HistoryItem[]> {
  const res = await fetch(`${BASE}/history?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error(`History failed: ${res.status}`);
  return res.json();
}

export async function deleteDocument(docId: string): Promise<void> {
  const res = await fetch(`${BASE}/documents/${docId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}
