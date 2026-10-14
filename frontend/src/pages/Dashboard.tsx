import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Clock, Layers, ScanLine, Sparkles, TrendingUp, XCircle } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDate } from "../lib/format";
import type { InspectionSummary } from "../lib/types";
import { Alert, Empty, OverallBadge, ProcessingBadge, Spinner, StatCard, useAsync } from "../components/ui";

interface Dash {
  total: number; completed: number; processing: number; mine: number; compliant: number; non_compliant: number;
  partially_compliant: number; needs_verification: number; pass_rate: number; average_score: number;
  by_category: { category: string; label: string; count: number }[];
  trend: { date: string; total: number; non_compliant: number }[];
  top_violations: { check_id: string; title: string; rule_no: string; count: number }[];
  recent: InspectionSummary[];
}

export default function Dashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { data: d, error, loading } = useAsync(() => api.get<Dash>("/api/dashboard"), []);
  if (loading && !d) return <Spinner />;
  if (error || !d) return <Alert kind="error">{error}</Alert>;
  const greet = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 17 ? "Good afternoon" : "Good evening";
  const maxTrend = Math.max(1, ...d.trend.map((t) => t.total));
  const maxViol = Math.max(1, ...d.top_violations.map((v) => v.count));
  const maxCat = Math.max(1, ...d.by_category.map((v) => v.count));

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="card hero-card">
        <div>
          <div className="row"><span className="eyebrow">Statutory inspection portal</span><span className="chip">Official mode</span></div>
          <h2>{greet}, {user?.name.split(" ")[0]}</h2>
          <p>SafeMetric automated regulatory compliance engine under the <b>Legal Metrology (Packaged Commodities) Rules, 2011</b>.</p>
        </div>
        <button className="btn btn-primary" style={{ padding: "14px 22px" }} onClick={() => nav("/app/inspections/new")}><ScanLine size={18} /> SCAN PRODUCT</button>
      </div>

      <div className="grid g5">
        <StatCard label="Total inspections" value={d.total} icon={<Layers size={18} />} desc={<><Clock size={12} /> {d.processing} processing · {d.mine} by you</>} tone="blue" />
        <StatCard label="Compliant" value={d.compliant} icon={<CheckCircle2 size={18} />} desc={`${d.pass_rate}% pass rate`} tone="green" />
        <StatCard label="Partially compliant" value={d.partially_compliant} icon={<Sparkles size={18} />} desc="Minor non-critical deviations" tone="orange" />
        <StatCard label="Non-compliant" value={d.non_compliant} icon={<XCircle size={18} />} desc="Statutory violations detected" tone="red" />
        <StatCard label="Needs verification" value={d.needs_verification} icon={<AlertTriangle size={18} />} desc="Requires physical audit" tone="amber" />
      </div>

      <div className="grid g3">
        <StatCard label="Average score" value={`${d.average_score}%`} icon={<TrendingUp size={18} />} desc="Across all analysed labels" tone="violet" />
        <div className="card card-pad span2">
          <div className="row" style={{ justifyContent: "space-between" }}><h3 style={{ fontSize: 15 }}>Inspections - last 14 days</h3>
            <span className="tiny muted"><span className="sw" style={{ display: "inline-block", width: 10, height: 10, background: "#bcd5fb", borderRadius: 3 }} /> total &nbsp; <span style={{ display: "inline-block", width: 10, height: 10, background: "var(--red)", borderRadius: 3 }} /> violations</span></div>
          <div className="cols">
            {d.trend.map((t) => (
              <div className="c" key={t.date} title={`${t.date}: ${t.total} inspections, ${t.non_compliant} with violations`}>
                <div className="b" style={{ height: `${(t.total / maxTrend) * 100}%` }}><div className="nc" style={{ height: t.total ? `${(t.non_compliant / t.total) * 100}%` : 0 }} /></div>
                <span>{t.date.slice(8)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <div className="card-head"><div className="grow"><h3>Most frequent violations</h3><p>Non-compliant checks across all inspections</p></div></div>
          <div className="card-pad">
            {d.top_violations.length === 0 ? <Empty title="No violations recorded yet" /> : (
              <div className="bars">{d.top_violations.map((v) => (
                <div className="hbar" key={v.check_id}><span title={v.check_id}><b className="mono" style={{ color: "var(--blue)" }}>{v.rule_no}</b> {v.title}</span>
                  <div className="track"><div className="fill" style={{ width: `${(v.count / maxViol) * 100}%`, background: "var(--red)" }} /></div><b>{v.count}</b></div>
              ))}</div>
            )}
          </div>
        </div>
        <div className="card">
          <div className="card-head"><div className="grow"><h3>Inspections by category</h3><p>Commodity mix in the repository</p></div></div>
          <div className="card-pad">
            {d.by_category.length === 0 ? <Empty title="No inspections yet" /> : (
              <div className="bars">{d.by_category.map((c) => (
                <div className="hbar" key={c.category}><span>{c.label}</span><div className="track"><div className="fill" style={{ width: `${(c.count / maxCat) * 100}%` }} /></div><b>{c.count}</b></div>
              ))}</div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head"><div className="grow"><h3>Recent inspections</h3><p>Latest activity across the department</p></div>
          <button className="btn btn-outline btn-sm" onClick={() => nav("/app/inspections")}>View all history</button></div>
        {d.recent.length === 0 ? <Empty title="No inspections yet"><p>Start by scanning a packaged product.</p></Empty> : (
          <div className="table-wrap"><table className="tbl">
            <thead><tr><th>Reference</th><th>Product</th><th>Category</th><th>Status</th><th>Score</th><th>Inspector</th><th>Date</th></tr></thead>
            <tbody>{d.recent.map((r) => (
              <tr key={r.id} className="click" onClick={() => nav(`/app/inspections/${r.id}`)}>
                <td className="mono strong">{r.reference}</td><td><b>{r.product_name || "—"}</b><div className="tiny muted">{r.brand}</div></td>
                <td>{r.category_label}</td>
                <td>{r.status === "COMPLETED" ? <OverallBadge status={r.overall_status} /> : <ProcessingBadge status={r.status} label={r.stage_label} />}</td>
                <td>{r.status === "COMPLETED" ? `${r.score}%` : "—"}</td><td>{r.inspector_name}</td><td className="small">{fmtDate(r.created_at)}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}
