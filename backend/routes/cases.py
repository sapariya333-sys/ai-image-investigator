import sqlite3
from flask import Blueprint, request, jsonify
from db import query

cases_bp = Blueprint("cases", __name__)


def _case_exists(case_id):
    return query("SELECT id FROM cases WHERE id = ?", (case_id,), fetchone=True) is not None


@cases_bp.route("", methods=["GET"])
def list_cases():
    cases = query("SELECT * FROM cases ORDER BY created_at DESC", fetchall=True)
    for c in cases:
        c["image_count"] = query(
            "SELECT COUNT(*) as n FROM images WHERE case_id = ?", (c["id"],), fetchone=True
        )["n"]
    return jsonify(cases)


@cases_bp.route("", methods=["POST"])
def create_case():
    data = request.get_json(force=True)
    case_number = (data.get("case_number") or "").strip()
    title = (data.get("title") or "").strip()
    if not case_number or not title:
        return jsonify({"error": "case_number and title are required"}), 400

    existing = query("SELECT id FROM cases WHERE case_number = ?", (case_number,), fetchone=True)
    if existing:
        return jsonify({"error": "case_number already exists"}), 409

    try:
        case_id = query(
            "INSERT INTO cases (case_number, title, investigator, description) VALUES (?, ?, ?, ?)",
            (case_number, title, data.get("investigator", ""), data.get("description", "")),
            commit=True,
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "case_number already exists"}), 409
    case = query("SELECT * FROM cases WHERE id = ?", (case_id,), fetchone=True)
    return jsonify(case), 201


@cases_bp.route("/<int:case_id>", methods=["GET"])
def get_case(case_id):
    case = query("SELECT * FROM cases WHERE id = ?", (case_id,), fetchone=True)
    if not case:
        return jsonify({"error": "case not found"}), 404
    case["images"] = query(
        "SELECT id, image_uid, original_filename, sha256, width, height, uploaded_at "
        "FROM images WHERE case_id = ? ORDER BY uploaded_at DESC",
        (case_id,), fetchall=True,
    )
    return jsonify(case)


@cases_bp.route("/<int:case_id>", methods=["PATCH"])
def update_case(case_id):
    if not _case_exists(case_id):
        return jsonify({"error": "case not found"}), 404

    data = request.get_json(force=True)
    fields, params = [], []
    for key in ("title", "investigator", "description", "status"):
        if key in data:
            fields.append(f"{key} = ?")
            params.append(data[key])
    if not fields:
        return jsonify({"error": "no updatable fields provided"}), 400
    params.append(case_id)
    query(f"UPDATE cases SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?", params, commit=True)
    return jsonify(query("SELECT * FROM cases WHERE id = ?", (case_id,), fetchone=True))


@cases_bp.route("/<int:case_id>/timeline", methods=["GET"])
def get_timeline(case_id):
    if not _case_exists(case_id):
        return jsonify({"error": "case not found"}), 404
    events = query(
        "SELECT * FROM timeline_events WHERE case_id = ? ORDER BY event_time IS NULL, event_time ASC",
        (case_id,), fetchall=True,
    )
    return jsonify(events)


@cases_bp.route("/<int:case_id>/notes", methods=["POST"])
def add_note(case_id):
    if not _case_exists(case_id):
        return jsonify({"error": "case not found"}), 404

    data = request.get_json(force=True)
    note = (data.get("note") or "").strip()
    if not note:
        return jsonify({"error": "note is required"}), 400

    image_id = data.get("image_id")
    if image_id is not None:
        image_ok = query("SELECT id FROM images WHERE id = ? AND case_id = ?", (image_id, case_id), fetchone=True)
        if not image_ok:
            return jsonify({"error": "image_id does not belong to this case"}), 400

    note_id = query(
        "INSERT INTO investigator_notes (case_id, image_id, note) VALUES (?, ?, ?)",
        (case_id, image_id, note),
        commit=True,
    )
    return jsonify(query("SELECT * FROM investigator_notes WHERE id = ?", (note_id,), fetchone=True)), 201


@cases_bp.route("/<int:case_id>/notes", methods=["GET"])
def list_notes(case_id):
    if not _case_exists(case_id):
        return jsonify({"error": "case not found"}), 404
    return jsonify(query(
        "SELECT * FROM investigator_notes WHERE case_id = ? ORDER BY created_at DESC",
        (case_id,), fetchall=True,
    ))
