import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Server, Trash2, Camera, Play, Square, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/infra/AppShell";
import { ResultBadge } from "@/components/infra/StatusBadge";
import { fetchHistory } from "@/lib/api";

export const Route = createFileRoute("/history")({
  component: HistoryPage,
});

const toolMeta: Record<string, { icon: typeof Server; tone: string; label: string }> = {
  create_vm:        { icon: Server,  tone: "bg-primary/15 text-primary border-primary/30",          label: "Created VM" },
  delete_vm:        { icon: Trash2,  tone: "bg-destructive/15 text-destructive border-destructive/30", label: "Deleted VM" },
  snapshot_vm:      { icon: Camera,  tone: "bg-info/15 text-info border-info/30",                   label: "Snapshot taken" },
  start_vm:         { icon: Play,    tone: "bg-success/15 text-success border-success/30",           label: "Powered on" },
  stop_vm:          { icon: Square,  tone: "bg-warning/15 text-warning border-warning/30",           label: "Powered off" },
  list_vms:         { icon: Server,  tone: "bg-accent/40 text-muted-foreground border-border",       label: "Listed VMs" },
  get_vm_status:    { icon: Server,  tone: "bg-accent/40 text-muted-foreground border-border",       label: "Checked status" },
  deploy_infrastructure: { icon: Server, tone: "bg-primary/15 text-primary border-primary/30",      label: "Deployed infrastructure" },
  read_pdf:         { icon: Server,  tone: "bg-info/15 text-info border-info/30",                   label: "Read PDF" },
  analyze_and_extract: { icon: Server, tone: "bg-info/15 text-info border-info/30",                 label: "Analyzed document" },
  save_yaml:        { icon: Server,  tone: "bg-primary/15 text-primary border-primary/30",          label: "Saved YAML" },
};

const defaultMeta = { icon: Server, tone: "bg-accent/40 text-muted-foreground border-border", label: "Agent action" };

function getVmName(action: any): string {
  try {
    const args = typeof action.arguments === "string" ? JSON.parse(action.arguments) : action.arguments;
    return args?.vm_name || args?.pdf_path || "-";
  } catch {
    return "-";
  }
}

function HistoryPage() {
  const [actions, setActions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const res = await fetchHistory(100);
      if (res.actions) setActions(res.actions);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { loadHistory(); }, []);

  return (
    <AppShell
      title="History"
      description="Everything the agent has done, newest first"
      actions={
        <button onClick={loadHistory} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent">
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      }
    >
      {loading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">Loading history...</div>
      ) : actions.length === 0 ? (
        <div className="py-20 text-center text-sm text-muted-foreground">No actions recorded yet.</div>
      ) : (
        <ol className="relative max-w-3xl space-y-6 border-l border-border pl-8">
          {actions.map((a: any, i: number) => {
            const { icon: Icon, tone, label } = toolMeta[a.tool_name] || defaultMeta;
            const vmName  = getVmName(a);
            const date    = a.timestamp?.slice(0, 19).replace("T", " ") || "";
            const success = a.succes === 1 || a.succes === true;
            return (
              <li key={a.id || i} className="relative">
                <span className={`absolute -left-[3.05rem] flex h-9 w-9 items-center justify-center rounded-full border ${tone}`}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="rounded-xl border border-border bg-card p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium">{label}</p>
                    <ResultBadge status={success ? "success" : "failed"} />
                  </div>
                  {vmName !== "-" && (
                    <p className="mt-1 font-mono text-xs text-muted-foreground">{vmName}</p>
                  )}
                  <p className="mt-2 font-mono text-[11px] text-muted-foreground">{date}</p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </AppShell>
  );
}
