# AI-Image Investigator

A web-based (browser only — no desktop/Windows client) image forensic
and investigation platform. Flask backend + a vanilla HTML/CSS/JS
frontend, SQLite for case storage, no external services required to
run locally.

## Login

The app is behind a login screen — everything under `/` and `/api/*`
requires a session. Set credentials via environment variables before
running (defaults are `investigator` / `changeme` — **change these**,
especially if you deploy it publicly):

```bash
export INVESTIGATOR_USERNAME="your-username"
export INVESTIGATOR_PASSWORD="a-strong-password"
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

## Deploying it as a hosted website (no laptop required after setup)

The app is containerized (`Dockerfile` + `docker-compose.yml` at the
project root), which is the easiest path to a real public URL. Two
things matter for a forensic tool specifically:

1. **Persistence** — case data, evidence files, and derivatives live
   under `DATA_DIR` (defaults to `backend/`, override with the
   `DATA_DIR` env var). On a hosting platform, this must be a
   **persistent volume**, or every redeploy/restart wipes your cases.
2. **Auth** — set `INVESTIGATOR_USERNAME`/`INVESTIGATOR_PASSWORD`/`SECRET_KEY`
   as real secrets on the platform, not the defaults.

### Option A — Fly.io (recommended: free allowance includes a persistent volume)

```bash
curl -L https://fly.io/install.sh | sh      # install flyctl
fly auth signup                              # or: fly auth login
cd ai-image-investigator
fly launch --copy-config --no-deploy         # uses fly.toml, pick a unique app name if prompted
fly volumes create investigator_data --size 3 --region bom
fly secrets set INVESTIGATOR_USERNAME=youruser INVESTIGATOR_PASSWORD=yourpass SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
fly deploy
```

You'll get a URL like `https://ai-image-investigator.fly.dev` — that's
it, accessible from any device, nothing running on your laptop.

### Option B — Render.com (simplest, but free tier has no persistent disk)

Push this folder to a GitHub repo, then on Render: **New → Web
Service → connect the repo → Environment: Docker**. Render auto-detects
the `Dockerfile`. Add the same three env vars in the dashboard. Fine
for demos; for real case data, add a paid persistent disk mounted at
`/data` and set `DATA_DIR=/data`, or use Option A instead.

### Option C — Any VPS (DigitalOcean/Hetzner/AWS Lightsail, full control)

```bash
git clone <your-repo-url> && cd ai-image-investigator
docker compose up -d --build
```

Put it behind Caddy or nginx for HTTPS + a domain, and open only that
port on the firewall.

## Audit changelog

A full audit (Aug 2026) found and fixed these real bugs — noting them
here so anyone reading the code later knows why things are shaped
this way:

- **HEIC uploads were silently broken.** Pillow can't decode HEIC
  without a plugin; added `pillow-heif` and registered it globally.
- **EXIF/GPS extraction silently failed on WEBP and HEIC.** The
  `exifread` library only reliably parses JPEG/TIFF containers.
  Rewrote metadata extraction on Pillow's own `getexif()`, which
  works consistently across JPEG/PNG/WEBP/TIFF/HEIC.
- **OCR crashed on HEIC** (and would have on some WEBP files) —
  pytesseract whitelists a small format set. Every image is now
  normalized to an in-memory PNG before OCR.
- **Face detection silently failed on HEIC** — `cv2.imread()` returns
  `None` on formats OpenCV's codec doesn't support, and the code
  quietly reported "0 faces detected" as if that were a real result
  instead of a failed read. Now decodes via Pillow first.
- **Similarity/duplicate search crashed on any case with 2+ images**
  — `imagehash`'s Hamming distance returns a numpy `int64`, which
  isn't JSON-serializable. Cast to a native `int`.
- **`investigator_notes` was missing its `FOREIGN KEY` constraint**,
  so orphaned notes could be attached to a nonexistent case with no
  error. Added the constraint.
- **Several routes 500'd on a nonexistent ID** instead of returning a
  clean 404 (case PATCH/timeline/notes, report download). Added
  existence checks throughout.
- **Bad enhancement input crashed the server** (unknown preset,
  invalid crop coordinates) instead of returning a 400. Now validated
  and clamped.
- **Frontend XSS gap**: EXIF fields, OCR'd text, and investigator
  notes were injected into the page via `innerHTML` without escaping
  — a crafted image (or a maliciously named file) could carry HTML/JS
  as "visible text" that would execute in the investigator's browser.
  Added an `escapeHtml()` helper and applied it everywhere
  user/EXIF/OCR-derived content is rendered.
- **Case-number race condition**: a duplicate-case-number check
  followed by an insert had a TOCTOU gap; now catches the resulting
  `IntegrityError` and returns 409 instead of a 500.
- **Gunicorn multi-worker session bug**: without an explicit
  `SECRET_KEY`, each worker process generated its own random key,
  which would silently invalidate sessions whenever a request landed
  on a different worker. The key is now generated once and persisted
  to `DATA_DIR/.secret_key` if not set explicitly (still — set
  `SECRET_KEY` yourself in production).

All fixes were verified end-to-end across JPEG, HEIC, WEBP, and TIFF
through every module (metadata, OCR, location, manipulation,
synthetic-media screening, visual, similarity, enhancement, and
report generation), plus a full sweep of every endpoint against
nonexistent IDs and malformed input.

## Quick start (local)

```bash
./setup.sh      # installs Tesseract (eng+hin+guj) and Python deps into .venv
./run.sh         # starts the app
```

Then open **http://localhost:5000**.

Everything runs locally: uploaded evidence, derivatives, the SQLite
database, and generated reports all stay on disk under `backend/`
(`uploads/`, `derivatives/`, `reports/`, `investigator.db`), or under
`DATA_DIR` if you set that env var.

## What's implemented right now (fully working, tested end-to-end)

| Module | Status |
|---|---|
| Case management (create/list/update, notes) | ✅ |
| Evidence upload, SHA-256/MD5/SHA-1 hashing, perceptual hash | ✅ |
| File properties (dimensions, MIME, size, color mode) | ✅ |
| EXIF extraction (camera, lens, exposure, timestamps) | ✅ |
| GPS extraction with "not proof of capture location" caveat | ✅ |
| OCR — English + Hindi + Gujarati in one pass, entity extraction (URLs, emails, phone numbers, plate-like strings) | ✅ |
| Location Intelligence — correlates GPS + OCR + script detection into a transparent, multi-clue assessment | ✅ |
| Reverse Image Search Hub — one-click links to Google Lens, Bing Visual Search, Yandex, TinEye | ✅ (link-based; see below for full API integration) |
| Authenticity & Manipulation Analysis — Error Level Analysis, compression/quantization heuristics, noise-consistency check | ✅ |
| Synthetic Media Screening — FFT frequency-domain heuristic | ✅ (screening-grade; see below) |
| AI Visual Investigator — face detection (OpenCV Haar cascades), lighting/day-night, coarse environment read | ✅ |
| Enhancement Lab — upscale/sharpen/denoise/contrast/gamma/crop/rotate/grayscale + 5 one-click presets (face, plate, document, CCTV frame, text) | ✅ |
| Evidence chain — original never overwritten, every derivative independently hashed | ✅ |
| Duplicate/Similar Image Finder — exact via SHA-256, similar via perceptual hash (Hamming distance) | ✅ |
| Evidence Timeline — auto-built from upload + EXIF capture time, source-labeled | ✅ |
| Case Mode UI — Overview / Images / Metadata / Visual / Search / Similarity / Manipulation / Timeline / Report tabs | ✅ |
| Forensic PDF report generator | ✅ |

## Honest limitations / integration points

This is a real, running local platform — not a mockup — but two
modules are intentionally built as transparent placeholders rather
than faked, because doing them properly needs external services or
trained models that a from-scratch build can't fabricate:

1. **Reverse image search** currently builds correct "open in
   provider" links (same pattern as browser extensions use) rather
   than pulling results back into the platform automatically. To
   automate result ingestion, add API credentials for Google
   Vision/Lens, Bing Visual Search, or TinEye in
   `backend/services/reverse_search.py` and extend it to call their
   APIs directly.

2. **Object-category detection** (e.g. "motorcycle", "helmet",
   "road sign") and **synthetic-media/deepfake detection** need a
   trained model. The Visual Investigator currently does real,
   local face detection (OpenCV) and lighting/environment heuristics;
   the Synthetic Media module runs a real frequency-domain heuristic.
   Both are clearly labeled as screening signals in the UI and PDF
   report. For production-grade detection, swap in a hosted vision
   model (e.g. via an API) inside `backend/services/visual.py` and
   `backend/services/synthetic.py` — the rest of the pipeline
   (storage, report, chain-of-custody hashing) does not need to
   change.

Every AI-derived finding in the UI and PDF report is labeled with a
confidence band and a note that it requires investigator
verification — this was a hard requirement from the original spec
and is enforced throughout, not just in the report footer.

## Project structure

```
ai-image-investigator/
├── setup.sh / run.sh
├── backend/
│   ├── app.py                  Flask entrypoint
│   ├── db.py                   SQLite schema + query helper
│   ├── requirements.txt
│   ├── routes/                 cases, images, analysis, reports blueprints
│   └── services/                one module per forensic capability
│       ├── hashing.py
│       ├── metadata.py
│       ├── ocr.py
│       ├── location.py
│       ├── manipulation.py
│       ├── synthetic.py
│       ├── visual.py
│       ├── similarity.py
│       ├── enhancement.py
│       ├── reverse_search.py
│       └── report_generator.py
└── frontend/
    ├── templates/index.html
    └── static/{css,js}
```

## API surface (all under `/api`)

- `GET/POST /cases`, `GET/PATCH /cases/<id>`, `GET /cases/<id>/timeline`
- `GET/POST /cases/<id>/notes`
- `POST /images` (multipart upload), `GET /images/<id>`, `GET /images/<id>/file`
- `POST /images/<id>/enhance` (preset or custom operations)
- `POST /analysis/<id>/ocr`, `/manipulation`, `/synthetic`, `/visual`
- `GET /analysis/<id>/location`, `/similarity`, `/reverse-search-links`
- `POST /reports/<id>/generate`, `GET /reports/<id>/download`

## Notes

- Max upload size: 50 MB per image (configurable in `app.py`).
- Supported formats: JPG, JPEG, PNG, WEBP, TIFF, HEIC.
- Tesseract language packs `hin`/`guj` are installed by `setup.sh`;
  if they're missing at runtime, OCR falls back to English only.
