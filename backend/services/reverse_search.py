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
from urllib.parse import quote


def build_search_links(public_image_url):
    encoded = quote(public_image_url, safe="")
    return {
        "image_url": public_image_url,
        "google_lens": f"https://lens.google.com/uploadbyurl?url={encoded}",
        "bing_visual_search": f"https://www.bing.com/images/search?q=imgurl:{encoded}&view=detailv2&iss=sbi",
        "yandex_images": f"https://yandex.com/images/search?rpt=imageview&url={encoded}",
        "tineye": f"https://tineye.com/search/?url={encoded}",
        "note": (
            "These open each provider's reverse-image search pre-loaded with "
            "this image. The link is single-use-ish: it embeds a signed token "
            "that expires after 15 minutes, so if a search comes back empty, "
            "generate a fresh link and try again. Full in-platform result "
            "ingestion requires that provider's API key — see README."
        ),
    }
