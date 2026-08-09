"""
OCR & Text Intelligence.

Runs Tesseract, preferring English + Hindi + Gujarati simultaneously
so mixed-script signage common in Indian street/CCTV imagery is
captured in a single pass, but falls back to English-only whenever
that's cleaner (see run_ocr below).

Two real accuracy issues were found by testing against actual sample
evidence photos and fixed here:

1. Tesseract's default page segmentation badly fails on photos where
   the real text is a small region against a large, low-contrast
   background (e.g. a caption across the top third of an otherwise
   plain photo) -- it would return nothing at all. A grayscale +
   autocontrast pass before OCR fixes this completely; verified
   against a real failing sample where it took extracted text from
   empty to fully correct.
2. Running eng+hin+guj simultaneously on mostly-English text
   sometimes misreads Latin characters -- including handwritten text
   -- as Gujarati/Devanagari lookalikes (e.g. "f/5.6" read as
   "\u0aea5.6", or "Cr" from cursive "Recon" read as a 3-character
   Devanagari run). Checking merely "did any non-Latin character
   appear" is too fragile to filter this kind of noise -- a single
   stray misread triggers it. Instead both passes are run and
   compared by _quality_score() (count of recognized alnum
   characters): the multi-language pass only wins if it recognized
   meaningfully MORE content than English alone, which is what
   happens when it's reading genuine Gujarati/Hindi text the
   English-only pass couldn't parse at all. On a near-tie, English
   alone is preferred since it doesn't introduce script-confusion
   noise into otherwise-Latin text.

Every image is first normalized to an in-memory PNG/grayscale image
regardless of source format. This also matters because pytesseract
only hands a small whitelist of formats straight through to
Tesseract (JPEG/PNG/TIFF/BMP/GIF/PPM-family) and raises TypeError on
anything else -- which includes HEIC, and can include WEBP depending
on the Tesseract build.
"""
import io
import re
import pytesseract
from PIL import Image, ImageOps

LANG_STRING = "eng+hin+guj"

PATTERNS = {
    "url": re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.IGNORECASE),
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"(\+?\d{1,3}[-\s]?)?\d{10}\b"),
    "vehicle_plate_in": re.compile(
        r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{0,3}[\s-]?\d{3,4}\b"
    ),
}

_ALNUM = re.compile(r"[A-Za-z0-9]")
_NON_LATIN = re.compile(r"[\u0900-\u097F\u0A80-\u0AFF]")

# multi-lang must recognize at least this much MORE content than
# English-only to be trusted over it -- a near-tie means the extra
# "content" is very likely script-confusion noise, not real text.
_MULTI_LANG_MARGIN = 1.20


def _normalize_for_ocr(path):
    with Image.open(path) as img:
        gray = ImageOps.autocontrast(img.convert("L"))
        buf = io.BytesIO()
        gray.save(buf, format="PNG")
        buf.seek(0)
        return Image.open(buf)


def _quality_score(text):
    return len(_ALNUM.findall(text)) + len(_NON_LATIN.findall(text))


def _tesseract(image, lang):
    return pytesseract.image_to_string(image, lang=lang)


def run_ocr(path):
    image = _normalize_for_ocr(path)

    try:
        text_multi = _tesseract(image, LANG_STRING)
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
        # hin/guj language pack likely missing entirely
        text_multi = ""

    try:
        text_eng = _tesseract(image, "eng")
    except pytesseract.TesseractError:
        text_eng = ""

    score_multi = _quality_score(text_multi)
    score_eng = _quality_score(text_eng)

    if score_multi > score_eng * _MULTI_LANG_MARGIN:
        text, lang_used = text_multi, LANG_STRING
    else:
        text, lang_used = text_eng, "eng"

    text = text.strip()
    entities = extract_entities(text)
    return {
        "language": lang_used,
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
