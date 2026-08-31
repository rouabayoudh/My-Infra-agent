import { createFileRoute } from "@tanstack/react-router";
import { Server, Trash2, Camera, Play, Square } from "lucide-react";
import { AppShell } from "@/components/infra/AppShell";
import { ResultBadge } from "@/components/infra/StatusBadge";
import { recentActions, type ActionType } from "@/data/mock";

export const Route = createFileRoute("/history")({
  head: () => ({
    meta: [
      { title: "History — InfraAgent" },
      { name: "description", content: "Chronological timeline of every action the InfraAgent performed on the fleet." },
      { property: "og:title", content: "History — InfraAgent" },
      { property: "og:description", content: "Audit trail of agent-driven VM creations, snapshots and power operations." },
    ],
  }),
  component: HistoryPage,
});

const meta: Record<ActionType, { icon: typeof Server; tone: string; label: string }> = {
  create: { icon: Server, tone: "bg-primary/15 text-primary border-primary/30", label: "Created VM" },
  delete: { icon: Trash2, tone: "bg-destructive/15 text-destructive border-destructive/30", label: "Deleted VM" },
  snapshot: { icon: Camera, tone: "bg-info/15 text-info border-info/30", label: "Snapshot taken" },
  start: { icon: Play, tone: "bg-success/15 text-success border-success/30", label: "Powered on" },
  stop: { icon: Square, tone: "bg-warning/15 text-warning border-warning/30", label: "Powered off" },
};

function HistoryPage() {
  return (
    <AppShell title="History" description="Everything the agent has done, newest first">
      <ol className="relative max-w-3xl space-y-6 border-l border-border pl-8">
        {recentActions.map((a) => {
          const { icon: Icon, tone, label } = meta[a.action];
          return (
            <li key={a.id} className="relative">
              <span
                className={`absolute -left-[3.05rem] flex h-9 w-9 items-center justify-center rounded-full border ${tone}`}
              >
                <Icon className="h-4 w-4" />
              </span>
              <div className="rounded-xl border border-border bg-card p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">{label}</p>
                  <ResultBadge status={a.status} />
                </div>
                <p className="mt-1 font-mono text-xs text-muted-foreground">{a.vm}</p>
                <p className="mt-2 font-mono text-[11px] text-muted-foreground">{a.timestamp}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </AppShell>
  );
}