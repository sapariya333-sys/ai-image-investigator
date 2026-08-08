"""
OCR & Text Intelligence.

Runs Tesseract across English + Hindi + Gujarati simultaneously
(tesseract's multi-language mode) so mixed-script signage common in
Indian street/CCTV imagery is captured in a single pass.

Every image is first normalized to an in-memory PNG. This matters
because pytesseract only hands a small whitelist of formats straight
through to Tesseract (JPEG/PNG/TIFF/BMP/GIF/PPM-family) and raises
TypeError on anything else -- which includes HEIC, and can include
WEBP depending on the Tesseract build. Re-encoding to PNG in memory
sidesteps that without ever writing a second copy of the evidence to
disk.
"""
import io
import re
import pytesseract
from PIL import Image

LANG_STRING = "eng+hin+guj"

PATTERNS = {
    "url": re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.IGNORECASE),
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"(\+?\d{1,3}[-\s]?)?\d{10}\b"),
    "vehicle_plate_in": re.compile(
        r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{0,3}[\s-]?\d{3,4}\b"
    ),
}


def _normalize_for_ocr(path):
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="PNG")
        buf.seek(0)
        return Image.open(buf)


def run_ocr(path):
    image = _normalize_for_ocr(path)
    try:
        text = pytesseract.image_to_string(image, lang=LANG_STRING)
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError(
            "The Tesseract OCR engine isn't installed on this server (only the "
            "pytesseract Python wrapper was). This happens when a host installs "
            "Python dependencies via pip but skips system packages -- Tesseract "
            "is a native binary, not a pip package. Deploy via the project's "
            "Dockerfile (which installs tesseract-ocr + language packs at the "
            "OS level), or install it manually: `apt-get install tesseract-ocr "
            "tesseract-ocr-hin tesseract-ocr-guj` on the host."
        ) from e
    except pytesseract.TesseractError:
        # a specific language pack (hin/guj) is likely missing -- fall back to English
        text = pytesseract.image_to_string(image, lang="eng")

    text = text.strip()
    entities = extract_entities(text)
    return {
        "language": LANG_STRING,
        "extracted_text": text,
        "entities": entities,
    }


def extract_entities(text):
    found = {}
    for label, pattern in PATTERNS.items():
        matches = sorted(set(m.strip() for m in pattern.findall(text) if m.strip()))
        if matches:
            found[label] = matches
    return found
