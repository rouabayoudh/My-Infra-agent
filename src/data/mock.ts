export type VmStatus = "PoweredOn" | "PoweredOff" | "NotFound";

export type Vm = {
  id: string;
  name: string;
  status: VmStatus;
  template: string;
  createdAt: string;
  environment: string;
  role: string;
};

export const templates: string[] = ["ubuntu-22.04"];
export const defaultTemplate = "ubuntu-22.04";

export const vms: Vm[] = [
  {
    id: "vm-1",
    name: "srv-dev-web-01",
    status: "PoweredOn",
    template: "ubuntu-22.04",
    createdAt: "2026-08-14 09:12",
    environment: "dev",
    role: "web",
  },
  {
    id: "vm-2",
    name: "srv-dev-api-01",
    status: "PoweredOn",
    template: "ubuntu-22.04",
    createdAt: "2026-08-15 14:38",
    environment: "dev",
    role: "api",
  },
  {
    id: "vm-3",
    name: "srv-dev-db-01",
    status: "PoweredOff",
    template: "ubuntu-22.04",
    createdAt: "2026-08-16 08:04",
    environment: "dev",
    role: "db",
  },
];

export type ActionType = "create" | "delete" | "snapshot" | "start" | "stop";

export type AgentAction = {
  id: string;
  timestamp: string;
  action: ActionType;
  vm: string;
  status: "success" | "failed";
};

export const recentActions: AgentAction[] = [
  { id: "a1", timestamp: "2026-08-20 10:42", action: "create", vm: "srv-dev-web-01", status: "success" },
  { id: "a2", timestamp: "2026-08-20 09:31", action: "snapshot", vm: "srv-dev-web-01", status: "success" },
  { id: "a3", timestamp: "2026-08-19 18:07", action: "delete", vm: "srv-dev-db-01", status: "success" },
  { id: "a4", timestamp: "2026-08-19 16:55", action: "start", vm: "srv-dev-api-01", status: "success" },
  { id: "a5", timestamp: "2026-08-19 11:20", action: "stop", vm: "srv-dev-db-01", status: "failed" },
];

export const creationActivity = [
  { day: "Aug 14", created: 2 },
  { day: "Aug 15", created: 4 },
  { day: "Aug 16", created: 1 },
  { day: "Aug 17", created: 5 },
  { day: "Aug 18", created: 3 },
  { day: "Aug 19", created: 6 },
  { day: "Aug 20", created: 4 },
];

export type LogLevel = "INFO" | "WARN" | "ERROR";

export type LogEntry = {
  id: string;
  timestamp: string;
  level: LogLevel;
  source: string;
  message: string;
};

export const logs: LogEntry[] = [
  { id: "l1", timestamp: "2026-08-20 10:42:11", level: "INFO", source: "vsphere", message: "Cloned ubuntu-22.04 -> srv-dev-web-01" },
  { id: "l2", timestamp: "2026-08-20 10:42:44", level: "INFO", source: "agent", message: "Customization spec applied to srv-dev-web-01" },
  { id: "l3", timestamp: "2026-08-20 09:31:02", level: "WARN", source: "monitoring", message: "Datastore ds-01 at 82% capacity" },
  { id: "l4", timestamp: "2026-08-19 18:07:31", level: "INFO", source: "vsphere", message: "Snapshot pre-upgrade created on srv-dev-web-01" },
  { id: "l5", timestamp: "2026-08-19 16:55:12", level: "ERROR", source: "agent", message: "Power-off task on srv-dev-db-01 timed out after 120s" },
  { id: "l6", timestamp: "2026-08-19 11:20:57", level: "ERROR", source: "vsphere", message: "Guest tools not responding on srv-dev-db-01" },
  { id: "l7", timestamp: "2026-08-18 15:03:19", level: "INFO", source: "api", message: "Template inventory refreshed (1 template)" },
  { id: "l8", timestamp: "2026-08-18 08:44:05", level: "WARN", source: "agent", message: "Retrying vCenter session, attempt 2/3" },
];