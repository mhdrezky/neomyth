import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface ToolControlPanelProps {
  children: ReactNode;
  className?: string;
}

/** Shared control strip for Neomyth tool pages (status, metrics, primary actions). */
export function ToolControlPanel({ children, className }: ToolControlPanelProps) {
  return (
    <div
      className={cn(
        "space-y-4 rounded-xl border border-border bg-card p-4 shadow-sm",
        className,
      )}
    >
      {children}
    </div>
  );
}
