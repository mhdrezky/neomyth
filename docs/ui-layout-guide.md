# Neomyth UI Layout Guide

Standard layout patterns for the Astro frontend (`web/`). **All current and future tool pages must follow the tool layout** defined here unless a module has a documented exception.

## Page types

| Type | Route example | Layout | Max width |
|------|---------------|--------|-----------|
| **Landing** | `/` | Custom marketing layout | `max-w-5xl` |
| **Tool** | `/voice`, `/parse`, `/spec` | `ToolPageLayout.astro` | `max-w-3xl` |

Landing (`web/src/pages/index.astro`) is unique: hero, module cards, FAQ. Do not reuse `ToolPageLayout` for the home page.

---

## Tool page anatomy

Every tool page uses the same vertical structure:

```text
┌─────────────────────────────────────────┐
│  ← Back to Neomyth                      │  nav
├─────────────────────────────────────────┤
│  Tool Name (h1)                         │
│  Short description paragraph            │  header (static, SEO)
├─────────────────────────────────────────┤
│  ┌ Tool control panel ────────────────┐ │
│  │ status · metrics · primary actions │ │  ToolControlPanel (React)
│  └────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│  ┌ Main work area ────────────────────┐ │
│  │ chat / editor / results / etc.     │ │  tool-specific (React island)
│  └────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│  errors / noscript fallback             │
└─────────────────────────────────────────┘
         ↓ page scroll (full document)
```

Reference implementation: [`web/src/pages/voice/index.astro`](../web/src/pages/voice/index.astro) + [`VoiceApp.tsx`](../web/src/components/VoiceApp.tsx).

---

## Shared Astro shell — `ToolPageLayout`

**File:** [`web/src/layouts/ToolPageLayout.astro`](../web/src/layouts/ToolPageLayout.astro)

Props:

| Prop | Required | Default | Purpose |
|------|----------|---------|---------|
| `title` | yes | — | Tool name in `<h1>` and browser title (`{title} — Neomyth`) |
| `description` | yes | — | Static paragraph under title (SEO/GEO) |
| `canonical` | no | — | Canonical URL |
| `backHref` | no | `/` | Back link target |
| `backLabel` | no | `← Back to Neomyth` | Back link text |

Slots:

| Slot | Purpose |
|------|---------|
| `head` | Optional JSON-LD, tool-specific meta |
| default | Tool React island + noscript |

### Template for a new tool page

```astro
---
import ToolPageLayout from "@/layouts/ToolPageLayout.astro";
import JsonLd from "@/components/seo/JsonLd.astro";
import ParseApp from "@/components/ParseApp";
---

<ToolPageLayout
  title="Neo-Parse"
  description="Extract structure and insights from documents."
  canonical={new URL("/parse", import.meta.env.PUBLIC_SITE_URL ?? "http://localhost:4321").href}
>
  <JsonLd type="parse" slot="head" />

  <ParseApp client:load />

  <noscript>
    <p class="mt-6 text-sm text-destructive">
      JavaScript is required for this tool.
    </p>
  </noscript>
</ToolPageLayout>
```

**Rules:**

- Keep **header copy in Astro** (static HTML for SEO).
- Put **interactivity in a React island** with `client:load` (or `client:visible` / `client:idle` when appropriate).
- Do not embed tool titles inside the React island — they belong in `ToolPageLayout`.

---

## Tool body layout (React)

Inside each `*App.tsx` island, use this stack:

```tsx
<div className="space-y-4">
  <ToolControlPanel>{/* status, metrics, buttons */}</ToolControlPanel>
  {/* main work area — ChatMessages, editor, upload zone, etc. */}
  {/* optional Alert for errors */}
</div>
```

**File:** [`web/src/components/ToolControlPanel.tsx`](../web/src/components/ToolControlPanel.tsx)

Styles: `rounded-xl border bg-card p-4 shadow-sm` — do not change per tool; extend content inside only.

---

## Conversational tools — `ChatMessages`

For chat-style tools (Neo-Voice, future agents):

**File:** [`web/src/components/ChatMessages.tsx`](../web/src/components/ChatMessages.tsx)

| Pattern | Value |
|---------|--------|
| User messages | Right-aligned bubble, `bg-primary` |
| AI messages | Left-aligned bubble, `bg-card` + border |
| Container height | Grows with content (no inner scroll) |
| Scroll | **Page-level** (`window`), not a nested scroll area |
| Auto-scroll | Pins to bottom while user is near bottom; stops if user scrolls up |
| Jump button | Fixed `New messages` when unpinned |

Pass `messages: ChatMessage[]` and optional `streamingAssistant` for live LLM text.

---

## Hydration (Astro islands)

| UI | Directive |
|----|-----------|
| Landing cards, FAQ | None (static Astro + shadcn pre-render) |
| Tool control + work area | `client:load` for mic/WebSocket/forms |
| Below-fold widgets | `client:visible` or `client:idle` |

---

## Styling tokens

- Theme: dark (`class="dark"` on `<html>` in `BaseLayout`)
- shadcn/ui components in `web/src/components/ui/`
- Spacing: `space-y-4` between control panel and work area
- Page padding: `px-6 py-8 pb-12` (set in `ToolPageLayout`)

---

## Adding a new tool — checklist

1. Register in [`web/src/data/modules.ts`](../web/src/data/modules.ts) (`href`, `status: "available"`).
2. Create `web/src/pages/<slug>/index.astro` using `ToolPageLayout`.
3. Create `web/src/components/<Tool>App.tsx` with `ToolControlPanel` + work area.
4. Add JSON-LD variant in `JsonLd.astro` if needed.
5. Add API routes in `api/routers/` (Python gateway only — no HTML).
6. Document backend in `docs/<tool-name>/architecture.md`.

---

## File map

```text
web/src/
├── layouts/
│   ├── BaseLayout.astro      # html shell, meta, globals.css
│   └── ToolPageLayout.astro  # tool pages — USE THIS
├── components/
│   ├── ToolControlPanel.tsx  # shared control strip
│   ├── ChatMessages.tsx      # messenger UI + page scroll
│   ├── VoiceApp.tsx          # Neo-Voice island (reference)
│   └── ui/                   # shadcn primitives
└── pages/
    ├── index.astro           # landing (different layout)
    └── voice/index.astro     # tool page (reference)
```

---

## Related docs

- [Neomyth Voice architecture](./neomyth-voice/architecture.md) — backend pipeline
- [AGENTS.md](../AGENTS.md) — monorepo conventions for agents
