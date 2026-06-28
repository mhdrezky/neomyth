import type { LucideIcon } from "lucide-react";
import { ArrowLeft } from "lucide-react";

import { cn } from "@/lib/utils";

interface ToolHeaderProps {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  iconGradient?: string;
  iconShadow?: string;
  backHref?: string;
  statusLabel?: string;
  statusActive?: boolean;
  children?: React.ReactNode;
}

export function ToolHeader({
  title,
  subtitle,
  icon: Icon,
  iconGradient = "linear-gradient(135deg, #1f6feb, #388bfd)",
  iconShadow = "0 0 0 1px #2f4d80, 0 2px 8px rgba(31,111,235,.35)",
  backHref = "/",
  statusLabel,
  statusActive = true,
  children,
}: ToolHeaderProps) {
  return (
    <header className="flex h-[54px] flex-none items-center justify-between border-b border-border px-[18px]">
      <div className="flex items-center gap-[11px]">
        <a
          href={backHref}
          className="flex h-[30px] w-[30px] items-center justify-center rounded-[7px] border border-border text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
          style={{ background: "#161b22" }}
          aria-label="Back to Neomyth"
        >
          <ArrowLeft className="h-[15px] w-[15px]" />
        </a>
        <div
          className="flex h-[30px] w-[30px] items-center justify-center rounded-[7px]"
          style={{ background: iconGradient, boxShadow: iconShadow }}
        >
          <Icon className="h-[17px] w-[17px] text-white" strokeWidth={2.2} />
        </div>
        <div className="flex flex-col leading-none">
          <span className="text-[15px] font-bold tracking-tight">{title}</span>
          <span className="mt-[3px] text-[10.5px] tracking-wide text-muted-foreground">
            {subtitle}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-[9px]">
        {children}
        {statusLabel && (
          <div
            className="flex items-center gap-[7px] rounded-lg border px-3 py-1.5"
            style={{ background: "#0d2a4d", borderColor: "#1f4b80" }}
          >
            <span
              className="h-[7px] w-[7px] rounded-full"
              style={{
                background: statusActive ? "#3fb950" : "#f85149",
                boxShadow: statusActive ? "0 0 6px #3fb950" : "0 0 6px #f85149",
              }}
            />
            <span className="text-xs font-medium" style={{ color: "#9fc4f0" }}>
              {statusLabel}
            </span>
          </div>
        )}
      </div>
    </header>
  );
}
