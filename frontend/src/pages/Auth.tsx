import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, BadgeCheck, Lock, Mail, MapPin, ShieldCheck, User } from "lucide-react";
import { useAuth } from "../lib/auth";
import { Alert } from "../components/ui";

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try { await login(email, password); nav(loc.state?.from || "/app/dashboard", { replace: true }); }
    catch (ex) { setErr((ex as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="logo"><ShieldCheck size={30} /></div>
        <h2>LEGAL METROLOGY COMPLIANCE SYSTEM</h2>
        <p className="s">Authorized Enforcement &amp; Inspector Portal</p>
        <div className="stack">
          {err && <Alert kind="error">{err}</Alert>}
          <div className="field"><label htmlFor="em">Officer Email Address</label>
            <div className="input-icon"><Mail size={16} /><input id="em" className="input" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="officer@department.gov.in" /></div></div>
          <div className="field"><label htmlFor="pw">Secure Password</label>
            <div className="input-icon"><Lock size={16} /><input id="pw" className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" /></div></div>
          <button className="btn btn-primary" disabled={busy} style={{ width: "100%", padding: 13 }}>{busy ? "Signing in…" : <>LOGIN TO SAFEMETRIC <ArrowRight size={16} /></>}</button>
          <p className="small" style={{ textAlign: "center", margin: 0 }}>Don't have an officer account? <Link to="/register">Create Account</Link></p>
          <p className="tiny muted" style={{ textAlign: "center", margin: 0 }}><Link to="/">← Back to home</Link></p>
        </div>
      </form>
    </div>
  );
}

export function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "", confirm: "", designation: "Inspector, Legal Metrology", jurisdiction: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    if (f.password !== f.confirm) { setErr("Passwords do not match."); return; }
    setBusy(true);
    try {
      const { confirm, ...data } = f;
      await register(data);
      nav("/app/dashboard", { replace: true });
    } catch (ex) { setErr((ex as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="logo"><BadgeCheck size={30} /></div>
        <h2>REGISTER INSPECTOR ACCOUNT</h2>
        <p className="s">New accounts receive the Inspector role</p>
        <div className="stack">
          {err && <Alert kind="error">{err}</Alert>}
          <div className="field"><label>Full name</label><div className="input-icon"><User size={16} /><input className="input" required minLength={2} value={f.name} onChange={set("name")} /></div></div>
          <div className="field"><label>Official email</label><div className="input-icon"><Mail size={16} /><input className="input" type="email" required value={f.email} onChange={set("email")} autoComplete="username" /></div></div>
          <div className="grid g2" style={{ gap: 12 }}>
            <div className="field"><label>Designation</label><input className="input" value={f.designation} onChange={set("designation")} /></div>
            <div className="field"><label>Jurisdiction</label><div className="input-icon"><MapPin size={16} /><input className="input" value={f.jurisdiction} onChange={set("jurisdiction")} placeholder="District / State" /></div></div>
          </div>
          <div className="grid g2" style={{ gap: 12 }}>
            <div className="field"><label>Password</label><input className="input" type="password" required minLength={8} value={f.password} onChange={set("password")} autoComplete="new-password" /></div>
            <div className="field"><label>Confirm</label><input className="input" type="password" required value={f.confirm} onChange={set("confirm")} autoComplete="new-password" /></div>
          </div>
          <span className="tiny muted">At least 8 characters with a letter and a number. Passwords are stored as bcrypt hashes.</span>
          <button className="btn btn-primary" disabled={busy} style={{ width: "100%", padding: 13 }}>{busy ? "Creating account…" : "Create Account"}</button>
          <p className="small" style={{ textAlign: "center", margin: 0 }}>Already registered? <Link to="/login">Sign in</Link></p>
        </div>
      </form>
    </div>
  );
}
