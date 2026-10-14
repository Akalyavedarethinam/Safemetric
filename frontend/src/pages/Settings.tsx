import { useState } from "react";
import { Database, KeyRound, ScanText, UserCog } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDate } from "../lib/format";
import type { Health } from "../lib/types";
import { Alert, Badge, useAsync, useToast } from "../components/ui";

interface AuditRow { id: number; user_email: string; action: string; detail: string; ip: string; created_at: string }

export default function Settings() {
  const { user, refresh } = useAuth();
  const toast = useToast();
  const [p, setP] = useState({ name: user?.name || "", designation: user?.designation || "", jurisdiction: user?.jurisdiction || "", phone: user?.phone || "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "", confirm: "" });
  const [pwErr, setPwErr] = useState("");
  const { data: h } = useAsync(() => api.get<Health>("/api/health"), []);
  const { data: audit } = useAsync(() => (user?.role === "admin" ? api.get<AuditRow[]>("/api/audit?limit=30") : Promise.resolve([])), [user?.role]);

  const saveProfile = async () => {
    try { await api.put("/api/auth/me", p); await refresh(); toast("Profile updated."); } catch (e) { toast((e as Error).message, true); }
  };
  const changePw = async () => {
    setPwErr("");
    if (pw.new_password !== pw.confirm) { setPwErr("New passwords do not match."); return; }
    try { await api.post("/api/auth/change-password", { current_password: pw.current_password, new_password: pw.new_password }); setPw({ current_password: "", new_password: "", confirm: "" }); toast("Password changed."); }
    catch (e) { setPwErr((e as Error).message); }
  };

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="grid g2">
        <div className="card">
          <div className="card-head"><UserCog size={20} color="var(--blue)" /><div className="grow"><h3>Inspector profile</h3><p>{user?.email} · <Badge tone="blue">{user?.role === "admin" ? "Administrator" : "Inspector"}</Badge></p></div></div>
          <div className="card-pad stack" style={{ gap: 12 }}>
            <div className="field"><label>Full name</label><input className="input" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></div>
            <div className="grid g2" style={{ gap: 12 }}>
              <div className="field"><label>Designation</label><input className="input" value={p.designation} onChange={(e) => setP({ ...p, designation: e.target.value })} /></div>
              <div className="field"><label>Jurisdiction</label><input className="input" value={p.jurisdiction} onChange={(e) => setP({ ...p, jurisdiction: e.target.value })} /></div>
            </div>
            <div className="field"><label>Phone</label><input className="input" value={p.phone} onChange={(e) => setP({ ...p, phone: e.target.value })} /></div>
            <button className="btn btn-primary" style={{ alignSelf: "flex-start" }} onClick={saveProfile}>Save profile</button>
            <span className="tiny muted">Member since {fmtDate(user?.created_at, false)} · last sign-in {fmtDate(user?.last_login)}</span>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><KeyRound size={20} color="var(--blue)" /><div className="grow"><h3>Change password</h3><p>Passwords are stored only as bcrypt hashes.</p></div></div>
          <div className="card-pad stack" style={{ gap: 12 }}>
            {pwErr && <Alert kind="error">{pwErr}</Alert>}
            <div className="field"><label>Current password</label><input className="input" type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} autoComplete="current-password" /></div>
            <div className="field"><label>New password</label><input className="input" type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} autoComplete="new-password" /></div>
            <div className="field"><label>Confirm new password</label><input className="input" type="password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} autoComplete="new-password" /></div>
            <button className="btn btn-primary" style={{ alignSelf: "flex-start" }} onClick={changePw}>Update password</button>
          </div>
        </div>
      </div>

      <div className="grid g2">
        <div className="card card-pad">
          <div className="row"><ScanText size={20} color="var(--blue)" /><h3 style={{ fontSize: 15 }}>OCR engine</h3>{h && (h.ocr.available ? <Badge tone="green">Online</Badge> : <Badge tone="red">Unavailable</Badge>)}</div>
          <ul className="small" style={{ color: "var(--ink-2)", paddingLeft: 18 }}>
            <li><b>Mode:</b> {h?.ocr.engine || "—"} → {h?.ocr.engine_label || "—"}</li>
            <li><b>Text detection &amp; recognition:</b> PP-OCR {h?.ocr.ppocr?.available ? `(${h?.ocr.ppocr?.det_model}, ${h?.ocr.ppocr?.rec_model})` : "unavailable"}</li>
            <li><b>Tesseract:</b> {h?.ocr.tesseract_available ? `${h?.ocr.version} (${h?.ocr.cmd})` : "not installed"} · languages {h?.ocr.languages?.join(", ") || "—"}</li>
            <li><b>Preprocessing:</b> EXIF orientation, text-line geometry (any angle, 180° check), contrast-enhanced second pass for dark / low-contrast photos, CLAHE &amp; threshold variants for Tesseract</li>
            <li><b>Post-processing:</b> context-safe clean-up (O→0 in numbers, restored spaces); raw engine output kept per pass</li>
            <li><b>Brand / product name:</b> {h?.line_role_model?.available ? `trained line-role model (${h.line_role_model.trained})` : "layout heuristic (model file not found)"}</li>
          </ul>
          {h && !h.ocr.available && <Alert kind="error">No OCR engine is available. Install <span className="mono">rapidocr_onnxruntime</span> (pip) or Tesseract and set <span className="mono">TESSERACT_CMD</span>.</Alert>}
        </div>
        <div className="card card-pad">
          <div className="row"><Database size={20} color="var(--blue)" /><h3 style={{ fontSize: 15 }}>Enforcement records persistence &amp; report generation</h3></div>
          <ul className="small" style={{ color: "var(--ink-2)", paddingLeft: 18 }}>
            <li><b>Storage engine:</b> {h?.database_engine === "sqlite" ? "SQLite" : "PostgreSQL"} with SQLAlchemy ORM · database {h?.database}</li>
            <li><b>File storage:</b> {h?.storage} {h?.storage === "local" ? "(filesystem)" : "(object storage)"}</li>
            <li><b>Report generator:</b> ReportLab (A4 PDF), python-docx (Word), openpyxl (Excel)</li>
            <li><b>Security:</b> JWT authorisation with bcrypt password hashing, role-based access, audit log</li>
            <li><b>Version:</b> SafeMetric {h?.version}</li>
          </ul>
        </div>
      </div>

      {user?.role === "admin" && (
        <div className="card">
          <div className="card-head"><div className="grow"><h3>Audit log</h3><p>Last 30 security-relevant events</p></div></div>
          <div className="table-wrap"><table className="tbl"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Detail</th><th>IP</th></tr></thead>
            <tbody>{audit?.map((a) => <tr key={a.id}><td className="small">{fmtDate(a.created_at)}</td><td className="small">{a.user_email || "—"}</td><td><span className="mono tiny">{a.action}</span></td><td className="small">{a.detail}</td><td className="tiny muted">{a.ip}</td></tr>)}</tbody></table></div>
        </div>
      )}
    </div>
  );
}
