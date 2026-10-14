"""
Relational model.

    User 1─* Inspection 1─* InspectionImage 1─* OcrResult
                        1─* ExtractedField
                        1─* RuleFinding
                        1─* EvidenceAttachment
    RuleSetting  (admin can activate / deactivate individual checks)
    AuditLog     (who did what, when)

Image binaries are NOT stored in the database - only their storage keys.
"""
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(200), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), default="inspector", nullable=False)
    designation = Column(String(120), default="Inspector, Legal Metrology")
    jurisdiction = Column(String(160), default="")
    phone = Column(String(30), default="")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    last_login = Column(DateTime, nullable=True)

    inspections = relationship("Inspection", back_populates="inspector")


class Inspection(Base):
    __tablename__ = "inspections"
    id = Column(Integer, primary_key=True)
    reference = Column(String(24), unique=True, index=True)

    # product information entered by the inspector
    product_name = Column(String(200), index=True, default="")
    brand = Column(String(160), index=True, default="")
    category = Column(String(40), index=True, default="other")
    manufacturer_info = Column(String(400), default="")
    is_imported = Column(Boolean, default=False)
    registration_number = Column(String(80), default="")
    inspector_name = Column(String(120), default="")
    inspection_datetime = Column(DateTime, default=utcnow)
    location = Column(String(200), default="")
    notes = Column(Text, default="")
    all_panels_captured = Column(Boolean, default=False)  # inspector confirms every label panel was photographed

    # processing state
    status = Column(String(20), default="DRAFT", index=True)  # DRAFT | PROCESSING | COMPLETED | FAILED
    stage = Column(String(40), default="")
    progress = Column(Integer, default=0)
    error = Column(Text, default="")
    processing_seconds = Column(Float, default=0.0)

    # results
    overall_status = Column(String(30), index=True, default="")
    score = Column(Float, default=0.0)
    earned_points = Column(Float, default=0.0)
    applicable_points = Column(Float, default=0.0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    needs_verification = Column(Integer, default=0)
    not_applicable = Column(Integer, default=0)
    ocr_confidence = Column(Float, default=0.0)
    summary = Column(JSON, default=dict)
    recommendations = Column(JSON, default=list)
    integrity_hash = Column(String(64), default="")

    user_id = Column(Integer, ForeignKey("users.id"))
    inspector = relationship("User", back_populates="inspections")
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    analyzed_at = Column(DateTime, nullable=True)

    images = relationship("InspectionImage", back_populates="inspection", cascade="all, delete-orphan",
                          order_by="InspectionImage.id")
    fields = relationship("ExtractedField", back_populates="inspection", cascade="all, delete-orphan",
                          order_by="ExtractedField.id")
    findings = relationship("RuleFinding", back_populates="inspection", cascade="all, delete-orphan",
                            order_by="RuleFinding.id")
    attachments = relationship("EvidenceAttachment", back_populates="inspection", cascade="all, delete-orphan",
                               order_by="EvidenceAttachment.id")


class InspectionImage(Base):
    __tablename__ = "inspection_images"
    id = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    side = Column(String(20), default="front")
    original_filename = Column(String(255), default="")
    storage_key = Column(String(300), nullable=False)        # original upload
    display_key = Column(String(300), default="")            # orientation-corrected image (bboxes refer to this)
    content_type = Column(String(60), default="image/jpeg")
    size_bytes = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    display_width = Column(Integer, default=0)
    display_height = Column(Integer, default=0)
    sha256 = Column(String(64), default="")
    # optional physical calibration of the photographed panel (enables Rule 7 measurement)
    panel_width_mm = Column(Float, nullable=True)
    panel_height_mm = Column(Float, nullable=True)

    quality_status = Column(String(20), default="")          # GOOD | ACCEPTABLE | POOR
    quality = Column(JSON, default=dict)
    preprocessing = Column(JSON, default=list)
    rotation_applied = Column(Float, default=0.0)
    created_at = Column(DateTime, default=utcnow)

    inspection = relationship("Inspection", back_populates="images")
    ocr = relationship("OcrResult", back_populates="image", cascade="all, delete-orphan", uselist=False)


class OcrResult(Base):
    __tablename__ = "ocr_results"
    id = Column(Integer, primary_key=True)
    image_id = Column(Integer, ForeignKey("inspection_images.id", ondelete="CASCADE"), index=True)
    engine = Column(String(60), default="tesseract")
    engine_version = Column(String(40), default="")
    full_text = Column(Text, default="")
    normalized_text = Column(Text, default="")
    mean_confidence = Column(Float, default=0.0)
    word_count = Column(Integer, default=0)
    lines = Column(JSON, default=list)       # [{text, confidence, bbox, words:[{text,confidence,bbox}], pass}]
    passes = Column(JSON, default=list)      # diagnostics per OCR pass
    created_at = Column(DateTime, default=utcnow)

    image = relationship("InspectionImage", back_populates="ocr")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    id = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    field = Column(String(60), index=True)
    label = Column(String(120), default="")
    value = Column(Text, default="")
    normalized = Column(JSON, default=dict)   # parsed value e.g. {"amount":120,"currency":"INR"}
    confidence = Column(Float, default=0.0)
    status = Column(String(30), default="NOT_DETECTED")  # DETECTED | NOT_DETECTED | LOW_CONFIDENCE | NEEDS_VERIFICATION
    source_image_id = Column(Integer, nullable=True)
    source_image = Column(String(255), default="")
    source_side = Column(String(20), default="")
    evidence = Column(Text, default="")
    bbox = Column(JSON, nullable=True)
    alternatives = Column(JSON, default=list)  # other candidate readings (e.g. conflicting MRPs)
    created_at = Column(DateTime, default=utcnow)

    inspection = relationship("Inspection", back_populates="fields")


class RuleFinding(Base):
    __tablename__ = "rule_findings"
    id = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    check_id = Column(String(60), index=True)
    rule_no = Column(String(20), index=True)
    rule_title = Column(String(200), default="")
    title = Column(String(200), default="")
    reference = Column(String(200), default="")
    severity = Column(String(10), default="MEDIUM")
    weight = Column(Float, default=1.0)
    applicable = Column(Boolean, default=True)
    applicability = Column(Text, default="")
    required_data = Column(JSON, default=list)
    condition = Column(Text, default="")
    status = Column(String(30), default="NEEDS_VERIFICATION")  # PASS | NON_COMPLIANT | NEEDS_VERIFICATION | NOT_APPLICABLE
    reason = Column(Text, default="")
    verification = Column(Text, default="")
    evidence = Column(JSON, default=list)
    recommendation = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    inspection = relationship("Inspection", back_populates="findings")


class EvidenceAttachment(Base):
    __tablename__ = "evidence_attachments"
    id = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    storage_key = Column(String(300), nullable=False)
    original_filename = Column(String(255), default="")
    content_type = Column(String(60), default="")
    size_bytes = Column(Integer, default=0)
    caption = Column(String(300), default="")
    uploaded_by = Column(String(120), default="")
    created_at = Column(DateTime, default=utcnow)

    inspection = relationship("Inspection", back_populates="attachments")


class RuleSetting(Base):
    __tablename__ = "rule_settings"
    id = Column(Integer, primary_key=True)
    check_id = Column(String(60), unique=True, index=True)
    active = Column(Boolean, default=True)
    updated_by = Column(String(200), default="")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    user_email = Column(String(200), default="")
    action = Column(String(60))
    detail = Column(Text, default="")
    ip = Column(String(64), default="")
    created_at = Column(DateTime, default=utcnow, index=True)
