"""
AI Visual Investigator.

Uses OpenCV's bundled Haar cascades for face detection (fully local,
no model download required) plus simple, transparent pixel-statistics
heuristics for day/night and indoor/outdoor framing. These are
intentionally conservative: every output states its method and a
confidence band, and the module never claims object-level detection
it cannot actually back up.

Images are decoded via Pillow (not cv2.imread) and converted to a
numpy array before handing them to OpenCV. cv2.imread has its own,
narrower codec set and silently returns None on formats it can't
read -- notably HEIC -- which would otherwise make this module report
"0 faces detected" on a HEIC photo as if that were a real finding,
when it had actually failed to read the file at all. Routing through
Pillow (which handles HEIC via the pillow_heif plugin registered in
app.py) keeps this module's confidence claims honest across every
format the platform accepts.
"""
import cv2
import numpy as np
from PIL import Image

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")


def _load_bgr(path):
    """Decode any supported image format into an OpenCV-style BGR array."""
    with Image.open(path) as img:
        rgb = np.array(img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def detect_faces(path):
    img = _load_bgr(path)
    if img is None or img.size == 0:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))

    results = []
    for (x, y, w, h) in faces:
        roi_gray = gray[y : y + h, x : x + w]
        eyes = EYE_CASCADE.detectMultiScale(roi_gray)
        results.append(
            {
                "bounding_box": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                "eyes_detected": len(eyes),
                "confidence": "moderate" if len(eyes) >= 1 else "low",
            }
        )
    return results


def brightness_profile(path):
    img = Image.open(path).convert("L")
    arr = np.asarray(img).astype(np.float32)
    mean_brightness = float(arr.mean())

    if mean_brightness > 140:
        lighting = "day / well-lit"
    elif mean_brightness > 70:
        lighting = "dusk, indoor, or overcast"
    else:
        lighting = "night / low-light"

    return {
        "mean_brightness": round(mean_brightness, 1),
        "assessment": lighting,
        "confidence": "low",
        "method": "global mean pixel brightness (coarse heuristic)",
    }


def color_profile(path):
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img).astype(np.float32)
    r, g, b = arr[..., 0].mean(), arr[..., 1].mean(), arr[..., 2].mean()

    green_bias = g - ((r + b) / 2)
    outdoor_leaning = green_bias > 8

    return {
        "avg_rgb": {"r": round(float(r), 1), "g": round(float(g), 1), "b": round(float(b), 1)},
        "assessment": "possible outdoor/vegetation presence" if outdoor_leaning else "inconclusive",
        "confidence": "low",
        "method": "average color-channel bias (coarse heuristic, not a scene classifier)",
    }


def analyze(path):
    faces = detect_faces(path)
    return {
        "faces_detected": len(faces),
        "faces": faces,
        "lighting": brightness_profile(path),
        "color_environment": color_profile(path),
        "note": (
            "Object-category detection (vehicles, signage, etc.) requires a "
            "trained detection model and is a configurable integration point "
            "— see README. All results above require investigator verification."
        ),
    }
