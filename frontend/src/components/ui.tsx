import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Inbox, Loader2, X } from "lucide-react";
import { api } from "../lib/api";
import { fieldMeta, findingMeta, overallMeta } from "../lib/format";

export function Badge({ tone = "slate", children, className = "" }: { tone?: string; children: ReactNode; className?: string }) {
  return <span className={`badge t-${tone} ${className}`}>{children}</span>;
}

export function OverallBadge({ status }: { status: string }) {
  const m = overallMeta[status] ?? { label: status, tone: "slate" };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

export function FindingBadge({ status }: { status: keyof typeof findingMeta }) {
  const m = findingMeta[status];
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

export function FieldBadge({ status }: { status: string }) {
  const m = fieldMeta[status] ?? { label: status, tone: "slate" };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge sev-${severity}`}>{severity}</span>;
}

export function ProcessingBadge({ status, label }: { status: string; label?: string }) {
  if (status === "PROCESSING") return <Badge tone="blue"><Loader2 size={11} className="spin" /> {label || "Processing"}</Badge>;
  if (status === "FAILED") return <Badge tone="red">Failed</Badge>;
  if (status === "DRAFT") return <Badge tone="slate">Draft</Badge>;
  return null;
}

export function StatCard({ label, value, desc, icon, tone = "blue" }: { label: string; value: ReactNode; desc?: ReactNode; icon?: ReactNode; tone?: string }) {
  return (
    <div className={`card stat ${tone}`}>
      <div className="top"><div className="k">{label}</div>{icon && <div className="ic">{icon}</div>}</div>
      <div className="v">{value}</div>
      {desc && <div className="d">{desc}</div>}
    </div>
  );
}

export function ScoreRing({ value, color = "#1463d8" }: { value: number; color?: string }) {
  const r = 44, c = 2 * Math.PI * r;
  return (
    <div className="score-ring" aria-label={`Score ${value}%`}>
      <svg width="104" height="104">
        <circle cx="52" cy="52" r={r} stroke="#e2e8f0" strokeWidth="9" fill="none" />
        <circle cx="52" cy="52" r={r} stroke={color} strokeWidth="9" fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(100, Math.max(0, value)) / 100)} style={{ transition: "stroke-dashoffset .8s" }} />
      </svg>
      <div className="lbl" style={{ color }}>{value.toFixed(1)}%</div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <div className="loading-page"><div className="row"><Loader2 className="spin" /> {label || "Loading…"}</div></div>;
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return <div className="empty">{icon || <Inbox size={36} />}<h4 style={{ color: "var(--ink-2)", marginBottom: 6 }}>{title}</h4>{children}</div>;
}

export function Alert({ kind = "info", children }: { kind?: "info" | "error" | "warn" | "ok"; children: ReactNode }) {
  const Icon = kind === "ok" ? CheckCircle2 : AlertCircle;
  return <div className={`alert alert-${kind}`}><Icon size={16} /><div>{children}</div></div>;
}

export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="card-head"><h3 className="grow">{title}</h3><button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
        <div className="card-pad">{children}</div>
        {footer && <div className="card-pad row" style={{ justifyContent: "flex-end", borderTop: "1px solid var(--line)" }}>{footer}</div>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- toasts */
type Toast = { id: number; text: string; err?: boolean };
const ToastCtx = createContext<(text: string, err?: boolean) => void>(() => undefined);
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, err = false) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, text, err }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.err ? "err" : ""}`}>
            {t.err ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />} {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------------------------------------------------------------- authorised image loading */
const blobCache = new Map<string, string>();

export function useAuthImage(path: string | null) {
  const [src, setSrc] = useState<string | null>(path ? blobCache.get(path) ?? null : null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!path) return;
    if (blobCache.has(path)) { setSrc(blobCache.get(path)!); return; }
    let alive = true;
    api.blob(path).then((b) => {
      const url = URL.createObjectURL(b);
      blobCache.set(path, url);
      if (alive) setSrc(url);
    }).catch(() => alive && setError(true));
    return () => { alive = false; };
  }, [path]);
  return { src, error };
}

export function AuthImage({ path, alt, className, style, onLoad }: { path: string; alt: string; className?: string; style?: React.CSSProperties; onLoad?: (e: React.SyntheticEvent<HTMLImageElement>) => void }) {
  const { src, error } = useAuthImage(path);
  if (error) return <div className="muted small">Image unavailable</div>;
  if (!src) return <Loader2 className="spin" color="#94a3b8" />;
  return <img src={src} alt={alt} className={className} style={style} onLoad={onLoad} />;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const run = useCallback(() => {
    setLoading(true);
    return fn().then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message)).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { data, error, loading, reload: run, setData };
}
