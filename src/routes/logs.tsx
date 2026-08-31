import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Download } from "lucide-react";
import { AppShell } from "@/components/infra/AppShell";
import { logs, type LogLevel } from "@/data/mock";

export const Route = createFileRoute("/logs")({
  head: () => ({
    meta: [
      { title: "Logs — InfraAgent" },
      { name: "description", content: "Filter agent and vSphere logs by level, source and date, then export to CSV." },
      { property: "og:title", content: "Logs — InfraAgent" },
      { property: "og:description", content: "Searchable INFO, WARN and ERROR logs from the InfraAgent control plane." },
    ],
  }),
  component: LogsPage,
});

const levelStyles: Record<LogLevel, string> = {
  ERROR: "bg-destructive/15 text-destructive border-destructive/30",
  WARN: "bg-warning/15 text-warning border-warning/30",
  INFO: "bg-info/15 text-info border-info/30",
};

function LogsPage() {
  const [level, setLevel] = useState("all");
  const [source, setSource] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const sources = useMemo(() => Array.from(new Set(logs.map((l) => l.source))), []);

  const filtered = logs.filter((l) => {
    const date = l.timestamp.slice(0, 10);
    if (level !== "all" && l.level !== level) return false;
    if (source !== "all" && l.source !== source) return false;
    if (from && date < from) return false;
    if (to && date > to) return false;
    return true;
  });

  const exportCsv = () => {
    const rows = [
      ["timestamp", "level", "source", "message"],
      ...filtered.map((l) => [l.timestamp, l.level, l.source, l.message]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "infraagent-logs.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const selectClass =
    "rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary";

  return (
    <AppShell
      title="Logs"
      description={`${filtered.length} of ${logs.length} entries`}
      actions={
        <button
          onClick={exportCsv}
          className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Download className="h-4 w-4" /> Export CSV
        </button>
      }
    >
      <div className="flex flex-wrap gap-3">
        <select value={level} onChange={(e) => setLevel(e.target.value)} className={selectClass}>
          <option value="all">All levels</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)} className={selectClass}>
          <option value="all">All sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={selectClass} />
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={selectClass} />
      </div>

      <div className="mt-6 overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted-foreground">
            <tr className="border-b border-border">
              <th className="px-5 py-3 text-left font-medium">Timestamp</th>
              <th className="px-5 py-3 text-left font-medium">Level</th>
              <th className="px-5 py-3 text-left font-medium">Source</th>
              <th className="px-5 py-3 text-left font-medium">Message</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((l) => (
              <tr key={l.id} className="border-b border-border/60 last:border-0 hover:bg-accent/40">
                <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-muted-foreground">{l.timestamp}</td>
                <td className="px-5 py-3">
                  <span className={`rounded-md border px-2 py-0.5 text-xs font-medium ${levelStyles[l.level]}`}>
                    {l.level}
                  </span>
                </td>
                <td className="px-5 py-3 text-muted-foreground">{l.source}</td>
                <td className="px-5 py-3 font-mono text-xs">{l.message}</td>
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-5 py-10 text-center text-sm text-muted-foreground">
                  No log entries match these filters.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}