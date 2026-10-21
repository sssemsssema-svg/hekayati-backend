import asyncio
import base64
import hashlib
import io
import math
import random

import cv2
import httpx
import numpy as np
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

import config
from services.prompts import RETRY_EXTRA

client = genai.Client(api_key=config.GEMINI_API_KEY)

SIZE = 1536
TIMEOUT = 60
MAX_ATTEMPTS = 3  # 1 try + 2 retries

# Cleaning settings per age group. Fine manga lines need a gentler cleaner than thick toddler lines.
PROFILES = {
    "3-5": dict(thresh=170, min_blob=30, dilate=3, close=5,
                max_black=0.25, min_black=0.02, max_mid_gray=0.08),
    "6-10": dict(thresh=185, min_blob=10, dilate=0, close=3,   # dilate 0 = keep fine lines fine
                 max_black=0.30, min_black=0.02, max_mid_gray=0.12),
}


def _mock_image(prompt: str) -> bytes:
    """Generate a mock children's coloring scene locally using Pillow."""
    h = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(h)
    img = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    w = 12

    try:
        font = ImageFont.truetype("arial.ttf", 64)
    except Exception:
        font = ImageFont.load_default(size=64)

    # Outline-style TEST IMAGE text at top
    bbox = draw.textbbox((0, 0), "COLORING PAGE", font=font)
    tw = bbox[2] - bbox[0]
    tx = (SIZE - tw) // 2
    draw.text((tx, 60), "COLORING PAGE", fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0), font=font)

    # Ground line
    draw.line([(80, SIZE - 180), (SIZE - 80, SIZE - 180)], fill=(0, 0, 0), width=w)

    # Smiling Sun
    draw.ellipse((SIZE - 320, 120, SIZE - 120, 320), outline=(0, 0, 0), width=w)
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        x1 = (SIZE - 220) + int(115 * math.cos(rad))
        y1 = 220 + int(115 * math.sin(rad))
        x2 = (SIZE - 220) + int(150 * math.cos(rad))
        y2 = 220 + int(150 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=(0, 0, 0), width=w)

    # Human Character
    cx = SIZE // 2
    cy = SIZE // 2
    draw.ellipse((cx - 120, cy - 240, cx + 120, cy), outline=(0, 0, 0), width=w)  # Head
    draw.ellipse((cx - 60, cy - 170, cx - 30, cy - 120), outline=(0, 0, 0), width=w)  # Eye L
    draw.ellipse((cx + 30, cy - 170, cx + 60, cy - 120), outline=(0, 0, 0), width=w)  # Eye R
    draw.arc((cx - 50, cy - 110, cx + 50, cy - 50), 0, 180, fill=(0, 0, 0), width=w)  # Smile
    draw.rectangle((cx - 130, cy, cx + 130, cy + 300), outline=(0, 0, 0), width=w)  # Body
    draw.line([(cx - 70, cy + 300), (cx - 70, SIZE - 180)], fill=(0, 0, 0), width=w)  # Leg L
    draw.line([(cx + 70, cy + 300), (cx + 70, SIZE - 180)], fill=(0, 0, 0), width=w)  # Leg R

    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


async def _raw_image(prompt: str) -> bytes:
    """Ask the image model and return raw image bytes."""
    if config.IMAGE_BACKEND == "mock":
        return _mock_image(prompt)

    elif config.IMAGE_BACKEND == "imagen":
        r = await client.aio.models.generate_images(
            model=config.IMAGE_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
        )
        return r.generated_images[0].image.image_bytes

    elif config.IMAGE_BACKEND == "gemini":
        r = await client.aio.models.generate_content(
            model=config.IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        for part in r.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data
        raise RuntimeError("No image returned by the model")

    elif config.IMAGE_BACKEND == "cloudflare":
        if not config.CLOUDFLARE_ACCOUNT_ID or not config.CLOUDFLARE_API_TOKEN:
            raise ValueError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set in .env")

        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
        )
        headers = {
            "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": prompt,
            "steps": 4,
        }

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            resp = await http_client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Cloudflare Workers AI returned status {resp.status_code}: {resp.text}")

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                data = resp.json()
                if "result" in data and "image" in data["result"]:
                    return base64.b64decode(data["result"]["image"])
                elif "image" in data:
                    return base64.b64decode(data["image"])
                raise RuntimeError(f"Unexpected Cloudflare JSON response: {data}")
            return resp.content

    raise ValueError(f"Unknown IMAGE_BACKEND: {config.IMAGE_BACKEND}")


def clean_image(raw: bytes, age_group: str = "3-5"):
    """Return (png_bytes, is_good). Output is pure black lines on pure white."""
    p = PROFILES[age_group]
    arr = np.frombuffer(raw, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("Could not decode image")
    gray = cv2.resize(gray, (SIZE, SIZE), interpolation=cv2.INTER_CUBIC)

    mid_gray_ratio = float(np.mean((gray > 70) & (gray < 190)))  # shading check BEFORE thresholding

    lines = (gray < p["thresh"]).astype(np.uint8)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(lines, connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= p["min_blob"]
    lines = keep[labels].astype(np.uint8)

    if p["dilate"]:
        lines = cv2.dilate(lines, np.ones((p["dilate"], p["dilate"]), np.uint8), iterations=1)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (p["close"], p["close"]))
    lines = cv2.morphologyEx(lines, cv2.MORPH_CLOSE, kernel)  # close tiny gaps for the paint bucket

    black_ratio = float(lines.mean())
    out = np.where(lines == 1, 0, 255).astype(np.uint8)

    good = (p["min_black"] <= black_ratio <= p["max_black"]) and (mid_gray_ratio <= p["max_mid_gray"])
    _, buf = cv2.imencode(".png", out)
    return buf.tobytes(), good


def placeholder_png() -> bytes:
    img = Image.new("L", (SIZE, SIZE), 255)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


async def generate_page(prompt: str, age_group: str = "3-5") -> bytes:
    """Generate one clean coloring page. Retries with a simpler prompt if shading is detected."""
    last_png = None
    for attempt in range(MAX_ATTEMPTS):
        pr = prompt if attempt == 0 else prompt + RETRY_EXTRA[age_group]
        try:
            raw = await asyncio.wait_for(_raw_image(pr), timeout=TIMEOUT)
            png, good = clean_image(raw, age_group)
            last_png = png
            if good:
                return png
        except Exception as e:
            print(f"[image] attempt {attempt + 1} failed: {e}")
    return last_png if last_png else placeholder_png()


async def generate_all(prompts, age_group: str = "3-5", on_progress=None):
    """Run all prompts in parallel. Results keep the same order as prompts."""
    done = 0

    async def one(p):
        nonlocal done
        try:
            res = await generate_page(p, age_group)
        except Exception as e:
            print(f"[image] page failed: {e}")
            res = placeholder_png()
        done += 1
        if on_progress:
            on_progress(done, len(prompts))
        return res

    return await asyncio.gather(*[one(p) for p in prompts])
