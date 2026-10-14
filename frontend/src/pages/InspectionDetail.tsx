import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, Calculator, Camera, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Copy, FileSpreadsheet, FileText, FileType2, Image as ImageIcon, Loader2, Paperclip, RefreshCcw, ScanText, ShieldAlert, Sparkles, Trash2, XCircle } from "lucide-react";
import { api, downloadFile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { SIDE_LABELS, findingMeta, fmtBytes, fmtDate, overallMeta } from "../lib/format";
import type { Finding, FindingStatus, InspectionDetail as Detail } from "../lib/types";
import EvidenceViewer from "../components/EvidenceViewer";
import { Alert, AuthImage, Badge, Empty, FieldBadge, FindingBadge, Modal, OverallBadge, ScoreRing, SeverityBadge, Spinner, StatCard, useToast } from "../components/ui";

type Tab = "result" | "fields" | "findings" | "evidence" | "record";
const TONE_COLOR: Record<string, string> = { green: "#16a34a", red: "#dc2626", amber: "#d97706", orange: "#ea580c", slate: "#64748b" };

export default function InspectionDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const toast = useToast();
  const { user } = useAuth();
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<Tab>("result");
  const [highlight, setHighlight] = useState<string | null>(null);
  const [imageId, setImageId] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);
  const timer = useRef<number | null>(null);

  const load = async () => {
    try {
      const r = await api.get<Detail>(`/api/inspections/${id}`);
      setD(r);
      setImageId((cur) => cur ?? r.images[0]?.id ?? null);
      if (r.status === "PROCESSING") timer.current = window.setTimeout(load, 1500);
    } catch (e) { setErr((e as Error).message); }
  };
  useEffect(() => { load(); return () => { if (timer.current) clearTimeout(timer.current); }; }, [id]); // eslint-disable-line
  useEffect(() => { if ((loc.state as { justAnalyzed?: boolean })?.justAnalyzed) toast("Analysis complete - inspection saved."); }, []); // eslint-disable-line

  if (err) return <Alert kind="error">{err}</Alert>;
  if (!d) return <Spinner />;
  const canEdit = user?.role === "admin" || user?.id === d.user_id;

  const openEvidence = (field: string | null, imgId?: number | null) => {
    setHighlight(field);
    if (imgId) setImageId(imgId);
    setTab("evidence");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const reanalyze = async () => {
    setBusy("analyze");
    try { await api.post(`/api/inspections/${d.id}/analyze`); toast("Re-analysis started."); await load(); }
    catch (e) { toast((e as Error).message, true); }
    finally { setBusy(""); }
  };
  const report = async (ext: "pdf" | "docx" | "xlsx") => {
    setBusy(ext);
    try { await downloadFile(`/api/inspections/${d.id}/report.${ext}`, `${d.reference}_report.${ext}`); }
    catch (e) { toast((e as Error).message, true); }
    finally { setBusy(""); }
  };
  const del = async () => {
    try { await api.del(`/api/inspections/${d.id}`); toast("Inspection deleted."); nav("/app/inspections"); }
    catch (e) { toast((e as Error).message, true); }
  };

  const tabs: [Tab, string, number?][] = [
    ["result", "Compliance Result"], ["fields", "Declarations", d.fields.filter((f) => f.status !== "NOT_DETECTED").length],
    ["findings", "Rule Findings", d.findings.length], ["evidence", "Images & Evidence", d.images.length], ["record", "Record & Attachments", d.attachments.length],
  ];

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div className="eyebrow">Record {d.reference}</div>
          <h2 style={{ fontSize: 24, fontWeight: 800 }}>{d.product_name || d.brand || d.summary.structured?.product_name?.value || "Unnamed product"} {d.brand && d.product_name && <span className="muted" style={{ fontWeight: 600 }}>· {d.brand}</span>}
            {!d.product_name && !d.brand && d.summary.structured?.product_name?.found && <span className="muted small" style={{ fontWeight: 600 }}> · read from label{d.summary.structured?.brand_name?.found ? ` (${d.summary.structured.brand_name.value})` : ""}</span>}</h2>
          <div className="row small muted" style={{ marginTop: 4 }}>
            <Badge tone="blue">{d.category_label}</Badge>{d.is_imported && <Badge tone="slate">Imported</Badge>}
            <span>Officer: <b>{d.inspector_name}</b></span><span>·</span><span>{fmtDate(d.inspection_datetime)}</span>
            {d.status === "COMPLETED" && <><span>·</span><span>analysed in {d.processing_seconds}s</span></>}
          </div>
        </div>
        <div className="row">
          {d.status === "COMPLETED" && <>
            <button className="btn btn-primary" onClick={() => report("pdf")} disabled={!!busy}>{busy === "pdf" ? <Loader2 size={16} className="spin" /> : <FileText size={16} />} PDF report</button>
            <button className="btn btn-outline" onClick={() => report("docx")} disabled={!!busy}>{busy === "docx" ? <Loader2 size={16} className="spin" /> : <FileType2 size={16} />} Word</button>
            <button className="btn btn-outline" onClick={() => report("xlsx")} disabled={!!busy}>{busy === "xlsx" ? <Loader2 size={16} className="spin" /> : <FileSpreadsheet size={16} />} Excel</button>
          </>}
          {canEdit && d.status !== "PROCESSING" && d.images.length > 0 && <button className="btn btn-outline" onClick={reanalyze} disabled={!!busy}><RefreshCcw size={16} /> {d.status === "COMPLETED" ? "Re-analyze" : "Run analysis"}</button>}
          {canEdit && <button className="btn btn-danger btn-icon" title="Delete inspection" aria-label="Delete inspection" onClick={() => setConfirmDel(true)}><Trash2 size={16} /></button>}
        </div>
      </div>

      {d.status === "PROCESSING" && (
        <div className="card card-pad"><div className="row"><Loader2 className="spin" color="var(--blue)" /><b>Analyzing package… {d.stage_label}</b><span className="muted">{d.progress}%</span></div>
          <div className="bar" style={{ marginTop: 10 }}><div style={{ width: `${d.progress}%` }} /></div></div>
      )}
      {d.status === "FAILED" && <Alert kind="error"><b>Analysis failed:</b> {d.error}</Alert>}
      {d.status === "DRAFT" && <Alert kind="info">This inspection has not been analysed yet. {d.images.length ? "Run the analysis to evaluate compliance." : "Upload package images first."}</Alert>}

      {d.status === "COMPLETED" && <>
        <div className="tabs" role="tablist">
          {tabs.map(([k, label, count]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>
              {label}{count !== undefined && <span className="count">{count}</span>}</button>
          ))}
        </div>
        {tab === "result" && <ResultTab d={d} onEvidence={openEvidence} goFindings={() => setTab("findings")} />}
        {tab === "fields" && <FieldsTab d={d} onEvidence={openEvidence} />}
        {tab === "findings" && <FindingsTab d={d} onEvidence={openEvidence} />}
        {tab === "evidence" && <EvidenceTab d={d} imageId={imageId} setImageId={setImageId} highlight={highlight} setHighlight={setHighlight} />}
        {tab === "record" && <RecordTab d={d} canEdit={canEdit} reload={load} />}
      </>}
      {d.status !== "COMPLETED" && <RecordTab d={d} canEdit={canEdit} reload={load} />}

      {confirmDel && <Modal title="Delete inspection?" onClose={() => setConfirmDel(false)}
        footer={<><button className="btn btn-outline" onClick={() => setConfirmDel(false)}>Cancel</button><button className="btn btn-danger" onClick={del}><Trash2 size={16} /> Delete permanently</button></>}>
        This permanently removes {d.reference}, its images, OCR results, findings and attachments.</Modal>}
    </div>
  );
}

/* ================================================================== result */
function ResultTab({ d, onEvidence, goFindings }: { d: Detail; onEvidence: (f: string | null, img?: number | null) => void; goFindings: () => void }) {
  const [open, setOpen] = useState(false);
  const m = overallMeta[d.overall_status] ?? overallMeta[""];
  const Icon = d.overall_status === "COMPLIANT" ? CheckCircle2 : d.overall_status === "NEEDS_VERIFICATION" ? CircleHelp : d.overall_status === "PARTIALLY_COMPLIANT" ? AlertTriangle : XCircle;
  const applicable = d.findings.filter((f) => f.status !== "NOT_APPLICABLE");
  const credit: Record<string, number> = { PASS: 1, NEEDS_VERIFICATION: 0.5, NON_COMPLIANT: 0 };
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className={`verdict ${m.tone}`}>
        <div className="vicon"><Icon size={34} /></div>
        <div className="grow">
          <h2>{m.label}</h2>
          <div className="small" style={{ color: "var(--ink-2)" }}>Commodity: <b>{d.product_name}</b> · Record ref: <b className="mono">{d.reference}</b></div>
          <div className="small muted" style={{ marginTop: 4 }}>{d.summary.overall_reason}</div>
          <div className="tiny muted" style={{ fontStyle: "italic", marginTop: 4 }}>*Evaluated per the Legal Metrology (Packaged Commodities) Rules, 2011 by a deterministic rule engine</div>
        </div>
        <ScoreRing value={d.score} color={TONE_COLOR[m.tone]} />
      </div>
      {d.summary.ocr_problem && <Alert kind="warn"><b>Photograph / OCR problem:</b> {d.summary.ocr_problem}</Alert>}
      {d.overall_status === "NEEDS_VERIFICATION" && <Alert kind="warn">No violation was established from the images, but this is <b>not</b> a certification of compliance: {d.needs_verification} check(s) need physical or authoritative verification.</Alert>}

      <div className="grid g4">
        <StatCard label="Compliance score" value={`${d.score}%`} desc="Legal Metrology compliance rating" icon={<ShieldAlert size={18} />} tone={m.tone === "slate" ? "blue" : m.tone} />
        <StatCard label="Passed checks" value={d.passed} desc="Statutory requirements fulfilled" icon={<CheckCircle2 size={18} />} tone="green" />
        <StatCard label="Failed checks" value={d.failed} desc="Statutory infractions identified" icon={<XCircle size={18} />} tone="red" />
        <StatCard label="Needs review" value={d.needs_verification} desc="Requires physical / optical verification" icon={<AlertTriangle size={18} />} tone="amber" />
      </div>

      <div className="card">
        <div className="card-head" style={{ cursor: "pointer" }} onClick={() => setOpen((v) => !v)}>
          <div className="ic" style={{ width: 38, height: 38, borderRadius: 10, background: "var(--blue-50)", color: "var(--blue)", display: "grid", placeItems: "center" }}><Calculator size={18} /></div>
          <div className="grow"><h3>Statutory Scoring Audit &amp; Mathematical Transparency <Badge tone="slate">Deterministic &amp; explainable</Badge></h3>
            <p>{d.earned_points} earned / {d.applicable_points} applicable weighted points · {applicable.length} rules evaluated (not applicable excluded from denominator)</p></div>
          <span className="small" style={{ color: "var(--blue)", fontWeight: 700 }}>View formula &amp; breakdown {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
        </div>
        {open && <div className="card-pad stack">
          <div className="alert alert-info small"><div><b>Formula:</b> {d.summary.formula}<br /><b>Weights:</b> HIGH = 3, MEDIUM = 2, LOW = 1 · <b>Credit:</b> Pass = 1, Needs verification = 0.5, Non-compliant = 0<br />
            <b>Overall status:</b> any high-severity non-compliance → Non-Compliant; other non-compliance → Partially Compliant; else any unverifiable check → Needs Verification; else Compliant.</div></div>
          <div className="table-wrap"><table className="tbl"><thead><tr><th>Check</th><th>Severity</th><th>Weight</th><th>Result</th><th>Credit</th><th>Points</th></tr></thead>
            <tbody>{applicable.map((f) => <tr key={f.id}><td><span className="mono tiny" style={{ color: "var(--blue)" }}>{f.rule_no}</span> {f.title}</td><td><SeverityBadge severity={f.severity} /></td><td>{f.weight}</td>
              <td><FindingBadge status={f.status} /></td><td>{credit[f.status]}</td><td><b>{(f.weight * credit[f.status]).toFixed(1)}</b></td></tr>)}
              <tr><td colSpan={5} style={{ textAlign: "right" }}><b>Total</b></td><td><b>{d.earned_points} / {d.applicable_points} = {d.score}%</b></td></tr></tbody></table></div>
        </div>}
      </div>

      <div className="card">
        <div className="card-head"><Sparkles size={20} color="var(--blue)" /><div className="grow"><h3>Statutory Recommendations &amp; Actionable Guidance</h3><p>Prescribed compliance directives under the Legal Metrology Act, 2009 &amp; Packaged Commodities Rules, 2011</p></div>
          <Badge tone="slate">{d.recommendations.length} action items</Badge></div>
        <div className="card-pad stack" style={{ gap: 10 }}>
          {d.recommendations.length === 0 ? <Empty title="No actions required" icon={<CheckCircle2 size={36} />} /> : d.recommendations.map((r) => (
            <div key={r.check_id} className={`rec ${r.type}`}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="typ">{r.type === "RECTIFY_VIOLATION" ? "RECTIFY VIOLATION" : "VERIFY"} <span className="muted" style={{ fontWeight: 600 }}>· Rule {r.rule_no}</span></span>
                <Badge tone={r.urgency === "HIGH" ? "red" : r.urgency === "MEDIUM" ? "orange" : "amber"}>{r.urgency} urgency</Badge></div>
              <div style={{ fontWeight: 800, fontSize: 15, margin: "4px 0" }}>{r.title}</div>
              <div className="small" style={{ color: "var(--ink-2)" }}>{r.action}</div>
              <div className="tiny muted">{r.reference}</div>
            </div>
          ))}
          <button className="btn btn-outline btn-sm" style={{ alignSelf: "flex-start" }} onClick={goFindings}>See all rule findings</button>
        </div>
      </div>

      <div className="card">
        <div className="card-head"><ImageIcon size={20} color="var(--blue)" /><div className="grow"><h3>Package photographs</h3><p>Click to inspect OCR evidence</p></div></div>
        <div className="card-pad thumbs">
          {d.images.map((img) => (
            <button key={img.id} className="thumb" style={{ cursor: "pointer", textAlign: "left" }} onClick={() => onEvidence(null, img.id)}>
              <div className="img"><AuthImage path={`/api/files/images/${img.id}?variant=display`} alt={img.side} /></div>
              <div className="body"><div className="row" style={{ justifyContent: "space-between" }}><b>{SIDE_LABELS[img.side] || img.side}</b><QualityBadge q={img.quality_status} /></div>
                <span className="tiny muted">{img.filename} · OCR {img.ocr?.mean_confidence?.toFixed(1) ?? 0}%</span></div>
            </button>))}
        </div>
      </div>
    </div>
  );
}

export function QualityBadge({ q }: { q: string }) {
  return <Badge tone={q === "GOOD" ? "green" : q === "ACCEPTABLE" ? "blue" : q === "POOR" ? "red" : "slate"}>{q || "—"}</Badge>;
}

/* ================================================================== fields */
const STRUCT_LABELS: Record<string, string> = {
  product_name: "Product name", brand_name: "Brand name", net_quantity: "Net quantity", mrp: "MRP (₹)",
  mfg_date: "Manufacturing date", packed_on: "Packed on", expiry_date: "Expiry / use by", best_before: "Best before",
  batch_number: "Batch / lot no.", manufacturer_name: "Manufacturer", manufacturer_address: "Manufacturer address",
  customer_care: "Customer care", fssai_license: "FSSAI licence no.", country_of_origin: "Country of origin",
  importer: "Importer", unit_sale_price: "Unit sale price (₹)",
};
const STRUCT_SOURCE: Record<string, string> = {
  mfg_date: "manufacture_date", best_before: "best_before_label", manufacturer_name: "manufacturer_packer",
  manufacturer_address: "manufacturer_packer", customer_care: "consumer_care",
};

function StructuredCard({ d, onEvidence }: { d: Detail; onEvidence: (f: string | null, img?: number | null) => void }) {
  const toast = useToast();
  const st = d.summary.structured;
  if (!st) return null;
  const flat = Object.fromEntries(Object.entries(st).filter(([, v]) => v.found).map(([k, v]) => [k, v.value]));
  const copy = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(flat, null, 2)); toast("Structured JSON copied."); }
    catch { toast("Copy failed - select the JSON below instead.", true); }
  };
  return (
    <div className="card">
      <div className="card-head"><ScanText size={20} color="var(--blue)" /><div className="grow"><h3>Structured product information</h3>
        <p>Normalised values extracted from the OCR text ({d.summary.engine}). Brand and product name come from print layout, not from a declaration label - verify them.</p></div>
        <button className="btn btn-outline btn-sm" onClick={copy}><Copy size={14} /> Copy JSON</button></div>
      <div className="table-wrap"><table className="tbl">
        <thead><tr><th>Field</th><th>Value</th><th>Confidence</th><th>How found</th><th>OCR evidence</th></tr></thead>
        <tbody>{Object.entries(STRUCT_LABELS).map(([k, label]) => {
          const v = st[k];
          const src = STRUCT_SOURCE[k] || k;
          return (
            <tr key={k} className={v?.bbox ? "click" : ""} onClick={() => v?.bbox && onEvidence(src, v.source_image_id)}>
              <td className="strong">{label}</td>
              <td className="mono small">{v?.found ? v.value : <span className="muted">— not found —</span>}</td>
              <td style={{ fontWeight: 700, color: !v?.found ? "var(--muted)" : v.confidence >= 85 ? "var(--green)" : v.confidence >= 65 ? "#b45309" : "var(--red)" }}>{v?.found ? `${v.confidence.toFixed(0)}%` : "—"}</td>
              <td className="tiny">{!v?.found ? "—" : v.method === "line_role_model" ? <Badge tone="blue">layout model</Badge> : v.method === "layout_heuristic" ? <Badge tone="amber">layout heuristic</Badge> : <Badge tone="slate">label rules</Badge>}</td>
              <td className="mono tiny" style={{ maxWidth: 320 }}>{v?.evidence || "—"}</td>
            </tr>);
        })}</tbody>
      </table></div>
      <details className="card-pad"><summary className="small" style={{ cursor: "pointer" }}>JSON output</summary>
        <pre className="ocr-text" style={{ marginTop: 8 }}>{JSON.stringify(flat, null, 2)}</pre></details>
    </div>
  );
}

function FieldsTab({ d, onEvidence }: { d: Detail; onEvidence: (f: string | null, img?: number | null) => void }) {
  return (
    <div className="stack" style={{ gap: 18 }}>
    <StructuredCard d={d} onEvidence={onEvidence} />
    <div className="card">
      <div className="card-head"><div className="grow"><h3>Mandatory declarations extracted under Rule 6(1)</h3><p>OCR-detected values - detection is evidence, not verification. Click a row to see where it appears on the package.</p></div></div>
      <div className="table-wrap"><table className="tbl">
        <thead><tr><th>Declaration</th><th>Extracted value</th><th>Status</th><th>Confidence</th><th>Source</th><th>OCR evidence</th></tr></thead>
        <tbody>{d.fields.map((f) => (
          <tr key={f.field} className={f.bbox ? "click" : ""} onClick={() => f.bbox && onEvidence(f.field, f.source_image_id)}>
            <td className="strong" style={{ textTransform: "uppercase", fontSize: 12.5 }}>{f.label}</td>
            <td>{f.value || <span className="muted">— Not detected —</span>}
              {f.field === "mrp" && f.alternatives?.some((a) => !(a as { same_value?: boolean }).same_value) &&
                <div className="tiny" style={{ color: "var(--red)" }}>Other MRP readings on package: {f.alternatives.filter((a) => !(a as { same_value?: boolean }).same_value).map((a) => a.value).join(", ")}</div>}
              {typeof f.normalized?.["ocr_reading"] === "number" && <div className="tiny muted">raw OCR reading: {String(f.normalized["ocr_reading"])}</div>}</td>
            <td><FieldBadge status={f.status} /></td>
            <td style={{ color: f.confidence >= 90 ? "var(--green)" : f.confidence >= 70 ? "#b45309" : "var(--muted)", fontWeight: 700 }}>{f.confidence ? `${f.confidence.toFixed(1)}%` : "—"}</td>
            <td className="small">{f.source_side ? <>{SIDE_LABELS[f.source_side] || f.source_side}<div className="tiny muted">{f.source_image}</div></> : "—"}</td>
            <td className="mono tiny" style={{ maxWidth: 320 }}>{f.evidence || "—"}</td>
          </tr>))}</tbody>
      </table></div>
    </div>
    </div>
  );
}

/* ================================================================== findings */
function FindingsTab({ d, onEvidence }: { d: Detail; onEvidence: (f: string | null, img?: number | null) => void }) {
  const [filter, setFilter] = useState<FindingStatus | "ALL">("ALL");
  const [open, setOpen] = useState<Set<number>>(new Set(d.findings.filter((f) => f.status === "NON_COMPLIANT").map((f) => f.id)));
  const list = d.findings.filter((f) => filter === "ALL" || f.status === filter);
  const groups = useMemo(() => {
    const g = new Map<string, Finding[]>();
    list.forEach((f) => g.set(`${f.rule_no}|${f.rule_title}`, [...(g.get(`${f.rule_no}|${f.rule_title}`) || []), f]));
    return [...g.entries()];
  }, [list]);
  const toggle = (id: number) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  return (
    <div className="stack">
      <div className="row">
        {(["ALL", "NON_COMPLIANT", "NEEDS_VERIFICATION", "PASS", "NOT_APPLICABLE"] as const).map((s) => (
          <button key={s} className={`btn btn-sm ${filter === s ? "btn-primary" : "btn-outline"}`} onClick={() => setFilter(s)}>
            {s === "ALL" ? "All" : findingMeta[s].label} ({s === "ALL" ? d.findings.length : d.findings.filter((f) => f.status === s).length})</button>))}
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(new Set(list.map((f) => f.id)))}>Expand all</button>
      </div>
      {groups.map(([key, items]) => {
        const [no, title] = key.split("|");
        return (
          <div key={key}>
            <h4 style={{ margin: "8px 0 8px", fontSize: 14 }}><span className="mono" style={{ color: "var(--blue)" }}>{no.startsWith("S") ? "Section 18" : `Rule ${no}`}</span> — {title}</h4>
            {items.map((f) => (
              <div key={f.id} className={`finding s-${f.status}`}>
                <div className="fh" onClick={() => toggle(f.id)}>
                  {open.has(f.id) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <span className="rn">{f.check_id}</span><span className="tt">{f.title}</span>
                  <SeverityBadge severity={f.severity} /><FindingBadge status={f.status} />
                </div>
                {open.has(f.id) && <div className="fb">
                  <dl className="kv">
                    <dt>Reason</dt><dd><b>{f.reason}</b></dd>
                    <dt>Validation condition</dt><dd>{f.condition}</dd>
                    <dt>Applicability</dt><dd>{f.applicability}</dd>
                    <dt>Required data</dt><dd>{f.required_data.join(", ")}</dd>
                    {f.verification && <><dt>Verification requirement</dt><dd>{f.verification}</dd></>}
                    {f.recommendation && <><dt>Recommendation</dt><dd>{f.recommendation}</dd></>}
                    <dt>Statutory reference</dt><dd className="small">{f.reference}</dd>
                  </dl>
                  {f.evidence.length > 0 && <div style={{ marginTop: 10 }}><div className="lbl">Evidence</div>
                    {f.evidence.map((e, i) => (
                      <div className="ev" key={i}><Paperclip size={14} style={{ marginTop: 2, flex: "none" }} color="var(--blue)" />
                        <div style={{ flex: 1 }}><span className="mono">“{e.text}”</span><div className="tiny muted">{e.label} · {SIDE_LABELS[e.side] || e.side} · {e.image} · OCR {e.confidence?.toFixed?.(0)}%{e.contrast_ratio ? ` · contrast ${e.contrast_ratio}:1` : ""}</div></div>
                        {e.bbox && e.image_id && <button className="btn btn-outline btn-sm" onClick={() => onEvidence(e.field !== "text" ? e.field : null, e.image_id)}>Show on image</button>}
                      </div>))}
                  </div>}
                </div>}
              </div>))}
          </div>
        );
      })}
      {groups.length === 0 && <Empty title="No findings in this filter" />}
    </div>
  );
}

/* ================================================================== evidence */
function EvidenceTab({ d, imageId, setImageId, highlight, setHighlight }: { d: Detail; imageId: number | null; setImageId: (n: number) => void; highlight: string | null; setHighlight: (f: string | null) => void }) {
  const img = d.images.find((i) => i.id === imageId) || d.images[0];
  if (!img) return <Empty title="No images" />;
  const mine = d.fields.filter((f) => f.source_image_id === img.id && f.status !== "NOT_DETECTED");
  const metrics = img.quality?.metrics || {};
  return (
    <div className="stack">
      <div className="row">{d.images.map((i) => (
        <button key={i.id} className={`btn btn-sm ${i.id === img.id ? "btn-primary" : "btn-outline"}`} onClick={() => { setImageId(i.id); setHighlight(null); }}>
          {SIDE_LABELS[i.side] || i.side} <span style={{ opacity: .7 }}>#{i.id}</span></button>))}</div>
      <div className="grid evgrid">
        <div className="card card-pad"><EvidenceViewer image={img} fields={d.fields} highlight={highlight} onSelect={setHighlight} /></div>
        <div className="card card-pad stack" style={{ gap: 10 }}>
          <h3 style={{ fontSize: 15 }}>Detected on this panel</h3>
          <div className="field-list">
            {mine.length === 0 && <span className="muted small">No declarations were mapped to this image.</span>}
            {mine.map((f) => (
              <button key={f.field} className={`field-item ${highlight === f.field ? "active" : ""}`} onClick={() => setHighlight(highlight === f.field ? null : f.field)}>
                <div className="row" style={{ justifyContent: "space-between" }}><b className="small">{f.label}</b><FieldBadge status={f.status} /></div>
                <div className="small">{f.value}</div><div className="tiny muted">{f.confidence.toFixed(1)}% confidence</div>
              </button>))}
          </div>
        </div>
      </div>
      <div className="grid g2">
        <div className="card card-pad">
          <div className="row" style={{ justifyContent: "space-between" }}><h3 style={{ fontSize: 15 }}>Image quality check</h3><QualityBadge q={img.quality_status} /></div>
          {img.quality?.warnings?.map((w) => <div key={w} style={{ marginTop: 8 }}><Alert kind="warn">{w}</Alert></div>)}
          <table className="tbl" style={{ marginTop: 10 }}><tbody>
            {Object.entries(metrics).map(([k, m]) => <tr key={k}><td className="strong" style={{ textTransform: "capitalize" }}>{k.replace("_", " ")}</td><td className="small">{String(m.value)} <span className="muted tiny">{m.unit}</span></td><td><QualityBadge q={m.grade} /></td></tr>)}
          </tbody></table>
          <div className="lbl" style={{ marginTop: 14 }}>Preprocessing applied</div>
          <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{img.preprocessing.map((p) => <li key={p}>{p}</li>)}</ul>
          <div className="tiny muted" style={{ marginTop: 10 }}>Original: {img.filename} · {img.width}×{img.height}px · {fmtBytes(img.size_bytes)} · SHA-256 <span className="mono">{img.sha256.slice(0, 16)}…</span>
            {img.panel_width_mm && <> · calibrated panel {img.panel_width_mm}×{img.panel_height_mm ?? "?"} mm</>}</div>
        </div>
        <OcrTextCard img={img} />
      </div>
    </div>
  );
}

function OcrTextCard({ img }: { img: Detail["images"][number] }) {
  const [view, setView] = useState<number>(-1);   // -1 = merged & cleaned text, otherwise index of a raw pass
  const passes = (img.ocr?.passes || []).filter((p) => p.variant !== "notes");
  const notes = (img.ocr?.passes || []).find((p) => p.variant === "notes");
  const text = view < 0 ? img.ocr?.full_text : passes[view]?.text;
  return (
    <div className="card card-pad">
      <div className="row" style={{ justifyContent: "space-between" }}><h3 style={{ fontSize: 15 }}>OCR text</h3>
        <span className="tiny muted">{img.ocr?.engine} · {img.ocr?.word_count} words · mean {img.ocr?.mean_confidence}%</span></div>
      <div className="row" style={{ marginTop: 8, flexWrap: "wrap", gap: 6 }}>
        <button className={`btn btn-sm ${view < 0 ? "btn-primary" : "btn-outline"}`} onClick={() => setView(-1)}>Merged (cleaned)</button>
        {passes.map((p, i) => p.text !== undefined && (
          <button key={i} className={`btn btn-sm ${view === i ? "btn-primary" : "btn-outline"}`} title={p.description}
            onClick={() => setView(i)}>{p.engine === "ppocr" ? "PP-OCR raw" : `Tesseract ${p.variant}/psm${p.psm}`}</button>))}
      </div>
      <div className="ocr-text" style={{ marginTop: 10 }}>{text || "(no text recognised)"}</div>
      {view >= 0 && <div className="tiny muted" style={{ marginTop: 6 }}>Unmodified engine output of this pass, kept for debugging. The merged text applies context-safe clean-up (digit repair such as O→0 in numbers, restored spaces); the evidence boxes always refer to the merged lines.</div>}
      <div className="lbl" style={{ marginTop: 12 }}>OCR passes merged</div>
      <div className="small muted">{passes.map((p) => `${p.description} (${p.lines} lines)`).join(" · ")}</div>
      {notes?.description && <div className="tiny" style={{ marginTop: 6, color: "#b45309" }}>{notes.description}</div>}
    </div>
  );
}

/* ================================================================== record */
function RecordTab({ d, canEdit, reload }: { d: Detail; canEdit: boolean; reload: () => Promise<void> }) {
  const toast = useToast();
  const [caption, setCaption] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const camRef = useRef<HTMLInputElement>(null);
  const [edits, setEdits] = useState<Record<number, { side: string; w: string; h: string }>>(
    Object.fromEntries(d.images.map((i) => [i.id, { side: i.side, w: i.panel_width_mm ? String(i.panel_width_mm) : "", h: i.panel_height_mm ? String(i.panel_height_mm) : "" }])));

  const upload = async (file: File) => {
    setUploading(true);
    const fd = new FormData(); fd.append("file", file); fd.append("caption", caption);
    try { await api.post(`/api/inspections/${d.id}/attachments`, fd); setCaption(""); toast("Evidence attached."); await reload(); }
    catch (e) { toast((e as Error).message, true); }
    finally { setUploading(false); }
  };
  const saveImage = async (id: number) => {
    const e = edits[id];
    try { await api.patch(`/api/inspections/${d.id}/images/${id}`, { side: e.side, panel_width_mm: e.w ? Number(e.w) : null, panel_height_mm: e.h ? Number(e.h) : null }); toast("Image details saved - re-analyze to apply."); await reload(); }
    catch (err) { toast((err as Error).message, true); }
  };
  const openAttachment = async (id: number, name: string) => {
    try { await downloadFile(`/api/files/attachments/${id}`, name); } catch (e) { toast((e as Error).message, true); }
  };

  return (
    <div className="grid g2">
      <div className="card card-pad">
        <h3 style={{ fontSize: 15, marginBottom: 10 }}>Product &amp; inspection</h3>
        <dl className="kv" style={{ gridTemplateColumns: "160px 1fr" }}>
          <dt>Reference</dt><dd className="mono">{d.reference}</dd>
          <dt>Product</dt><dd>{d.product_name || "—"}</dd><dt>Brand</dt><dd>{d.brand || "—"}</dd>
          <dt>Category</dt><dd>{d.category_label}</dd><dt>Imported</dt><dd>{d.is_imported ? "Yes" : "No"}</dd>
          <dt>Manufacturer (input)</dt><dd>{d.manufacturer_info || "—"}</dd><dt>Registration no.</dt><dd>{d.registration_number || "—"}</dd>
          <dt>Inspector</dt><dd>{d.inspector_name}</dd><dt>Date / time</dt><dd>{fmtDate(d.inspection_datetime)}</dd>
          <dt>Location</dt><dd>{d.location || "—"}</dd><dt>All panels captured</dt><dd>{d.all_panels_captured ? "Confirmed" : "Not confirmed"}</dd>
          <dt>Remarks</dt><dd>{d.notes || "—"}</dd>
          <dt>Created</dt><dd>{fmtDate(d.created_at)}</dd><dt>Analysed</dt><dd>{fmtDate(d.analyzed_at)}</dd>
          {d.integrity_hash && <><dt>Integrity hash</dt><dd className="mono tiny" style={{ wordBreak: "break-all" }}>{d.integrity_hash}</dd></>}
        </dl>
      </div>
      <div className="stack">
        <div className="card card-pad">
          <h3 style={{ fontSize: 15 }}>Supporting evidence</h3>
          <p className="small muted" style={{ marginTop: 2 }}>Attach additional photographs or documents (JPG, PNG, WEBP, PDF). Attachments are not OCR-analysed.</p>
          {d.attachments.length === 0 && <div className="muted small">No attachments yet.</div>}
          {d.attachments.map((a) => (
            <div key={a.id} className="ev"><Paperclip size={14} style={{ flex: "none", marginTop: 2 }} /><div style={{ flex: 1 }}>
              <button className="btn btn-ghost btn-sm" style={{ padding: 0 }} onClick={() => openAttachment(a.id, a.filename)}><b>{a.filename}</b></button>
              <div className="tiny muted">{a.caption} · {fmtBytes(a.size_bytes)} · {a.uploaded_by} · {fmtDate(a.created_at)}</div></div>
              {canEdit && <button className="btn btn-ghost btn-icon" aria-label="Remove attachment" onClick={async () => { await api.del(`/api/inspections/${d.id}/attachments/${a.id}`); reload(); }}><Trash2 size={14} /></button>}
            </div>))}
          {canEdit && <div className="row" style={{ marginTop: 12 }}>
            <input className="input" style={{ flex: 1, minWidth: 160 }} placeholder="Caption (e.g. seizure memo, shelf photo)" value={caption} onChange={(e) => setCaption(e.target.value)} />
            <button className="btn btn-outline" disabled={uploading} onClick={() => fileRef.current?.click()}>{uploading ? <Loader2 size={16} className="spin" /> : <Paperclip size={16} />} Attach</button>
            <button className="btn btn-outline" disabled={uploading} title="Take a photo with the device camera" onClick={() => camRef.current?.click()}><Camera size={16} /> Photo</button>
            <input ref={fileRef} type="file" hidden accept=".jpg,.jpeg,.png,.webp,.pdf" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            <input ref={camRef} type="file" hidden accept="image/*" capture="environment" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
          </div>}
        </div>
        {canEdit && <div className="card card-pad">
          <h3 style={{ fontSize: 15 }}>Package images</h3>
          <p className="small muted" style={{ marginTop: 2 }}>Correct the side assignment or add physical calibration, then re-analyze.</p>
          {d.images.map((i) => (
            <div key={i.id} className="row" style={{ marginTop: 8 }}>
              <span className="small" style={{ width: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={i.filename}>{i.filename}</span>
              <select className="select" style={{ width: 130 }} value={edits[i.id]?.side} onChange={(e) => setEdits({ ...edits, [i.id]: { ...edits[i.id], side: e.target.value } })}>
                {Object.entries(SIDE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <input className="input" style={{ width: 90 }} placeholder="W mm" value={edits[i.id]?.w} onChange={(e) => setEdits({ ...edits, [i.id]: { ...edits[i.id], w: e.target.value } })} />
              <input className="input" style={{ width: 90 }} placeholder="H mm" value={edits[i.id]?.h} onChange={(e) => setEdits({ ...edits, [i.id]: { ...edits[i.id], h: e.target.value } })} />
              <button className="btn btn-outline btn-sm" onClick={() => saveImage(i.id)}>Save</button>
            </div>))}
        </div>}
      </div>
    </div>
  );
}

