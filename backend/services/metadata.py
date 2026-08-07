"""
Metadata Explorer service.

Extracts file-level properties and EXIF/GPS data, and clearly tags
every value with its source so the UI never presents a filesystem
timestamp as if it were a capture timestamp.

Uses Pillow's built-in EXIF reader (Image.getexif() + get_ifd) rather
than a separate exifread pass: Pillow's reader works consistently
across JPEG, PNG, WEBP, TIFF, and HEIC (via pillow_heif), whereas
exifread targets JPEG/TIFF containers and silently returns nothing
for the others -- which would have meant EXIF/GPS extraction quietly
failing on WEBP images and on HEIC photos straight off an iPhone,
without any error to indicate it happened.
"""
import os
from PIL import Image, ExifTags

FRIENDLY_NAMES = {
    "DateTimeOriginal": "Date/Time Original",
    "DateTime": "Modify Date",
    "Make": "Camera Manufacturer",
    "Model": "Camera Model",
    "LensModel": "Lens Model",
    "FocalLength": "Focal Length",
    "FNumber": "Aperture (F-Number)",
    "ExposureTime": "Shutter Speed",
    "ISOSpeedRatings": "ISO",
    "PhotographicSensitivity": "ISO",
    "Flash": "Flash",
    "Orientation": "Orientation",
    "Software": "Software / Processing Application",
}


def _dms_to_decimal(dms, ref):
    try:
        degrees, minutes, seconds = [float(v) for v in dms]
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


def extract_file_properties(path, original_filename):
    stat = os.stat(path)
    with Image.open(path) as img:
        width, height = img.size
        mode = img.mode
        fmt = img.format

    return {
        "filename": original_filename,
        "file_extension": os.path.splitext(original_filename)[1].lower(),
        "mime_type": Image.MIME.get(fmt, "application/octet-stream"),
        "file_size_bytes": stat.st_size,
        "width": width,
        "height": height,
        "megapixels": round((width * height) / 1_000_000, 2),
        "color_mode": mode,
        # explicitly labeled -- NOT capture time
        "filesystem_modified_time": {
            "value": stat.st_mtime,
            "source": "filesystem (not capture time)",
        },
    }


def extract_exif(path):
    """Returns (exif_findings: list[dict], gps: dict|None)."""
    findings = []

    with Image.open(path) as img:
        exif = img.getexif()
        if not exif:
            return findings, None

        tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}

        # Exif sub-IFD holds most camera settings (focal length, ISO, etc.)
        try:
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
            tag_map.update({ExifTags.TAGS.get(k, k): v for k, v in exif_ifd.items()})
        except Exception:
            pass

        for key, friendly in FRIENDLY_NAMES.items():
            if key in tag_map and tag_map[key] not in (None, ""):
                findings.append(
                    {"field_name": friendly, "field_value": str(tag_map[key]), "source": "EXIF"}
                )

        gps = None
        try:
            gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        except Exception:
            gps_ifd = {}

        if gps_ifd:
            gps_tags = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
            lat, lon = gps_tags.get("GPSLatitude"), gps_tags.get("GPSLongitude")
            if lat and lon:
                lat_dec = _dms_to_decimal(lat, gps_tags.get("GPSLatitudeRef", "N"))
                lon_dec = _dms_to_decimal(lon, gps_tags.get("GPSLongitudeRef", "E"))
                if lat_dec is not None and lon_dec is not None:
                    gps = {
                        "latitude": lat_dec,
                        "longitude": lon_dec,
                        "altitude": str(gps_tags.get("GPSAltitude")) if gps_tags.get("GPSAltitude") is not None else None,
                        "gps_timestamp": str(gps_tags.get("GPSTimeStamp")) if gps_tags.get("GPSTimeStamp") is not None else None,
                        "direction": str(gps_tags.get("GPSImgDirection")) if gps_tags.get("GPSImgDirection") is not None else None,
                        "caveat": (
                            "GPS metadata can be modified and should not, by itself, "
                            "be treated as proof of where this image was captured."
                        ),
                    }

    return findings, gps
