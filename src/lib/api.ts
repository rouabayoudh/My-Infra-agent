const BASE_URL = "http://localhost:8000/api";

export async function fetchVMs() {
  const res = await fetch(`${BASE_URL}/vms`);
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${BASE_URL}/stats`);
  return res.json();
}

export async function fetchTemplates() {
  const res = await fetch(`${BASE_URL}/templates`);
  return res.json();
}

export async function fetchHistory(limit = 50) {
  const res = await fetch(`${BASE_URL}/history?limit=${limit}`);
  return res.json();
}

export async function fetchLogs(level?: string, source?: string, limit = 50) {
  const params = new URLSearchParams();
  if (level) params.append("level", level);
  if (source) params.append("source", source);
  params.append("limit", String(limit));
  const res = await fetch(`${BASE_URL}/logs?${params}`);
  return res.json();
}

export async function createVM(vm_name: string, template_id: string) {
  const res = await fetch(`${BASE_URL}/vms`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vm_name, template_id }),
  });
  return res.json();
}

export async function deleteVM(vm_name: string) {
  const res = await fetch(`${BASE_URL}/vms/${vm_name}`, { method: "DELETE" });
  return res.json();
}

export async function startVM(vm_name: string) {
  const res = await fetch(`${BASE_URL}/vms/${vm_name}/start`, { method: "POST" });
  return res.json();
}

export async function stopVM(vm_name: string) {
  const res = await fetch(`${BASE_URL}/vms/${vm_name}/stop`, { method: "POST" });
  return res.json();
}

export async function snapshotVM(vm_name: string, snapshot_name?: string) {
  const res = await fetch(`${BASE_URL}/vms/${vm_name}/snapshot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snapshot_name: snapshot_name || "" }),
  });
  return res.json();
}

export async function sendChat(message: string) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return res.json();
}

export async function fetchMonitoringStatus() {
  const res = await fetch(`${BASE_URL}/monitoring`);
  return res.json();
}

export async function startMonitoring() {
  const res = await fetch(`${BASE_URL}/monitoring/start`, { method: "POST" });
  return res.json();
}

export async function stopMonitoring() {
  const res = await fetch(`${BASE_URL}/monitoring/stop`, { method: "POST" });
  return res.json();
}
