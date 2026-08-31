import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Server, Play, Square, Layers, Activity } from "lucide-react";
import { AppShell } from "@/components/infra/AppShell";
import { ResultBadge } from "@/components/infra/StatusBadge";
import { creationActivity, recentActions, templates, vms } from "@/data/mock";
import { fetchVMs, fetchStats, fetchHistory, startMonitoring, stopMonitoring } from "@/lib/api";

export const Route = createFileRoute("/")(
  { component: Dashboard }
);

function StatCard({ label, value, icon: Icon, tone }: {
  label: string; value: number; icon: typeof Server; tone: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className={`rounded-lg p-2 ${tone}`}><Icon className="h-4 w-4" /></span>
      </div>
      <p className="mt-3 text-3xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Dashboard() {
  const [vmsData, setVmsData]   = useState(vms);
  const [history, setHistory]   = useState(recentActions);
  const [monitoring, setMonitoring] = useState(false);
  const [stats, setStats] = useState({ vms_running: 0, vms_stopped: 0 });

  useEffect(() => {
    fetchVMs().then(d => d.vms && setVmsData(d.vms)).catch(() => {});
    fetchStats().then(d => { setStats(d); setMonitoring(d.monitoring_active); }).catch(() => {});
    fetchHistory(5).then(d => d.actions && setHistory(d.actions)).catch(() => {});
  }, []);

  const toggleMonitoring = async () => {
    if (monitoring) { await stopMonitoring(); setMonitoring(false); }
    else { await startMonitoring(); setMonitoring(true); }
  };

  const total   = vmsData.length;
  const running = stats.vms_running || vmsData.filter((v: any) => v.status === "PoweredOn").length;
  const stopped = stats.vms_stopped || vmsData.filter((v: any) => v.status === "PoweredOff").length;

  return (
    <AppShell title="Dashboard" description="Fleet overview and agent activity">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total VMs"    value={total}          icon={Server} tone="bg-primary/15 text-primary" />
        <StatCard label="Running VMs"  value={running}        icon={Play}   tone="bg-success/15 text-success" />
        <StatCard label="Stopped VMs"  value={stopped}        icon={Square} tone="bg-destructive/15 text-destructive" />
        <StatCard label="Templates"    value={templates.length} icon={Layers} tone="bg-info/15 text-info" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <section className="rounded-xl border border-border bg-card p-5 xl:col-span-2">
          <h2 className="text-sm font-semibold">VM creation activity</h2>
          <p className="text-xs text-muted-foreground">Last 7 days</p>
          <div className="mt-5 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={creationActivity} margin={{ left: -20, right: 8, top: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" stroke="var(--muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="var(--muted-foreground)" fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: "0.5rem", color: "var(--popover-foreground)", fontSize: 12 }} />
                <Line type="monotone" dataKey="created" stroke="var(--primary)" strokeWidth={2.5} dot={{ r: 3, fill: "var(--primary)" }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">Monitoring</h2>
          </div>
          <span className={`mt-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${monitoring ? "border-success/30 bg-success/15 text-success" : "border-destructive/30 bg-destructive/15 text-destructive"}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {monitoring ? "Running" : "Stopped"}
          </span>
          <button onClick={toggleMonitoring} className={`mt-5 flex w-full items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${monitoring ? "bg-destructive/90 text-destructive-foreground hover:bg-destructive" : "bg-primary text-primary-foreground hover:bg-primary/90"}`}>
            {monitoring ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {monitoring ? "Stop monitoring" : "Start monitoring"}
          </button>
        </section>
      </div>

      <section className="mt-6 rounded-xl border border-border bg-card">
        <h2 className="border-b border-border px-5 py-4 text-sm font-semibold">Recent actions</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-5 py-3 text-left font-medium">Timestamp</th>
                <th className="px-5 py-3 text-left font-medium">Action</th>
                <th className="px-5 py-3 text-left font-medium">VM name</th>
                <th className="px-5 py-3 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {history.map((a: any) => (
                <tr key={a.id || a.timestamp} className="border-b border-border/60 last:border-0 hover:bg-accent/40">
                  <td className="px-5 py-3 font-mono text-xs text-muted-foreground">{a.timestamp}</td>
                  <td className="px-5 py-3 capitalize">{a.action || a.tool_name}</td>
                  <td className="px-5 py-3 font-mono text-xs">{a.vm || JSON.parse(a.arguments || "{}").vm_name || "-"}</td>
                  <td className="px-5 py-3"><ResultBadge status={a.status || (a.succes ? "success" : "failed")} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </AppShell>
  );
}
