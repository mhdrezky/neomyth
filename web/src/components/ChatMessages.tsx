import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown, Bot, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface ChatMessagesProps {
  messages: ChatMessage[];
  streamingAssistant?: string;
}

const SCROLL_THRESHOLD = 120;

// Tool pages may scroll at page level (per ui-layout-guide) or inside a
// nested overflow container (fullWidth app shell); detect which applies.
function getScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null;
  while (node) {
    const { overflowY } = window.getComputedStyle(node);
    if (/(auto|scroll|overlay)/.test(overflowY)) return node;
    node = node.parentElement;
  }
  return null;
}

function distanceFromBottom(container: HTMLElement | null): number {
  if (container) {
    return container.scrollHeight - container.scrollTop - container.clientHeight;
  }
  const doc = document.documentElement;
  return doc.scrollHeight - window.scrollY - doc.clientHeight;
}

function scrollTargetToBottom(
  container: HTMLElement | null,
  behavior: ScrollBehavior = "auto",
) {
  if (container) {
    container.scrollTo({
      top: Math.max(0, container.scrollHeight - container.clientHeight),
      behavior,
    });
    return;
  }
  const top = document.documentElement.scrollHeight - window.innerHeight;
  window.scrollTo({ top: Math.max(0, top), behavior });
}

export function ChatMessages({ messages, streamingAssistant }: ChatMessagesProps) {
  const chatRef = useRef<HTMLDivElement>(null);
  const scrollParentRef = useRef<HTMLElement | null>(null);
  const pinnedRef = useRef(true);
  const programmaticScrollRef = useRef(false);
  const [showJumpButton, setShowJumpButton] = useState(false);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    programmaticScrollRef.current = true;

    const run = () => scrollTargetToBottom(scrollParentRef.current, behavior);

    if (behavior === "auto") {
      requestAnimationFrame(() => {
        run();
        requestAnimationFrame(() => {
          programmaticScrollRef.current = false;
        });
      });
    } else {
      run();
      window.setTimeout(() => {
        programmaticScrollRef.current = false;
      }, 300);
    }

    pinnedRef.current = true;
    setShowJumpButton(false);
  }, []);

  const handleScroll = useCallback(() => {
    if (programmaticScrollRef.current) return;

    const pinned = distanceFromBottom(scrollParentRef.current) < SCROLL_THRESHOLD;
    pinnedRef.current = pinned;
    setShowJumpButton(!pinned);
  }, []);

  // Resolve the scroll parent before the pinning effect below runs.
  useLayoutEffect(() => {
    scrollParentRef.current = getScrollParent(chatRef.current);
  }, []);

  useEffect(() => {
    const target: HTMLElement | Window = scrollParentRef.current ?? window;
    target.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => target.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  useLayoutEffect(() => {
    if (!pinnedRef.current) return;
    scrollToBottom("auto");
  }, [messages, streamingAssistant, scrollToBottom]);

  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;

    const observer = new ResizeObserver(() => {
      if (!pinnedRef.current) return;
      scrollToBottom("auto");
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [scrollToBottom]);

  const hasStreaming = Boolean(streamingAssistant?.trim());
  const isEmpty = messages.length === 0 && !hasStreaming;

  return (
    <>
      <div
        ref={chatRef}
        className="rounded-xl border border-border bg-card/50 px-4 py-6 shadow-sm"
        aria-live="polite"
        aria-label="Conversation"
      >
        <div className="mx-auto flex w-full flex-col gap-4">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
                <Bot className="h-7 w-7 text-muted-foreground" aria-hidden />
              </div>
              <p className="text-lg font-medium">Start speaking to begin</p>
              <p className="max-w-sm text-sm text-muted-foreground">
                Your voice is transcribed, answered by the LLM, and read aloud. Messages
                appear here like a chat.
              </p>
            </div>
          ) : (
            <>
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              {hasStreaming && (
                <MessageBubble
                  message={{
                    id: "streaming",
                    role: "assistant",
                    content: streamingAssistant!,
                  }}
                  isStreaming
                />
              )}
            </>
          )}
        </div>
      </div>

      {showJumpButton && (
        <div className="pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="pointer-events-auto gap-2 rounded-full shadow-lg"
            onClick={() => scrollToBottom("smooth")}
          >
            <ArrowDown className="h-4 w-4" aria-hidden />
            New messages
          </Button>
        </div>
      )}
    </>
  );
}

function MessageBubble({
  message,
  isStreaming = false,
}: {
  message: ChatMessage;
  isStreaming?: boolean;
}) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full gap-2.5",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground",
        )}
        aria-hidden
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div
        className={cn(
          "flex max-w-[min(100%,42rem)] flex-col gap-1",
          isUser ? "items-end" : "items-start",
        )}
      >
        <span className="px-1 text-xs font-medium text-muted-foreground">
          {isUser ? "You" : "Neo-Voice"}
          {isStreaming && (
            <span className="ml-1.5 inline-flex gap-0.5 align-middle">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:0ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:300ms]" />
            </span>
          )}
        </span>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm",
            isUser
              ? "rounded-br-md bg-primary text-primary-foreground"
              : "rounded-bl-md border border-border bg-card text-card-foreground",
          )}
        >
          {message.content}
        </div>
      </div>
    </div>
  );
}
