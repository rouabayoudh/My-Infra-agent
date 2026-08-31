import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Play, Square, Camera, Trash2, Plus, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/infra/AppShell";
import { StatusBadge } from "@/components/infra/StatusBadge";
import { defaultTemplate, templates as mockTemplates } from "@/data/mock";
import { fetchVMs, fetchTemplates, createVM, deleteVM, startVM, stopVM, snapshotVM } from "@/lib/api";

export const Route = createFileRoute("/vms")({
  component: VmsPage,
});

function VmsPage() {
  const [list, setList]           = useState<any[]>([]);
  const [templates, setTemplates] = useState<string[]>(mockTemplates);
  const [loading, setLoading]     = useState(true);
  const [toDelete, setToDelete]   = useState<any | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "", template: defaultTemplate, environment: "dev", role: "web", index: 1,
  });

  const loadData = async () => {
    setLoading(true);
    try {
      const [vmsRes, tplRes] = await Promise.all([fetchVMs(), fetchTemplates()]);
      if (vmsRes.vms) setList(vmsRes.vms);
      if (tplRes.templates) setTemplates(tplRes.templates.map((t: any) => t.name));
    } catch {}
    setLoading(false);
  };

  useEffect(() => { loadData(); }, []);

  const handleStart = async (vm: any) => {
    setActionLoading(vm.name + "-start");
    await startVM(vm.name).catch(() => {});
    await loadData();
    setActionLoading(null);
  };

  const handleStop = async (vm: any) => {
    setActionLoading(vm.name + "-stop");
    await stopVM(vm.name).catch(() => {});
    await loadData();
    setActionLoading(null);
  };

  const handleSnapshot = async (vm: any) => {
    setActionLoading(vm.name + "-snapshot");
    await snapshotVM(vm.name).catch(() => {});
    setActionLoading(null);
    alert(`Snapshot created for ${vm.name}`);
  };

  const handleDelete = async () => {
    if (!toDelete) return;
    setActionLoading(toDelete.name + "-delete");
    await deleteVM(toDelete.name).catch(() => {});
    setToDelete(null);
    await loadData();
    setActionLoading(null);
  };

  const handleCreate = async () => {
    const name = form.name || `srv-${form.environment}-${form.role}-${String(form.index).padStart(2, "0")}`;
    setActionLoading("create");
    await createVM(name, form.template).catch(() => {});
    setCreateOpen(false);
    setForm({ name: "", template: defaultTemplate, environment: "dev", role: "web", index: 1 });
    await loadData();
    setActionLoading(null);
  };

  return (
    <AppShell
      title="Virtual Machines"
      description={`${list.length} managed VMs`}
      actions={
        <div className="flex gap-2">
          <button onClick={loadData} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <button onClick={() => setCreateOpen(true)} className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Plus className="h-4 w-4" /> Create VM
          </button>
        </div>
      }
    >
      {loading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">Loading VMs...</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-5 py-3 text-left font-medium">Name</th>
                <th className="px-5 py-3 text-left font-medium">Status</th>
                <th className="px-5 py-3 text-left font-medium">Template</th>
                <th className="px-5 py-3 text-left font-medium">Created at</th>
                <th className="px-5 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <tr><td colSpan={5} className="px-5 py-10 text-center text-muted-foreground">No VMs found. Create one to get started.</td></tr>
              ) : list.map((vm) => (
                <tr key={vm.name} className="border-b border-border/60 last:border-0 hover:bg-accent/40">
                  <td className="px-5 py-3 font-mono text-xs">{vm.name}</td>
                  <td className="px-5 py-3"><StatusBadge status={vm.status} /></td>
                  <td className="px-5 py-3 text-muted-foreground">{vm.template}</td>
                  <td className="px-5 py-3 font-mono text-xs text-muted-foreground">{vm.created_at || vm.createdAt}</td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-1">
                      <IconAction label="Start" onClick={() => handleStart(vm)} disabled={actionLoading === vm.name + "-start"}>
                        <Play className="h-4 w-4" />
                      </IconAction>
                      <IconAction label="Stop" onClick={() => handleStop(vm)} disabled={actionLoading === vm.name + "-stop"}>
                        <Square className="h-4 w-4" />
                      </IconAction>
                      <IconAction label="Snapshot" onClick={() => handleSnapshot(vm)} disabled={actionLoading === vm.name + "-snapshot"}>
                        <Camera className="h-4 w-4" />
                      </IconAction>
                      <IconAction label="Delete" destructive onClick={() => setToDelete(vm)} disabled={actionLoading === vm.name + "-delete"}>
                        <Trash2 className="h-4 w-4" />
                      </IconAction>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && (
        <Modal title="Create virtual machine" onClose={() => setCreateOpen(false)}>
          <div className="space-y-4">
            <Field label="VM name (optional — auto-generated if empty)">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="srv-dev-web-02"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
            </Field>
            <Field label="Template">
              <select value={form.template} onChange={(e) => setForm({ ...form, template: e.target.value })}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                {templates.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Environment">
                <select value={form.environment} onChange={(e) => setForm({ ...form, environment: e.target.value })}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                  {["dev", "staging", "prod"].map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </Field>
              <Field label="Role">
                <input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
              </Field>
            </div>
            <Field label="Index">
              <input type="number" min={1} value={form.index} onChange={(e) => setForm({ ...form, index: Number(e.target.value) })}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
            </Field>
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <button onClick={() => setCreateOpen(false)} className="rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-accent">Cancel</button>
            <button onClick={handleCreate} disabled={actionLoading === "create"}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {actionLoading === "create" ? "Creating..." : "Create"}
            </button>
          </div>
        </Modal>
      )}

      {toDelete && (
        <Modal title="Delete virtual machine" onClose={() => setToDelete(null)}>
          <p className="text-sm text-muted-foreground">
            This permanently removes <span className="font-mono text-foreground">{toDelete.name}</span>.
            A snapshot will be taken automatically before deletion.
          </p>
          <div className="mt-6 flex justify-end gap-2">
            <button onClick={() => setToDelete(null)} className="rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-accent">Cancel</button>
            <button onClick={handleDelete} disabled={actionLoading === toDelete.name + "-delete"}
              className="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50">
              {actionLoading ? "Deleting..." : "Delete"}
            </button>
          </div>
        </Modal>
      )}
    </AppShell>
  );
}

function IconAction({ label, onClick, destructive, disabled, children }: {
  label: string; onClick: () => void; destructive?: boolean; disabled?: boolean; children: React.ReactNode;
}) {
  return (
    <button title={label} aria-label={label} onClick={onClick} disabled={disabled}
      className={`rounded-md border border-border p-2 transition-colors hover:bg-accent disabled:opacity-40 ${
        destructive ? "text-destructive hover:border-destructive/40" : "text-muted-foreground hover:text-foreground"
      }`}>
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode; }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl">
        <h2 className="text-base font-semibold">{title}</h2>
        <div className="mt-4">{children}</div>
      </div>
      <button className="absolute inset-0 -z-10" aria-label="Close" onClick={onClose} />
    </div>
  );
}
