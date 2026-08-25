"""
PDF Renderer Service — Feature #21: Digital Emergency Operation Record (PDF)

Renders a formal, professional Clinical Operation Record PDF using reportlab.
"""

import io
import os
import re
from pathlib import Path
from typing import Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.record import OperationRecordData

# Base directory for storing generated PDFs
STORAGE_DIR = Path("storage/operation_records")


def sanitize_filename(tx_id: str) -> str:
    """Sanitizes tx_id to prevent path traversal attacks."""
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "", tx_id)
    return f"operation-record-{clean}.pdf"


def render_operation_record_pdf(
    data: OperationRecordData,
    output_dir: Path = STORAGE_DIR,
) -> Tuple[str, bytes]:
    """
    Renders OperationRecordData into a professional PDF document,
    saves it to disk under output_dir, and returns (file_path, pdf_bytes).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(data.tx_id)
    file_path = str(output_dir / filename)

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    header_title_style = ParagraphStyle(
        "HeaderTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0F172A"),
    )
    header_subtitle_style = ParagraphStyle(
        "HeaderSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748B"),
    )
    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1E293B"),
    )
    body_bold_style = ParagraphStyle(
        "BodyBoldCustom",
        parent=body_style,
        fontName="Helvetica-Bold",
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
    )
    footer_style = ParagraphStyle(
        "FooterCustom",
        parent=styles["Italic"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#94A3B8"),
        alignment=1,  # Centered
    )

    story = []

    # ─────────────────────────────────────────────────────────────────────────
    # 1. HEADER BANNER
    # ─────────────────────────────────────────────────────────────────────────
    header_table_data = [
        [
            Paragraph("MEDICARE CLINICAL NETWORK — EMERGENCY COORDINATOR", header_subtitle_style),
            Paragraph(f"<b>TX ID:</b> {data.tx_id}", ParagraphStyle("TxIdH", parent=body_style, alignment=2)),
        ],
        [
            Paragraph("DIGITAL EMERGENCY OPERATION RECORD", header_title_style),
            Paragraph(f"<b>Audit Trace:</b> {data.audit_id}", ParagraphStyle("AuditH", parent=body_style, alignment=2)),
        ],
        [
            Paragraph(f"Closed: {data.closed_at}", header_subtitle_style),
            Paragraph(f"<b>Final Status:</b> {data.status}", ParagraphStyle("StatH", parent=body_bold_style, alignment=2)),
        ],
    ]
    header_table = Table(header_table_data, colWidths=[340, 200])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=8))

    # ─────────────────────────────────────────────────────────────────────────
    # 2. PATIENT & CASE CONTEXT
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Paragraph("1. PATIENT & CASE CONTEXT", section_heading_style))
    p = data.patient
    pat_table_data = [
        [
            Paragraph("<b>Patient Identifier:</b>", body_style),
            Paragraph(str(p.get("patient_id", "N/A")), body_bold_style),
            Paragraph("<b>Clinical Procedure:</b>", body_style),
            Paragraph(str(p.get("procedure_type", "N/A")), body_style),
        ],
        [
            Paragraph("<b>Patient Name:</b>", body_style),
            Paragraph(str(p.get("name", "N/A")), body_style),
            Paragraph("<b>Acuity Rating:</b>", body_style),
            Paragraph(f"{p.get('acuity_score', 0.0)} ({p.get('criticality_label', 'Standard')})", body_bold_style),
        ],
    ]
    pat_table = Table(pat_table_data, colWidths=[110, 160, 110, 160])
    pat_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(pat_table)
    story.append(Spacer(1, 6))

    # ─────────────────────────────────────────────────────────────────────────
    # 3. MEDICAL CARE TEAM
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Paragraph("2. MEDICAL CARE TEAM", section_heading_style))
    team_data = [[
        Paragraph("Staff ID", table_header_style),
        Paragraph("Full Name", table_header_style),
        Paragraph("Assigned Clinical Role", table_header_style),
    ]]
    for member in data.medical_team:
        team_data.append([
            Paragraph(member.get("employee_id", "N/A"), body_style),
            Paragraph(member.get("name", "N/A"), body_bold_style),
            Paragraph(member.get("role", "Clinician"), body_style),
        ])

    team_table = Table(team_data, colWidths=[120, 220, 200])
    team_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(team_table)
    story.append(Spacer(1, 6))

    # ─────────────────────────────────────────────────────────────────────────
    # 4. ALLOCATED CLINICAL RESOURCES
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Paragraph("3. ALLOCATED CLINICAL RESOURCES", section_heading_style))
    res_data = [[
        Paragraph("Resource ID", table_header_style),
        Paragraph("Category / Type", table_header_style),
        Paragraph("Designation / Label", table_header_style),
        Paragraph("Final Status", table_header_style),
    ]]
    for r in data.resources:
        status_color = colors.HexColor("#16A34A") if r.get("final_status") == "COMMITTED" else colors.HexColor("#DC2626")
        res_data.append([
            Paragraph(r.get("resource_id", "N/A"), body_style),
            Paragraph(str(r.get("type", "Resource")).upper(), body_style),
            Paragraph(r.get("label", "N/A"), body_bold_style),
            Paragraph(f"<b>{r.get('final_status', 'COMMITTED')}</b>", ParagraphStyle("RStat", parent=body_style, textColor=status_color)),
        ])

    if len(res_data) == 1:
        res_data.append([
            Paragraph("N/A", body_style),
            Paragraph("N/A", body_style),
            Paragraph("No resources allocated in transaction", body_style),
            Paragraph("N/A", body_style),
        ])

    res_table = Table(res_data, colWidths=[110, 130, 180, 120])
    res_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(res_table)
    story.append(Spacer(1, 6))

    # ─────────────────────────────────────────────────────────────────────────
    # 5. TRANSACTION LIFECYCLE TIMELINE
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Paragraph("4. TRANSACTION LIFECYCLE & AUDIT TIMELINE", section_heading_style))
    time_data = [[
        Paragraph("Timestamp", table_header_style),
        Paragraph("Event / Lifecycle Step", table_header_style),
        Paragraph("Authorizing Actor", table_header_style),
        Paragraph("Outcome / Score", table_header_style),
    ]]
    for t_item in data.timeline:
        score_txt = f"{t_item['score']} pts" if t_item.get("score") is not None else t_item.get("decision", "OK")
        time_data.append([
            Paragraph(t_item.get("timestamp", ""), body_style),
            Paragraph(t_item.get("event", ""), body_bold_style),
            Paragraph(t_item.get("actor", ""), body_style),
            Paragraph(str(score_txt), body_style),
        ])

    timeline_table = Table(time_data, colWidths=[130, 170, 130, 110])
    timeline_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(timeline_table)

    # Footnote for Arbiter Conflict Resolution if applicable
    if data.arbiter_notes:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Arbiter Footnote:</b> {data.arbiter_notes}", ParagraphStyle("ArbNotes", parent=body_style, textColor=colors.HexColor("#B45309"))))

    # ─────────────────────────────────────────────────────────────────────────
    # 6. AUDIT TRACEABILITY FOOTER
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#94A3B8"), spaceAfter=4))
    story.append(
        Paragraph(
            f"Official Electronic Clinical Record · Sourced from Audit Stream ({data.audit_id}) · "
            "Confidential Hospital Medical Record — Unauthorized distribution prohibited.",
            footer_style,
        )
    )

    doc.build(story)

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    # Write to disk
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)

    return file_path, pdf_bytes
