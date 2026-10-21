import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-2.5-flash")
IMAGE_BACKEND = os.getenv("IMAGE_BACKEND", "imagen")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "imagen-4.0-generate-001")

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")

MAX_AUDIO_MB = 25          # max upload size (accommodates 3+ minutes)
MAX_BOOKS_PER_HOUR = 5     # per IP
CLEANUP_AFTER_HOURS = 24   # delete old books
MIN_SCENES = 4
MAX_SCENES = 10
DEBUG_TRANSCRIPT = True
