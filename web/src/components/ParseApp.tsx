import { useCallback, useRef, useState, useEffect } from "react";
import {
  Upload,
  Play,
  Copy,
  Check,
  X,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Code2,
  Eye,
  Braces,
  AlertCircle,
  ArrowLeft,
  RefreshCw,
  Inbox,
  Webhook,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { ToolHeader } from "@/components/ToolHeader";
import {
  uploadDocument,
  startJob,
  getJob,
  getHistory,
  pageImageUrl,
  type HistoryItem,
  type JobResult,
  type SectionResult,
} from "@/lib/parse-api";

type View = "dashboard" | "results";
type Tab = "markdown" | "json";

interface PendingUpload {
  key: string;
  filename: string;
  error?: string;
}

const PAGE_SIZE = 10;

const DOC_TYPE_COLORS: Record<string, string> = {
  INVOICE: "#3fb950",
  CONTRACT: "#a371f7",
  RECEIPT: "#f0883e",
  REPORT: "#58a6ff",
  OTHER: "#8b949e",
};

const STATUS_COLORS: Record<string, string> = {
  QUEUED: "#8b949e",
  PENDING: "#8b949e",
  PROCESSING: "#58a6ff",
  COMPLETED: "#3fb950",
  FAILED: "#f85149",
};

const DEFAULT_SCHEMA = `{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "vendor": {
      "type": "object",
      "properties": { "name": { "type": "string" }, "address": { "type": "string" } }
    },
    "invoice": {
      "type": "object",
      "properties": { "number": { "type": "string" }, "date": { "type": "string" } },
      "required": ["number"]
    },
    "line_items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "description": { "type": "string" },
          "qty": { "type": "number" },
          "unit_price": { "type": "number" }
        },
        "required": ["description"]
      }
    },
    "total_due": { "type": "number" }
  },
  "required": ["invoice"]
}`;

const ACC = "#58a6ff";

function hexA(hex: string, a: number) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

export default function ParseApp() {
  const [view, setView] = useState<View>("dashboard");
  const [activeTab, setActiveTab] = useState<Tab>("markdown");
  const [hovered, setHovered] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [schema, setSchema] = useState(DEFAULT_SCHEMA);
  const [metadataText, setMetadataText] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [apiConnected, setApiConnected] = useState(false);
  const [result, setResult] = useState<JobResult | null>(null);
  const [pageNumber, setPageNumber] = useState(1);

  const fileRef = useRef<HTMLInputElement>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  useEffect(() => () => clearTimers(), [clearTimers]);

  const loadJobs = useCallback(async (pageArg: number) => {
    setRefreshing(true);
    try {
      const data = await getHistory(PAGE_SIZE, pageArg * PAGE_SIZE);
      setJobs(data.items);
      setTotal(data.total);
      setApiConnected(true);
    } catch {
      setApiConnected(false);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadJobs(0); }, [loadJobs]);

  const goToPage = useCallback(
    (p: number) => {
      setPage(p);
      loadJobs(p);
    },
    [loadJobs],
  );

  // Upload each file and enqueue a job; the queue runs server-side, so the
  // dashboard stays interactive and rows update on manual refresh.
  const handleFiles = useCallback(
    async (files: File[]) => {
      const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
      if (pdfs.length === 0) {
        setError("Only PDF files are supported.");
        return;
      }
      setError("");
      const schemaText = schema.trim() ? schema : undefined;
      const webhook = webhookUrl.trim() || undefined;
      let metadata: Record<string, unknown> | undefined;
      if (metadataText.trim()) {
        try {
          const parsed = JSON.parse(metadataText);
          if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
            throw new Error("not an object");
          }
          metadata = parsed;
        } catch {
          setError("Metadata must be a valid JSON object, e.g. {\"client_ref\": \"order-42\"}.");
          setDeliveryOpen(true);
          return;
        }
      }
      for (const file of pdfs) {
        const key = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        setPendingUploads((prev) => [...prev, { key, filename: file.name }]);
        try {
          const doc = await uploadDocument(file);
          await startJob(doc.id, schemaText, metadata, webhook);
          setPendingUploads((prev) => prev.filter((p) => p.key !== key));
        } catch (e) {
          const msg = e instanceof Error ? e.message : "Upload failed";
          setPendingUploads((prev) =>
            prev.map((p) => (p.key === key ? { ...p, error: msg } : p)),
          );
        }
      }
      setPage(0);
      await loadJobs(0);
    },
    [schema, metadataText, webhookUrl, loadJobs],
  );

  const dismissPending = useCallback((key: string) => {
    setPendingUploads((prev) => prev.filter((p) => p.key !== key));
  }, []);

  const openJob = useCallback(async (item: HistoryItem) => {
    if (item.status !== "COMPLETED") return;
    setError("");
    setHovered(null);
    setPageNumber(1);
    setFileName(item.filename);
    try {
      const r = await getJob(item.job_id);
      setResult(r);
      setView("results");
    } catch {
      setError("Could not load that document.");
    }
  }, []);

  const backToDashboard = useCallback(() => {
    setView("dashboard");
    setHovered(null);
    setResult(null);
    loadJobs(page);
  }, [loadJobs, page]);

  const hoverSection = useCallback((s: SectionResult | null) => {
    setHovered(s?.id ?? null);
    if (s) setPageNumber(s.page_number);
  }, []);

  const copyOutput = useCallback(() => {
    if (!result) return;
    const txt =
      activeTab === "markdown"
        ? result.sections.map((s) => s.markdown).join("\n\n")
        : JSON.stringify(result.json_output ?? {}, null, 2);
    navigator.clipboard?.writeText(txt).catch(() => {});
    setCopied(true);
    const t = setTimeout(() => setCopied(false), 1200);
    timersRef.current.push(t);
  }, [activeTab, result]);

  const sections = result?.sections ?? [];
  const pageCount = Math.max(1, ...sections.map((s) => s.page_number), 1);
  const pageSections = sections.filter((s) => s.page_number === pageNumber);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const visiblePending = page === 0 ? pendingUploads : [];

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background text-foreground" style={{ fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
      {/* TOP BAR */}
      <ToolHeader
        title="Neo-Parse"
        subtitle="PDF → Markdown · Structured JSON"
        icon={FileText}
        statusLabel={apiConnected ? "api · connected" : "api · offline"}
        statusActive={apiConnected}
      >
        {view === "results" && (
          <Button variant="outline" size="sm" onClick={backToDashboard} className="gap-[7px]">
            <ArrowLeft className="h-[14px] w-[14px]" />
            Back to documents
          </Button>
        )}
      </ToolHeader>

      {/* MAIN */}
      <div className="relative flex-1 overflow-hidden">
        {/* DASHBOARD VIEW */}
        {view === "dashboard" && (
          <div className="absolute inset-0 overflow-y-auto">
            <div className="mx-auto flex max-w-[780px] flex-col gap-[22px] px-7 pb-[60px] pt-[38px]">
              {/* Hero text */}
              <div className="mb-1 text-center">
                <h1 className="text-[27px] font-bold tracking-tight">Parse any document into clean data</h1>
                <p className="mt-[10px] text-[14.5px] leading-relaxed text-muted-foreground">
                  Drop PDFs below — they are queued and parsed in the background.
                  <br />
                  Define an optional schema to shape the output exactly how you need it.
                </p>
              </div>

              {error && (
                <div className="flex items-center gap-2 rounded-[10px] border px-4 py-3 text-[12.5px]" style={{ background: "#1c1408", borderColor: "#3d2e04", color: "#d29922" }}>
                  <AlertCircle className="h-[15px] w-[15px] flex-none" />
                  {error}
                </div>
              )}

              {/* Dropzone */}
              <div
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  const files = Array.from(e.dataTransfer.files ?? []);
                  if (files.length) handleFiles(files);
                }}
                className="flex min-h-[170px] cursor-pointer flex-col items-center justify-center gap-2 rounded-[14px] text-center transition-all"
                style={{
                  border: `2px dashed ${dragging ? ACC : "#30363d"}`,
                  background: dragging ? hexA(ACC, 0.08) : "#10151c",
                }}
              >
                <div
                  className="mb-[6px] flex h-[52px] w-[52px] items-center justify-center rounded-[14px]"
                  style={{ background: "#0d2a4d", border: "1px solid #1f4b80" }}
                >
                  <Upload className="h-[24px] w-[24px]" style={{ color: ACC }} />
                </div>
                <div className="text-[16px] font-semibold">Drag & drop PDFs here</div>
                <div className="text-[13px] text-muted-foreground">
                  or <span className="font-semibold" style={{ color: ACC }}>browse files</span> · multiple PDFs up to 25&nbsp;MB each
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/pdf"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []);
                    if (files.length) handleFiles(files);
                    e.target.value = "";
                  }}
                />
              </div>

              {/* Schema editor */}
              <div className="overflow-hidden rounded-xl border border-border" style={{ background: "#10151c" }}>
                <button
                  onClick={() => setSchemaOpen(!schemaOpen)}
                  className="flex w-full items-center justify-between border-none bg-transparent px-4 py-[13px] text-foreground"
                  style={{ fontFamily: "inherit" }}
                >
                  <span className="flex items-center gap-[10px]">
                    <Code2 className="h-[15px] w-[15px]" style={{ color: "#a371f7" }} />
                    <span className="text-[13.5px] font-semibold">JSON output schema (draft-07)</span>
                    <span className="rounded-full border border-border px-[7px] py-[2px] text-[11px] text-muted-foreground" style={{ background: "#161b22" }}>
                      optional
                    </span>
                  </span>
                  <ChevronDown
                    className="h-4 w-4 text-muted-foreground transition-transform"
                    style={{ transform: schemaOpen ? "rotate(180deg)" : "none" }}
                  />
                </button>
                {schemaOpen && (
                  <div className="border-t border-border">
                    <div className="flex items-center justify-between border-b border-border px-[14px] py-2" style={{ background: "#0d1117" }}>
                      <span className="text-[11.5px] text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>schema.json</span>
                      <span className="text-[11px] text-muted-foreground">Leave empty for free-form extraction</span>
                    </div>
                    <textarea
                      value={schema}
                      onChange={(e) => setSchema(e.target.value)}
                      spellCheck={false}
                      className="block w-full resize-y border-none bg-background p-[14px] text-[12.5px] leading-[1.65] outline-none"
                      style={{ fontFamily: "'JetBrains Mono', monospace", color: "#9db8d8", minHeight: 188 }}
                    />
                  </div>
                )}
              </div>

              {/* Metadata & webhook */}
              <div className="overflow-hidden rounded-xl border border-border" style={{ background: "#10151c" }}>
                <button
                  onClick={() => setDeliveryOpen(!deliveryOpen)}
                  className="flex w-full items-center justify-between border-none bg-transparent px-4 py-[13px] text-foreground"
                  style={{ fontFamily: "inherit" }}
                >
                  <span className="flex items-center gap-[10px]">
                    <Webhook className="h-[15px] w-[15px]" style={{ color: "#f0883e" }} />
                    <span className="text-[13.5px] font-semibold">Metadata & webhook</span>
                    <span className="rounded-full border border-border px-[7px] py-[2px] text-[11px] text-muted-foreground" style={{ background: "#161b22" }}>
                      optional
                    </span>
                  </span>
                  <ChevronDown
                    className="h-4 w-4 text-muted-foreground transition-transform"
                    style={{ transform: deliveryOpen ? "rotate(180deg)" : "none" }}
                  />
                </button>
                {deliveryOpen && (
                  <div className="flex flex-col gap-[14px] border-t border-border p-[14px]">
                    <div>
                      <div className="mb-[6px] flex items-center justify-between">
                        <span className="text-[12px] font-semibold text-muted-foreground">Metadata (JSON object)</span>
                        <span className="text-[10.5px] text-muted-foreground">Echoed back in responses & the webhook payload</span>
                      </div>
                      <textarea
                        value={metadataText}
                        onChange={(e) => setMetadataText(e.target.value)}
                        spellCheck={false}
                        placeholder={'{ "client_ref": "order-42", "source": "erp" }'}
                        className="block w-full resize-y rounded-[8px] border border-border bg-background p-[11px] text-[12px] leading-[1.6] outline-none"
                        style={{ fontFamily: "'JetBrains Mono', monospace", color: "#9db8d8", minHeight: 68 }}
                      />
                    </div>
                    <div>
                      <div className="mb-[6px] flex items-center justify-between">
                        <span className="text-[12px] font-semibold text-muted-foreground">Webhook URL</span>
                        <span className="text-[10.5px] text-muted-foreground">POSTed the job result when parsing finishes</span>
                      </div>
                      <input
                        type="url"
                        value={webhookUrl}
                        onChange={(e) => setWebhookUrl(e.target.value)}
                        spellCheck={false}
                        placeholder="http://localhost:5000/parse/webhook-test"
                        className="block w-full rounded-[8px] border border-border bg-background px-[11px] py-[9px] text-[12px] outline-none"
                        style={{ fontFamily: "'JetBrains Mono', monospace", color: "#9db8d8" }}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Select button */}
              <button
                onClick={() => fileRef.current?.click()}
                className="flex cursor-pointer items-center justify-center gap-[9px] rounded-[10px] border-none text-[14.5px] font-semibold text-white"
                style={{
                  height: 46,
                  background: "linear-gradient(135deg, #1f6feb, #388bfd)",
                  boxShadow: "0 2px 12px rgba(31,111,235,.3)",
                  fontFamily: "inherit",
                }}
              >
                <Play className="h-[17px] w-[17px]" fill="white" />
                Select & queue documents
              </button>

              {/* Documents list */}
              <div className="mt-[8px]">
                <div className="mb-[10px] flex items-center justify-between">
                  <div className="flex items-center gap-[10px]">
                    <span className="text-[15px] font-semibold">Documents</span>
                    <span className="rounded-full border border-border px-2 py-[2px] text-[11px] text-muted-foreground" style={{ background: "#161b22" }}>
                      {total}
                    </span>
                  </div>
                  <button
                    onClick={() => loadJobs(page)}
                    disabled={refreshing}
                    className="flex items-center gap-[7px] rounded-[8px] border border-border px-3 text-[12.5px] font-medium disabled:opacity-60"
                    style={{ height: 32, background: "#161b22", color: "#9fb6cf", fontFamily: "inherit", cursor: refreshing ? "default" : "pointer" }}
                  >
                    <RefreshCw className={`h-[13px] w-[13px] ${refreshing ? "animate-spin" : ""}`} />
                    Refresh status
                  </button>
                </div>

                <div className="flex flex-col gap-[8px]">
                  {visiblePending.map((p) => (
                    <PendingRow key={p.key} item={p} onDismiss={dismissPending} />
                  ))}

                  {jobs.length === 0 && visiblePending.length === 0 ? (
                    <div className="flex flex-col items-center gap-2 rounded-[11px] border border-border py-10 text-muted-foreground" style={{ background: "#10151c" }}>
                      <Inbox className="h-6 w-6" />
                      <span className="text-[13px]">No documents yet. Drop PDFs above to get started.</span>
                    </div>
                  ) : (
                    jobs.map((item) => (
                      <JobQueueRow key={item.job_id} item={item} onOpen={openJob} />
                    ))
                  )}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="mt-[14px] flex items-center justify-center gap-[12px]">
                    <button
                      onClick={() => goToPage(Math.max(0, page - 1))}
                      disabled={page <= 0}
                      className="flex h-[28px] w-[28px] items-center justify-center rounded border border-border text-muted-foreground disabled:opacity-40"
                      style={{ background: "#161b22", cursor: page <= 0 ? "default" : "pointer" }}
                    >
                      <ChevronLeft className="h-[14px] w-[14px]" />
                    </button>
                    <span className="text-[12px] text-muted-foreground">
                      Page {page + 1} of {totalPages}
                    </span>
                    <button
                      onClick={() => goToPage(Math.min(totalPages - 1, page + 1))}
                      disabled={page >= totalPages - 1}
                      className="flex h-[28px] w-[28px] items-center justify-center rounded border border-border text-muted-foreground disabled:opacity-40"
                      style={{ background: "#161b22", cursor: page >= totalPages - 1 ? "default" : "pointer" }}
                    >
                      <ChevronRight className="h-[14px] w-[14px]" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* RESULTS VIEW */}
        {view === "results" && (
          <div className="absolute inset-0 flex min-h-0 flex-col">
            {error && (
              <div className="flex items-center gap-2 border-b border-border px-4 py-2 text-[12.5px]" style={{ background: "#1c1408", borderColor: "#3d2e04", color: "#d29922" }}>
                <AlertCircle className="h-[14px] w-[14px] flex-none" />
                {error}
              </div>
            )}
            <div className="grid min-h-0 flex-1 grid-cols-2">
              {/* LEFT: extracted output */}
              <section className="flex min-h-0 flex-col border-r border-border">
                {/* Tabs */}
                <div className="flex flex-none items-center justify-between border-b border-border px-[14px]" style={{ height: 46 }}>
                  <div className="flex h-full items-end gap-[2px]">
                    {(["markdown", "json"] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className="flex h-full items-center gap-[7px] border-none bg-transparent px-[13px] text-[13px] font-semibold"
                        style={{
                          fontFamily: "inherit",
                          borderBottom: activeTab === tab ? `2px solid ${ACC}` : "2px solid transparent",
                          color: activeTab === tab ? "#e6edf3" : "#6e7681",
                          marginBottom: -1,
                          cursor: "pointer",
                        }}
                      >
                        {tab === "markdown" ? <FileText className="h-[14px] w-[14px]" /> : <Braces className="h-[14px] w-[14px]" />}
                        {tab === "markdown" ? "Markdown" : "JSON"}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={copyOutput}
                    className="flex items-center gap-[6px] rounded-[7px] border border-border px-[11px] text-[12px] font-medium"
                    style={{ height: 30, background: "#161b22", color: "#9fb6cf", fontFamily: "inherit", cursor: "pointer" }}
                  >
                    {copied ? <Check className="h-[13px] w-[13px]" /> : <Copy className="h-[13px] w-[13px]" />}
                    {copied ? "Copied!" : "Copy"}
                  </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-[14px] pb-7" style={{ minHeight: 0 }}>
                  {sections.length === 0 ? (
                    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-muted-foreground">
                      <AlertCircle className="h-7 w-7" />
                      <p className="text-[14px]">No extractable content found in this document.</p>
                    </div>
                  ) : activeTab === "markdown" ? (
                    <div className="flex flex-col gap-1">
                      {sections.map((s) => (
                        <SectionBlock key={s.id} section={s} hovered={hovered} onHover={hoverSection} accent={ACC} />
                      ))}
                    </div>
                  ) : (
                    <pre className="m-0 whitespace-pre-wrap break-words px-[14px] text-[12.5px] leading-[1.7]" style={{ fontFamily: "'JetBrains Mono', monospace", color: "#9db8d8" }}>
                      {JSON.stringify(result?.json_output ?? {}, null, 2)}
                    </pre>
                  )}
                </div>
              </section>

              {/* RIGHT: document preview */}
              <section className="flex min-h-0 flex-col" style={{ background: "#010409" }}>
                <div className="flex flex-none items-center justify-between border-b border-border px-[14px]" style={{ height: 46, background: "#0d1117" }}>
                  <div className="flex min-w-0 items-center gap-[9px]">
                    <FileText className="h-[15px] w-[15px] flex-none" style={{ color: "#f0883e" }} />
                    <span className="truncate text-[13px] font-medium" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{fileName}</span>
                  </div>
                  <div className="flex flex-none items-center gap-[10px]">
                    {pageCount > 1 && (
                      <div className="flex items-center gap-[6px]">
                        <button
                          onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
                          disabled={pageNumber <= 1}
                          className="flex h-[22px] w-[22px] items-center justify-center rounded border border-border text-muted-foreground disabled:opacity-40"
                          style={{ background: "#161b22", cursor: pageNumber <= 1 ? "default" : "pointer" }}
                        >
                          <ChevronLeft className="h-[13px] w-[13px]" />
                        </button>
                        <span className="text-[11.5px] text-muted-foreground">Page {pageNumber} / {pageCount}</span>
                        <button
                          onClick={() => setPageNumber((p) => Math.min(pageCount, p + 1))}
                          disabled={pageNumber >= pageCount}
                          className="flex h-[22px] w-[22px] items-center justify-center rounded border border-border text-muted-foreground disabled:opacity-40"
                          style={{ background: "#161b22", cursor: pageNumber >= pageCount ? "default" : "pointer" }}
                        >
                          <ChevronRight className="h-[13px] w-[13px]" />
                        </button>
                      </div>
                    )}
                    {pageCount <= 1 && (
                      <span className="text-[11.5px] text-muted-foreground">Page 1 / 1</span>
                    )}
                    <span className="flex items-center gap-[5px] rounded-full border px-[9px] py-[3px] text-[11px]" style={{ color: "#9fc4f0", background: "#0d2a4d", borderColor: "#1f4b80" }}>
                      <span className="h-[6px] w-[6px] rounded-full" style={{ background: ACC }} />
                      source grounding
                    </span>
                  </div>
                </div>

                <div className="flex flex-1 justify-center overflow-y-auto p-[26px]" style={{ minHeight: 0 }}>
                  <div className="relative w-full max-w-[560px] self-start overflow-hidden rounded-[3px] bg-white" style={{ boxShadow: "0 10px 50px rgba(0,0,0,.55)" }}>
                    {result && (
                      <img
                        src={pageImageUrl(result.document_id, pageNumber)}
                        alt={`Page ${pageNumber}`}
                        className="block w-full"
                      />
                    )}
                    {pageSections.map((s) => (
                      <OverlayRegion key={s.id} section={s} hovered={hovered} onHover={hoverSection} accent={ACC} />
                    ))}
                  </div>
                </div>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status, queuePosition }: { status: string; queuePosition: number | null }) {
  const color = STATUS_COLORS[status] ?? STATUS_COLORS.PENDING;
  const label =
    status === "QUEUED" && queuePosition
      ? `QUEUED · #${queuePosition}`
      : status;
  return (
    <span
      className="flex flex-none items-center gap-[6px] rounded-full px-[10px] py-[3px] text-[10.5px] font-semibold tracking-wide"
      style={{ color, background: hexA(color, 0.12), border: `1px solid ${hexA(color, 0.35)}` }}
    >
      {status === "PROCESSING" && (
        <span className="h-[6px] w-[6px] animate-pulse rounded-full" style={{ background: color }} />
      )}
      {label}
    </span>
  );
}

function JobQueueRow({ item, onOpen }: { item: HistoryItem; onOpen: (item: HistoryItem) => void }) {
  const color = DOC_TYPE_COLORS[item.doc_type] ?? DOC_TYPE_COLORS.OTHER;
  const clickable = item.status === "COMPLETED";
  return (
    <div
      onClick={() => clickable && onOpen(item)}
      className={`rounded-[11px] border border-border p-[13px] transition-colors ${clickable ? "cursor-pointer hover:border-primary/40" : ""}`}
      style={{ background: "#10151c" }}
    >
      <div className="flex items-center gap-[12px]">
        <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-lg" style={{ background: hexA(color, 0.13), color }}>
          <FileText className="h-[16px] w-[16px]" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12.5px] font-semibold" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
            {item.filename}
          </div>
          <div className="mt-[3px] flex items-center gap-[8px] text-[11px] text-muted-foreground">
            <span className="rounded-full px-[7px] py-[1px] text-[9.5px] font-semibold" style={{ color, background: hexA(color, 0.12) }}>
              {item.doc_type}
            </span>
            <span>{new Date(item.created_at).toLocaleString()}</span>
            {item.status === "COMPLETED" && <span>· {item.section_count} sections</span>}
          </div>
        </div>
        <StatusBadge status={item.status} queuePosition={item.queue_position} />
      </div>
      {item.status === "FAILED" && item.error_msg && (
        <div className="mt-[9px] flex items-start gap-[7px] rounded-[8px] px-[10px] py-[7px] text-[11.5px]" style={{ background: hexA("#f85149", 0.07), color: "#f0a8a4" }}>
          <AlertCircle className="mt-[1px] h-[12px] w-[12px] flex-none" />
          <span className="break-words" style={{ minWidth: 0 }}>{item.error_msg}</span>
        </div>
      )}
    </div>
  );
}

function PendingRow({ item, onDismiss }: { item: PendingUpload; onDismiss: (key: string) => void }) {
  const failed = Boolean(item.error);
  const color = failed ? "#f85149" : ACC;
  return (
    <div className="rounded-[11px] border border-border p-[13px]" style={{ background: "#10151c" }}>
      <div className="flex items-center gap-[12px]">
        <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-lg" style={{ background: hexA(color, 0.13), color }}>
          <Upload className="h-[16px] w-[16px]" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12.5px] font-semibold" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
            {item.filename}
          </div>
          {failed && (
            <div className="mt-[3px] text-[11px]" style={{ color: "#f0a8a4" }}>{item.error}</div>
          )}
        </div>
        {failed ? (
          <button
            onClick={() => onDismiss(item.key)}
            className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-[7px] border border-border text-muted-foreground"
            style={{ background: "#161b22", cursor: "pointer" }}
          >
            <X className="h-[13px] w-[13px]" />
          </button>
        ) : (
          <span
            className="flex flex-none items-center gap-[6px] rounded-full px-[10px] py-[3px] text-[10.5px] font-semibold tracking-wide"
            style={{ color: ACC, background: hexA(ACC, 0.12), border: `1px solid ${hexA(ACC, 0.35)}` }}
          >
            <RefreshCw className="h-[10px] w-[10px] animate-spin" />
            UPLOADING
          </span>
        )}
      </div>
    </div>
  );
}

function SectionBlock({
  section,
  hovered,
  onHover,
  accent,
}: {
  section: SectionResult;
  hovered: string | null;
  onHover: (s: SectionResult | null) => void;
  accent: string;
}) {
  const active = hovered === section.id;
  return (
    <div
      onMouseEnter={() => onHover(section)}
      onMouseLeave={() => onHover(null)}
      className="cursor-pointer rounded-[7px] px-3 py-[9px] transition-all"
      style={{
        borderLeft: active ? `3px solid ${accent}` : "3px solid transparent",
        background: active ? hexA(accent, 0.09) : "transparent",
      }}
    >
      <div className="mb-[7px] flex items-center gap-[7px]">
        <span className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">{section.label}</span>
        <span className="h-px flex-1" style={{ background: "#1c2330" }} />
        <span className="text-[9px] font-semibold transition-colors" style={{ color: active ? accent : "#586069", fontFamily: "'JetBrains Mono', monospace" }}>
          § {section.region}
        </span>
      </div>
      <pre className="m-0 whitespace-pre-wrap break-words text-[12.5px] leading-[1.7]" style={{ fontFamily: "'JetBrains Mono', monospace", color: "#c9d6e3" }}>
        {section.markdown}
      </pre>
    </div>
  );
}

function OverlayRegion({
  section,
  hovered,
  onHover,
  accent,
}: {
  section: SectionResult;
  hovered: string | null;
  onHover: (s: SectionResult | null) => void;
  accent: string;
}) {
  const active = hovered === section.id;
  return (
    <div
      onMouseEnter={() => onHover(section)}
      onMouseLeave={() => onHover(null)}
      className="absolute cursor-pointer rounded transition-all"
      style={{
        top: `${section.rect.top}%`,
        left: `${section.rect.left}%`,
        width: `${section.rect.width}%`,
        height: `${section.rect.height}%`,
        border: active ? `2px solid ${accent}` : "2px solid transparent",
        background: active ? hexA(accent, 0.12) : "transparent",
        boxShadow: active ? `0 0 0 4px ${hexA(accent, 0.15)}` : "none",
      }}
    >
      <span
        className="absolute left-2 whitespace-nowrap rounded px-[6px] py-[1px] text-[8.5px] font-bold uppercase tracking-wide text-white transition-opacity"
        style={{
          top: -9,
          background: accent,
          opacity: active ? 1 : 0,
        }}
      >
        {section.label}
      </span>
    </div>
  );
}
