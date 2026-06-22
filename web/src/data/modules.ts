import type { LucideIcon } from "lucide-react";
import { FileSearch, FileText, Mic } from "lucide-react";

export type ModuleStatus = "available" | "coming_soon";

export interface NeomythModule {
  id: string;
  name: string;
  description: string;
  longDescription: string;
  href?: string;
  status: ModuleStatus;
  icon: LucideIcon;
  accentClass: string;
}

export const modules: NeomythModule[] = [
  {
    id: "neo-voice",
    name: "Neo-Voice",
    description: "Real-time voice assistant with STT, LLM, and TTS.",
    longDescription:
      "Neo-Voice is a full-duplex voice assistant that transcribes your speech, reasons with a local LLM, and speaks responses aloud. Pipeline: speech-to-text → LLM → text-to-speech over WebSocket.",
    href: "/voice",
    status: "available",
    icon: Mic,
    accentClass: "text-primary border-primary/40 hover:ring-primary/50",
  },
  {
    id: "neo-parse",
    name: "Neo-Parse",
    description: "Extract structure and insights from documents.",
    longDescription:
      "Neo-Parse will parse PDFs, markdown, and codebases into structured data for downstream AI workflows. Coming soon.",
    status: "coming_soon",
    icon: FileSearch,
    accentClass: "text-muted-foreground border-border",
  },
  {
    id: "neo-spec",
    name: "Neo-Spec",
    description: "Generate and refine technical specifications with AI.",
    longDescription:
      "Neo-Spec will help teams draft, review, and iterate on product and engineering specs. Coming soon.",
    status: "coming_soon",
    icon: FileText,
    accentClass: "text-muted-foreground border-border",
  },
];

export const faqItems = [
  {
    question: "What is Neomyth?",
    answer:
      "Neomyth is a modular AI toolkit. Each module (Neo-Voice, Neo-Parse, Neo-Spec) solves a focused problem with local or self-hosted models where possible.",
  },
  {
    question: "What is Neo-Voice?",
    answer:
      "Neo-Voice is a real-time voice assistant. You speak, it transcribes with Whisper, replies via an LLM, and reads answers with Kokoro TTS.",
  },
  {
    question: "What are Neo-Parse and Neo-Spec?",
    answer:
      "Neo-Parse will extract structure from documents. Neo-Spec will help generate technical specifications. Both are on the roadmap.",
  },
  {
    question: "How do I get started?",
    answer:
      "Start Docker workers (STT, LLM, TTS), run the API on port 5000, then open Neo-Voice from this site and click Start Session.",
  },
];
