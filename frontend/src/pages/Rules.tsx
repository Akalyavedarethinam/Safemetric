import { useState } from "react";
import { Info } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Alert, Badge, Modal, Spinner, useAsync, useToast } from "../components/ui";

interface Check {
  check_id: string; rule_no: string; rule_title: string; rule_group_title: string; title: string; reference: string; severity: string;
  applicability: string; required_data: string[]; condition: string; verification: string; active: boolean;
}
interface RulesResp {
  checks: Check[]; scoring: { description: string }; overall_status_rules: string[]; severity_weights: Record<string, number>;
  categories: { key: string; label: string; config: { quantity_basis: string[]; best_before_required: boolean; unit_sale_price_applicable: boolean; additional_declarations: { title: string; source: string }[]; notes?: string } }[];
}

export default function Rules() {
  const { user } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useAsync(() => api.get<RulesResp>("/api/rules"), []);
  const [sel, setSel] = useState<Check | null>(null);
  if (loading && !data) return <Spinner />;
  if (error || !data) return <Alert kind="error">{error}</Alert>;
  const isAdmin = user?.role === "admin";
  const groups = [...new Set(data.checks.map((c) => `${c.rule_no}|${c.rule_group_title}`))];

  const toggle = async (c: Check) => {
    try { await api.put(`/api/rules/${c.check_id}`, { active: !c.active }); toast(`${c.check_id} ${c.active ? "deactivated" : "activated"}.`); reload(); }
    catch (e) { toast((e as Error).message, true); }
  };

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Alert kind="info">Compliance decisions are made by these explicit rules only. Each check returns <b>Pass</b>, <b>Non-Compliant</b>, <b>Needs Verification</b> or <b>Not Applicable</b>. {isAdmin ? "As administrator you can deactivate a check; deactivated checks are reported as Not Applicable with that reason." : ""}</Alert>
      <div className="grid g2">
        <div className="card card-pad"><h3 style={{ fontSize: 15 }}>Overall status logic</h3>
          <ol className="small" style={{ paddingLeft: 18 }}>{data.overall_status_rules.map((r) => <li key={r} className="mono">{r}</li>)}</ol></div>
        <div className="card card-pad"><h3 style={{ fontSize: 15 }}>Score</h3><p className="small">{data.scoring.description}</p>
          <div className="row">{Object.entries(data.severity_weights).map(([k, v]) => <span key={k} className={`badge sev-${k}`}>{k} = {v}</span>)}</div></div>
      </div>
      <div className="card">
        <div className="card-head"><div className="grow"><h3>Statutory rule catalogue</h3><p>{data.checks.length} checks · click a check for its full specification</p></div></div>
        <div className="card-pad">
          {groups.map((g) => {
            const [no, title] = g.split("|");
            return (
              <div key={g} style={{ marginBottom: 16 }}>
                <h4 style={{ margin: "4px 0 10px", fontSize: 14 }}><span className="mono" style={{ color: "var(--blue)" }}>{no.startsWith("S") ? "Section 18" : `Rule ${no}`}</span> — {title}</h4>
                {data.checks.filter((c) => c.rule_no === no && c.rule_group_title === title).map((c) => (
                  <div key={c.check_id} className="rule-row">
                    <span className="t" style={{ cursor: "pointer" }} onClick={() => setSel(c)}>{no.startsWith("S") ? "Section 18" : `Rule ${no}`} — {c.title} <Info size={13} style={{ opacity: .6 }} /></span>
                    <span className={`badge sev-${c.severity}`}>{c.severity}</span>
                    {isAdmin ? <button className={`badge ${c.active ? "on" : "off"}`} style={{ cursor: "pointer" }} onClick={() => toggle(c)}>{c.active ? "ACTIVE" : "INACTIVE"}</button>
                      : <span className={`badge ${c.active ? "on" : "off"}`}>{c.active ? "ACTIVE" : "INACTIVE"}</span>}
                    <span className="desc">{c.check_id} · {c.applicability}</span>
                  </div>))}
              </div>);
          })}
        </div>
      </div>
      <div className="card">
        <div className="card-head"><div className="grow"><h3>Commodity category configuration</h3><p>Loaded from <span className="mono">backend/app/rules/config/&lt;category&gt;_rules.json</span> - add a file to support a new category.</p></div></div>
        <div className="table-wrap"><table className="tbl"><thead><tr><th>Category</th><th>Quantity basis (Rule 13)</th><th>Best before</th><th>Unit sale price</th><th>Additional declarations (Rule 15)</th></tr></thead>
          <tbody>{data.categories.map((c) => <tr key={c.key}><td className="strong">{c.label}</td><td>{c.config.quantity_basis.join(", ") || <span className="muted">not configured</span>}</td>
            <td>{c.config.best_before_required ? <Badge tone="green">Required</Badge> : "—"}</td><td>{c.config.unit_sale_price_applicable ? <Badge tone="green">Applicable</Badge> : "—"}</td>
            <td className="small">{c.config.additional_declarations.map((a) => a.title).join("; ") || "—"}{c.config.notes && <div className="tiny muted">{c.config.notes}</div>}</td></tr>)}</tbody></table></div>
      </div>
      {sel && <Modal title={`${sel.check_id} — ${sel.title}`} onClose={() => setSel(null)}>
        <dl className="kv" style={{ marginTop: 0 }}>
          <dt>Rule</dt><dd>{sel.rule_no} — {sel.rule_group_title}</dd><dt>Severity</dt><dd><span className={`badge sev-${sel.severity}`}>{sel.severity}</span></dd>
          <dt>Applicability</dt><dd>{sel.applicability}</dd><dt>Required data</dt><dd>{sel.required_data.join(", ")}</dd>
          <dt>Validation condition</dt><dd>{sel.condition}</dd>{sel.verification && <><dt>Verification</dt><dd>{sel.verification}</dd></>}
          <dt>Reference</dt><dd className="small">{sel.reference}</dd>
        </dl></Modal>}
    </div>
  );
}
