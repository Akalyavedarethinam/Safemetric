import { useMemo, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import type { BBox, ExtractedField, InspectionImage } from "../lib/types";
import { AuthImage, FieldBadge } from "./ui";

/**
 * Shows an inspection image with OCR bounding boxes. Boxes are expressed in display-image pixels,
 * so they are drawn as percentages of the image size and stay aligned at any zoom level.
 */
export default function EvidenceViewer({ image, fields, highlight, onSelect, showLines: initialLines = false }: {
  image: InspectionImage; fields: ExtractedField[]; highlight?: string | null; onSelect?: (field: string | null) => void; showLines?: boolean;
}) {
  const [showLines, setShowLines] = useState(initialLines);
  const [showFields, setShowFields] = useState(true);
  const W = image.display_width || image.width, H = image.display_height || image.height;
  const pct = (b: BBox) => ({ left: `${(b.x / W) * 100}%`, top: `${(b.y / H) * 100}%`, width: `${(b.width / W) * 100}%`, height: `${(b.height / H) * 100}%` });
  const mine = useMemo(() => fields.filter((f) => f.source_image_id === image.id && f.bbox && f.status !== "NOT_DETECTED"), [fields, image.id]);

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row small">
        <button className="btn btn-outline btn-sm" onClick={() => setShowFields((v) => !v)}>{showFields ? <EyeOff size={14} /> : <Eye size={14} />} Declarations</button>
        <button className="btn btn-outline btn-sm" onClick={() => setShowLines((v) => !v)}>{showLines ? <EyeOff size={14} /> : <Eye size={14} />} All OCR lines</button>
        <span className="muted tiny">Click a box to select the declaration. Coordinates refer to the orientation-corrected image.</span>
      </div>
      <div style={{ textAlign: "center" }}>
        <div className="viewer">
          <AuthImage path={`/api/files/images/${image.id}?variant=display`} alt={`${image.side} panel`} />
          {showLines && image.ocr?.lines.map((l, i) => (
            <div key={`l${i}`} className="bb line" style={pct(l.bbox)} title={`${l.text} (${l.confidence.toFixed(0)}%)`} />
          ))}
          {showFields && mine.map((f) => (
            <div key={f.field} className={`bb ${highlight === f.field ? "hl" : ""}`} style={pct(f.bbox!)}
              title={`${f.label}: ${f.value} (${f.confidence.toFixed(0)}%)`} onClick={() => onSelect?.(highlight === f.field ? null : f.field)}>
              <span className="t">{f.label}</span>
            </div>
          ))}
        </div>
      </div>
      {highlight && (() => {
        const f = fields.find((x) => x.field === highlight);
        if (!f) return null;
        return (
          <div className="alert alert-info">
            <div><b>{f.label}</b> <FieldBadge status={f.status} /> · OCR confidence {f.confidence.toFixed(1)}% · {f.source_side} panel<br />
              <span className="mono small">“{f.evidence}”</span>
              {f.bbox && <div className="tiny muted">Location: x={f.bbox.x}, y={f.bbox.y}, w={f.bbox.width}, h={f.bbox.height} px</div>}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
