import json
import os
import re
from pathlib import Path
from typing import Dict, Tuple

import requests
from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "api_config.json"
ENV_ROOT_PATH = ROOT / ".env"
ENV_API_PATH = Path(__file__).resolve().parent / ".env"

# Load envs explicitly (avoid load_dotenv() auto-discovery issues)
load_dotenv(dotenv_path=ENV_ROOT_PATH, override=True)
load_dotenv(dotenv_path=ENV_API_PATH, override=True)

ACCOUNT_ID = os.getenv("account_id")
GATEWAY_ID = os.getenv("gateway_id")
CLOUDFLARE_TOKEN = os.getenv("cloudflare_token")

SDXL_ENDPOINT = "@cf/stabilityai/stable-diffusion-xl-base-1.0"
LEONARDO_PHOENIX_ENDPOINT = "@cf/leonardo/phoenix-1.0"


def _load_config() -> Dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _pick_size_from_text(text: str) -> Tuple[int, int]:
    """Very small heuristic: detect 16:9 / 9:16 etc. Defaults to 1024x1024."""
    t = text.lower().replace(" ", "")
    # common aspect ratios
    if "16:9" in t or "16/9" in t:
        return 1024, 576
    if "9:16" in t or "9/16" in t:
        return 576, 1024
    if "4:3" in t or "4/3" in t:
        return 1024, 768
    if "3:4" in t or "3/4" in t:
        return 768, 1024
    if "1:1" in t or "1/1" in t:
        return 1024, 1024
    return 1024, 1024


def _deepseek_prompt(user_text: str, width: int, height: int) -> str:
    """Use DeepSeek (OpenAI-compatible) to expand user text into an English SDXL prompt."""
    cfg = _load_config()
    api_name = "deepseek"
    client = OpenAI(api_key=cfg[api_name]["key"], base_url=cfg[api_name]["base_url"])
    model = cfg[api_name]["models"]

    sys = (
        "You are a text-to-image prompt engineer for SDXL. "
        "Convert the user request into ONE concise but vivid English prompt suitable for SDXL. "
        "Do not include any policy text. Do not output markdown. Do not output JSON. "
        "Keep it descriptive: subject, style, composition, lighting, colors, details. "
        f"The target image size is {width}x{height} (keep composition suitable for this aspect ratio)."
    )

    # Strip an explicit ratio token to avoid it polluting the actual prompt
    cleaned = re.sub(r"\b(\d+\s*[:/]\s*\d+)\b", "", user_text).strip()

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": cleaned},
        ],
        temperature=0.6,
        max_tokens=300,
    )
    return (resp.choices[0].message.content or "").strip()


def generate_image_sdxl(user_text: str) -> Tuple[bytes, Dict]:
    """Generate image bytes via Cloudflare AI Gateway -> Workers AI (SDXL).

    Returns: (png_bytes, meta)
    meta includes final_prompt/width/height.
    """
    if not ACCOUNT_ID or not GATEWAY_ID or not CLOUDFLARE_TOKEN:
        raise RuntimeError("Missing Cloudflare gateway env vars: account_id/gateway_id/cloudflare_token")

    width, height = _pick_size_from_text(user_text)
    final_prompt = _deepseek_prompt(user_text, width=width, height=height)
    if not final_prompt:
        raise RuntimeError("DeepSeek returned empty prompt")

    payload = [
        {
            "provider": "workers-ai",
            "endpoint": SDXL_ENDPOINT,
            "headers": {
                "Authorization": f"Bearer {CLOUDFLARE_TOKEN}",
                "Content-Type": "application/json",
            },
            "query": {
                "prompt": final_prompt,
                "width": width,
                "height": height,
                "num_steps": 20,
            },
        }
    ]

    url = f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_ID}/"
    resp = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload), timeout=180)
    resp.raise_for_status()

    ct = (resp.headers.get("content-type") or "").lower()
    if ct.startswith("image/"):
        return resp.content, {"final_prompt": final_prompt, "width": width, "height": height}

    # Fallback: sometimes gateway returns JSON with base64 image
    try:
        obj = resp.json()
        b64 = None
        if isinstance(obj, dict):
            if isinstance(obj.get("result"), dict):
                b64 = obj["result"].get("image") or obj["result"].get("image_base64")
            b64 = b64 or obj.get("image") or obj.get("image_base64")
        if not b64:
            raise RuntimeError(f"Unexpected gateway response content-type={ct}, keys={list(obj) if isinstance(obj, dict) else type(obj)}")
        import base64

        return base64.b64decode(b64), {"final_prompt": final_prompt, "width": width, "height": height}
    except Exception as e:
        raise RuntimeError(f"Unexpected gateway response (not image, not json-with-b64). content-type={ct}. error={e}")


def generate_image_leonardo(user_text: str) -> Tuple[bytes, Dict]:
    """Generate image bytes via Cloudflare AI Gateway -> Workers AI (Leonardo Phoenix 1.0)."""
    if not ACCOUNT_ID or not GATEWAY_ID or not CLOUDFLARE_TOKEN:
        raise RuntimeError("Missing Cloudflare gateway env vars: account_id/gateway_id/cloudflare_token")

    width, height = _pick_size_from_text(user_text)
    # Re-use SDXL prompt expansion logic for now
    final_prompt = _deepseek_prompt(user_text, width=width, height=height)
    if not final_prompt:
        raise RuntimeError("DeepSeek returned empty prompt")

    payload = [
        {
            "provider": "workers-ai",
            "endpoint": LEONARDO_PHOENIX_ENDPOINT,
            "headers": {
                "Authorization": f"Bearer {CLOUDFLARE_TOKEN}",
                "Content-Type": "application/json",
            },
            "query": {
                "prompt": final_prompt,
                # Leonardo Phoenix supports width/height, though limits may vary
                "width": width,
                "height": height,
            },
        }
    ]

    url = f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_ID}/"
    resp = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload), timeout=180)
    resp.raise_for_status()

    ct = (resp.headers.get("content-type") or "").lower()
    if ct.startswith("image/"):
        return resp.content, {"final_prompt": final_prompt, "width": width, "height": height, "model": "leonardo-phoenix"}

    try:
        obj = resp.json()
        b64 = None
        if isinstance(obj, dict):
            if isinstance(obj.get("result"), dict):
                b64 = obj["result"].get("image") or obj["result"].get("image_base64")
            b64 = b64 or obj.get("image") or obj.get("image_base64")
        if not b64:
             raise RuntimeError(f"Unexpected gateway response content-type={ct}")
        import base64
        return base64.b64decode(b64), {"final_prompt": final_prompt, "width": width, "height": height, "model": "leonardo-phoenix"}
    except Exception as e:
        raise RuntimeError(f"Unexpected gateway response. error={e}")
