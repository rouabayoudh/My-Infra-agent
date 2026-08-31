import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Send } from "lucide-react";
import { AppShell } from "@/components/infra/AppShell";
import logo from "@/assets/infraagent-logo.png";

export const Route = createFileRoute("/chat")({
  head: () => ({
    meta: [
      { title: "Agent Chat — InfraAgent" },
      { name: "description", content: "Talk to the InfraAgent operator to provision, snapshot and inspect VMware VMs." },
      { property: "og:title", content: "Agent Chat — InfraAgent" },
      { property: "og:description", content: "Conversational control plane for your VMware infrastructure." },
    ],
  }),
  component: ChatPage,
});

type Msg = { id: string; role: "user" | "agent"; text: string; tools?: string[] };

const initial: Msg[] = [
  { id: "m1", role: "user", text: "Create a web server in dev from the ubuntu template." },
  {
    id: "m2",
    role: "agent",
    text: "Provisioned **srv-dev-web-01** from `ubuntu-22.04` and powered it on. Guest tools reported healthy after 42s.",
    tools: ["create_vm", "power_on"],
  },
  { id: "m3", role: "user", text: "Take a snapshot before the upgrade." },
  {
    id: "m4",
    role: "agent",
    text: "Snapshot `pre-upgrade` created on srv-dev-web-01 (2.1 GB delta).",
    tools: ["snapshot_vm"],
  },
];

const suggestions = ["Create 3 web servers", "Import PDF", "Show last errors"];

function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>(initial);
  const [input, setInput] = useState("");

  const send = (text: string) => {
    const value = text.trim();
    if (!value) return;
    const id = Date.now().toString();
    setMessages((prev) => [
      ...prev,
      { id, role: "user", text: value },
      {
        id: `${id}-a`,
        role: "agent",
        text: "Queued. I'll run the matching vSphere tools and report the result here.",
        tools: ["plan_task"],
      },
    ]);
    setInput("");
  };

  return (
    <AppShell title="Agent Chat" description="Natural language control over the VMware fleet">
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
                <img src={logo} alt="" width={28} height={28} className="mt-1 h-7 w-7 shrink-0" />
                <div className="max-w-[85%] space-y-2">
                  {m.tools?.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {m.tools.map((t) => (
                        <span
                          key={t}
                          className="rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 font-mono text-[11px] text-primary"
                        >
                          [{t}]
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <p className="text-sm leading-relaxed text-foreground">{m.text}</p>
                </div>
              </div>
            ),
          )}
        </div>

        <div className="border-t border-border p-4">
          <div className="mb-3 flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-end gap-2 rounded-lg border border-input bg-background p-2"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={2}
              placeholder="Ask InfraAgent to provision, snapshot or inspect a VM…"
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground"
            />
            <button
              type="submit"
              aria-label="Send message"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    </AppShell>
  );
}