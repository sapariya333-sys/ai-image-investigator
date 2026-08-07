"""
Reverse Image Search Hub.

Full API-based automation for Google Lens / Bing Visual Search /
Yandex / TinEye requires provider API keys and is subject to each
provider's terms of service — those are configuration, not code, and
are documented in README.md.

Until keys are configured, this module provides one-click "open in
provider" links pre-built from the image's public URL, which is the
same interaction pattern browser extensions for reverse image search
use. This keeps the module honest about what is automated (link
construction) versus what still needs a provider integration
(fetching results back into the platform).
"""


def build_search_links(public_image_url):
    return {
        "google_lens": f"https://lens.google.com/uploadbyurl?url={public_image_url}",
        "bing_visual_search": f"https://www.bing.com/images/search?view=detailv2&iss=sbiupload&q=imgurl:{public_image_url}",
        "yandex_images": f"https://yandex.com/images/search?rpt=imageview&url={public_image_url}",
        "tineye": f"https://tineye.com/search?url={public_image_url}",
        "note": (
            "These open each provider's reverse-image search pre-loaded with "
            "this image. Full in-platform result ingestion requires that "
            "provider's API key — see README for configuration."
        ),
    }
