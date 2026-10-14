import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { BookOpenCheck, FileText, History, LayoutDashboard, LogOut, Menu, Plus, ScanLine, Settings, Shield, ShieldCheck, Users } from "lucide-react";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import type { Health } from "../lib/types";

const TITLES: [RegExp, string][] = [
  [/^\/app\/dashboard/, "Enforcement Dashboard"],
  [/^\/app\/inspections\/new/, "New Commodity Inspection"],
  [/^\/app\/inspections\/\d+/, "Inspection Record Details"],
  [/^\/app\/inspections/, "Inspection History"],
  [/^\/app\/reports/, "Compliance Reports"],
  [/^\/app\/rules/, "Statutory Rules"],
  [/^\/app\/users/, "User Management"],
  [/^\/app\/settings/, "Settings & Inspector Profile"],
];

export function EngineStatus() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    const load = () => api.get<Health>("/api/health").then(setH).catch(() => setH(null));
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);
  const ok = h?.ocr.available && h.database === "ok";
  return (
    <span className={`engine ${h && !ok ? "off" : ""}`} title={h ? `${h.ocr.engine_label || "OCR"} · DB ${h.database_engine} · storage ${h.storage}` : "checking"}>
      <span className="dot" /> {h ? (ok ? "Engine Online • PCR 2011 Active" : h.ocr.available ? "Database unavailable" : "OCR engine unavailable") : "Checking engine…"}
    </span>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [loc.pathname]);
  const title = TITLES.find(([r]) => r.test(loc.pathname))?.[1] ?? "SafeMetric";

  const link = (to: string, icon: ReactNode, label: string) => (
    <NavLink to={to} end={to === "/app/inspections"} className={({ isActive }) => (isActive ? "active" : "")}>{icon}{label}</NavLink>
  );

  return (
    <div className="shell grid-bg">
      <div className={`scrim ${open ? "show" : ""}`} onClick={() => setOpen(false)} />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-logo"><ShieldCheck size={22} /></div>
          <div><div className="brand-name">SAFE METRIC</div><div className="brand-sub">Legal Metrology AI</div></div>
        </div>
        <div className="brand-note">Legal Metrology (Packaged Commodities) Rules, 2011</div>
        <div className="nav-title">Enforcement suite</div>
        <nav className="nav">
          {link("/app/dashboard", <LayoutDashboard size={18} />, "Dashboard")}
          {link("/app/inspections/new", <ScanLine size={18} />, "New Inspection")}
          {link("/app/inspections", <History size={18} />, "Inspection History")}
          {link("/app/reports", <FileText size={18} />, "Reports")}
          {link("/app/rules", <BookOpenCheck size={18} />, "Statutory Rules")}
          {user?.role === "admin" && link("/app/users", <Users size={18} />, "User Management")}
          {link("/app/settings", <Settings size={18} />, "Settings & Profile")}
        </nav>
        <div className="authority">
          <b>Statutory Authority</b>
          <span>Automated assistance under the Legal Metrology Act, 2009. Final decisions rest with the authorised officer.</span>
        </div>
        <div className="side-user">
          <div className="avatar">{user?.name?.[0]?.toUpperCase()}</div>
          <div className="who"><b>{user?.name}</b><span>{user?.role === "admin" ? "Administrator" : "Inspector"}</span></div>
          <button className="btn btn-ghost btn-icon" title="Sign out" aria-label="Sign out" onClick={() => { logout(); nav("/login"); }}><LogOut size={18} /></button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost btn-icon menu-btn" onClick={() => setOpen(true)} aria-label="Open menu"><Menu size={20} /></button>
          <h1>{title}</h1>
          <span className="chip hide-sm"><Shield size={13} /> Legal Metrology Department</span>
          <div className="spacer" />
          <span className="hide-sm"><EngineStatus /></span>
          <button className="btn btn-primary" onClick={() => nav("/app/inspections/new")}><Plus size={18} /> <span className="hide-sm">Scan Product</span></button>
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
