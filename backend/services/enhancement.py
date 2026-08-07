"""
Image Enhancement Lab.

Every operation reads the ORIGINAL evidence file and writes a brand
new ENHANCED DERIVATIVE — the original on disk is never touched.
Callers are responsible for hashing the derivative after this returns
(see routes/images.py) to keep the evidence chain intact:

    ORIGINAL EVIDENCE -> WORKING COPY -> ENHANCED DERIVATIVE
"""
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

PRESETS = {
    "enhance_face": {"sharpen": 1.6, "contrast": 1.15, "brightness": 1.05, "denoise": True},
    "enhance_number_plate": {"sharpen": 2.0, "contrast": 1.35, "brightness": 1.1, "grayscale": True},
    "enhance_document": {"sharpen": 1.3, "contrast": 1.4, "brightness": 1.15, "grayscale": True},
    "enhance_cctv_frame": {"sharpen": 1.8, "contrast": 1.25, "brightness": 1.2, "denoise": True, "upscale": 2},
    "enhance_text": {"sharpen": 2.2, "contrast": 1.5, "brightness": 1.0, "grayscale": True},
}


def apply_operations(path, out_path, ops):
    """
    ops: dict, any of:
      upscale (int factor), sharpen (float), denoise (bool),
      brightness (float), contrast (float), gamma (float),
      exposure (float), grayscale (bool), rotate (degrees),
      crop ([left, top, right, bottom]), perspective (bool - noop placeholder)
    """
    img = Image.open(path).convert("RGB")

    if ops.get("crop"):
        left, top, right, bottom = [int(v) for v in ops["crop"]]
        left = max(0, min(left, img.width - 1))
        top = max(0, min(top, img.height - 1))
        right = max(left + 1, min(right, img.width))
        bottom = max(top + 1, min(bottom, img.height))
        img = img.crop((left, top, right, bottom))

    if ops.get("rotate"):
        img = img.rotate(-float(ops["rotate"]), expand=True)

    if ops.get("upscale"):
        factor = max(1, min(4, int(ops["upscale"])))
        img = img.resize((img.width * factor, img.height * factor), Image.LANCZOS)

    if ops.get("denoise"):
        img = img.filter(ImageFilter.MedianFilter(size=3))

    if ops.get("sharpen"):
        img = ImageEnhance.Sharpness(img).enhance(float(ops["sharpen"]))

    if ops.get("brightness"):
        img = ImageEnhance.Brightness(img).enhance(float(ops["brightness"]))

    if ops.get("contrast"):
        img = ImageEnhance.Contrast(img).enhance(float(ops["contrast"]))

    if ops.get("gamma"):
        gamma = float(ops["gamma"])
        lut = [pow(x / 255.0, 1.0 / gamma) * 255 for x in range(256)]
        img = img.point(lut * 3)

    if ops.get("exposure"):
        img = ImageEnhance.Brightness(img).enhance(float(ops["exposure"]))

    if ops.get("grayscale"):
        img = ImageOps.grayscale(img)

    img.save(out_path)
    return out_path


def apply_preset(path, out_path, preset_name):
    if preset_name not in PRESETS:
        raise ValueError(f"Unknown preset: {preset_name}")
    return apply_operations(path, out_path, PRESETS[preset_name])
