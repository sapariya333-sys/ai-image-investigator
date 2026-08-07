"""
Image Authenticity & Manipulation Analysis.

Implements Error Level Analysis (ELA) and a handful of lightweight,
deterministic compression/noise heuristics. This module intentionally
never returns a verdict like "fake" or "authentic" — only indicators,
each carrying an explicit severity band, plus the standing note that
further forensic examination is recommended.

These heuristics are a legitimate, widely-used *first pass* in image
forensics, but — like all such heuristics — they can false-positive
on legitimately re-saved or re-compressed images, so they are always
surfaced as leads, not conclusions.
"""
import os
from PIL import Image, ImageChops
import numpy as np


def error_level_analysis(path, out_path, quality=90, scale=15):
    """
    Re-saves the image at a known JPEG quality and diffs it against the
    original. Regions that were edited/composited after the original
    save tend to show a different error level than untouched regions.
    """
    original = Image.open(path).convert("RGB")
    tmp_path = out_path + ".tmp.jpg"
    original.save(tmp_path, "JPEG", quality=quality)
    resaved = Image.open(tmp_path)

    diff = ImageChops.difference(original, resaved)
    diff_array = np.asarray(diff).astype(np.float32)

    max_diff = diff_array.max() if diff_array.size else 0
    mean_diff = float(diff_array.mean()) if diff_array.size else 0.0
    std_diff = float(diff_array.std()) if diff_array.size else 0.0

    # amplify for visualization
    if max_diff > 0:
        amplified = np.clip(diff_array * (255.0 * scale / max_diff), 0, 255).astype("uint8")
    else:
        amplified = diff_array.astype("uint8")

    Image.fromarray(amplified).save(out_path, "PNG")
    os.remove(tmp_path)

    return {
        "ela_image_path": out_path,
        "mean_error_level": round(mean_diff, 3),
        "std_error_level": round(std_diff, 3),
        "max_error_level": round(float(max_diff), 3),
    }


def compression_heuristics(path):
    """Cheap, deterministic signals about compression history."""
    indicators = []
    img = Image.open(path)

    if img.format == "JPEG":
        quantization = getattr(img, "quantization", None)
        if quantization:
            tables = list(quantization.values())
            if len(tables) > 1:
                variance = np.var([np.mean(t) for t in tables])
                if variance > 50:
                    indicators.append(
                        {
                            "indicator": "Inconsistent quantization tables",
                            "detail": (
                                "Luminance and chrominance quantization tables "
                                "differ more than typical for a single-generation "
                                "JPEG save, which can indicate re-compression."
                            ),
                            "severity": "moderate",
                        }
                    )

    if "exif" not in img.info and img.format == "JPEG":
        indicators.append(
            {
                "indicator": "No embedded EXIF in a JPEG file",
                "detail": (
                    "JPEGs from cameras/phones normally carry EXIF data. Its "
                    "absence is consistent with metadata stripping, "
                    "screenshotting, or re-saving through an editor — but is "
                    "not on its own evidence of manipulation."
                ),
                "severity": "low",
            }
        )

    return indicators


def noise_edge_heuristics(path):
    """Simple noise-uniformity check using local standard deviation blocks."""
    indicators = []
    img = Image.open(path).convert("L")
    arr = np.asarray(img).astype(np.float32)

    h, w = arr.shape
    block = 32
    stds = []
    for y in range(0, h - block, block):
        for x in range(0, w - block, block):
            patch = arr[y : y + block, x : x + block]
            stds.append(patch.std())

    if len(stds) > 4:
        stds = np.array(stds)
        overall_std = stds.std()
        if overall_std > stds.mean() * 0.9 and stds.mean() > 0:
            indicators.append(
                {
                    "indicator": "Noise-level inconsistency across regions",
                    "detail": (
                        "Local noise variance differs substantially across the "
                        "frame, which can result from splicing regions from "
                        "different source images or from selective denoising."
                    ),
                    "severity": "moderate",
                }
            )

    return indicators


def analyze(path, ela_out_path):
    ela = error_level_analysis(path, ela_out_path)
    indicators = compression_heuristics(path) + noise_edge_heuristics(path)

    if ela["std_error_level"] > 12:
        indicators.append(
            {
                "indicator": "Elevated error-level variance (ELA)",
                "detail": (
                    "Error Level Analysis shows uneven error levels across the "
                    "image, a pattern sometimes associated with localized "
                    "edits. Review the ELA overlay directly."
                ),
                "severity": "moderate",
            }
        )

    return {
        "ela": ela,
        "indicators": indicators,
        "summary": (
            "Potential manipulation indicators detected. Further forensic "
            "examination recommended."
            if indicators
            else "No manipulation indicators surfaced by automated screening. "
            "This does not rule out manipulation — manual review is still "
            "recommended for evidentiary use."
        ),
    }
