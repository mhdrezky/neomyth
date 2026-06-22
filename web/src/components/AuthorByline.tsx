import { Linkedin, Mail } from "lucide-react";

export function AuthorByline() {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-center gap-x-3 gap-y-2">
      <span className="text-sm text-muted-foreground">
        by <span className="font-medium text-foreground">mhdrezky</span>
      </span>
      <span className="hidden text-muted-foreground sm:inline" aria-hidden>
        ·
      </span>
      <div className="flex items-center gap-3">
        <a
          href="https://www.linkedin.com/in/mhdrezky/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-primary"
          aria-label="mhdrezky on LinkedIn"
        >
          <Linkedin className="h-4 w-4 shrink-0" aria-hidden />
          <span>LinkedIn</span>
        </a>
        <a
          href="mailto:mhdrezky@gmail.com"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-primary"
          aria-label="Email mhdrezky@gmail.com"
        >
          <Mail className="h-4 w-4 shrink-0" aria-hidden />
          <span>mhdrezky@gmail.com</span>
        </a>
      </div>
    </div>
  );
}
