import { Link } from "react-router-dom";
import { Award, BookOpenCheck, CheckCircle2, Database, FileSpreadsheet, FileText, Fingerprint, LayoutGrid, ScanLine, ScanText, ShieldCheck, Workflow } from "lucide-react";
import { useAuth } from "../lib/auth";

const FEATURES = [
  { icon: <ScanLine size={20} />, t: "Multi-panel image intake", d: "Upload front, back, side, top and bottom photographs of any packaged commodity - JPG, PNG or WEBP." },
  { icon: <ScanText size={20} />, t: "Real OCR with evidence", d: "Quality checks, orientation & deskew, CLAHE/threshold variants and multi-pass Tesseract OCR with word-level bounding boxes." },
  { icon: <BookOpenCheck size={20} />, t: "Deterministic rule engine", d: "Rules 6, 7, 8, 9, 11/12, 13, 15, 27 and Section 18 evaluated by explicit, explainable conditions - never by an AI model." },
  { icon: <Fingerprint size={20} />, t: "Honest uncertainty", d: "Anything a photograph cannot prove (letter height, spacing, registration) is reported as Needs Verification, not passed." },
  { icon: <FileText size={20} />, t: "Reports in PDF, Word & Excel", d: "Tamper-evident inspection reports with photographs, extracted declarations, findings, evidence crops and sign-off." },
  { icon: <LayoutGrid size={20} />, t: "Enforcement dashboard", d: "Track inspections, violation trends, categories and recent activity. Search and retrieve every past record." },
];

const RULES = [
  ["Rule 6", "Mandatory declarations - manufacturer/packer/importer, common name, net quantity, MRP, date, consumer care, origin, unit sale price"],
  ["Rule 7", "Minimum numeral height on the principal display panel (with physical calibration)"],
  ["Rule 8", "Principal display panel placement & spacing"],
  ["Rule 9", "Legibility and prominence (OCR confidence, contrast ratio, relative size)"],
  ["Rules 11 & 12", "Numeric value, standard unit symbols, no 'approx.' qualifiers"],
  ["Rule 13", "Quantity basis by weight / measure / number per commodity category"],
  ["Rule 15", "Category-specific declarations from configuration files"],
  ["Rule 27", "Registration - verified only against an authoritative source"],
  ["Section 18", "Misleading price expressions such as 'plus taxes'"],
];

export default function Landing() {
  const { user } = useAuth();
  return (
    <div className="landing">
      <nav className="lnav">
        <div className="brand" style={{ border: 0, margin: 0, padding: 0 }}>
          <div className="brand-logo"><ShieldCheck size={22} /></div>
          <div><div className="brand-name">SAFEMETRIC</div><div className="brand-sub">Legal Metrology Compliance AI</div></div>
        </div>
        <div className="links"><a href="#top">Home</a><a href="#features">Features</a><a href="#rules">Statutory Rules</a><a href="#architecture">Architecture</a></div>
        {user ? <Link className="btn btn-primary" to="/app/dashboard">Open Dashboard</Link> : (
          <div className="row"><Link className="btn" to="/login">Officer Sign In</Link><Link className="btn btn-primary" to="/register">Register Inspector</Link></div>
        )}
      </nav>
      <section className="hero" id="top">
        <span className="award"><Award size={14} /> SMART INDIA HACKATHON INNOVATION</span>
        <h1>Automated Legal Metrology Compliance for Packaged Commodities</h1>
        <p>Rule-based enforcement engine verifying label declarations directly from package photographs under the <b>Legal Metrology Act, 2009</b> and the <b>Legal Metrology (Packaged Commodities) Rules, 2011</b> - with zero external product database dependencies.</p>
        <div className="cta">
          <Link className="btn btn-primary" to={user ? "/app/inspections/new" : "/login"}><ScanLine size={18} /> Launch New Inspection</Link>
          <Link className="btn" to={user ? "/app/dashboard" : "/login"}><LayoutGrid size={18} /> Enforcement Dashboard</Link>
        </div>
        <div className="ticks">
          <span><CheckCircle2 size={15} /> PCR 2011 Rule 6(1) enforced</span>
          <span><CheckCircle2 size={15} /> Automated USP verification</span>
          <span><CheckCircle2 size={15} /> Tesseract OCR with bounding boxes</span>
          <span><CheckCircle2 size={15} /> Statutory PDF / DOCX / XLSX reports</span>
        </div>
      </section>
      <section className="lsection" id="features">
        <h2>Built for field inspectors</h2>
        <p className="sub">Every finding is traceable to the exact text and location on the package that produced it.</p>
        <div className="grid g3">{FEATURES.map((f) => <div className="fcard" key={f.t}><div className="ic">{f.icon}</div><h4>{f.t}</h4><p>{f.d}</p></div>)}</div>
      </section>
      <section className="lsection" id="rules">
        <h2>Statutory rules evaluated</h2>
        <p className="sub">Each check returns Pass, Non-Compliant, Needs Verification or Not Applicable with a written reason and evidence.</p>
        <div className="grid g3">{RULES.map(([r, d]) => <div className="fcard" key={r}><h4>{r}</h4><p>{d}</p></div>)}</div>
      </section>
      <section className="lsection" id="architecture">
        <h2>Architecture</h2>
        <p className="sub">React + TypeScript frontend · FastAPI backend · OpenCV + Tesseract OCR · SQLAlchemy (SQLite / PostgreSQL) · S3-compatible object storage.</p>
        <div className="arch">
          {["Image upload", "Quality check", "Preprocessing", "Multi-pass OCR", "Field extraction", "Rule engine", "Findings + evidence", "Database", "Reports"].map((n, i, a) => (
            <span key={n} className="row"><span className="node">{n}</span>{i < a.length - 1 && <Workflow size={16} className="arrow" />}</span>
          ))}
        </div>
        <div className="grid g3" style={{ marginTop: 30 }}>
          <div className="fcard"><div className="ic"><Database size={20} /></div><h4>Persistent repository</h4><p>Users, inspections, images, OCR results, extracted fields and rule findings in relational tables.</p></div>
          <div className="fcard"><div className="ic"><ShieldCheck size={20} /></div><h4>Secure by design</h4><p>bcrypt password hashing, JWT sessions, role-based access, audit log, upload validation.</p></div>
          <div className="fcard"><div className="ic"><FileSpreadsheet size={20} /></div><h4>Cloud deployable</h4><p>Single Docker image with Tesseract included; deploy to Render, Railway, AWS, GCP or Azure.</p></div>
        </div>
      </section>
      <footer className="lfoot">SafeMetric · Legal Metrology compliance inspection system · decisions support authorised officers and do not replace them.</footer>
    </div>
  );
}
