import os
import uuid
from flask import Blueprint, jsonify, current_app, request
from itsdangerous import URLSafeTimedSerializer

from db import query
from services import ocr as ocr_service
from services import manipulation as manipulation_service
from services import synthetic as synthetic_service
from services import visual as visual_service
from services import location as location_service
from services import similarity as similarity_service
from services import reverse_search as reverse_search_service
from services.hashing import hash_file

analysis_bp = Blueprint("analysis", __name__)


def _get_image_or_404(image_id):
    return query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)


@analysis_bp.route("/<int:image_id>/ocr", methods=["POST"])
def run_ocr(image_id):
    image = _get_image_or_404(image_id)
    if not image:
        return jsonify({"error": "not found"}), 404

    try:
        result = ocr_service.run_ocr(image["stored_path"])
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    query(
        "INSERT INTO ocr_results (image_id, language, extracted_text, confidence) VALUES (?,?,?,?)",
        (image_id, result["language"], result["extracted_text"], None),
        commit=True,
    )
    return jsonify(result)


@analysis_bp.route("/<int:image_id>/manipulation", methods=["POST"])
def run_manipulation(image_id):
    image = _get_image_or_404(image_id)
    if not image:
        return jsonify({"error": "not found"}), 404

    ela_name = f"{image['image_uid']}_ela_{uuid.uuid4().hex[:6]}.png"
    ela_path = os.path.join(current_app.config["DERIVATIVE_DIR"], ela_name)
    result = manipulation_service.analyze(image["stored_path"], ela_path)

    hashes = hash_file(ela_path)
    query(
        "INSERT INTO derivatives (image_id, derivative_type, label, stored_path, sha256) VALUES (?,?,?,?,?)",
        (image_id, "ela", "Error Level Analysis overlay", ela_path, hashes["sha256"]),
        commit=True,
    )

    for ind in result["indicators"]:
        query(
            "INSERT INTO manipulation_findings (image_id, indicator, detail, severity, ela_derivative_path) VALUES (?,?,?,?,?)",
            (image_id, ind["indicator"], ind["detail"], ind["severity"], ela_path),
            commit=True,
        )

    return jsonify(result)


@analysis_bp.route("/<int:image_id>/synthetic", methods=["POST"])
def run_synthetic(image_id):
    image = _get_image_or_404(image_id)
    if not image:
        return jsonify({"error": "not found"}), 404
    return jsonify(synthetic_service.analyze(image["stored_path"]))


@analysis_bp.route("/<int:image_id>/visual", methods=["POST"])
def run_visual(image_id):
    image = _get_image_or_404(image_id)
    if not image:
        return jsonify({"error": "not found"}), 404
    return jsonify(visual_service.analyze(image["stored_path"]))


@analysis_bp.route("/<int:image_id>/location", methods=["GET"])
def run_location(image_id):
    image = _get_image_or_404(image_id)
    if not image:
        return jsonify({"error": "not found"}), 404

    gps_rows = query(
        "SELECT field_name, field_value FROM metadata_findings WHERE image_id = ? AND category = 'gps'",
        (image_id,), fetchall=True,
    )
    gps = None
    if gps_rows:
        gps_dict = {r["field_name"]: r["field_value"] for r in gps_rows}
        if "latitude" in gps_dict and "longitude" in gps_dict:
            gps = {
                "latitude": gps_dict["latitude"],
                "longitude": gps_dict["longitude"],
                "caveat": (
                    "GPS metadata can be modified and should not, by itself, "
                    "be treated as proof of where this image was captured."
                ),
            }

    ocr_row = query(
        "SELECT extracted_text FROM ocr_results WHERE image_id = ? ORDER BY id DESC LIMIT 1",
        (image_id,), fetchone=True,
    )
    ocr_text = ocr_row["extracted_text"] if ocr_row else ""
    entities = ocr_service.extract_entities(ocr_text) if ocr_text else {}

    result = location_service.build_assessment(gps, ocr_text, entities)
    return jsonify(result)


@analysis_bp.route("/<int:image_id>/similarity", methods=["GET"])
def run_similarity(image_id):
    image = _get_image_or_404(image_id)
    if not image:
        return jsonify({"error": "not found"}), 404

    others = query(
        "SELECT id, original_filename, sha256, phash FROM images WHERE case_id = ? AND id != ?",
        (image["case_id"], image_id), fetchall=True,
    )
    exact, similar = similarity_service.find_matches(image["phash"], image["sha256"], others)
    return jsonify({"exact_duplicates": exact, "similar_images": similar})


@analysis_bp.route("/<int:image_id>/reverse-search-links", methods=["GET"])
def reverse_search_links(image_id):
    image = _get_image_or_404(image_id)
    if not image:
        return jsonify({"error": "not found"}), 404

    # Almost every hosting platform terminates TLS at an edge/proxy and
    # forwards plain HTTP internally. request.host_url reflects that
    # internal scheme unless the proxy's X-Forwarded-Proto header is both
    # sent AND correctly trusted by ProxyFix's hop count -- which varies
    # per platform and is easy to get wrong. Since reverse-search providers
    # fetch this URL from their own servers (not the investigator's
    # browser), a scheme mismatch means a silent failure with no visible
    # error. Forcing https for any non-local host sidesteps that entirely.
    host = request.host
    is_local = host.startswith("localhost") or host.startswith("127.0.0.1")
    scheme = request.scheme if is_local else "https"
    base = f"{scheme}://{host}"

    token = URLSafeTimedSerializer(current_app.secret_key, salt="public-image-link").dumps(image_id)
    public_url = f"{base}/api/images/{image_id}/public-file?token={token}"
    return jsonify(reverse_search_service.build_search_links(public_url))
