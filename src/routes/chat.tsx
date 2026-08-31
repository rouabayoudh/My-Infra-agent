import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import { Send, Loader2 } from "lucide-react";
import { AppShell } from "@/components/infra/AppShell";
import { sendChat } from "@/lib/api";
import logo from "@/assets/infraagent-logo.png";
import ReactMarkdown from "react-markdown";

export const Route = createFileRoute("/chat")({
  component: ChatPage,
});

type Msg = { id: string; role: "user" | "agent"; text: string; tools?: string[]; loading?: boolean };

const suggestions = [
  "List all VMs",
  "Create VM srv-dev-web-01 from ubuntu-22.04",
  "Status of srv-dev-web-01",
  "Take a snapshot of srv-dev-web-01",
  "Show last errors",
  "history",
];

const markdownComponents = {
  table: (props: any) => (
    <div className="overflow-x-auto my-2">
      <table className="w-full text-xs border-collapse" {...props} />
    </div>
  ),
  thead: (props: any) => <thead className="bg-accent/40" {...props} />,
  th: (props: any) => <th className="border border-border px-3 py-2 text-left font-medium text-muted-foreground" {...props} />,
  td: (props: any) => <td className="border border-border px-3 py-2" {...props} />,
  tr: (props: any) => <tr className="hover:bg-accent/20" {...props} />,
  code: (props: any) => <code className="bg-accent px-1 py-0.5 rounded text-xs font-mono" {...props} />,
  strong: (props: any) => <strong className="font-semibold text-foreground" {...props} />,
  p: (props: any) => <p className="mb-2 last:mb-0" {...props} />,
  ul: (props: any) => <ul className="list-disc list-inside space-y-1 mb-2" {...props} />,
  li: (props: any) => <li className="text-sm" {...props} />,
};

function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([
    {
      id: "welcome",
      role: "agent",
      text: "Hello! I am **InfraAgent**. I can create, manage and monitor your VMware virtual machines.\n\nWhat would you like to do?",
    },
  ]);
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef             = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text: string) => {
    const value = text.trim();
    if (!value || loading) return;
    const userId = Date.now().toString();
    setMessages(prev => [...prev, { id: userId, role: "user", text: value }]);
    setInput("");
    setLoading(true);
    const loadingId = userId + "-loading";
    setMessages(prev => [...prev, { id: loadingId, role: "agent", text: "", loading: true }]);
    try {
      const res = await sendChat(value);
      const toolNames = (res.tool_calls || []).map((t: any) => t.tool);
      setMessages(prev => prev
        .filter(m => m.id !== loadingId)
        .concat({ id: userId + "-a", role: "agent", text: res.response || "Done.", tools: toolNames })
      );
    } catch {
      setMessages(prev => prev
        .filter(m => m.id !== loadingId)
        .concat({ id: userId + "-err", role: "agent", text: "Error connecting to InfraAgent API. Make sure the API is running on port 8000." })
      );
    }
    setLoading(false);
  };

  return (
    <AppShell title="Agent Chat" description="Natural language control over your VMware infrastructure">
      <div className="mx-auto flex h-[calc(100vh-11rem)] max-w-3xl flex-col rounded-xl border border-border bg-card">
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                  {m.text}
                </p>
              </div>
            ) : (
              <div key={m.id} className="flex gap-3">
                <img src={logo} alt="" width={28} height={28} className="mt-1 h-7 w-7 shrink-0 rounded-full" />
                <div className="max-w-[85%] space-y-2">
                  {m.tools?.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {m.tools.map((t) => (
                        <span key={t} className="rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 font-mono text-[11px] text-primary">
                          [{t}]
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {m.loading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Thinking...</span>
                    </div>
                  ) : (
                    <div className="text-sm leading-relaxed text-foreground">
                      <ReactMarkdown components={markdownComponents}>{m.text}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            )
          )}
          <div ref={bottomRef} />
        </div>
        <div className="border-t border-border p-4">
          <div className="mb-3 flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button key={s} onClick={() => send(s)} disabled={loading}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:opacity-40">
                {s}
              </button>
            ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="flex items-end gap-2 rounded-lg border border-input bg-background p-2">
            <textarea value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
              rows={2} placeholder="Ask InfraAgent to provision, snapshot or inspect a VM..."
              disabled={loading}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50" />
            <button type="submit" disabled={loading || !input.trim()} aria-label="Send"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
