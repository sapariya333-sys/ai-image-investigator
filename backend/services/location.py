"""
Location Intelligence.

Rather than emitting a single opaque "AI Location: X — 98%" figure,
this module lists every clue it found (text, GPS, script/language)
and states, in plain language, how consistent they are with each
other — so the investigator can see *why*, not just *what*.
"""
import re

INDIAN_PLACE_HINT = re.compile(
    r"\b(road|rd|nagar|chowk|circle|marg|gali|colony|pura|ganj|peth)\b", re.IGNORECASE
)


def script_hint(text):
    """Very rough script detection based on Unicode block ranges."""
    if not text:
        return None
    if re.search(r"[\u0A80-\u0AFF]", text):
        return "Gujarati script detected"
    if re.search(r"[\u0900-\u097F]", text):
        return "Devanagari (Hindi) script detected"
    if re.search(r"[A-Za-z]", text):
        return "Latin/English script detected"
    return None


def build_assessment(gps, ocr_text, ocr_entities, faces_detected=0):
    clues = []

    if gps:
        clues.append(
            {
                "type": "metadata",
                "label": "GPS coordinates",
                "detail": f"{gps['latitude']}, {gps['longitude']}",
                "caveat": gps.get("caveat"),
            }
        )

    script = script_hint(ocr_text)
    if script:
        clues.append({"type": "text", "label": "Script/language", "detail": script})

    place_hints = INDIAN_PLACE_HINT.findall(ocr_text or "")
    if place_hints:
        clues.append(
            {
                "type": "text",
                "label": "Place-name-style token in OCR text",
                "detail": f"Matched pattern(s): {', '.join(sorted(set(w.lower() for w in place_hints)))}",
            }
        )

    if ocr_entities.get("vehicle_plate_in"):
        clues.append(
            {
                "type": "text",
                "label": "Possible vehicle registration plate",
                "detail": ", ".join(ocr_entities["vehicle_plate_in"]),
                "caveat": "Format matched heuristically — verify manually before relying on it.",
            }
        )

    if ocr_entities.get("phone"):
        clues.append(
            {
                "type": "text",
                "label": "Phone number in image",
                "detail": ", ".join(ocr_entities["phone"]),
            }
        )

    if not clues:
        narrative = "No location-relevant clues were extracted from metadata or OCR text."
    elif len(clues) == 1:
        narrative = "Only one location-relevant clue was found; treat as a weak, unconfirmed lead."
    else:
        narrative = (
            f"{len(clues)} independent clue(s) were extracted. Review whether they are "
            "mutually consistent before drawing a location conclusion."
        )

    return {"clues": clues, "narrative": narrative}
