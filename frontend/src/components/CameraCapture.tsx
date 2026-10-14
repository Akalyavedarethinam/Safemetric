import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Camera, CameraOff, Check, RefreshCcw, SwitchCamera, X, Zap, ZapOff } from "lucide-react";
import { SIDE_LABELS } from "../lib/format";

/**
 * Live camera scanner for package panels.
 *
 * Opens the device camera (rear camera on phones), shows a framing guide, and captures each package side as a
 * full-resolution JPEG. Each shot gets a quick on-device quality check (sharpness + exposure) so the inspector can
 * retake a blurred or dark photo before it is uploaded. Captured photos are handed back as ordinary File objects,
 * so they go through exactly the same upload / OCR pipeline as selected files.
 *
 * Browsers only allow the camera on a secure origin (https:// or http://localhost / 127.0.0.1). Where the live
 * camera is not available the caller falls back to the phone's native camera through <input capture>.
 */

export interface Shot { file: File; side: string; url: string; quality: Quality }
interface Quality { sharpness: number; brightness: number; ok: boolean; issues: string[] }

const ORDER = ["front", "back", "left", "right", "top", "bottom", "additional"];

export function cameraSupported(): boolean {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && window.isSecureContext;
}

function assess(canvas: HTMLCanvasElement): Quality {
  // down-sample to ~320 px wide and compute the variance of a Laplacian (sharpness) and the mean luminance
  const w = 320, h = Math.max(1, Math.round((canvas.height / canvas.width) * 320));
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(canvas, 0, 0, w, h);
  const d = ctx.getImageData(0, 0, w, h).data;
  const g = new Float32Array(w * h);
  let sum = 0;
  for (let i = 0; i < w * h; i++) { g[i] = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2]; sum += g[i]; }
  const brightness = sum / (w * h);
  let m = 0, m2 = 0, n = 0;
  for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
    const i = y * w + x;
    const lap = 4 * g[i] - g[i - 1] - g[i + 1] - g[i - w] - g[i + w];
    m += lap; m2 += lap * lap; n++;
  }
  const sharpness = n ? m2 / n - (m / n) ** 2 : 0;
  // exposure is judged on the central 60 % of the frame (where the label is)
  let cSum = 0, cN = 0;
  for (let y = Math.floor(h * 0.2); y < h * 0.8; y++) for (let x = Math.floor(w * 0.2); x < w * 0.8; x++) { cSum += g[y * w + x]; cN++; }
  const centre = cN ? cSum / cN : brightness;
  // glare = blown-out (clipped) pixels that are NOT connected to the frame border; a white table or studio
  // background touches the border and is ignored (same idea as the server-side quality check)
  const clip = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) clip[i] = g[i] >= 252 ? 1 : 0;
  const stack: number[] = [];
  for (let x = 0; x < w; x++) { stack.push(x, (h - 1) * w + x); }
  for (let y = 0; y < h; y++) { stack.push(y * w, y * w + w - 1); }
  while (stack.length) {
    const i = stack.pop()!;
    if (clip[i] !== 1) continue;
    clip[i] = 2;
    const x = i % w;
    if (x > 0) stack.push(i - 1); if (x < w - 1) stack.push(i + 1);
    if (i >= w) stack.push(i - w); if (i < w * (h - 1)) stack.push(i + w);
  }
  let glare = 0;
  for (let i = 0; i < w * h; i++) if (clip[i] === 1) glare++;
  const issues: string[] = [];
  if (sharpness < 60) issues.push("The photo looks blurred - hold the phone steady and tap to focus");
  if (centre < 60) issues.push("The photo is too dark - add light or turn on the torch");
  if (glare / (w * h) > 0.03) issues.push("Glare on the label - tilt the pack slightly or move away from direct light");
  return { sharpness: Math.round(sharpness), brightness: Math.round(brightness), ok: issues.length === 0, issues };
}

export default function CameraCapture({ usedSides, sides, onDone, onClose }: {
  usedSides: string[]; sides: string[]; onDone: (shots: Shot[]) => void; onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>("");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [torch, setTorch] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [shots, setShots] = useState<Shot[]>([]);
  const [review, setReview] = useState<Shot | null>(null);
  const [flash, setFlash] = useState(false);
  const firstFree = () => {
    const used = new Set([...usedSides, ...shots.map((s) => s.side)]);
    return ORDER.find((s) => sides.includes(s) && !used.has(s)) || "additional";
  };
  const [side, setSide] = useState<string>(() => ORDER.find((s) => sides.includes(s) && !usedSides.includes(s)) || "additional");

  const stop = useCallback(() => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; }, []);

  const start = useCallback(async (id?: string) => {
    stop();
    setReady(false); setError(""); setTorch(false);
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: id ? { deviceId: { exact: id }, width: { ideal: 3840 }, height: { ideal: 2160 } }
          : { facingMode: { ideal: "environment" }, width: { ideal: 3840 }, height: { ideal: 2160 } },
      });
      stream.current = s;
      const track = s.getVideoTracks()[0];
      const caps = (track.getCapabilities?.() || {}) as MediaTrackCapabilities & { torch?: boolean; focusMode?: string[] };
      setTorchAvailable(!!caps.torch);
      if (caps.focusMode?.includes("continuous")) {
        track.applyConstraints({ advanced: [{ focusMode: "continuous" } as MediaTrackConstraintSet] }).catch(() => undefined);
      }
      if (video.current) { video.current.srcObject = s; await video.current.play().catch(() => undefined); }
      const list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
      setDevices(list);
      setDeviceId(track.getSettings().deviceId || id || "");
      setReady(true);
    } catch (e) {
      const name = (e as DOMException)?.name;
      setError(name === "NotAllowedError" ? "Camera permission was denied. Allow camera access for this site in the browser settings and try again."
        : name === "NotFoundError" ? "No camera was found on this device."
          : name === "NotReadableError" ? "The camera is being used by another application. Close it and try again."
            : `The camera could not be started (${name || "unknown error"}).`);
    }
  }, [stop]);

  useEffect(() => { start(); return stop; }, []); // eslint-disable-line

  const toggleTorch = async () => {
    const track = stream.current?.getVideoTracks()[0];
    if (!track) return;
    try { await track.applyConstraints({ advanced: [{ torch: !torch } as MediaTrackConstraintSet] }); setTorch(!torch); } catch { /* not supported */ }
  };

  const capture = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    const quality = assess(c);
    setFlash(true); setTimeout(() => setFlash(false), 180);
    c.toBlob((blob) => {
      if (!blob) return;
      const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
      const file = new File([blob], `camera_${side}_${stamp}.jpg`, { type: "image/jpeg", lastModified: Date.now() });
      setReview({ file, side, url: URL.createObjectURL(blob), quality });
    }, "image/jpeg", 0.92);
  };

  const keep = () => {
    if (!review) return;
    const next = [...shots.filter((s) => s.side !== review.side || review.side === "additional"), review];
    setShots(next);
    setReview(null);
    const used = new Set([...usedSides, ...next.map((s) => s.side)]);
    setSide(ORDER.find((s) => sides.includes(s) && !used.has(s)) || "additional");
  };
  const retake = () => { if (review) URL.revokeObjectURL(review.url); setReview(null); };
  const finish = () => { stop(); onDone(shots); };
  const cancel = () => { stop(); shots.forEach((s) => URL.revokeObjectURL(s.url)); if (review) URL.revokeObjectURL(review.url); onClose(); };

  return (
    <div className="modal-bg cam-bg" role="dialog" aria-modal="true" aria-label="Scan package with camera">
      <div className="cam">
        <div className="cam-head">
          <div className="grow"><b>Scan package with camera</b><div className="tiny muted">Photograph each side that carries declarations. Fill the frame with the label, keep it flat and avoid glare.</div></div>
          <button className="btn btn-icon btn-ghost" aria-label="Close camera" onClick={cancel}><X size={18} /></button>
        </div>

        <div className="cam-stage">
          <video ref={video} playsInline muted autoPlay style={{ visibility: review || error ? "hidden" : "visible" }} />
          {error ? (
            <div className="cam-error"><CameraOff size={34} /><p>{error}</p><button className="btn btn-outline btn-sm" onClick={() => start(deviceId || undefined)}><RefreshCcw size={14} /> Try again</button></div>
          ) : review ? (
            <div className="cam-review">
              <img src={review.url} alt={`Captured ${review.side}`} />
              <div className={`cam-q ${review.quality.ok ? "ok" : "warn"}`}>
                {review.quality.ok ? <><Check size={16} /> Good photo - sharp and well lit</>
                  : <><AlertTriangle size={16} /> <span>{review.quality.issues.join(". ")}.</span></>}
              </div>
            </div>
          ) : (
            <>
              {ready && <div className="cam-guide"><span className="tl" /><span className="tr" /><span className="bl" /><span className="br" />
                <div className="cam-tag">{SIDE_LABELS[side] || side}</div></div>}
              {!ready && <div className="cam-wait">Starting camera…</div>}
              {flash && <div className="cam-flash" />}
            </>
          )}
        </div>

        <div className="cam-bar">
          <label className="small cam-side">Side
            <select className="select" value={side} onChange={(e) => setSide(e.target.value)} disabled={!!review}>
              {sides.map((s) => <option key={s} value={s}>{SIDE_LABELS[s] || s}{shots.some((x) => x.side === s) ? " ✓" : ""}</option>)}
            </select>
          </label>
          {review ? (
            <div className="row" style={{ gap: 8 }}>
              <button className="btn btn-outline" onClick={retake}><RefreshCcw size={16} /> Retake</button>
              <button className="btn btn-primary" onClick={keep}><Check size={16} /> Use photo</button>
            </div>
          ) : (
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              {devices.length > 1 && (
                <button className="btn btn-outline btn-icon" title="Switch camera" aria-label="Switch camera" onClick={() => {
                  const i = devices.findIndex((d) => d.deviceId === deviceId);
                  start(devices[(i + 1) % devices.length].deviceId);
                }}><SwitchCamera size={18} /></button>)}
              {torchAvailable && <button className="btn btn-outline btn-icon" title="Torch" aria-label="Torch" onClick={toggleTorch}>{torch ? <ZapOff size={18} /> : <Zap size={18} />}</button>}
              <button className="cam-shutter" aria-label={`Capture ${SIDE_LABELS[side] || side}`} disabled={!ready} onClick={capture}><Camera size={26} /></button>
            </div>
          )}
          <button className="btn btn-primary" disabled={shots.length === 0 || !!review} onClick={finish}>Done ({shots.length})</button>
        </div>

        {shots.length > 0 && (
          <div className="cam-strip">
            {shots.map((s) => (
              <div key={s.url} className="cam-thumb" title={s.quality.ok ? "Good photo" : s.quality.issues.join(". ")}>
                <img src={s.url} alt={s.side} />
                <span className={s.quality.ok ? "ok" : "warn"}>{SIDE_LABELS[s.side] || s.side}</span>
                <button aria-label={`Remove ${s.side}`} onClick={() => { URL.revokeObjectURL(s.url); setShots((x) => x.filter((y) => y !== s)); if (!review) setSide(s.side); }}><X size={12} /></button>
              </div>
            ))}
            <div className="tiny muted" style={{ alignSelf: "center" }}>Next: {SIDE_LABELS[firstFree()] || firstFree()}</div>
          </div>
        )}
      </div>
    </div>
  );
}
