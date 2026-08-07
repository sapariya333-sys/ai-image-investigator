"""
Synthetic Media Analysis (screening only).

Real deepfake/AI-image detection needs a trained classifier. Rather
than fabricate that capability, this module runs a transparent
frequency-domain heuristic (many GAN/diffusion outputs leave subtle,
regular high-frequency artifacts from upsampling) and reports it as a
coarse screening signal only — never a verdict. The README documents
where to plug in a real classifier (e.g. a hosted detection API) for
production use.
"""
import numpy as np
from PIL import Image


def fft_artifact_score(path):
    img = Image.open(path).convert("L")
    # normalize size for comparable frequency bins
    img = img.resize((512, 512))
    arr = np.asarray(img).astype(np.float32)

    f = np.fft.fft2(arr)
    fshift = np.fft.fftshift(f)
    magnitude = np.log(np.abs(fshift) + 1)

    h, w = magnitude.shape
    cy, cx = h // 2, w // 2
    radius_low = min(h, w) // 8
    radius_high = min(h, w) // 2 - 4

    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)

    low_band = magnitude[dist <= radius_low].mean()
    high_band = magnitude[(dist > radius_low) & (dist <= radius_high)].mean()

    ratio = float(high_band / low_band) if low_band > 0 else 0.0
    return ratio, magnitude


def analyze(path):
    ratio, _ = fft_artifact_score(path)

    # Thresholds are heuristic, not calibrated against a labeled dataset —
    # documented in README as an integration point for a real classifier.
    if ratio > 0.75:
        assessment = "Elevated high-frequency regularity — weak indicator of synthetic/upsampled content"
        confidence = "low-moderate"
    else:
        assessment = "No strong frequency-domain indicator of synthetic content"
        confidence = "low"

    return {
        "assessment": assessment,
        "confidence": confidence,
        "frequency_ratio": round(ratio, 3),
        "method": "FFT high-to-low frequency band ratio (coarse heuristic)",
        "disclaimer": (
            "This is a screening signal only, not a deepfake/AI-detection "
            "verdict. Production use should route through a dedicated, "
            "validated synthetic-media classifier — see README integration "
            "notes."
        ),
    }
