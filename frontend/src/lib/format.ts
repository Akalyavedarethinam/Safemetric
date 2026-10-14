import type { FindingStatus, OverallStatus } from "./types";

export const fmtDate = (s?: string | null, withTime = true) => {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", withTime
    ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "short", year: "numeric" });
};

export const fmtBytes = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${(n / 1024).toFixed(1)} KB`);

export const overallMeta: Record<string, { label: string; tone: string }> = {
  COMPLIANT: { label: "Compliant", tone: "green" },
  NON_COMPLIANT: { label: "Non-Compliant", tone: "red" },
  PARTIALLY_COMPLIANT: { label: "Partially Compliant", tone: "orange" },
  NEEDS_VERIFICATION: { label: "Needs Verification", tone: "amber" },
  "": { label: "Pending", tone: "slate" },
};

export const findingMeta: Record<FindingStatus, { label: string; tone: string }> = {
  PASS: { label: "Pass", tone: "green" },
  NON_COMPLIANT: { label: "Non-Compliant", tone: "red" },
  NEEDS_VERIFICATION: { label: "Needs Verification", tone: "amber" },
  NOT_APPLICABLE: { label: "Not Applicable", tone: "slate" },
};

export const fieldMeta: Record<string, { label: string; tone: string }> = {
  DETECTED: { label: "Detected", tone: "green" },
  LOW_CONFIDENCE: { label: "Low confidence", tone: "amber" },
  NEEDS_VERIFICATION: { label: "Needs verification", tone: "amber" },
  NOT_DETECTED: { label: "Not detected", tone: "red" },
};

export const overallLabel = (s: OverallStatus | string) => overallMeta[s]?.label ?? s;

export const SIDE_LABELS: Record<string, string> = {
  front: "Front (PDP)", back: "Back", left: "Left", right: "Right", top: "Top", bottom: "Bottom", additional: "Additional",
};

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
