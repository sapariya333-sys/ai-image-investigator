"""
Duplicate / Similar Image Finder.

Exact duplicates are found via SHA-256 (already computed at upload).
Visually similar images are found via perceptual hashing (pHash),
which tolerates re-compression, resizing, and minor edits.
"""
import imagehash
from PIL import Image


def compute_phash(path):
    return str(imagehash.phash(Image.open(path)))


def hamming_distance(hash_a, hash_b):
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def find_matches(target_phash, target_sha256, other_images, phash_threshold=8):
    """
    other_images: list of dicts with keys id, original_filename, sha256, phash
    Returns exact_duplicates and similar_images (excluding the target itself).
    """
    exact_duplicates = []
    similar_images = []

    for img in other_images:
        if img["sha256"] == target_sha256:
            exact_duplicates.append(img)
            continue
        if img.get("phash"):
            try:
                dist = int(hamming_distance(target_phash, img["phash"]))
            except Exception:
                continue
            if dist <= phash_threshold:
                similarity_pct = round(max(0, (64 - dist) / 64 * 100), 1)
                similar_images.append({**img, "hamming_distance": dist, "similarity_pct": similarity_pct})

    similar_images.sort(key=lambda x: x["hamming_distance"])
    return exact_duplicates, similar_images
