"""
AI-Image Investigator — Backend
Flask application entrypoint.
"""
import os
import secrets
from functools import wraps
from flask import Flask, jsonify, request, session, redirect, url_for, render_template
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import pillow_heif

pillow_heif.register_heif_opener()  # makes PIL.Image.open() handle .heic/.heif

from db import init_db
from routes.cases import cases_bp
from routes.images import images_bp
from routes.analysis import analysis_bp
from routes.reports import reports_bp

ADMIN_USERNAME = os.environ.get("INVESTIGATOR_USERNAME", "investigator")
ADMIN_PASSWORD = os.environ.get("INVESTIGATOR_PASSWORD", "changeme")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DERIVATIVE_DIR = os.path.join(DATA_DIR, "derivatives")
REPORT_DIR = os.path.join(DATA_DIR, "reports")

for d in (UPLOAD_DIR, DERIVATIVE_DIR, REPORT_DIR):
    os.makedirs(d, exist_ok=True)


def create_app():
    app = Flask(
        __name__,
        static_folder=os.path.join(BASE_DIR, "..", "frontend", "static"),
        template_folder=os.path.join(BASE_DIR, "..", "frontend", "templates"),
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    app.config["UPLOAD_DIR"] = UPLOAD_DIR
    app.config["DERIVATIVE_DIR"] = DERIVATIVE_DIR
    app.config["REPORT_DIR"] = REPORT_DIR
    app.config["DATA_DIR"] = DATA_DIR
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB per upload

    secret = os.environ.get("SECRET_KEY")
    if not secret:
        # Without an explicit SECRET_KEY, generate one but persist it to disk so
        # every gunicorn worker process (and every restart) shares the same
        # key. A fresh random key per-process would silently invalidate
        # sessions whenever a request landed on a different worker.
        key_path = os.path.join(app.config.get("DATA_DIR", BASE_DIR), ".secret_key")
        if os.path.exists(key_path):
            with open(key_path) as f:
                secret = f.read().strip()
        if not secret:
            secret = secrets.token_hex(32)
            with open(key_path, "w") as f:
                f.write(secret)
    app.secret_key = secret

    CORS(app, supports_credentials=True)
    init_db()

    def _is_exempt(path):
        if path.startswith("/login") or path.startswith("/static/"):
            return True
        # token-gated route used by external reverse-search providers --
        # authenticated via its own signed token, not a session
        if path.endswith("/public-file"):
            return True
        return False

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("authenticated"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "authentication required"}), 401
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    @app.before_request
    def enforce_login():
        if _is_exempt(request.path):
            return None
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login"))
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                session["authenticated"] = True
                session.permanent = True
                return redirect(url_for("index"))
            error = "Invalid username or password."
        return render_template("login.html", error=error)

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))

    app.register_blueprint(cases_bp, url_prefix="/api/cases")
    app.register_blueprint(images_bp, url_prefix="/api/images")
    app.register_blueprint(analysis_bp, url_prefix="/api/analysis")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "file too large (50MB limit)"}), 413

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
