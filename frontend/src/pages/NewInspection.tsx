import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowLeft, ArrowRight, Camera, Check, FolderOpen, ImagePlus, Loader2, Play, RefreshCcw, Ruler, ShieldCheck, Trash2, Upload } from "lucide-react";
import CameraCapture, { cameraSupported, type Shot } from "../components/CameraCapture";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { SIDE_LABELS, fmtBytes } from "../lib/format";
import type { InspectionDetail, Meta } from "../lib/types";
import { Alert, useAsync } from "../components/ui";

interface Pending { id: string; file: File; url: string; side: string; w: string; h: string; dims?: string; error?: string; source?: "camera" | "file"; warn?: string }

const STAGES = [
  ["UPLOADING", "Uploading"], ["CHECKING_IMAGES", "Checking image"], ["PREPROCESSING", "Processing images"],
  ["OCR", "Running OCR"], ["EXTRACTING", "Extracting declarations"], ["RULES", "Checking rules"],
  ["SAVING", "Saving inspection"], ["COMPLETE", "Complete"],
] as const;
const DEFAULT_SIDES = ["front", "back", "left", "right", "top", "bottom"];

function localIso(d = new Date()) {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function NewInspection() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { data: meta } = useAsync(() => api.get<Meta>("/api/meta"), []);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    product_name: "", brand: "", category: "food", manufacturer_info: "", is_imported: false, registration_number: "",
    inspector_name: user?.name || "", inspection_datetime: localIso(), location: "", notes: "", all_panels_captured: false,
  });
  const [files, setFiles] = useState<Pending[]>([]);
  const [drag, setDrag] = useState(false);
  const [calib, setCalib] = useState(false);
  const [err, setErr] = useState("");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState<string>("");
  const [pct, setPct] = useState(0);
  const [inspId, setInspId] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const nativeCam = useRef<HTMLInputElement>(null);
  const [camOpen, setCamOpen] = useState(false);
  const maxMb = meta?.max_upload_mb ?? 10;
  const allowed = [".jpg", ".jpeg", ".png", ".webp"];

  useEffect(() => () => files.forEach((f) => URL.revokeObjectURL(f.url)), []); // eslint-disable-line

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  const addFiles = (list: FileList | File[], opts?: { sides?: string[]; source?: "camera" | "file"; warns?: string[] }) => {
    const next: Pending[] = [];
    const used = new Set(files.map((f) => f.side));
    Array.from(list).forEach((file, i) => {
      const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
      const side = opts?.sides?.[i] || DEFAULT_SIDES.find((s) => !used.has(s)) || "additional";
      used.add(side);
      const p: Pending = { id: Math.random().toString(36).slice(2), file, url: URL.createObjectURL(file), side, w: "", h: "",
        source: opts?.source || "file", warn: opts?.warns?.[i] };
      if (!allowed.includes(ext)) p.error = `Unsupported file type ${ext}. Use JPG, PNG or WEBP.`;
      else if (file.size > maxMb * 1024 * 1024) p.error = `File exceeds ${maxMb} MB.`;
      next.push(p);
    });
    setFiles((f) => [...f, ...next].slice(0, meta?.max_images ?? 12));
  };
  const openCamera = () => { if (cameraSupported()) setCamOpen(true); else nativeCam.current?.click(); };
  const onShots = (shots: Shot[]) => {
    setCamOpen(false);
    // a camera shot replaces an earlier image of the same side (except "additional")
    const sidesTaken = new Set(shots.map((s) => s.side).filter((s) => s !== "additional"));
    setFiles((x) => x.filter((y) => { if (sidesTaken.has(y.side)) { URL.revokeObjectURL(y.url); return false; } return true; }));
    shots.forEach((s) => URL.revokeObjectURL(s.url));
    setTimeout(() => addFiles(shots.map((s) => s.file), { sides: shots.map((s) => s.side), source: "camera",
      warns: shots.map((s) => s.quality.ok ? "" : s.quality.issues.join(". ")) }), 0);
  };

  const valid = files.filter((f) => !f.error);
  const canNext1 = (form.product_name.trim() || form.brand.trim()) && form.category;
  const hasFront = valid.some((f) => f.side === "front");

  const poll = (id: number) => new Promise<void>((resolve, reject) => {
    const tick = async () => {
      try {
        const p = await api.get<{ status: string; stage: string; progress: number; error: string }>(`/api/inspections/${id}/progress`);
        setStage(p.stage); setPct(p.progress);
        if (p.status === "COMPLETED") return resolve();
        if (p.status === "FAILED") return reject(new Error(p.error || "Analysis failed."));
        setTimeout(tick, 900);
      } catch (e) { reject(e); }
    };
    tick();
  });

  const analyze = async () => {
    if (running) return;
    setErr(""); setRunning(true); setStep(3);
    try {
      let id = inspId;
      if (!id) {
        setStage("UPLOADING"); setPct(1);
        const body = { ...form, inspection_datetime: form.inspection_datetime ? new Date(form.inspection_datetime).toISOString() : null };
        const created = await api.post<InspectionDetail>("/api/inspections", body);
        id = created.id;
        const fd = new FormData();
        valid.forEach((f) => { fd.append("files", f.file); fd.append("sides", f.side); fd.append("panel_width_mm", f.w); fd.append("panel_height_mm", f.h); });
        await api.post(`/api/inspections/${id}/images`, fd);
        setInspId(id);
      }
      setPct(3);
      await api.post(`/api/inspections/${id}/analyze`);
      await poll(id!);
      setStage("COMPLETE"); setPct(100);
      setTimeout(() => nav(`/app/inspections/${id}`, { state: { justAnalyzed: true } }), 600);
    } catch (e) {
      setErr((e as Error).message);
      setRunning(false);
    }
  };

  const stageIndex = STAGES.findIndex(([k]) => k === stage);
  const preview = useMemo(() => valid.find((f) => f.side === "front") || valid[0], [valid]);

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div>
        <div className="eyebrow">Commodity intake</div>
        <h2 style={{ fontSize: 26, fontWeight: 800 }}>Upload Packaged Product Images</h2>
        <p className="muted" style={{ margin: "4px 0 0" }}>Photograph every panel that carries declarations. The uploaded photographs are the sole ground truth - no product database is consulted.</p>
      </div>
      <div className="wizard">
        {["Product details", "Upload images", "Analyze", "Results"].map((t, i) => (
          <div key={t} className={`wstep ${step === i + 1 ? "active" : step > i + 1 ? "done" : ""}`}><span className="n">{step > i + 1 ? <Check size={14} /> : i + 1}</span>{t}</div>
        ))}
      </div>

      {step === 1 && (
        <div className="card">
          <div className="card-head"><div className="grow"><h3>Step 1 — Product information</h3><p>Used to select the applicable rules (category, import status) and to identify the record.</p></div></div>
          <div className="card-pad grid g3">
            <div className="field"><label>Packaged commodity name *</label><input className="input" value={form.product_name} onChange={(e) => set("product_name", e.target.value)} placeholder="e.g. Basmati Rice, Sunflower Oil" /></div>
            <div className="field"><label>Brand</label><input className="input" value={form.brand} onChange={(e) => set("brand", e.target.value)} /></div>
            <div className="field"><label>Product category *</label>
              <select className="select" value={form.category} onChange={(e) => set("category", e.target.value)}>
                {(meta?.categories ?? [{ key: "food", label: "Food" }]).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select><span className="hint">Controls category-specific rules (Rules 6, 13, 15).</span></div>
            <div className="field span2"><label>Manufacturer / packer / importer (if known)</label><input className="input" value={form.manufacturer_info} onChange={(e) => set("manufacturer_info", e.target.value)} placeholder="Optional - for reference only, never used as a substitute for the label" /></div>
            <div className="field"><label>LM registration number (Rule 27)</label><input className="input" value={form.registration_number} onChange={(e) => set("registration_number", e.target.value)} placeholder="Optional" /></div>
            <div className="field"><label>Inspecting officer</label><input className="input" value={form.inspector_name} onChange={(e) => set("inspector_name", e.target.value)} /></div>
            <div className="field"><label>Inspection date / time</label><input className="input" type="datetime-local" value={form.inspection_datetime} onChange={(e) => set("inspection_datetime", e.target.value)} /></div>
            <div className="field"><label>Location / premises</label><input className="input" value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="Shop, market, warehouse, e-commerce URL…" /></div>
            <label className="check span2"><input type="checkbox" checked={form.is_imported} onChange={(e) => set("is_imported", e.target.checked)} />
              <span><b>Imported product</b><br /><span className="muted small">Enables importer and country-of-origin declarations.</span></span></label>
            <div className="field" style={{ gridColumn: "1 / -1" }}><label>Officer remarks</label><textarea className="textarea" value={form.notes} onChange={(e) => set("notes", e.target.value)} /></div>
          </div>
          <div className="card-pad row" style={{ justifyContent: "flex-end", borderTop: "1px solid var(--line)" }}>
            <button className="btn btn-primary" disabled={!canNext1} onClick={() => setStep(2)}>Continue to images <ArrowRight size={16} /></button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="card">
          <div className="card-head"><div className="grow"><h3>Step 2 — Package photographs</h3><p>One or more images. Assign each to the package side it shows; mark the principal display panel as Front.</p></div>
            <button className="btn btn-outline btn-sm" onClick={() => setCalib((v) => !v)}><Ruler size={14} /> {calib ? "Hide" : "Add"} physical calibration</button></div>
          <div className="card-pad stack">
            <div className={`dropzone ${drag ? "drag" : ""}`} aria-label="Drop package photos here"
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}>
              <div className="up"><Upload size={24} /></div>
              <h4>Scan the package with your camera, or upload photos</h4>
              <div className="muted small">Take a photo of each labelled side with the camera, or drag &amp; drop / browse existing photos. Both can be combined.</div>
              <div className="row" style={{ gap: 10, justifyContent: "center", margin: "12px 0 4px", flexWrap: "wrap" }}>
                <button type="button" className="btn btn-primary" onClick={(e) => { e.stopPropagation(); openCamera(); }}><Camera size={16} /> Scan with camera</button>
                <button type="button" className="btn btn-outline" onClick={(e) => { e.stopPropagation(); input.current?.click(); }}><FolderOpen size={16} /> Upload files</button>
              </div>
              <div className="pill-row"><span className="pill">Formats: JPG, JPEG, PNG, WEBP</span><span className="pill">Maximum size: {maxMb} MB each</span><span className="pill">Up to {meta?.max_images ?? 12} images</span></div>
              <input ref={input} type="file" accept=".jpg,.jpeg,.png,.webp,image/*" multiple hidden onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
              <input ref={nativeCam} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { if (e.target.files) addFiles(e.target.files, { source: "camera" }); e.target.value = ""; }} />
            </div>
            {calib && <Alert kind="info">Optional: enter the physical width/height (mm) of the panel shown in each photo, with the photo cropped to that panel. This lets Rule 7 convert pixel measurements to millimetres. Without it Rule 7 is reported as Needs Verification.</Alert>}
            {files.length > 0 && (
              <div className="thumbs">
                {files.map((f) => (
                  <div className="thumb" key={f.id}>
                    <div className="img"><img src={f.url} alt={f.file.name} onLoad={(e) => { const i = e.currentTarget; setFiles((x) => x.map((y) => y.id === f.id ? { ...y, dims: `${i.naturalWidth}×${i.naturalHeight}px` } : y)); }} />
                      <button className="btn btn-danger btn-icon rm" style={{ background: "#fff" }} aria-label="Remove" onClick={() => { URL.revokeObjectURL(f.url); setFiles((x) => x.filter((y) => y.id !== f.id)); }}><Trash2 size={14} /></button></div>
                    <div className="body">
                      <div className="small" style={{ wordBreak: "break-all" }}><b>{f.file.name}</b><div className="tiny muted">{f.source === "camera" && <span className="cam-badge"><Camera size={11} /> Camera</span>} {fmtBytes(f.file.size)} {f.dims && `· ${f.dims}`}</div></div>
                      {f.warn && <div className="tiny" style={{ color: "var(--amber)" }}><AlertTriangle size={12} /> {f.warn} - consider retaking.</div>}
                      {f.error ? <Alert kind="error">{f.error}</Alert> : (
                        <select className="select" value={f.side} onChange={(e) => setFiles((x) => x.map((y) => y.id === f.id ? { ...y, side: e.target.value } : y))} aria-label="Package side">
                          {(meta?.sides ?? Object.keys(SIDE_LABELS)).map((s) => <option key={s} value={s}>{SIDE_LABELS[s] || s}</option>)}
                        </select>)}
                      {calib && !f.error && (
                        <div className="row" style={{ gap: 6 }}>
                          <input className="input" style={{ flex: 1 }} placeholder="Width mm" inputMode="decimal" value={f.w} onChange={(e) => setFiles((x) => x.map((y) => y.id === f.id ? { ...y, w: e.target.value } : y))} />
                          <input className="input" style={{ flex: 1 }} placeholder="Height mm" inputMode="decimal" value={f.h} onChange={(e) => setFiles((x) => x.map((y) => y.id === f.id ? { ...y, h: e.target.value } : y))} />
                        </div>)}
                    </div>
                  </div>
                ))}
                <div className="thumb" style={{ display: "grid", placeItems: "center", minHeight: 200, borderStyle: "dashed", gap: 8, padding: 12 }}>
                  <span className="muted small" style={{ textAlign: "center" }}><ImagePlus /><br />Add another side</span>
                  <button type="button" className="btn btn-outline btn-sm" onClick={openCamera}><Camera size={14} /> Camera</button>
                  <button type="button" className="btn btn-outline btn-sm" onClick={() => input.current?.click()}><FolderOpen size={14} /> Files</button>
                </div>
              </div>
            )}
            {valid.length > 0 && !hasFront && <Alert kind="warn">No image is marked as <b>Front (PDP)</b>. Rule 8 placement checks will need verification.</Alert>}
            <label className="check"><input type="checkbox" checked={form.all_panels_captured} onChange={(e) => set("all_panels_captured", e.target.checked)} />
              <span><b>I confirm every label panel of this package has been photographed.</b><br /><span className="muted small">Only then can a declaration that is not found be treated as missing (Non-Compliant) rather than Needs Verification.</span></span></label>
            <div className="alert alert-info"><ShieldCheck size={16} /><div><b>Legal Metrology physical intake:</b> the uploaded package photographs serve as the sole ground truth for regulatory verification. No pre-seeded commodity database lookups are performed.</div></div>
          </div>
          <div className="card-pad row" style={{ justifyContent: "space-between", borderTop: "1px solid var(--line)" }}>
            <button className="btn btn-outline" onClick={() => setStep(1)}><ArrowLeft size={16} /> Back</button>
            <button className="btn btn-primary" disabled={valid.length === 0 || running} onClick={analyze}><Play size={16} /> Analyze {valid.length} image{valid.length !== 1 && "s"}</button>
          </div>
        </div>
      )}

      {camOpen && <CameraCapture usedSides={files.filter((f) => !f.error).map((f) => f.side)}
        sides={meta?.sides ?? Object.keys(SIDE_LABELS)} onDone={onShots} onClose={() => setCamOpen(false)} />}

      {step >= 3 && (
        <div className="grid g2">
          <div className="card card-pad">
            <div className="scanner">
              {preview && <img src={preview.url} alt="package being analysed" />}
              <span className="corner c1" /><span className="corner c2" /><span className="corner c3" /><span className="corner c4" />
              {running && <>
                <div className="beam" />
                <span className="tag" style={{ top: "28%", left: "30%" }}>DETECTING…</span>
                <span className="tag" style={{ top: "52%", left: "14%", animationDelay: ".5s" }}>EXTRACTING…</span>
                <span className="box" style={{ top: "33%", left: "35%", width: "38%", height: "9%" }} />
                <span className="box" style={{ top: "57%", left: "20%", width: "30%", height: "8%", animationDelay: ".7s" }} />
              </>}
            </div>
            <div className="row small muted" style={{ marginTop: 12, justifyContent: "space-between" }}>
              <span>{valid.length} image(s): {valid.map((f) => f.side).join(", ")}</span>
              <span>{form.product_name || form.brand}</span>
            </div>
          </div>
          <div className="card card-pad stack">
            <div>
              <h3 style={{ fontSize: 18 }}>{err ? "Analysis stopped" : stage === "COMPLETE" ? "Analysis complete" : "Analyzing package…"}</h3>
              <p className="muted small" style={{ margin: "4px 0 10px" }}>Real OCR and the deterministic rule engine are running on the server. Large photos can take 10-30 seconds per image.</p>
              <div className="bar"><div style={{ width: `${pct}%` }} /></div>
              <div className="tiny muted" style={{ marginTop: 4 }}>{pct}%</div>
            </div>
            <div className="steps">
              {STAGES.map(([k, label], i) => {
                const cls = stage === "COMPLETE" || i < stageIndex ? "done" : i === stageIndex ? (err ? "" : "now") : "";
                return <div key={k} className={`step ${cls}`}><span className="n">{cls === "done" ? <Check size={14} /> : cls === "now" ? <Loader2 size={14} className="spin" /> : i + 1}</span>{label}</div>;
              })}
            </div>
            {err && <>
              <Alert kind="error"><b>{err}</b></Alert>
              <div className="row">
                <button className="btn btn-primary" onClick={analyze}><RefreshCcw size={16} /> Retry analysis</button>
                {inspId ? <button className="btn btn-outline" onClick={() => nav(`/app/inspections/${inspId}`)}>Open record</button>
                  : <button className="btn btn-outline" onClick={() => setStep(2)}><ArrowLeft size={16} /> Back to images</button>}
              </div>
            </>}
            {!err && <div className="alert alert-warn"><AlertTriangle size={16} /><div className="small">Please keep this page open. Duplicate submissions are disabled while the analysis runs.</div></div>}
          </div>
        </div>
      )}
    </div>
  );
}
