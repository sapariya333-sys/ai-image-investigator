import os
import uuid
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
from PIL import Image

from db import query
from services.hashing import hash_file
from services.metadata import extract_file_properties, extract_exif
from services.similarity import compute_phash
from services.enhancement import apply_operations, apply_preset

images_bp = Blueprint("images", __name__)

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "tiff", "tif", "heic"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@images_bp.route("", methods=["POST"])
def upload_image():
    case_id = request.form.get("case_id")
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400

    case = query("SELECT * FROM cases WHERE id = ?", (case_id,), fetchone=True)
    if not case:
        return jsonify({"error": "case not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "no file provided"}), 400
    file = request.files["file"]
    if file.filename == "" or not _allowed(file.filename):
        return jsonify({"error": "unsupported or missing file"}), 400

    original_filename = secure_filename(file.filename)
    image_uid = uuid.uuid4().hex[:12]
    ext = original_filename.rsplit(".", 1)[1].lower()
    stored_name = f"{image_uid}.{ext}"
    stored_path = os.path.join(current_app.config["UPLOAD_DIR"], stored_name)
    file.save(stored_path)

    try:
        with Image.open(stored_path) as im:
            im.verify()
    except Exception:
        os.remove(stored_path)
        return jsonify({"error": "file is not a valid image"}), 400

    hashes = hash_file(stored_path)
    props = extract_file_properties(stored_path, original_filename)
    phash = compute_phash(stored_path)

    image_id = query(
        """INSERT INTO images
           (case_id, image_uid, original_filename, stored_path, mime_type, file_size,
            width, height, color_mode, sha256, md5, sha1, phash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            case_id, image_uid, original_filename, stored_path, props["mime_type"],
            props["file_size_bytes"], props["width"], props["height"], props["color_mode"],
            hashes["sha256"], hashes["md5"], hashes["sha1"], phash,
        ),
        commit=True,
    )

    query(
        "INSERT INTO timeline_events (case_id, image_id, event_time, event_label, source_field) VALUES (?,?,?,?,?)",
        (case_id, image_id, None, f"Evidence uploaded: {original_filename}", "system"),
        commit=True,
    )

    exif_findings, gps = extract_exif(stored_path)
    for f in exif_findings:
        query(
            "INSERT INTO metadata_findings (image_id, category, field_name, field_value, source) VALUES (?,?,?,?,?)",
            (image_id, "exif", f["field_name"], f["field_value"], f["source"]),
            commit=True,
        )
        if f["field_name"] == "Date/Time Original":
            query(
                "INSERT INTO timeline_events (case_id, image_id, event_time, event_label, source_field) VALUES (?,?,?,?,?)",
                (case_id, image_id, f["field_value"], "Image capture timestamp (EXIF)", "EXIF DateTimeOriginal"),
                commit=True,
            )

    if gps:
        for k in ("latitude", "longitude", "altitude", "gps_timestamp"):
            if gps.get(k) is not None:
                query(
                    "INSERT INTO metadata_findings (image_id, category, field_name, field_value, source) VALUES (?,?,?,?,?)",
                    (image_id, "gps", k, str(gps[k]), "EXIF GPS"),
                    commit=True,
                )

    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    return jsonify({"image": image, "exif_findings": exif_findings, "gps": gps}), 201


@images_bp.route("/<int:image_id>", methods=["GET"])
def get_image(image_id):
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404
    image["metadata"] = query("SELECT * FROM metadata_findings WHERE image_id = ?", (image_id,), fetchall=True)
    image["derivatives"] = query("SELECT * FROM derivatives WHERE image_id = ?", (image_id,), fetchall=True)
    return jsonify(image)


@images_bp.route("/<int:image_id>/file", methods=["GET"])
def get_image_file(image_id):
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404
    return send_file(image["stored_path"])


@images_bp.route("/<int:image_id>/enhance", methods=["POST"])
def enhance_image(image_id):
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True)
    preset = data.get("preset")
    ops = data.get("operations", {})

    ext = image["stored_path"].rsplit(".", 1)[1]
    derivative_name = f"{image['image_uid']}_enhanced_{uuid.uuid4().hex[:6]}.{ext}"
    out_path = os.path.join(current_app.config["DERIVATIVE_DIR"], derivative_name)

    if preset:
        try:
            apply_preset(image["stored_path"], out_path, preset)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        label = f"Preset: {preset}"
    else:
        try:
            apply_operations(image["stored_path"], out_path, ops)
        except Exception as e:
            return jsonify({"error": f"invalid enhancement operation: {e}"}), 400
        label = f"Custom operations: {ops}"

    hashes = hash_file(out_path)
    deriv_id = query(
        "INSERT INTO derivatives (image_id, derivative_type, label, stored_path, sha256) VALUES (?,?,?,?,?)",
        (image_id, "enhanced", label, out_path, hashes["sha256"]),
        commit=True,
    )
    derivative = query("SELECT * FROM derivatives WHERE id = ?", (deriv_id,), fetchone=True)
    return jsonify(derivative), 201


@images_bp.route("/derivatives/<int:derivative_id>/file", methods=["GET"])
def get_derivative_file(derivative_id):
    d = query("SELECT * FROM derivatives WHERE id = ?", (derivative_id,), fetchone=True)
    if not d:
        return jsonify({"error": "not found"}), 404
    return send_file(d["stored_path"])
