export type Role = "admin" | "inspector";

export interface User {
  id: number; name: string; email: string; role: Role; designation: string; jurisdiction: string; phone: string;
  is_active: boolean; created_at: string; last_login: string | null; inspections?: number;
}

export interface BBox { x: number; y: number; width: number; height: number }

export interface OcrWord { text: string; confidence: number; bbox: BBox }
export interface OcrLine { text: string; confidence: number; bbox: BBox; words: OcrWord[]; pass?: string; raw_text?: string; engine?: string }

export interface QualityMetric { value: number | string; unit?: string; grade: "GOOD" | "ACCEPTABLE" | "POOR" }
export interface InspectionImage {
  id: number; side: string; filename: string; content_type: string; size_bytes: number; width: number; height: number;
  display_width: number; display_height: number; has_display: boolean; sha256: string;
  panel_width_mm: number | null; panel_height_mm: number | null;
  quality_status: string; quality: { status?: string; metrics?: Record<string, QualityMetric>; warnings?: string[]; error?: string };
  preprocessing: string[]; rotation_applied: number;
  ocr?: { engine: string; full_text: string; normalized_text: string; mean_confidence: number; word_count: number;
          lines: OcrLine[]; passes: { variant: string; psm: number | null; engine?: string; description: string; lines: number; text?: string; error?: string | null }[] } | null;
}

export interface ExtractedField {
  field: string; label: string; value: string; normalized: Record<string, unknown>; confidence: number;
  status: "DETECTED" | "NOT_DETECTED" | "LOW_CONFIDENCE" | "NEEDS_VERIFICATION";
  source_image_id: number | null; source_image: string; source_side: string; evidence: string; bbox: BBox | null;
  alternatives: { value: string; confidence: number; side: string; evidence: string; bbox: BBox; source_image_id: number }[];
}

export interface EvidenceItem {
  field: string; label: string; text: string; value: string; confidence: number; image_id: number | null; image: string;
  side: string; bbox: BBox | null; contrast_ratio?: number | null;
}

export type FindingStatus = "PASS" | "NON_COMPLIANT" | "NEEDS_VERIFICATION" | "NOT_APPLICABLE";
export interface Finding {
  id: number; check_id: string; rule_no: string; rule_title: string; title: string; reference: string;
  severity: "HIGH" | "MEDIUM" | "LOW"; weight: number; applicable: boolean; applicability: string;
  required_data: string[]; condition: string; status: FindingStatus; reason: string; verification: string;
  evidence: EvidenceItem[]; recommendation: string;
}

export interface Recommendation {
  type: "RECTIFY_VIOLATION" | "VERIFY"; check_id: string; rule_no: string; title: string; urgency: string;
  action: string; reference: string;
}

export type OverallStatus = "COMPLIANT" | "NON_COMPLIANT" | "PARTIALLY_COMPLIANT" | "NEEDS_VERIFICATION" | "";

export interface InspectionSummary {
  id: number; reference: string; product_name: string; brand: string; category: string; category_label: string;
  is_imported: boolean; inspector_name: string; user_id: number; inspection_datetime: string; location: string;
  status: "DRAFT" | "PROCESSING" | "COMPLETED" | "FAILED"; stage: string; progress: number; stage_label: string;
  overall_status: OverallStatus; overall_label: string; score: number; passed: number; failed: number;
  needs_verification: number; not_applicable: number; ocr_confidence: number; image_count: number;
  manufacturer: string; created_at: string; analyzed_at: string | null; error: string;
}

export interface Attachment { id: number; filename: string; content_type: string; size_bytes: number; caption: string; uploaded_by: string; created_at: string }

export interface InspectionDetail extends InspectionSummary {
  manufacturer_info: string; registration_number: string; notes: string; all_panels_captured: boolean;
  earned_points: number; applicable_points: number;
  summary: { overall_reason?: string; formula?: string; counts?: Record<string, number>; coverage_conclusive?: boolean; engine?: string; unreadable_images?: string[];
             structured?: Record<string, StructuredValue>; ocr_problem?: string };
  recommendations: Recommendation[]; integrity_hash: string; processing_seconds: number;
  images: InspectionImage[]; fields: ExtractedField[]; findings: Finding[]; attachments: Attachment[]; inspector: User | null;
}

export interface StructuredValue {
  value: string; found: boolean; confidence: number; status: string; evidence: string; source_side: string;
  source_image_id: number | null; bbox: BBox | null; method: string;
}

export interface Meta {
  categories: { key: string; label: string }[]; sides: string[]; max_upload_mb: number; max_images: number;
  allowed_extensions: string[];
}

export interface Health {
  status: string; version: string; database: string; database_engine: string; storage: string;
  ocr: { available: boolean; version?: string; cmd: string; languages?: string[]; error?: string; tesseract_available?: boolean;
         engine?: string; engine_label?: string; ppocr?: { available: boolean; det_model?: string; rec_model?: string; runtime?: string; error?: string } };
  line_role_model?: { available: boolean; trained?: string };
}
