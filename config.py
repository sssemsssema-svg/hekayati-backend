import os
import base64
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_DEFAULT_GEMINI = base64.b64decode("QVEuQWI4Uk42S2c0ZTF4Qm1sVHA0WmhpbHZOMTJhRE5UTm1RX01FV1diTjZTMHNBbTdwWWc=").decode("utf-8")
_DEFAULT_CF_ID = base64.b64decode("ZmVmZTFlNDNiZmY5NTk3ODExNGNiMDNkNmMyMGZlZjg=").decode("utf-8")
_DEFAULT_CF_TOKEN = base64.b64decode("Y2Z1dF92WkVJdnUyZ0JodmpzZWM0Nk9XUlZtc0dqenBRV2FRYkFCNW5aZUZaYzhjZDA0ZDQ=").decode("utf-8")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", _DEFAULT_GEMINI)
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-3.5-flash-lite")
IMAGE_BACKEND = os.getenv("IMAGE_BACKEND", "cloudflare")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-2.5-flash-image")

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", _DEFAULT_CF_ID)
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", _DEFAULT_CF_TOKEN)

MAX_AUDIO_MB = 25          # max upload size
MAX_BOOKS_PER_HOUR = 5     # per IP
CLEANUP_AFTER_HOURS = 24   # delete old books
MIN_SCENES = 4
MAX_SCENES = 10
DEBUG_TRANSCRIPT = True
