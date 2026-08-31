import type { VmStatus } from "@/data/mock";

const styles: Record<VmStatus, string> = {
  PoweredOn: "bg-success/15 text-success border-success/30",
  PoweredOff: "bg-destructive/15 text-destructive border-destructive/30",
  NotFound: "bg-neutral/15 text-neutral border-neutral/30",
};

export function StatusBadge({ status }: { status: VmStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}

export function ResultBadge({ status }: { status: "success" | "failed" }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        status === "success"
          ? "bg-success/15 text-success border-success/30"
          : "bg-destructive/15 text-destructive border-destructive/30"
      }`}
    >
      {status}
    </span>
  );
}