import os
import io
import uuid
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
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


def _as_browser_safe_jpeg(path, max_dimension=1200, quality=88):
    """
    Re-encodes any supported source format into an in-memory JPEG.

    Chrome, Firefox, and Edge have no built-in HEIC or TIFF decoder for
    <img> tags -- a correct Content-Type header doesn't change that, the
    browser simply can't decode the bytes. Reverse-search providers
    (TinEye confirmed explicitly) reject HEIC outright too. JPEG is the
    one format every browser and every provider accepts, so anything
    meant for inline display or an external fetch goes through this
    first. The original file on disk is never touched -- this only
    affects what gets served to a *viewer* of the evidence, not the
    evidence itself.
    """
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        if max(rgb.size) > max_dimension:
            ratio = max_dimension / max(rgb.size)
            rgb = rgb.resize((int(rgb.width * ratio), int(rgb.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        return buf


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
    """The untouched original evidence file -- byte-for-byte, whatever format it was uploaded in."""
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404
    return send_file(image["stored_path"])


@images_bp.route("/<int:image_id>/thumbnail", methods=["GET"])
def get_image_thumbnail(image_id):
    """Browser-safe JPEG render of the evidence, for inline <img> display (see _as_browser_safe_jpeg)."""
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404
    buf = _as_browser_safe_jpeg(image["stored_path"])
    return send_file(buf, mimetype="image/jpeg")


@images_bp.route("/<int:image_id>/public-file", methods=["GET"])
def get_public_image_file(image_id):
    """
    Serves a browser/provider-safe JPEG WITHOUT requiring a login session
    -- exempted from the global auth check in app.py (any path ending in
    /public-file).

    This exists only for reverse-image-search providers (Google Lens,
    Bing, etc.), which fetch the URL from their own servers and so can
    never carry our session cookie. Access requires a signed,
    15-minute token minted specifically for this image (see
    routes/analysis.py reverse_search_links) -- so it's not a
    permanently open evidence URL, just a short window for one lookup.
    Always re-encoded to JPEG regardless of source format, since HEIC
    (and some TIFF variants) aren't accepted by these providers at all.
    """
    token = request.args.get("token", "")
    try:
        payload_image_id = URLSafeTimedSerializer(
            current_app.secret_key, salt="public-image-link"
        ).loads(token, max_age=900)
    except SignatureExpired:
        return jsonify({"error": "this link has expired — generate a new one from the Search tab"}), 403
    except BadSignature:
        return jsonify({"error": "invalid link"}), 403

    if payload_image_id != image_id:
        return jsonify({"error": "invalid link"}), 403

    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404
    buf = _as_browser_safe_jpeg(image["stored_path"])
    return send_file(buf, mimetype="image/jpeg")


@images_bp.route("/<int:image_id>/enhance", methods=["POST"])
def enhance_image(image_id):
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True)
    preset = data.get("preset")
    ops = data.get("operations", {})

    # Always save as JPEG regardless of the original's format -- derivatives
    # are working copies meant to be viewed in-browser, and preserving a
    # HEIC/TIFF extension here would produce a preview image nothing but
    # Safari could actually display. enhancement.py already normalizes to
    # RGB before any operation, so this is a lossless format change only.
    derivative_name = f"{image['image_uid']}_enhanced_{uuid.uuid4().hex[:6]}.jpg"
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


@images_bp.route("/<int:image_id>", methods=["DELETE"])
def delete_image(image_id):
    image = query("SELECT * FROM images WHERE id = ?", (image_id,), fetchone=True)
    if not image:
        return jsonify({"error": "not found"}), 404

    derivatives = query("SELECT * FROM derivatives WHERE image_id = ?", (image_id,), fetchall=True)
    for d in derivatives:
        try:
            if d["stored_path"] and os.path.exists(d["stored_path"]):
                os.remove(d["stored_path"])
        except OSError:
            pass

    try:
        if image["stored_path"] and os.path.exists(image["stored_path"]):
            os.remove(image["stored_path"])
    except OSError:
        pass

    # manual cascade -- SQLite doesn't auto-cascade unless the FK was
    # declared with ON DELETE CASCADE, which ours weren't.
    for table in (
        "metadata_findings", "ocr_results", "manipulation_findings",
        "derivatives", "timeline_events", "investigator_notes",
    ):
        query(f"DELETE FROM {table} WHERE image_id = ?", (image_id,), commit=True)

    query(
        "INSERT INTO timeline_events (case_id, image_id, event_time, event_label, source_field) VALUES (?,?,?,?,?)",
        (image["case_id"], None, None, f"Evidence removed from case: {image['original_filename']}", "system"),
        commit=True,
    )
    query("DELETE FROM images WHERE id = ?", (image_id,), commit=True)

    return jsonify({"deleted": True, "image_id": image_id}), 200


@images_bp.route("/derivatives/<int:derivative_id>/file", methods=["GET"])
def get_derivative_file(derivative_id):
    d = query("SELECT * FROM derivatives WHERE id = ?", (derivative_id,), fetchone=True)
    if not d:
        return jsonify({"error": "not found"}), 404
    return send_file(d["stored_path"])
