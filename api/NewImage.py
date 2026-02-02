import json
import re
from pathlib import Path

from openai import OpenAI


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "api_config.json"


def _load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def generate_image_flux_url(prompt: str) -> str:
    """Generate image via FLUX endpoint and return a URL usable by Telegram send_photo."""
    cfg = _load_config()
    api_name = "flux"
    client = OpenAI(api_key=cfg[api_name]["key"], base_url=cfg[api_name]["base_url"])
    model = cfg[api_name]["models"]

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    text = (resp.choices[0].message.content or "").strip()

    # Prefer a direct URL if present
    url_match = re.search(r"(https?://[^\s\)]+)", text)
    if not url_match:
        raise RuntimeError(f"FLUX returned no URL. raw={text[:200]}")
    return url_match.group(1)


# Backward-compatible name used by old code
fluxImage = generate_image_flux_url
