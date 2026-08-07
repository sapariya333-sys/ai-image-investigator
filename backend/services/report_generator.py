"""
Investigation Report Generator.

Builds the PDF export described in the spec: case info, evidence
info, hashes, metadata/EXIF/GPS findings, OCR results, visual/AI
findings, manipulation assessment, enhancement history, derived
hashes, investigator notes, and the standing evidentiary disclaimer.
"""
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    PageBreak,
)

DISCLAIMER = (
    "Automated and AI-generated findings in this report are investigative "
    "leads and should be independently verified before being relied upon as "
    "evidentiary conclusions."
)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading2"],
            spaceBefore=14,
            spaceAfter=6,
            textColor=colors.HexColor("#1a2b4c"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Mono",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=8.5,
            textColor=colors.HexColor("#333333"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caveat",
            parent=styles["Normal"],
            fontSize=8.5,
            textColor=colors.HexColor("#8a5a00"),
            leftIndent=8,
        )
    )
    return styles


def _kv_table(rows, styles):
    data = [[Paragraph(f"<b>{k}</b>", styles["Normal"]), Paragraph(str(v), styles["Mono"])] for k, v in rows]
    t = Table(data, colWidths=[5.5 * cm, 11 * cm])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f4f8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def generate_report(out_path, case, image, metadata_findings, gps, ocr, manipulation,
                     synthetic, visual, location, similarity, derivatives, notes,
                     timeline, thumbnail_path=None):
    styles = _styles()
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    story = []

    story.append(Paragraph("AI-Image Investigator", styles["Title"]))
    story.append(Paragraph("Forensic Image Investigation Report", styles["Heading3"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 10))

    if thumbnail_path:
        try:
            story.append(RLImage(thumbnail_path, width=8 * cm, height=8 * cm, kind="proportional"))
            story.append(Spacer(1, 10))
        except Exception:
            pass

    story.append(Paragraph("1. Case Information", styles["SectionHeading"]))
    story.append(_kv_table([
        ("Case Number", case.get("case_number", "-")),
        ("Title", case.get("title", "-")),
        ("Investigator", case.get("investigator", "-")),
        ("Status", case.get("status", "-")),
        ("Case Created", case.get("created_at", "-")),
    ], styles))

    story.append(Paragraph("2. Evidence Information", styles["SectionHeading"]))
    story.append(_kv_table([
        ("Image ID", image.get("image_uid", "-")),
        ("Original Filename", image.get("original_filename", "-")),
        ("File Size", f"{image.get('file_size', 0):,} bytes"),
        ("Dimensions", f"{image.get('width')} x {image.get('height')}"),
        ("Color Mode", image.get("color_mode", "-")),
        ("Uploaded At", image.get("uploaded_at", "-")),
    ], styles))

    story.append(Paragraph("3. Evidence Integrity — Original Hashes", styles["SectionHeading"]))
    story.append(_kv_table([
        ("SHA-256 (primary)", image.get("sha256", "-")),
        ("MD5", image.get("md5", "-")),
        ("SHA-1", image.get("sha1", "-")),
        ("Perceptual Hash (pHash)", image.get("phash", "-")),
    ], styles))

    story.append(Paragraph("4. Metadata & EXIF Findings", styles["SectionHeading"]))
    if metadata_findings:
        story.append(_kv_table([(m["field_name"], m["field_value"]) for m in metadata_findings], styles))
    else:
        story.append(Paragraph("No EXIF metadata present in this file.", styles["Normal"]))

    story.append(Paragraph("5. GPS Findings", styles["SectionHeading"]))
    if gps:
        story.append(_kv_table([
            ("Latitude", gps.get("latitude")),
            ("Longitude", gps.get("longitude")),
            ("Altitude", gps.get("altitude") or "-"),
            ("GPS Timestamp", gps.get("gps_timestamp") or "-"),
        ], styles))
        story.append(Paragraph(gps.get("caveat", ""), styles["Caveat"]))
    else:
        story.append(Paragraph("No GPS metadata present in this file.", styles["Normal"]))

    story.append(Paragraph("6. OCR Results", styles["SectionHeading"]))
    if ocr and ocr.get("extracted_text"):
        story.append(Paragraph(f"Language mode: {ocr.get('language')}", styles["Normal"]))
        story.append(Paragraph(ocr["extracted_text"].replace("\n", "<br/>")[:2000], styles["Mono"]))
        if ocr.get("entities"):
            story.append(Spacer(1, 4))
            story.append(_kv_table(list(ocr["entities"].items()), styles))
    else:
        story.append(Paragraph("No text detected.", styles["Normal"]))

    story.append(Paragraph("7. Location Assessment", styles["SectionHeading"]))
    if location:
        story.append(Paragraph(location.get("narrative", ""), styles["Normal"]))
        for clue in location.get("clues", []):
            story.append(Paragraph(f"• {clue['label']}: {clue['detail']}", styles["Normal"]))
            if clue.get("caveat"):
                story.append(Paragraph(clue["caveat"], styles["Caveat"]))

    story.append(Paragraph("8. AI Visual Findings", styles["SectionHeading"]))
    if visual:
        story.append(_kv_table([
            ("Faces detected", visual.get("faces_detected", 0)),
            ("Lighting assessment", visual["lighting"]["assessment"]),
            ("Color/environment note", visual["color_environment"]["assessment"]),
        ], styles))
        story.append(Paragraph(visual.get("note", ""), styles["Caveat"]))

    story.append(PageBreak())
    story.append(Paragraph("9. Manipulation Assessment", styles["SectionHeading"]))
    if manipulation:
        story.append(Paragraph(manipulation.get("summary", ""), styles["Normal"]))
        for ind in manipulation.get("indicators", []):
            story.append(Paragraph(f"• [{ind['severity'].upper()}] {ind['indicator']}: {ind['detail']}", styles["Normal"]))
        ela = manipulation.get("ela", {})
        story.append(_kv_table([
            ("ELA mean error level", ela.get("mean_error_level", "-")),
            ("ELA std deviation", ela.get("std_error_level", "-")),
        ], styles))

    story.append(Paragraph("10. Synthetic Media Screening", styles["SectionHeading"]))
    if synthetic:
        story.append(_kv_table([
            ("Assessment", synthetic.get("assessment")),
            ("Confidence", synthetic.get("confidence")),
            ("Frequency ratio", synthetic.get("frequency_ratio")),
        ], styles))
        story.append(Paragraph(synthetic.get("disclaimer", ""), styles["Caveat"]))

    story.append(Paragraph("11. Similarity / Duplicate Findings", styles["SectionHeading"]))
    if similarity and (similarity.get("exact_duplicates") or similarity.get("similar_images")):
        for d in similarity.get("exact_duplicates", []):
            story.append(Paragraph(f"• Exact duplicate: {d['original_filename']}", styles["Normal"]))
        for s in similarity.get("similar_images", []):
            story.append(Paragraph(
                f"• Similar ({s['similarity_pct']}%): {s['original_filename']} (Hamming distance {s['hamming_distance']})",
                styles["Normal"],
            ))
    else:
        story.append(Paragraph("No duplicate or visually similar images found in this case.", styles["Normal"]))

    story.append(Paragraph("12. Enhancement History", styles["SectionHeading"]))
    if derivatives:
        story.append(_kv_table([(d["derivative_type"], f"{d['label']} — SHA-256: {d['sha256']}") for d in derivatives], styles))
    else:
        story.append(Paragraph("No derivative images generated.", styles["Normal"]))

    story.append(Paragraph("13. Evidence Timeline", styles["SectionHeading"]))
    if timeline:
        for t in timeline:
            story.append(Paragraph(f"• {t.get('event_time') or 'Unknown time'} — {t['event_label']} (source: {t.get('source_field','-')})", styles["Normal"]))
    else:
        story.append(Paragraph("No timeline events recorded.", styles["Normal"]))

    story.append(Paragraph("14. Investigator Notes", styles["SectionHeading"]))
    if notes:
        for n in notes:
            story.append(Paragraph(f"• [{n['created_at']}] {n['note']}", styles["Normal"]))
    else:
        story.append(Paragraph("No notes recorded.", styles["Normal"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph(DISCLAIMER, styles["Caveat"]))

    doc.build(story)
    return out_path
