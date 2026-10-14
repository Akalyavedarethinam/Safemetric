import { useState } from "react";
import { UserPlus } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDate } from "../lib/format";
import type { User } from "../lib/types";
import { Alert, Badge, Modal, Spinner, useAsync, useToast } from "../components/ui";

export default function Users() {
  const { user: me } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useAsync(() => api.get<User[]>("/api/users"), []);
  const [show, setShow] = useState(false);
  const [f, setF] = useState({ name: "", email: "", password: "", role: "inspector", designation: "Inspector, Legal Metrology", jurisdiction: "" });
  const [err, setErr] = useState("");
  const [reset, setReset] = useState<User | null>(null);
  const [pw, setPw] = useState("");

  if (me?.role !== "admin") return <Alert kind="error">Administrator privileges are required.</Alert>;
  if (loading && !data) return <Spinner />;
  if (error) return <Alert kind="error">{error}</Alert>;

  const create = async () => {
    setErr("");
    try { await api.post("/api/users", f); setShow(false); toast("User created."); setF({ ...f, name: "", email: "", password: "" }); reload(); }
    catch (e) { setErr((e as Error).message); }
  };
  const update = async (u: User, patch: Record<string, unknown>) => {
    try { await api.put(`/api/users/${u.id}`, patch); toast("User updated."); reload(); }
    catch (e) { toast((e as Error).message, true); }
  };

  return (
    <div className="card">
      <div className="card-head"><div className="grow"><h3>Officer accounts</h3><p>Role-based access: Administrators manage users and statutory rule activation; Inspectors create and analyse inspections.</p></div>
        <button className="btn btn-primary" onClick={() => setShow(true)}><UserPlus size={16} /> Add officer</button></div>
      <div className="table-wrap"><table className="tbl">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Designation</th><th>Inspections</th><th>Last sign-in</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{data?.map((u) => (
          <tr key={u.id}>
            <td className="strong">{u.name}<div className="tiny muted">{u.jurisdiction}</div></td><td className="small">{u.email}</td>
            <td><select className="select" style={{ width: 130 }} value={u.role} disabled={u.id === me.id} onChange={(e) => update(u, { role: e.target.value })}>
              <option value="inspector">Inspector</option><option value="admin">Administrator</option></select></td>
            <td className="small">{u.designation}</td><td>{u.inspections}</td><td className="small">{fmtDate(u.last_login)}</td>
            <td>{u.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="slate">Deactivated</Badge>}</td>
            <td><div className="row" style={{ gap: 6 }}>
              {u.id !== me.id && <button className="btn btn-outline btn-sm" onClick={() => update(u, { is_active: !u.is_active })}>{u.is_active ? "Deactivate" : "Activate"}</button>}
              <button className="btn btn-outline btn-sm" onClick={() => { setReset(u); setPw(""); }}>Reset password</button></div></td>
          </tr>))}</tbody>
      </table></div>
      {show && <Modal title="Add officer account" onClose={() => setShow(false)} footer={<><button className="btn btn-outline" onClick={() => setShow(false)}>Cancel</button><button className="btn btn-primary" onClick={create}>Create</button></>}>
        <div className="stack" style={{ gap: 12 }}>
          {err && <Alert kind="error">{err}</Alert>}
          <div className="field"><label>Full name</label><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="field"><label>Email</label><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
          <div className="field"><label>Initial password</label><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /><span className="hint">8+ characters with a letter and a number.</span></div>
          <div className="grid g2" style={{ gap: 12 }}>
            <div className="field"><label>Role</label><select className="select" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="inspector">Inspector</option><option value="admin">Administrator</option></select></div>
            <div className="field"><label>Jurisdiction</label><input className="input" value={f.jurisdiction} onChange={(e) => setF({ ...f, jurisdiction: e.target.value })} /></div>
          </div>
          <div className="field"><label>Designation</label><input className="input" value={f.designation} onChange={(e) => setF({ ...f, designation: e.target.value })} /></div>
        </div></Modal>}
      {reset && <Modal title={`Reset password — ${reset.name}`} onClose={() => setReset(null)} footer={<><button className="btn btn-outline" onClick={() => setReset(null)}>Cancel</button>
        <button className="btn btn-primary" onClick={async () => { await update(reset, { new_password: pw }); setReset(null); }}>Set password</button></>}>
        <div className="field"><label>New password</label><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></div></Modal>}
    </div>
  );
}
