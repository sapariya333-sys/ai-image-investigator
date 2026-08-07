import os
from flask import Blueprint, jsonify, current_app, send_file

from db import query
from services import ocr as ocr_service
from services import manipulation as manipulation_service
from services import synthetic as synthetic_service
from services import visual as visual_service
from services import location as location_service
from services import similarity as similarity_service
from services.report_generator import generate_report

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/<int:image_id>/generate", methods=["POST"])
def generate(image_id):
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404
    case = query("SELECT * FROM cases WHERE id = ?", (image["case_id"],), fetchone=True)

    metadata_findings = query(
        "SELECT * FROM metadata_findings WHERE image_id = ? AND category = 'exif'", (image_id,), fetchall=True
    )
    gps_rows = query(
        "SELECT field_name, field_value FROM metadata_findings WHERE image_id = ? AND category = 'gps'",
        (image_id,), fetchall=True,
    )
    gps = None
    if gps_rows:
        gps_dict = {r["field_name"]: r["field_value"] for r in gps_rows}
        if "latitude" in gps_dict and "longitude" in gps_dict:
            gps = {**gps_dict, "caveat": "GPS metadata can be modified and should not, by itself, be treated as proof of capture location."}

    ocr_row = query("SELECT * FROM ocr_results WHERE image_id = ? ORDER BY id DESC LIMIT 1", (image_id,), fetchone=True)
    ocr = None
    if ocr_row:
        entities = ocr_service.extract_entities(ocr_row["extracted_text"])
        ocr = {"language": ocr_row["language"], "extracted_text": ocr_row["extracted_text"], "entities": entities}
    else:
        ocr = ocr_service.run_ocr(image["stored_path"])

    manipulation = manipulation_service.analyze(
        image["stored_path"],
        os.path.join(current_app.config["DERIVATIVE_DIR"], f"{image['image_uid']}_report_ela.png"),
    )
    synthetic = synthetic_service.analyze(image["stored_path"])
    visual = visual_service.analyze(image["stored_path"])

    location = location_service.build_assessment(
        gps, ocr["extracted_text"] if ocr else "", ocr["entities"] if ocr else {}
    )

    others = query(
        "SELECT id, original_filename, sha256, phash FROM images WHERE case_id = ? AND id != ?",
        (image["case_id"], image_id), fetchall=True,
    )
    exact, similar = similarity_service.find_matches(image["phash"], image["sha256"], others)
    similarity = {"exact_duplicates": exact, "similar_images": similar}

    derivatives = query("SELECT * FROM derivatives WHERE image_id = ?", (image_id,), fetchall=True)
    notes = query(
        "SELECT * FROM investigator_notes WHERE case_id = ? AND (image_id = ? OR image_id IS NULL) ORDER BY created_at",
        (image["case_id"], image_id), fetchall=True,
    )
    timeline = query(
        "SELECT * FROM timeline_events WHERE case_id = ? AND (image_id = ? OR image_id IS NULL) ORDER BY created_at",
        (image["case_id"], image_id), fetchall=True,
    )

    out_name = f"report_{case['case_number']}_{image['image_uid']}.pdf"
    out_path = os.path.join(current_app.config["REPORT_DIR"], out_name)

    generate_report(
        out_path, case, image, metadata_findings, gps, ocr, manipulation,
        synthetic, visual, location, similarity, derivatives, notes, timeline,
        thumbnail_path=image["stored_path"],
    )

    return jsonify({"report_path": out_path, "download_url": f"/api/reports/{image_id}/download"})


@reports_bp.route("/<int:image_id>/download", methods=["GET"])
def download(image_id):
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "image not found"}), 404
    case = query("SELECT * FROM cases WHERE id = ?", (image["case_id"],), fetchone=True)
    if not case:
        return jsonify({"error": "case not found"}), 404
    out_name = f"report_{case['case_number']}_{image['image_uid']}.pdf"
    out_path = os.path.join(current_app.config["REPORT_DIR"], out_name)
    if not os.path.exists(out_path):
        return jsonify({"error": "report not yet generated"}), 404
    return send_file(out_path, as_attachment=True, download_name=out_name)
