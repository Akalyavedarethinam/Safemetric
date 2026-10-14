import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp, Download, Search, SearchX } from "lucide-react";
import { api, downloadFile } from "../lib/api";
import { fmtDate } from "../lib/format";
import type { InspectionSummary, Meta } from "../lib/types";
import { Alert, Empty, OverallBadge, ProcessingBadge, Spinner, useAsync, useToast } from "../components/ui";

interface Page { items: InspectionSummary[]; total: number; page: number; page_size: number }
const COLS: [string, string][] = [["reference", "Inspection ID"], ["product_name", "Product"], ["brand", "Brand"], ["category", "Category"],
  ["overall_status", "Overall status"], ["score", "Score"], ["inspector_name", "Inspector"], ["created_at", "Date / time"]];

export default function History() {
  const nav = useNavigate();
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const { data: meta } = useAsync(() => api.get<Meta>("/api/meta"), []);
  const [q, setQ] = useState(sp.get("q") || "");
  const params = {
    q: sp.get("q") || "", status: sp.get("status") || "", category: sp.get("category") || "", date_from: sp.get("from") || "",
    date_to: sp.get("to") || "", mine: sp.get("mine") || "", sort: sp.get("sort") || "created_at", order: sp.get("order") || "desc",
    page: Number(sp.get("page") || 1),
  };
  const qs = new URLSearchParams({ q: params.q, status: params.status, category: params.category, date_from: params.date_from,
    date_to: params.date_to, sort: params.sort, order: params.order, page: String(params.page), page_size: "15", ...(params.mine ? { mine: "true" } : {}) }).toString();
  const { data, error, loading } = useAsync(() => api.get<Page>(`/api/inspections?${qs}`), [qs]);
  useEffect(() => { const t = setTimeout(() => { if (q !== params.q) update({ q, page: "1" }); }, 350); return () => clearTimeout(t); }, [q]); // eslint-disable-line

  const update = (patch: Record<string, string>) => {
    const n = new URLSearchParams(sp);
    Object.entries(patch).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)));
    setSp(n, { replace: true });
  };
  const sortBy = (col: string) => update({ sort: col, order: params.sort === col && params.order === "desc" ? "asc" : "desc" });
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="stack">
      <div className="card card-pad grid filters">
        <div className="field"><label>Search</label><div className="input-icon"><Search size={16} /><input className="input" placeholder="Reference, product, brand, manufacturer, inspector, location" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
        <div className="field"><label>Status</label><select className="select" value={params.status} onChange={(e) => update({ status: e.target.value, page: "1" })}>
          <option value="">All</option><option value="COMPLIANT">Compliant</option><option value="PARTIALLY_COMPLIANT">Partially compliant</option>
          <option value="NON_COMPLIANT">Non-compliant</option><option value="NEEDS_VERIFICATION">Needs verification</option></select></div>
        <div className="field"><label>Category</label><select className="select" value={params.category} onChange={(e) => update({ category: e.target.value, page: "1" })}>
          <option value="">All</option>{meta?.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select></div>
        <div className="field"><label>From</label><input className="input" type="date" value={params.date_from} onChange={(e) => update({ from: e.target.value, page: "1" })} /></div>
        <div className="field"><label>To</label><input className="input" type="date" value={params.date_to} onChange={(e) => update({ to: e.target.value, page: "1" })} /></div>
        <div className="row" style={{ paddingBottom: 2 }}>
          <label className="check small"><input type="checkbox" checked={!!params.mine} onChange={(e) => update({ mine: e.target.checked ? "1" : "", page: "1" })} /> Mine</label>
          <button className="btn btn-outline btn-sm" title="Export CSV" onClick={() => downloadFile(`/api/inspections/export.csv?q=${encodeURIComponent(params.q)}&status=${params.status}&category=${params.category}`, "safemetric_inspections.csv").catch((e) => toast(e.message, true))}><Download size={14} /> CSV</button>
        </div>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="card">
        <div className="card-head"><div className="grow"><h3>Inspection repository</h3><p>{data ? `${data.total} record(s)` : "…"} · click a row to open the complete record</p></div></div>
        {loading && !data ? <Spinner /> : data && data.items.length === 0 ? <Empty title="No inspections match" icon={<SearchX size={36} />}>Try clearing the filters.</Empty> : (
          <div className="table-wrap"><table className="tbl">
            <thead><tr>{COLS.map(([k, l]) => (
              <th key={k} className="sortable" onClick={() => sortBy(k)}>{l} {params.sort === k && (params.order === "desc" ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}</th>))}
              <th>Images</th></tr></thead>
            <tbody>{data?.items.map((r) => (
              <tr key={r.id} className="click" onClick={() => nav(`/app/inspections/${r.id}`)}>
                <td className="mono strong">{r.reference}</td><td className="strong">{r.product_name || "—"}{r.manufacturer && <div className="tiny muted" style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.manufacturer}</div>}</td>
                <td>{r.brand || "—"}</td><td>{r.category_label}{r.is_imported && <div className="tiny muted">Imported</div>}</td>
                <td>{r.status === "COMPLETED" ? <OverallBadge status={r.overall_status} /> : <ProcessingBadge status={r.status} label={r.stage_label} />}</td>
                <td>{r.status === "COMPLETED" ? <b>{r.score}%</b> : "—"}</td><td>{r.inspector_name}</td>
                <td className="small">{fmtDate(r.inspection_datetime || r.created_at)}</td><td>{r.image_count}</td>
              </tr>))}</tbody>
          </table></div>
        )}
        <div className="pager">
          <span className="small muted">Page {params.page} of {pages}</span>
          <button className="btn btn-outline btn-sm" disabled={params.page <= 1} onClick={() => update({ page: String(params.page - 1) })}>Previous</button>
          <button className="btn btn-outline btn-sm" disabled={params.page >= pages} onClick={() => update({ page: String(params.page + 1) })}>Next</button>
        </div>
      </div>
    </div>
  );
}
