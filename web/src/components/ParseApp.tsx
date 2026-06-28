import { useCallback, useRef, useState, useEffect } from "react";
import {
  Upload,
  Play,
  History,
  Copy,
  Check,
  Plus,
  X,
  ChevronDown,
  FileText,
  Code2,
  Eye,
  Braces,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { ToolHeader } from "@/components/ToolHeader";
import { cn } from "@/lib/utils";

type View = "upload" | "processing" | "results";
type Tab = "markdown" | "json";

interface Section {
  id: string;
  label: string;
  region: string;
  rect: { top: number; left: number; width: number; height: number };
  md: string;
  json: string;
}

const SECTIONS: Section[] = [
  {
    id: "header",
    label: "Header",
    region: "A1",
    rect: { top: 4, left: 6, width: 88, height: 11 },
    md: "# Acme Corporation\n123 Market Street, San Francisco, CA 94103\n\n## INVOICE",
    json: '  "vendor": {\n    "name": "Acme Corporation",\n    "address": "123 Market Street, San Francisco, CA 94103"\n  },',
  },
  {
    id: "billto",
    label: "Bill To",
    region: "B1",
    rect: { top: 20, left: 6, width: 42, height: 14 },
    md: "**Bill To**\nGlobex Inc.\nAttn: Jane Smith\n500 Industrial Way\nAustin, TX 78701",
    json: '  "customer": {\n    "name": "Globex Inc.",\n    "contact": "Jane Smith",\n    "address": "500 Industrial Way, Austin, TX 78701"\n  },',
  },
  {
    id: "meta",
    label: "Invoice details",
    region: "B2",
    rect: { top: 20, left: 54, width: 40, height: 14 },
    md: "| Field | Value |\n|-------|-------|\n| Invoice # | INV-2026-0042 |\n| Date | Jun 12, 2026 |\n| Due Date | Jul 12, 2026 |",
    json: '  "invoice": {\n    "number": "INV-2026-0042",\n    "date": "2026-06-12",\n    "due_date": "2026-07-12"\n  },',
  },
  {
    id: "items",
    label: "Line items",
    region: "C1",
    rect: { top: 38, left: 6, width: 88, height: 30 },
    md: "| Description | Qty | Unit Price | Amount |\n|-------------|-----|-----------|--------|\n| Design retainer | 1 | $4,500.00 | $4,500.00 |\n| Frontend dev (hrs) | 32 | $120.00 | $3,840.00 |\n| Cloud hosting | 3 | $90.00 | $270.00 |",
    json: '  "line_items": [\n    { "description": "Design retainer", "qty": 1, "unit_price": 4500.00, "amount": 4500.00 },\n    { "description": "Frontend dev (hrs)", "qty": 32, "unit_price": 120.00, "amount": 3840.00 },\n    { "description": "Cloud hosting", "qty": 3, "unit_price": 90.00, "amount": 270.00 }\n  ],',
  },
  {
    id: "totals",
    label: "Totals",
    region: "D1",
    rect: { top: 70, left: 54, width: 40, height: 13 },
    md: "**Subtotal:** $8,610.00\n**Tax (8.5%):** $731.85\n**Total Due: $9,341.85**",
    json: '  "totals": {\n    "subtotal": 8610.00,\n    "tax": 731.85,\n    "total_due": 9341.85\n  },',
  },
  {
    id: "notes",
    label: "Notes",
    region: "E1",
    rect: { top: 86, left: 6, width: 88, height: 9 },
    md: "> Payment due within 30 days. Make checks payable to Acme Corporation.\n> Thank you for your business!",
    json: '  "notes": "Payment due within 30 days. Thank you for your business!"',
  },
];

const STEP_LABELS = [
  "Uploading document…",
  "Running layout analysis…",
  "Extracting text & structure…",
  "Mapping fields to schema…",
  "Finalizing output…",
];

const HISTORY_ITEMS = [
  { file: "invoice_acme_2026.pdf", type: "Invoice", date: "Jun 12, 2026", sections: 6, color: "#3fb950" },
  { file: "globex_msa_contract.pdf", type: "Contract", date: "Jun 05, 2026", sections: 11, color: "#a371f7" },
  { file: "starbucks_receipt.pdf", type: "Receipt", date: "May 28, 2026", sections: 4, color: "#f0883e" },
  { file: "q2_earnings_report.pdf", type: "Report", date: "May 15, 2026", sections: 18, color: "#58a6ff" },
];

const DEFAULT_SCHEMA = `{
  "vendor": { "name": "string", "address": "string" },
  "customer": { "name": "string", "contact": "string", "address": "string" },
  "invoice": { "number": "string", "date": "date", "due_date": "date" },
  "line_items": [
    { "description": "string", "qty": "number", "unit_price": "number", "amount": "number" }
  ],
  "totals": { "subtotal": "number", "tax": "number", "total_due": "number" },
  "notes": "string"
}`;

function hexA(hex: string, a: number) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

export default function ParseApp() {
  const [view, setView] = useState<View>("upload");
  const [activeTab, setActiveTab] = useState<Tab>("markdown");
  const [hovered, setHovered] = useState<string | null>(null);
  const [fileName, setFileName] = useState("invoice_acme_2026.pdf");
  const [step, setStep] = useState(0);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [schema, setSchema] = useState(DEFAULT_SCHEMA);

  const fileRef = useRef<HTMLInputElement>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  useEffect(() => () => clearTimers(), [clearTimers]);

  const startProcessing = useCallback(
    (name: string) => {
      clearTimers();
      setView("processing");
      setStep(0);
      setProgress(6);
      setHistoryOpen(false);
      setHovered(null);
      setFileName(name);

      const tick = (i: number) => {
        setStep(i);
        setProgress(Math.round(((i + 1) / 5) * 100));
        if (i < 4) {
          timersRef.current.push(setTimeout(() => tick(i + 1), 620));
        } else {
          timersRef.current.push(setTimeout(() => setView("results"), 560));
        }
      };
      timersRef.current.push(setTimeout(() => tick(0), 220));
    },
    [clearTimers],
  );

  const reset = useCallback(() => {
    clearTimers();
    setView("upload");
    setHovered(null);
  }, [clearTimers]);

  const copyOutput = useCallback(() => {
    const txt =
      activeTab === "markdown"
        ? SECTIONS.map((s) => s.md).join("\n\n")
        : "{\n" + SECTIONS.map((s) => s.json).join("\n") + "\n}";
    navigator.clipboard?.writeText(txt).catch(() => {});
    setCopied(true);
    const t = setTimeout(() => setCopied(false), 1200);
    timersRef.current.push(t);
  }, [activeTab]);

  const ACC = "#58a6ff";

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background text-foreground" style={{ fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
      {/* TOP BAR */}
      <ToolHeader
        title="Neo-Parse"
        subtitle="PDF → Markdown · Structured JSON"
        icon={FileText}
        statusLabel="parser-v2 · ready"
      >
        {view === "results" && (
          <Button variant="outline" size="sm" onClick={reset} className="gap-[7px]">
            <Plus className="h-[14px] w-[14px]" />
            New document
          </Button>
        )}
      </ToolHeader>

      {/* MAIN */}
      <div className="relative flex-1 overflow-hidden">
        {/* UPLOAD VIEW */}
        {view === "upload" && (
          <div className="absolute inset-0 overflow-y-auto">
            <div className="mx-auto flex max-w-[780px] flex-col gap-[22px] px-7 pb-[120px] pt-[46px]">
              {/* Hero text */}
              <div className="mb-1 text-center">
                <h1 className="text-[27px] font-bold tracking-tight">Parse any document into clean data</h1>
                <p className="mt-[10px] text-[14.5px] leading-relaxed text-muted-foreground">
                  Drop a PDF and let the model extract Markdown and structured JSON.
                  <br />
                  Define an optional schema to shape the output exactly how you need it.
                </p>
              </div>

              {/* Dropzone */}
              <div
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  const f = e.dataTransfer.files?.[0];
                  startProcessing(f?.name ?? "document.pdf");
                }}
                className="flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-2 rounded-[14px] text-center transition-all"
                style={{
                  border: `2px dashed ${dragging ? ACC : "#30363d"}`,
                  background: dragging ? hexA(ACC, 0.08) : "#10151c",
                }}
              >
                <div
                  className="mb-[6px] flex h-[58px] w-[58px] items-center justify-center rounded-[14px]"
                  style={{ background: "#0d2a4d", border: "1px solid #1f4b80" }}
                >
                  <Upload className="h-[26px] w-[26px]" style={{ color: ACC }} />
                </div>
                <div className="text-[16px] font-semibold">Drag & drop your PDF here</div>
                <div className="text-[13px] text-muted-foreground">
                  or <span className="font-semibold" style={{ color: ACC }}>browse files</span> · PDF up to 25&nbsp;MB
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) startProcessing(f.name);
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
                    <span className="text-[13.5px] font-semibold">JSON output schema</span>
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
                      <span className="text-[11px] text-muted-foreground">Leave empty to auto-detect structure</span>
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

              {/* Action buttons */}
              <div className="flex gap-3">
                <button
                  onClick={() => startProcessing(fileName)}
                  className="flex flex-1 cursor-pointer items-center justify-center gap-[9px] rounded-[10px] border-none text-[14.5px] font-semibold text-white"
                  style={{
                    height: 46,
                    background: "linear-gradient(135deg, #1f6feb, #388bfd)",
                    boxShadow: "0 2px 12px rgba(31,111,235,.3)",
                    fontFamily: "inherit",
                  }}
                >
                  <Play className="h-[17px] w-[17px]" fill="white" />
                  Parse document
                </button>
                <button
                  onClick={() => setHistoryOpen(true)}
                  className="flex cursor-pointer items-center gap-[9px] rounded-[10px] border border-border px-[18px] text-[14px] font-medium text-foreground"
                  style={{ height: 46, background: "#161b22", fontFamily: "inherit" }}
                >
                  <History className="h-4 w-4 text-muted-foreground" />
                  History
                </button>
              </div>

              {/* Feature cards */}
              <div className="mt-[6px] flex gap-[14px]">
                {[
                  { icon: <FileText className="h-[18px] w-[18px]" style={{ color: "#3fb950" }} />, title: "Layout-aware Markdown", desc: "Headings, tables & lists preserved." },
                  { icon: <Braces className="h-[18px] w-[18px]" style={{ color: "#a371f7" }} />, title: "Schema-bound JSON", desc: "Typed fields mapped to source." },
                  { icon: <Eye className="h-[18px] w-[18px]" style={{ color: ACC }} />, title: "Source grounding", desc: "Every block traces to a region." },
                ].map((f) => (
                  <div key={f.title} className="flex flex-1 gap-[11px] rounded-[11px] border border-border p-[14px]" style={{ background: "#10151c" }}>
                    <div className="mt-[1px] flex-none">{f.icon}</div>
                    <div>
                      <div className="text-[13px] font-semibold">{f.title}</div>
                      <div className="mt-[3px] text-[11.5px] leading-[1.4] text-muted-foreground">{f.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* PROCESSING VIEW */}
        {view === "processing" && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex w-[420px] max-w-[90%] flex-col items-center gap-[22px]">
              {/* Animated document */}
              <div className="relative h-[120px] w-[96px] overflow-hidden rounded-lg bg-white" style={{ boxShadow: "0 8px 40px rgba(31,111,235,.25)" }}>
                {[14, 28, 42, 62, 76, 96].map((t, i) => (
                  <div
                    key={i}
                    className="absolute rounded-[3px]"
                    style={{
                      left: 12, top: t, right: i === 0 ? 12 : 20 + i * 5,
                      height: i === 0 ? 6 : 5,
                      background: i === 0 ? "#e6e6e6" : "#ededed",
                    }}
                  />
                ))}
                <div
                  className="absolute left-0 right-0 h-[26px]"
                  style={{
                    background: "linear-gradient(180deg, rgba(56,139,253,0), rgba(56,139,253,.55))",
                    borderBottom: "2px solid #58a6ff",
                    animation: "pf-scan 1.5s ease-in-out infinite",
                  }}
                />
              </div>

              <div className="text-center">
                <div className="text-[16px] font-semibold">{STEP_LABELS[step]}</div>
                <div className="mt-[5px] text-[12.5px] text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  {fileName}
                </div>
              </div>

              {/* Progress bar */}
              <div className="h-[6px] w-full overflow-hidden rounded border border-border" style={{ background: "#161b22" }}>
                <div
                  className="h-full rounded transition-[width] duration-400"
                  style={{
                    width: `${progress}%`,
                    background: `linear-gradient(90deg, ${ACC}, ${hexA(ACC, 0.6)})`,
                  }}
                />
              </div>

              {/* Step dots */}
              <div className="flex gap-2">
                {STEP_LABELS.map((_, i) => (
                  <span
                    key={i}
                    className="h-2 w-2 rounded-full transition-colors"
                    style={{ background: i <= step ? ACC : "#21262d" }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        {/* RESULTS VIEW */}
        {view === "results" && (
          <div className="absolute inset-0 grid min-h-0 grid-cols-2">
            {/* LEFT: extracted output */}
            <section className="flex min-h-0 flex-col border-r border-border">
              {/* Tabs */}
              <div className="flex flex-none items-center justify-between border-b border-border px-[14px]" style={{ height: 46 }}>
                <div className="flex h-full items-end gap-[2px]">
                  {(["markdown", "json"] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className="flex h-full items-center gap-[7px] border-none bg-transparent px-[13px] text-[13px] font-semibold capitalize"
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
                {activeTab === "markdown" ? (
                  <div className="flex flex-col gap-1">
                    {SECTIONS.map((s) => (
                      <SectionBlock key={s.id} section={s} field="md" hovered={hovered} onHover={setHovered} accent={ACC} />
                    ))}
                  </div>
                ) : (
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "12.5px", lineHeight: 1.7 }}>
                    <div className="px-[14px] text-muted-foreground">{"{"}</div>
                    {SECTIONS.map((s) => (
                      <SectionBlock key={s.id} section={s} field="json" hovered={hovered} onHover={setHovered} accent={ACC} />
                    ))}
                    <div className="px-[14px] text-muted-foreground">{"}"}</div>
                  </div>
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
                  <span className="text-[11.5px] text-muted-foreground">Page 1 / 1</span>
                  <span className="flex items-center gap-[5px] rounded-full border px-[9px] py-[3px] text-[11px]" style={{ color: "#9fc4f0", background: "#0d2a4d", borderColor: "#1f4b80" }}>
                    <span className="h-[6px] w-[6px] rounded-full" style={{ background: ACC }} />
                    source grounding
                  </span>
                </div>
              </div>

              <div className="flex flex-1 justify-center overflow-y-auto p-[26px]" style={{ minHeight: 0 }}>
                <div className="relative w-full max-w-[560px] self-start overflow-hidden rounded-[3px] bg-white" style={{ aspectRatio: "1 / 1.414", boxShadow: "0 10px 50px rgba(0,0,0,.55)" }}>
                  <InvoicePreview />
                  {SECTIONS.map((s) => (
                    <OverlayRegion key={s.id} section={s} hovered={hovered} onHover={setHovered} accent={ACC} />
                  ))}
                </div>
              </div>
            </section>
          </div>
        )}
      </div>

      {/* HISTORY DRAWER */}
      {historyOpen && (
        <div className="fixed inset-0 z-[39] transition-opacity" style={{ background: "rgba(1,4,9,.55)" }} onClick={() => setHistoryOpen(false)} />
      )}
      <div
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border transition-transform"
        style={{
          background: "#0d1117",
          boxShadow: "0 -12px 40px rgba(0,0,0,.5)",
          transform: historyOpen ? "translateY(0)" : "translateY(110%)",
          transitionTimingFunction: "cubic-bezier(.4,0,.2,1)",
          transitionDuration: "280ms",
        }}
      >
        <div className="flex items-center justify-between border-b border-border px-[18px] py-[13px]">
          <div className="flex items-center gap-[10px]">
            <History className="h-4 w-4" style={{ color: ACC }} />
            <span className="text-[14px] font-semibold">Parsing history</span>
            <span className="rounded-full border border-border px-2 py-[2px] text-[11px] text-muted-foreground" style={{ background: "#161b22" }}>
              {HISTORY_ITEMS.length} documents
            </span>
          </div>
          <button
            onClick={() => setHistoryOpen(false)}
            className="flex h-[30px] w-[30px] items-center justify-center rounded-[7px] border border-border text-muted-foreground"
            style={{ background: "#161b22", cursor: "pointer" }}
          >
            <X className="h-[15px] w-[15px]" />
          </button>
        </div>
        <div className="flex gap-3 overflow-x-auto px-[18px] py-4">
          {HISTORY_ITEMS.map((h) => (
            <div
              key={h.file}
              onClick={() => startProcessing(h.file)}
              className="flex-none cursor-pointer rounded-[11px] border border-border p-[14px] transition-colors hover:border-primary/40"
              style={{ width: 232, background: "#10151c" }}
            >
              <div className="mb-[11px] flex items-center gap-[9px]">
                <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-lg" style={{ background: hexA(h.color, 0.13), color: h.color }}>
                  <FileText className="h-[15px] w-[15px]" />
                </div>
                <span className="rounded-full px-2 py-[2px] text-[10px] font-semibold" style={{ color: h.color, background: hexA(h.color, 0.12) }}>
                  {h.type}
                </span>
              </div>
              <div className="truncate text-[12.5px] font-semibold" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{h.file}</div>
              <div className="mt-[9px] flex items-center justify-between text-[11px] text-muted-foreground">
                <span>{h.date}</span>
                <span>{h.sections} sections</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* History floating tab */}
      {!historyOpen && view !== "processing" && (
        <button
          onClick={() => setHistoryOpen(true)}
          className="fixed bottom-4 right-[18px] z-30 flex items-center gap-2 rounded-full border border-border px-[14px]"
          style={{ height: 38, background: "#161b22", color: "#9fb6cf", fontFamily: "inherit", cursor: "pointer", boxShadow: "0 4px 16px rgba(0,0,0,.4)" }}
        >
          <History className="h-[14px] w-[14px]" />
          <span className="text-[12.5px] font-medium">History</span>
          <span className="rounded-[10px] border border-border px-[7px] py-[1px] text-[10px] text-muted-foreground" style={{ background: "#0d1117" }}>
            {HISTORY_ITEMS.length}
          </span>
        </button>
      )}

      <style>{`
        @keyframes pf-scan {
          0% { top: 0; }
          100% { top: 100%; }
        }
      `}</style>
    </div>
  );
}

function SectionBlock({
  section,
  field,
  hovered,
  onHover,
  accent,
}: {
  section: Section;
  field: "md" | "json";
  hovered: string | null;
  onHover: (id: string | null) => void;
  accent: string;
}) {
  const active = hovered === section.id;
  return (
    <div
      onMouseEnter={() => onHover(section.id)}
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
      <pre className="m-0 whitespace-pre-wrap break-words text-[12.5px] leading-[1.7]" style={{ fontFamily: "'JetBrains Mono', monospace", color: field === "md" ? "#c9d6e3" : "#9db8d8" }}>
        {section[field]}
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
  section: Section;
  hovered: string | null;
  onHover: (id: string | null) => void;
  accent: string;
}) {
  const active = hovered === section.id;
  return (
    <div
      onMouseEnter={() => onHover(section.id)}
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

function InvoicePreview() {
  return (
    <div className="pointer-events-none absolute inset-0" style={{ color: "#1a1a1a" }}>
      {/* Header */}
      <div className="absolute flex justify-between" style={{ top: "4%", left: "6%", width: "88%", height: "11%" }}>
        <div>
          <div className="text-[18px] font-bold" style={{ color: "#111" }}>Acme Corporation</div>
          <div className="mt-1 text-[9.5px] leading-[1.4]" style={{ color: "#777" }}>123 Market Street<br />San Francisco, CA 94103</div>
        </div>
        <div className="text-right">
          <div className="text-[26px] font-light tracking-[3px]" style={{ color: "#9aa0a6" }}>INVOICE</div>
        </div>
      </div>
      {/* Bill To */}
      <div className="absolute" style={{ top: "20%", left: "6%", width: "42%" }}>
        <div className="text-[8.5px] font-bold uppercase tracking-[1px]" style={{ color: "#9aa0a6" }}>BILL TO</div>
        <div className="mt-[6px] text-[12px] font-bold" style={{ color: "#222" }}>Globex Inc.</div>
        <div className="mt-[3px] text-[9.5px] leading-[1.5]" style={{ color: "#555" }}>Attn: Jane Smith<br />500 Industrial Way<br />Austin, TX 78701</div>
      </div>
      {/* Meta */}
      <div className="absolute" style={{ top: "20%", left: "54%", width: "40%" }}>
        {[
          ["Invoice #", "INV-2026-0042"],
          ["Date", "Jun 12, 2026"],
          ["Due Date", "Jul 12, 2026"],
        ].map(([label, val], i) => (
          <div key={label} className="flex justify-between border-b py-[3px] text-[9.5px]" style={{ borderColor: i < 2 ? "#eee" : "transparent" }}>
            <span style={{ color: "#888" }}>{label}</span>
            <span className="font-semibold" style={{ color: "#222" }}>{val}</span>
          </div>
        ))}
      </div>
      {/* Items table */}
      <div className="absolute" style={{ top: "38%", left: "6%", width: "88%" }}>
        <div className="flex rounded-[3px] px-2 py-[6px] text-[8.5px] font-bold uppercase tracking-wide text-white" style={{ background: "#1a1a1a" }}>
          <span className="flex-1">Description</span>
          <span className="w-[34px] text-right">Qty</span>
          <span className="w-[70px] text-right">Unit</span>
          <span className="w-[70px] text-right">Amount</span>
        </div>
        {[
          ["Design retainer", "1", "$4,500.00", "$4,500.00"],
          ["Frontend dev (hrs)", "32", "$120.00", "$3,840.00"],
          ["Cloud hosting", "3", "$90.00", "$270.00"],
        ].map(([desc, qty, unit, amt]) => (
          <div key={desc} className="flex border-b px-2 py-2 text-[9.5px]" style={{ borderColor: "#eee", color: "#333" }}>
            <span className="flex-1">{desc}</span>
            <span className="w-[34px] text-right">{qty}</span>
            <span className="w-[70px] text-right">{unit}</span>
            <span className="w-[70px] text-right">{amt}</span>
          </div>
        ))}
      </div>
      {/* Totals */}
      <div className="absolute" style={{ top: "70%", left: "54%", width: "40%" }}>
        <div className="flex justify-between py-[3px] text-[9.5px]" style={{ color: "#555" }}><span>Subtotal</span><span>$8,610.00</span></div>
        <div className="flex justify-between border-b py-[3px] text-[9.5px]" style={{ color: "#555", borderColor: "#eee" }}><span>Tax (8.5%)</span><span>$731.85</span></div>
        <div className="flex justify-between py-[7px] text-[13px] font-bold" style={{ color: "#111" }}><span>Total Due</span><span>$9,341.85</span></div>
      </div>
      {/* Notes */}
      <div className="absolute border-t pt-2" style={{ top: "86%", left: "6%", width: "88%", borderColor: "#eee" }}>
        <div className="text-[9px] italic leading-[1.5]" style={{ color: "#888" }}>
          Payment due within 30 days. Make checks payable to Acme Corporation.<br />Thank you for your business!
        </div>
      </div>
    </div>
  );
}
