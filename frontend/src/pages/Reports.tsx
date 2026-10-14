import { useNavigate } from "react-router-dom";
import { Download, FileSpreadsheet, FileText, FileType2 } from "lucide-react";
import { api, downloadFile } from "../lib/api";
import { fmtDate } from "../lib/format";
import type { InspectionSummary } from "../lib/types";
import { Alert, Empty, OverallBadge, Spinner, useAsync, useToast } from "../components/ui";

interface Summary {
  completed: number;
  by_rule: { rule_no: string; non_compliant: number; needs_verification: number }[];
  by_category: { category: string; label: string; inspections: number; non_compliant: number }[];
  recent_completed: InspectionSummary[];
}

export default function Reports() {
  const nav = useNavigate();
  const toast = useToast();
  const { data, error, loading } = useAsync(() => api.get<Summary>("/api/reports/summary"), []);
  if (loading && !data) return <Spinner />;
  if (error || !data) return <Alert kind="error">{error}</Alert>;
  const max = Math.max(1, ...data.by_rule.map((r) => r.non_compliant + r.needs_verification));
  const dl = (id: number, ref: string, ext: string) => downloadFile(`/api/inspections/${id}/report.${ext}`, `${ref}_report.${ext}`).catch((e) => toast(e.message, true));

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="grid g2">
        <div className="card">
          <div className="card-head"><div className="grow"><h3>Violation summary by rule</h3><p>Across {data.completed} analysed inspection(s)</p></div></div>
          <div className="card-pad">
            {data.by_rule.length === 0 ? <Empty title="No findings yet" /> : <div className="bars">
              {data.by_rule.map((r) => (
                <div className="hbar" key={r.rule_no}><span><b className="mono">{r.rule_no.startsWith("S") ? "Sec 18" : `Rule ${r.rule_no}`}</b></span>
                  <div className="track" style={{ display: "flex" }}>
                    <div className="fill" style={{ width: `${(r.non_compliant / max) * 100}%`, background: "var(--red)", borderRadius: 0 }} />
                    <div className="fill" style={{ width: `${(r.needs_verification / max) * 100}%`, background: "#f59e0b", borderRadius: 0 }} /></div>
                  <span className="tiny"><b style={{ color: "var(--red)" }}>{r.non_compliant}</b>/<b style={{ color: "#b45309" }}>{r.needs_verification}</b></span></div>))}
              <div className="tiny muted"><span style={{ color: "var(--red)" }}>■</span> non-compliant &nbsp; <span style={{ color: "#f59e0b" }}>■</span> needs verification</div>
            </div>}
          </div>
        </div>
        <div className="card">
          <div className="card-head"><div className="grow"><h3>Category compliance</h3><p>Inspections with violations per commodity category</p></div></div>
          <div className="table-wrap"><table className="tbl"><thead><tr><th>Category</th><th>Inspections</th><th>With violations</th><th>Rate</th></tr></thead>
            <tbody>{data.by_category.map((c) => <tr key={c.category}><td className="strong">{c.label}</td><td>{c.inspections}</td><td>{c.non_compliant}</td>
              <td>{c.inspections ? Math.round((c.non_compliant / c.inspections) * 100) : 0}%</td></tr>)}</tbody></table></div>
        </div>
      </div>
      <div className="card">
        <div className="card-head"><div className="grow"><h3>Inspection reports</h3><p>Download statutory reports as PDF, or in editable Word / Excel formats. Export the full register as CSV from Inspection History.</p></div>
          <button className="btn btn-outline btn-sm" onClick={() => downloadFile("/api/inspections/export.csv", "safemetric_inspections.csv").catch((e) => toast(e.message, true))}><Download size={14} /> Export register (CSV)</button></div>
        {data.recent_completed.length === 0 ? <Empty title="No completed inspections yet" /> : (
          <div className="table-wrap"><table className="tbl"><thead><tr><th>Reference</th><th>Product</th><th>Status</th><th>Score</th><th>Analysed</th><th>Download</th></tr></thead>
            <tbody>{data.recent_completed.map((r) => (
              <tr key={r.id}><td className="mono strong"><a onClick={() => nav(`/app/inspections/${r.id}`)} style={{ cursor: "pointer" }}>{r.reference}</a></td>
                <td>{r.product_name}<div className="tiny muted">{r.category_label}</div></td><td><OverallBadge status={r.overall_status} /></td><td>{r.score}%</td>
                <td className="small">{fmtDate(r.analyzed_at)}</td>
                <td><div className="row" style={{ gap: 6 }}>
                  <button className="btn btn-outline btn-sm" onClick={() => dl(r.id, r.reference, "pdf")}><FileText size={14} /> PDF</button>
                  <button className="btn btn-outline btn-sm" onClick={() => dl(r.id, r.reference, "docx")}><FileType2 size={14} /> DOCX</button>
                  <button className="btn btn-outline btn-sm" onClick={() => dl(r.id, r.reference, "xlsx")}><FileSpreadsheet size={14} /> XLSX</button></div></td></tr>))}</tbody></table></div>
        )}
      </div>
    </div>
  );
}
