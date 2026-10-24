# حكاياتي الملونة — الخطوات الكاملة (أمر + كود جاهز)

## طريقة الاستخدام
1. ابدئي محادثة جديدة مع Gemini والصقي **الخطوة 0** الأول.
2. بعدها الصقي **خطوة واحدة بس** (الأمر + كل الملفات اللي تحتها)، وجرّبي الاختبار، وبعدين الخطوة اللي بعدها.
3. لو حصل خطأ: ابعتي الخطأ كامل لـ Gemini وقولي "صلّح بأصغر تعديل ممكن".
4. أسماء موديلات Gemini/Imagen بتتغير، راجعيها من ai.google.dev/gemini-api/docs/models وحطي الصحيح في ملف `.env`.

---

## الخطوة 0 — تعريف الدور (الصقيها أول حاجة)

```text
You are my implementation assistant for a project called "My Colorful Tales" (Flutter app + Python FastAPI backend + Gemini API).
I will send steps. Each step contains exact files with complete code. Rules:
1) Create every file exactly as given, with the same name and path. Do NOT rewrite, refactor, rename, "improve" or add extras.
2) If something fails, show me the error and suggest the smallest possible fix, and wait for my approval.
3) After creating the files, give me only the exact commands to run and how to test.
4) Do only the current step.
Reply "ready" if you understand.
```

---

# الجزء الأول: الباك إند (مجلد backend)

## الخطوة 1 — هيكل الباك إند

```text
Step 1: Create these files exactly as given inside a folder named backend. Then give me the commands to create a venv, install requirements, run the server, and test GET /health.
```

### FILE: backend/requirements.txt
```text
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9
python-dotenv>=1.0
google-genai>=1.0
pydantic>=2.7
pillow>=10.3
opencv-python-headless>=4.9
numpy>=1.26
reportlab>=4.2
arabic-reshaper>=3.0
python-bidi>=0.5
```

### FILE: backend/.env.example
```text
GEMINI_API_KEY=put_your_key_here
TEXT_MODEL=gemini-2.5-flash
# imagen  = Imagen models via generate_images
# gemini  = Gemini image models via generate_content
IMAGE_BACKEND=imagen
IMAGE_MODEL=imagen-4.0-generate-001
```

### FILE: backend/config.py
```python
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

MAX_AUDIO_MB = 10          # max upload size
MAX_BOOKS_PER_HOUR = 5     # per IP
CLEANUP_AFTER_HOURS = 24   # delete old books
```

### FILE: backend/main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="My Colorful Tales")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}
```

**تشغيل (ويندوز):**
```text
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env     (وبعدين حطي المفتاح في .env)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
افتحي `http://localhost:8000/health` لازم تشوفي `{"ok": true}`.

---

## الخطوة 2 — خدمة القصة (صوت ← 4 مشاهد)

```text
Step 2: Create these files exactly as given inside backend. Then replace backend/main.py with the new version given here. Give me the command to test with a sample audio file (m4a or wav) using test_story.py.
```

### FILE: backend/utils.py
```python
from fastapi import HTTPException

AUDIO_MIME = {
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
}


def mime_for(filename: str) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext not in AUDIO_MIME:
        raise HTTPException(400, "Unsupported audio type. Use m4a, wav or mp3.")
    return AUDIO_MIME[ext]
```

### FILE: backend/services/__init__.py
```python
```

### FILE: backend/services/story_service.py
```python
import json
from typing import List

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

import config

client = genai.Client(api_key=config.GEMINI_API_KEY)

# Added to EVERY image prompt by code (not by the model) so it is never forgotten.
IMAGE_SUFFIX = (
    "children's coloring book page, thick uniform black outlines only, pure white background, "
    "no shading, no gradients, no grayscale, no filled black areas, no hatching, no textures, "
    "no shadows, large simple closed shapes, easy for a 5 year old to color, no text, no watermark"
)

SYSTEM_PROMPT = """You are a children's story director for kids aged 3-8.
You will hear an Arabic voice recording of a child telling a story idea. Understand child pronunciation.
Tasks:
1. Understand the idea. Remove anything violent, scary, sexual, hateful or otherwise inappropriate and rewrite it gently and warmly.
2. If the whole idea is unsafe and cannot be rewritten, return safe=false with a short reason and empty scenes.
3. Otherwise write a coherent, kind story in exactly 4 scenes (beginning, problem/adventure, solution, happy ending).
4. Define ONE main character with a very detailed English description (age, hair, clothes, colors, accessories, special features). Keep it fixed.
5. For each scene write: narration_ar = 1-2 short simple Arabic sentences; scene_en = an English description of ONE simple scene,
   the character centered, at most 3 simple background objects. Do NOT repeat the character description inside scene_en, just say "the character".
Return ONLY this JSON and nothing else:
{"safe": true, "reason": "", "title": "Arabic title",
 "character_description": "English description",
 "scenes": [{"narration_ar": "...", "scene_en": "..."}, ... exactly 4 items]}
"""


class Scene(BaseModel):
    narration_ar: str
    scene_en: str
    image_prompt_en: str = ""


class Story(BaseModel):
    safe: bool
    reason: str = ""
    title: str = ""
    character_description: str = ""
    scenes: List[Scene] = Field(default_factory=list)


async def make_story(audio_bytes: bytes, mime_type: str) -> Story:
    last_error = None
    for _ in range(2):  # one retry on invalid JSON
        try:
            resp = await client.aio.models.generate_content(
                model=config.TEXT_MODEL,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Listen to the child's story and follow the instructions.",
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            story = Story.model_validate_json(resp.text)
            if story.safe:
                if len(story.scenes) != 4:
                    raise ValueError("Expected exactly 4 scenes")
                for s in story.scenes:
                    s.image_prompt_en = (
                        f"{story.character_description}. "
                        f"Scene: {s.scene_en}. {IMAGE_SUFFIX}"
                    )
            return story
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_error = e
    raise RuntimeError(f"Story generation failed: {last_error}")
```

### FILE: backend/test_story.py
```python
import asyncio
import json
import sys

from services.story_service import make_story
from utils import AUDIO_MIME

path = sys.argv[1]  # usage: python test_story.py sample.m4a
ext = path.rsplit(".", 1)[-1].lower()
data = open(path, "rb").read()
story = asyncio.run(make_story(data, AUDIO_MIME[ext]))
print(json.dumps(story.model_dump(), ensure_ascii=False, indent=2))
```

### FILE: backend/main.py  (استبدلي القديم بده)
```python
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from services.story_service import make_story
from utils import mime_for

app = FastAPI(title="My Colorful Tales")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/story")
async def story(audio: UploadFile = File(...)):
    mime = mime_for(audio.filename)
    data = await audio.read()
    if not data or len(data) > config.MAX_AUDIO_MB * 1024 * 1024:
        raise HTTPException(400, "Audio is empty or too large")
    result = await make_story(data, mime)
    return result.model_dump()
```

**اختبار:** سجلي ملف صوت صغير `sample.m4a` بحكاية بالعربي وشغلي `python test_story.py sample.m4a`. لازم يطلع JSON فيه 4 مشاهد.

---

## الخطوة 3 — توليد صور التلوين النضيفة

```text
Step 3: Create these files exactly as given inside backend. Then give me the command to run test_images.py and tell me where the 4 PNGs are saved.
```

### FILE: backend/services/image_service.py
```python
import asyncio
import io

import cv2
import numpy as np
from google import genai
from google.genai import types
from PIL import Image

import config

client = genai.Client(api_key=config.GEMINI_API_KEY)

# ---- tunable constants (change here if shading still appears) ----
SIZE = 1536
THRESH = 170            # raise to 190 if lines look too thin / light gray lines vanish
MIN_BLOB = 30           # remove black specks smaller than this (pixels)
MAX_BLACK = 0.25        # more black than this => filled shapes / too dark
MIN_BLACK = 0.02        # less black than this => almost empty
MAX_MID_GRAY = 0.08     # more mid-gray than this (before threshold) => shading
RETRY_EXTRA = ", even simpler, fewer details, bolder outlines, absolutely no shading"
TIMEOUT = 60
MAX_ATTEMPTS = 3        # 1 try + 2 retries


async def _raw_image(prompt: str) -> bytes:
    """Ask the image model and return raw image bytes."""
    if config.IMAGE_BACKEND == "imagen":
        r = await client.aio.models.generate_images(
            model=config.IMAGE_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
        )
        return r.generated_images[0].image.image_bytes

    r = await client.aio.models.generate_content(
        model=config.IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    )
    for part in r.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    raise RuntimeError("No image returned by the model")


def clean_image(raw: bytes):
    """Return (png_bytes, is_good). Output is pure black lines on pure white."""
    arr = np.frombuffer(raw, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("Could not decode image")
    gray = cv2.resize(gray, (SIZE, SIZE), interpolation=cv2.INTER_CUBIC)

    # shading check BEFORE thresholding
    mid_gray_ratio = float(np.mean((gray > 70) & (gray < 190)))

    # 1) threshold: 1 = line, 0 = background
    lines = (gray < THRESH).astype(np.uint8)

    # 2) remove tiny specks
    n, labels, stats, _ = cv2.connectedComponentsWithStats(lines, connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= MIN_BLOB
    lines = keep[labels].astype(np.uint8)

    # 3) make lines a bit bolder
    lines = cv2.dilate(lines, np.ones((3, 3), np.uint8), iterations=1)

    # 4) close tiny gaps so shapes are closed (needed for the paint bucket)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    lines = cv2.morphologyEx(lines, cv2.MORPH_CLOSE, kernel)

    black_ratio = float(lines.mean())
    out = np.where(lines == 1, 0, 255).astype(np.uint8)

    good = (MIN_BLACK <= black_ratio <= MAX_BLACK) and (mid_gray_ratio <= MAX_MID_GRAY)
    _, buf = cv2.imencode(".png", out)
    return buf.tobytes(), good


def placeholder_png() -> bytes:
    img = Image.new("L", (SIZE, SIZE), 255)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


async def generate_page(prompt: str) -> bytes:
    """Generate one clean coloring page. Retries with a simpler prompt if shading is detected."""
    last_png = None
    for attempt in range(MAX_ATTEMPTS):
        p = prompt if attempt == 0 else prompt + RETRY_EXTRA
        try:
            raw = await asyncio.wait_for(_raw_image(p), timeout=TIMEOUT)
            png, good = clean_image(raw)
            last_png = png
            if good:
                return png
        except Exception as e:
            print(f"[image] attempt {attempt + 1} failed: {e}")
    return last_png if last_png else placeholder_png()


async def generate_all(prompts, on_progress=None):
    """Run all prompts in parallel. Results keep the same order as prompts."""
    done = 0

    async def one(p):
        nonlocal done
        try:
            res = await generate_page(p)
        except Exception as e:
            print(f"[image] page failed: {e}")
            res = placeholder_png()
        done += 1
        if on_progress:
            on_progress(done, len(prompts))
        return res

    return await asyncio.gather(*[one(p) for p in prompts])
```

### FILE: backend/test_images.py
```python
import asyncio

from services.image_service import generate_all
from services.story_service import IMAGE_SUFFIX

CHAR = ("A 6 year old girl with two black braids, round glasses, a polka dot dress, "
        "rain boots and a small backpack")
SCENES = [
    "the character waves hello next to a big tree",
    "the character finds a friendly dragon in a cave",
    "the character and the dragon fly over a small village",
    "the character and the dragon eat cake under the sun",
]
prompts = [f"{CHAR}. Scene: {s}. {IMAGE_SUFFIX}" for s in SCENES]

results = asyncio.run(generate_all(prompts))
for i, png in enumerate(results, 1):
    with open(f"test_page_{i}.png", "wb") as f:
        f.write(png)
print("Saved test_page_1.png ... test_page_4.png")
```

**اختبار:** افتحي الـ 4 صور. المطلوب: خطوط سودا على أبيض بس، بدون أي رمادي. لو فيه تظليل ارفعي `THRESH` لـ 190.

---

## الخطوة 4 — الـ PDF بالعربي

```text
Step 4: Create these files exactly as given inside backend. Also tell me exactly where to download the font Amiri-Regular.ttf and where to put it (backend/fonts/). Then give me the command to run test_pdf.py.
```

**الخط:** نزّلي `Amiri-Regular.ttf` من fonts.google.com/specimen/Amiri وحطيه في `backend/fonts/`. (مهم: Amiri بالذات لأن Cairo على جوجل نسخة متغيرة ومش بتشتغل مع reportlab.)

### FILE: backend/services/pdf_service.py
```python
import io
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_PATH = Path(__file__).resolve().parent.parent / "fonts" / "Amiri-Regular.ttf"
FONT = "AR"
_registered = False


def _ensure_font():
    global _registered
    if _registered:
        return
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Arabic font not found: {FONT_PATH}")
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))
    _registered = True


def _shape(text: str) -> str:
    """Fix Arabic letter joining + right-to-left order."""
    return get_display(arabic_reshaper.reshape(text))


def _wrap(text: str, size: float, max_w: float):
    lines, cur = [], ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if pdfmetrics.stringWidth(_shape(test), FONT, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def build_pdf(title: str, pages: list, out_path: str):
    """pages = [{"png": bytes, "narration": str}, ...]"""
    _ensure_font()
    W, H = A4
    m = 2 * cm
    c = canvas.Canvas(out_path, pagesize=A4)
    c.setTitle(title)

    # ---- cover ----
    c.setFont(FONT, 44)
    c.drawCentredString(W / 2, H - 4 * cm, _shape(title))
    c.setFont(FONT, 20)
    c.drawCentredString(W / 2, H - 5.6 * cm, _shape("حكاياتي الملونة"))
    size = 14 * cm
    c.drawImage(ImageReader(io.BytesIO(pages[0]["png"])), (W - size) / 2, H - 6.5 * cm - size,
                size, size)
    c.setFont(FONT, 18)
    c.drawCentredString(W / 2, 3 * cm, _shape("لوّن حكايتك وخلّيها حقيقية!"))
    c.showPage()

    # ---- story pages ----
    img_size = W - 2 * m
    for p in pages:
        top = H - m
        c.drawImage(ImageReader(io.BytesIO(p["png"])), m, top - img_size, img_size, img_size)
        c.setFont(FONT, 22)
        y = top - img_size - 1.5 * cm
        for line in _wrap(p["narration"], 22, W - 2 * m):
            c.drawRightString(W - m, y, _shape(line))
            y -= 1.1 * cm
        c.showPage()

    c.save()
```

### FILE: backend/test_pdf.py
```python
import io

from PIL import Image, ImageDraw

from services.pdf_service import build_pdf


def sample():
    img = Image.new("L", (800, 800), 255)
    d = ImageDraw.Draw(img)
    d.ellipse((200, 200, 600, 600), outline=0, width=8)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


pages = [{"png": sample(), "narration": "كان يا ما كان، في قديم الزمان، طفلة صغيرة اسمها ليلى تحب المغامرات."}
         for _ in range(4)]
build_pdf("مغامرة ليلى", pages, "test.pdf")
print("Saved test.pdf")
```

**اختبار:** افتحي `test.pdf` والعربي لازم يبان متصل وصح من اليمين لليسار.

---

## الخطوة 5 — المنسّق الرئيسي (Jobs)

```text
Step 5: Replace backend/main.py with the version below (complete). Do not change anything. Then give me the curl commands to test POST /create-book and GET /status/{job_id}.
```

الصوت بيتحفظ في الذاكرة بس ومش بيتكتب على الديسك خالص، فبيتمسح تلقائي بعد المعالجة (أحسن لخصوصية الأطفال).

### FILE: backend/main.py  (استبدلي)
```python
import asyncio
import logging
import shutil
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from services.image_service import generate_all
from services.pdf_service import build_pdf
from services.story_service import make_story
from utils import mime_for

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tales")

JOBS: dict = {}
RATE: dict = {}  # ip -> list of timestamps

UNSAFE_MSG = "الفكرة دي مش مناسبة للأطفال 🌈 جرّب حكاية تانية حلوة!"
ERROR_MSG = "حصلت مشكلة صغيرة 😢 جرّب تاني بعد شوية."


async def cleanup_loop():
    """Delete output folders and jobs older than CLEANUP_AFTER_HOURS."""
    while True:
        cutoff = time.time() - config.CLEANUP_AFTER_HOURS * 3600
        for d in config.OUTPUT_DIR.iterdir():
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    JOBS.pop(d.name, None)
            except Exception:
                pass
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="My Colorful Tales", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/files", StaticFiles(directory=config.OUTPUT_DIR), name="files")


def check_rate(ip: str):
    now = time.time()
    hits = [t for t in RATE.get(ip, []) if now - t < 3600]
    if len(hits) >= config.MAX_BOOKS_PER_HOUR:
        raise HTTPException(429, "Too many requests, try again later")
    hits.append(now)
    RATE[ip] = hits


def update(job_id, **kw):
    JOBS[job_id].update(kw)


async def run_job(job_id: str, audio: bytes, mime: str):
    try:
        update(job_id, progress=5, step_label_ar="بنسمع حكايتك... 👂")
        story = await make_story(audio, mime)
        del audio  # audio is never saved to disk

        if not story.safe:
            update(job_id, status="failed", unsafe=True, error=UNSAFE_MSG, progress=100)
            return

        update(job_id, progress=25, title=story.title, step_label_ar="بنرسم الصور... 🎨")

        def on_progress(done, total):
            update(job_id, progress=25 + int(60 * done / total),
                   step_label_ar=f"خلّصنا {done} من {total} صور 🖍️")

        prompts = [s.image_prompt_en for s in story.scenes]
        pngs = await generate_all(prompts, on_progress)

        job_dir = config.OUTPUT_DIR / job_id
        pages = []
        for i, (png, scene) in enumerate(zip(pngs, story.scenes), 1):
            (job_dir / f"page_{i}.png").write_bytes(png)
            pages.append({"png": png, "narration": scene.narration_ar})

        update(job_id, progress=90, step_label_ar="بنجهّز الكتاب للطباعة... 📖")
        pdf_path = job_dir / "book.pdf"
        await asyncio.to_thread(build_pdf, story.title, pages, str(pdf_path))

        update(
            job_id,
            status="done",
            progress=100,
            step_label_ar="الكتاب جاهز! 🎉",
            pages=[{"image_path": f"/files/{job_id}/page_{i}.png",
                    "narration_ar": s.narration_ar}
                   for i, s in enumerate(story.scenes, 1)],
            pdf_path=f"/files/{job_id}/book.pdf",
        )
    except Exception:
        log.exception("job %s failed", job_id)  # no audio / personal data in logs
        update(job_id, status="failed", error=ERROR_MSG, progress=100)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/create-book")
async def create_book(request: Request, background: BackgroundTasks,
                      audio: UploadFile = File(...)):
    check_rate(request.client.host if request.client else "unknown")
    mime = mime_for(audio.filename)
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio")
    if len(data) > config.MAX_AUDIO_MB * 1024 * 1024:
        raise HTTPException(413, "Audio too large")

    job_id = uuid.uuid4().hex[:12]
    (config.OUTPUT_DIR / job_id).mkdir(parents=True, exist_ok=True)
    JOBS[job_id] = {
        "status": "processing", "progress": 0, "step_label_ar": "بنبدأ... ✨",
        "title": "", "pages": [], "pdf_path": None, "error": None, "unsafe": False,
    }
    background.add_task(run_job, job_id, data, mime)
    return {"job_id": job_id}


@app.get("/status/{job_id}")
def status(job_id: str, request: Request):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    base = str(request.base_url).rstrip("/")
    return {
        "status": job["status"],
        "progress": job["progress"],
        "step_label_ar": job["step_label_ar"],
        "title": job["title"],
        "pages": [{"image_url": base + p["image_path"], "narration_ar": p["narration_ar"]}
                  for p in job["pages"]],
        "pdf_url": (base + job["pdf_path"]) if job["pdf_path"] else None,
        "error": job["error"],
        "unsafe": job["unsafe"],
    }
```

**اختبار:**
```text
curl -X POST -F "audio=@sample.m4a" http://localhost:8000/create-book
curl http://localhost:8000/status/<job_id>
```
كرري أمر status كل كام ثانية لحد `"status": "done"`، وبعدين افتحي `pdf_url` في المتصفح.

> ✅ الباك إند خلص. جرّبيه على 10 حكايات مختلفة قبل ما تكملي. **لو الصور مش نضيفة، متروحيش للتطبيق.**

---

# الجزء التاني: تطبيق Flutter (مجلد app)

أول حاجة، من الـ terminal (مش من Gemini): `flutter create app` ثم ادخلي المجلد `cd app`.

## الخطوة 6 — الهيكل والثيم والموديلات

```text
Step 6: In the existing Flutter project in /app, replace pubspec.yaml dependencies section as shown, and create/replace these files exactly as given. Then give me commands: flutter pub get, flutter run.
```

### FILE: app/pubspec.yaml  (حدّثي قسم dependencies بس)
```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_localizations:
    sdk: flutter
  intl: any
  google_fonts: ^6.2.1
  http: ^1.2.2
  record: ^5.1.2
  path_provider: ^2.1.4
  printing: ^5.13.2
  share_plus: ^10.0.0
  gal: ^2.3.0
```

### FILE: app/lib/theme.dart
```dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFFFF7043),
    brightness: Brightness.light,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: const Color(0xFFFFF8E1),
    textTheme: GoogleFonts.cairoTextTheme(),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      centerTitle: true,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        textStyle: GoogleFonts.cairo(fontSize: 18, fontWeight: FontWeight.bold),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      ),
    ),
  );
}
```

### FILE: app/lib/main.dart
```dart
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/home_screen.dart';
import 'theme.dart';

void main() => runApp(const TalesApp());

class TalesApp extends StatelessWidget {
  const TalesApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'حكاياتي الملونة',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: const HomeScreen(),
    );
  }
}
```

### FILE: app/lib/models/book.dart
```dart
class BookPage {
  final String imageUrl;
  final String narration;
  BookPage({required this.imageUrl, required this.narration});

  factory BookPage.fromJson(Map<String, dynamic> j) =>
      BookPage(imageUrl: j['image_url'], narration: j['narration_ar']);
}

class Book {
  final String title;
  final List<BookPage> pages;
  final String pdfUrl;
  Book({required this.title, required this.pages, required this.pdfUrl});
}

class JobStatus {
  final String status; // processing | done | failed
  final int progress;
  final String stepLabel;
  final String? error;
  final bool unsafe;
  final Book? book;

  JobStatus({
    required this.status,
    required this.progress,
    required this.stepLabel,
    this.error,
    this.unsafe = false,
    this.book,
  });

  factory JobStatus.fromJson(Map<String, dynamic> j) {
    Book? book;
    if (j['status'] == 'done') {
      book = Book(
        title: j['title'] ?? '',
        pages: (j['pages'] as List).map((e) => BookPage.fromJson(e)).toList(),
        pdfUrl: j['pdf_url'] ?? '',
      );
    }
    return JobStatus(
      status: j['status'],
      progress: (j['progress'] ?? 0) as int,
      stepLabel: j['step_label_ar'] ?? '',
      error: j['error'],
      unsafe: j['unsafe'] ?? false,
      book: book,
    );
  }
}
```

### FILE: app/lib/screens/home_screen.dart  (مؤقت)
```dart
import 'package:flutter/material.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: Text('الشاشة الرئيسية')));
}
```

### FILE: app/lib/screens/loading_screen.dart  (مؤقت)
```dart
import 'package:flutter/material.dart';

class LoadingScreen extends StatelessWidget {
  final String audioPath;
  const LoadingScreen({super.key, required this.audioPath});

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: Text('جاري التحميل')));
}
```

### FILE: app/lib/screens/book_screen.dart  (مؤقت)
```dart
import 'package:flutter/material.dart';
import '../models/book.dart';

class BookScreen extends StatelessWidget {
  final Book book;
  const BookScreen({super.key, required this.book});

  @override
  Widget build(BuildContext context) =>
      Scaffold(body: Center(child: Text(book.title)));
}
```

---

## الخطوة 7 — شاشة التسجيل

```text
Step 7: Replace app/lib/screens/home_screen.dart with the code below. Also apply the Android and iOS permission changes listed below. Do not connect to the server. Give me the commands to run and test recording.
```

**تعديلات الصلاحيات (لازم Gemini يطبقها):**

- **Android** — في `android/app/src/main/AndroidManifest.xml` قبل وسم `<application`:
```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.RECORD_AUDIO"/>
```
وجوه وسم `<application` ضيفي: `android:usesCleartextTraffic="true"` (للتجربة على http بس).
وفي `android/app/build.gradle` اتأكدي إن `minSdkVersion` على الأقل 23.

- **iOS** — في `ios/Runner/Info.plist` جوه `<dict>`:
```xml
<key>NSMicrophoneUsageDescription</key>
<string>نحتاج المايك علشان نسمع حكايتك</string>
<key>NSPhotoLibraryAddUsageDescription</key>
<string>لحفظ الصور الملونة في الألبوم</string>
```

### FILE: app/lib/screens/home_screen.dart
```dart
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import 'loading_screen.dart';

enum _S { idle, recording, recorded }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with SingleTickerProviderStateMixin {
  static const int maxSeconds = 60;
  final _rec = AudioRecorder();
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 800));
  _S _state = _S.idle;
  int _seconds = 0;
  Timer? _timer;
  String? _path;

  @override
  void dispose() {
    _timer?.cancel();
    _pulse.dispose();
    _rec.dispose();
    super.dispose();
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _start() async {
    if (!await _rec.hasPermission()) {
      _snack('محتاجين إذن المايك علشان نسمع حكايتك 🎤');
      return;
    }
    final dir = await getTemporaryDirectory();
    final path = '${dir.path}/story_${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _rec.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        sampleRate: 16000,
        numChannels: 1,
        bitRate: 64000,
      ),
      path: path,
    );
    setState(() {
      _state = _S.recording;
      _seconds = 0;
      _path = null;
    });
    _pulse.repeat(reverse: true);
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _seconds++);
      if (_seconds >= maxSeconds) _stop();
    });
  }

  Future<void> _stop() async {
    if (_state != _S.recording) return;
    _timer?.cancel();
    _pulse.stop();
    _pulse.value = 0;
    final p = await _rec.stop();
    if (!mounted) return;
    if (_seconds < 2 || p == null) {
      setState(() => _state = _S.idle);
      _snack('الحكاية قصيرة قوي، جرّب تاني 😊');
      return;
    }
    setState(() {
      _state = _S.recorded;
      _path = p;
    });
  }

  String get _time {
    final m = (_seconds ~/ 60).toString().padLeft(2, '0');
    final s = (_seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final recording = _state == _S.recording;
    final text = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text('حكاياتي الملونة 🎨',
                    style: text.headlineLarge?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(height: 12),
                Text(
                  recording
                      ? 'بنسمعك... احكي حكايتك!'
                      : _state == _S.recorded
                          ? 'حلو! تحب نبعتها؟'
                          : 'دوس على الزرار واحكيلي حكاية',
                  style: text.titleLarge,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 40),
                if (_state != _S.recorded)
                  GestureDetector(
                    onTap: recording ? _stop : _start,
                    child: ScaleTransition(
                      scale: Tween(begin: 1.0, end: 1.15).animate(_pulse),
                      child: Container(
                        width: 180,
                        height: 180,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: recording ? Colors.red : const Color(0xFFFF7043),
                          boxShadow: [
                            BoxShadow(
                              color: (recording ? Colors.red : Colors.deepOrange)
                                  .withOpacity(0.4),
                              blurRadius: 24,
                              spreadRadius: 4,
                            ),
                          ],
                        ),
                        child: Icon(recording ? Icons.stop_rounded : Icons.mic_rounded,
                            size: 90, color: Colors.white),
                      ),
                    ),
                  ),
                const SizedBox(height: 24),
                Text(_time, style: text.headlineMedium),
                Text('الحد الأقصى دقيقة', style: text.bodySmall),
                const SizedBox(height: 32),
                if (_state == _S.recorded)
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      OutlinedButton.icon(
                        onPressed: () => setState(() {
                          _state = _S.idle;
                          _seconds = 0;
                        }),
                        icon: const Icon(Icons.refresh),
                        label: const Text('من جديد'),
                      ),
                      const SizedBox(width: 16),
                      FilledButton.icon(
                        onPressed: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                              builder: (_) => LoadingScreen(audioPath: _path!)),
                        ),
                        icon: const Icon(Icons.send_rounded),
                        label: const Text('ابعت'),
                      ),
                    ],
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
```

---

## الخطوة 8 — الربط بالسيرفر وشاشة الانتظار

```text
Step 8: Create app/lib/services/api_service.dart and replace app/lib/screens/loading_screen.dart with the code below. Give me the flutter run command with the API_URL define, for both the Android emulator and a real phone.
```

### FILE: app/lib/services/api_service.dart
```dart
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/book.dart';

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
}

class ApiService {
  // Android emulator = 10.0.2.2 ; real phone = your PC's IP, e.g. http://192.168.1.5:8000
  static const String baseUrl =
      String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

  static Future<String> uploadAudio(String path) async {
    try {
      final req = http.MultipartRequest('POST', Uri.parse('$baseUrl/create-book'));
      req.files.add(await http.MultipartFile.fromPath('audio', path));
      final streamed = await req.send().timeout(const Duration(seconds: 60));
      final res = await http.Response.fromStream(streamed);
      if (res.statusCode == 429) {
        throw ApiException('كتبنا كتب كتير النهاردة! جرّب بعد شوية 😊');
      }
      if (res.statusCode != 200) {
        throw ApiException('حصلت مشكلة في الإرسال، جرّب تاني');
      }
      return jsonDecode(res.body)['job_id'] as String;
    } on SocketException {
      throw ApiException('مفيش إنترنت 📶 اتأكد من الاتصال وجرّب تاني');
    } on TimeoutException {
      throw ApiException('الاتصال بطيء، جرّب تاني');
    }
  }

  static Future<JobStatus> getStatus(String jobId) async {
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/status/$jobId'))
          .timeout(const Duration(seconds: 20));
      if (res.statusCode == 404) {
        throw ApiException('حصلت مشكلة، جرّب تسجيل الحكاية تاني');
      }
      if (res.statusCode != 200) throw ApiException('حصلت مشكلة، جرّب تاني');
      return JobStatus.fromJson(jsonDecode(utf8.decode(res.bodyBytes)));
    } on SocketException {
      throw ApiException('مفيش إنترنت 📶 اتأكد من الاتصال وجرّب تاني');
    } on TimeoutException {
      throw ApiException('الاتصال بطيء، جرّب تاني');
    }
  }
}
```

### FILE: app/lib/screens/loading_screen.dart
```dart
import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import 'book_screen.dart';

class LoadingScreen extends StatefulWidget {
  final String audioPath;
  const LoadingScreen({super.key, required this.audioPath});

  @override
  State<LoadingScreen> createState() => _LoadingScreenState();
}

class _LoadingScreenState extends State<LoadingScreen> with SingleTickerProviderStateMixin {
  static const int timeoutSeconds = 120;
  late final AnimationController _bounce =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 700))
        ..repeat(reverse: true);
  int _progress = 0;
  String _label = 'بنجهّز كل حاجة...';
  String? _error;
  bool _unsafe = false;
  bool _cancelled = false;

  @override
  void initState() {
    super.initState();
    _run();
  }

  @override
  void dispose() {
    _cancelled = true;
    _bounce.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    setState(() {
      _error = null;
      _unsafe = false;
      _progress = 0;
      _label = 'بنجهّز كل حاجة...';
    });
    try {
      final id = await ApiService.uploadAudio(widget.audioPath);
      final deadline = DateTime.now().add(const Duration(seconds: timeoutSeconds));
      while (!_cancelled) {
        if (DateTime.now().isAfter(deadline)) {
          throw ApiException('الحكاية أخدت وقت أطول من المتوقع، جرّب تاني');
        }
        await Future.delayed(const Duration(seconds: 2));
        if (_cancelled || !mounted) return;
        final s = await ApiService.getStatus(id);
        if (!mounted) return;
        if (s.status == 'done') {
          Navigator.pushReplacement(
              context, MaterialPageRoute(builder: (_) => BookScreen(book: s.book!)));
          return;
        }
        if (s.status == 'failed') {
          setState(() {
            _error = s.error ?? 'حصلت مشكلة، جرّب تاني';
            _unsafe = s.unsafe;
          });
          return;
        }
        setState(() {
          _progress = s.progress;
          _label = s.stepLabel;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Center(
            child: _error != null ? _errorView(text) : _progressView(text),
          ),
        ),
      ),
    );
  }

  Widget _progressView(TextTheme text) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ScaleTransition(
            scale: Tween(begin: 0.85, end: 1.2).animate(
                CurvedAnimation(parent: _bounce, curve: Curves.easeInOut)),
            child: const Text('🎨', style: TextStyle(fontSize: 96)),
          ),
          const SizedBox(height: 32),
          Text(_label, style: text.titleLarge, textAlign: TextAlign.center),
          const SizedBox(height: 24),
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: LinearProgressIndicator(
                value: _progress / 100, minHeight: 16),
          ),
          const SizedBox(height: 8),
          Text('$_progress%'),
        ],
      );

  Widget _errorView(TextTheme text) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(_unsafe ? '🌈' : '😢', style: const TextStyle(fontSize: 80)),
          const SizedBox(height: 16),
          Text(_error!, style: text.titleLarge, textAlign: TextAlign.center),
          const SizedBox(height: 24),
          if (_unsafe)
            FilledButton(
                onPressed: () => Navigator.pop(context), child: const Text('حكاية جديدة'))
          else
            FilledButton.icon(
                onPressed: _run,
                icon: const Icon(Icons.refresh),
                label: const Text('حاول تاني')),
        ],
      );
}
```

**تشغيل:**
```text
flutter run --dart-define=API_URL=http://10.0.2.2:8000          (محاكي أندرويد)
flutter run --dart-define=API_URL=http://192.168.1.X:8000       (موبايل حقيقي، نفس شبكة الواي فاي)
```

---

## الخطوة 9 — خدمة التحميل والطباعة والمشاركة

```text
Step 9: Create app/lib/services/pdf_actions.dart exactly as given. Do not touch other files. Tell me if any platform permission is needed.
```

### FILE: app/lib/services/pdf_actions.dart
```dart
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:printing/printing.dart';
import 'package:share_plus/share_plus.dart';

class PdfActions {
  static Future<Uint8List> _bytes(String url) async {
    final res = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 60));
    if (res.statusCode != 200) throw Exception('download failed');
    return res.bodyBytes;
  }

  /// Opens the system "save / share" sheet so the user can save it to Files / Drive.
  static Future<void> save(String url) async {
    final bytes = await _bytes(url);
    await Printing.sharePdf(bytes: bytes, filename: 'hekayati.pdf');
  }

  static Future<void> print(String url) async {
    final bytes = await _bytes(url);
    await Printing.layoutPdf(onLayout: (_) async => bytes);
  }

  static Future<void> share(String url) async {
    final bytes = await _bytes(url);
    final dir = await getTemporaryDirectory();
    final f = File('${dir.path}/hekayati.pdf');
    await f.writeAsBytes(bytes);
    await Share.shareXFiles([XFile(f.path)], text: 'شوف حكايتي الملونة! 🎨');
  }
}
```

---

## الخطوة 10 — شاشة الكتاب

```text
Step 10: Replace app/lib/screens/book_screen.dart with the code below exactly. Keep the comment marker COLOR_BUTTON_HERE as is. Give me the command to run and test page flipping and the three buttons.
```

### FILE: app/lib/screens/book_screen.dart
```dart
import 'package:flutter/material.dart';

import '../models/book.dart';
import '../services/pdf_actions.dart';

class BookScreen extends StatefulWidget {
  final Book book;
  const BookScreen({super.key, required this.book});

  @override
  State<BookScreen> createState() => _BookScreenState();
}

class _BookScreenState extends State<BookScreen> {
  final _c = PageController();
  bool _busy = false;

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _run(Future<void> Function() job, String ok) async {
    setState(() => _busy = true);
    try {
      await job();
      if (mounted) _snack(ok);
    } catch (_) {
      if (mounted) _snack('حصلت مشكلة، جرّب تاني 😢');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _cover(TextTheme text) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('📖', style: TextStyle(fontSize: 90)),
              const SizedBox(height: 16),
              Text(widget.book.title,
                  style: text.displaySmall?.copyWith(fontWeight: FontWeight.bold),
                  textAlign: TextAlign.center),
              const SizedBox(height: 16),
              Text('اسحب لقلب الصفحة', style: text.titleMedium),
            ],
          ),
        ),
      );

  Widget _page(BookPage p, TextTheme text) => Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: const [BoxShadow(blurRadius: 8, color: Colors.black12)],
                ),
                clipBehavior: Clip.antiAlias,
                child: Image.network(
                  p.imageUrl,
                  fit: BoxFit.contain,
                  loadingBuilder: (c, w, prog) => prog == null
                      ? w
                      : const Center(child: CircularProgressIndicator()),
                  errorBuilder: (c, e, s) =>
                      const Center(child: Icon(Icons.broken_image, size: 48)),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(p.narration,
                style: text.headlineSmall?.copyWith(height: 1.6),
                textAlign: TextAlign.center),
            // COLOR_BUTTON_HERE
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final pages = widget.book.pages;
    return Scaffold(
      appBar: AppBar(title: Text(widget.book.title)),
      body: Column(
        children: [
          Expanded(
            child: PageView.builder(
              controller: _c,
              itemCount: pages.length + 1,
              itemBuilder: (context, i) {
                return AnimatedBuilder(
                  animation: _c,
                  builder: (context, child) {
                    double v = -i.toDouble();
                    if (_c.hasClients && _c.position.haveDimensions) {
                      v = (_c.page ?? 0) - i;
                    }
                    v = v.clamp(-1.0, 1.0);
                    return Transform(
                      alignment: Alignment.center,
                      transform: Matrix4.identity()
                        ..setEntry(3, 2, 0.0012)
                        ..rotateY(v * 0.8),
                      child: Opacity(
                          opacity: (1 - v.abs() * 0.6).clamp(0.0, 1.0), child: child),
                    );
                  },
                  child: i == 0 ? _cover(text) : _page(pages[i - 1], text),
                );
              },
            ),
          ),
          if (_busy) const LinearProgressIndicator(),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
              child: Row(
                children: [
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: _busy
                          ? null
                          : () => _run(() => PdfActions.save(widget.book.pdfUrl),
                              'تم ✅'),
                      icon: const Icon(Icons.download),
                      label: const Text('تحميل'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: _busy
                          ? null
                          : () => _run(() => PdfActions.print(widget.book.pdfUrl),
                              'تمت الطباعة 🖨️'),
                      icon: const Icon(Icons.print),
                      label: const Text('طباعة'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: _busy
                          ? null
                          : () => _run(() => PdfActions.share(widget.book.pdfUrl),
                              'تمت المشاركة ✅'),
                      icon: const Icon(Icons.share),
                      label: const Text('مشاركة'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
```

---

## الخطوة 11 — التلوين الرقمي (اختياري)

```text
Step 11: Create app/lib/screens/color_screen.dart exactly as given. Then edit app/lib/screens/book_screen.dart in ONLY two places: (1) add the import line `import 'color_screen.dart';` at the top, (2) replace the comment line `// COLOR_BUTTON_HERE` with the button code given below. Change nothing else. Add the gal package permissions note for iOS (already in Info.plist). Give me the run command.
```

**استبدلي السطر `// COLOR_BUTTON_HERE` بده:**
```dart
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => ColorScreen(imageUrl: p.imageUrl)),
              ),
              icon: const Icon(Icons.brush),
              label: const Text('لوّن الصفحة'),
            ),
```

### FILE: app/lib/screens/color_screen.dart
```dart
import 'dart:async';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:gal/gal.dart';
import 'package:http/http.dart' as http;

const int N = 768; // working resolution

class _Stroke {
  final Path path = Path();
  final Color color;
  final double width;
  _Stroke(this.color, this.width);
}

class _Action {
  final _Stroke? stroke;
  final Uint8List? prevFill;
  _Action.stroke(this.stroke) : prevFill = null;
  _Action.fill(this.prevFill) : stroke = null;
}

class _Painter extends CustomPainter {
  final ui.Image fill;
  final ui.Image lines;
  final List<_Stroke> strokes;
  _Painter(this.fill, this.lines, this.strokes);

  @override
  void paint(Canvas canvas, Size size) {
    final dst = Offset.zero & size;
    final src = Rect.fromLTWH(0, 0, N.toDouble(), N.toDouble());
    canvas.drawImageRect(fill, src, dst, Paint());
    canvas.save();
    canvas.scale(size.width / N);
    for (final s in strokes) {
      canvas.drawPath(
        s.path,
        Paint()
          ..color = s.color
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round
          ..strokeWidth = s.width,
      );
    }
    canvas.restore();
    // black lines multiplied on top, so they always stay black
    canvas.drawImageRect(lines, src, dst, Paint()..blendMode = BlendMode.multiply);
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => true;
}

class ColorScreen extends StatefulWidget {
  final String imageUrl;
  const ColorScreen({super.key, required this.imageUrl});

  @override
  State<ColorScreen> createState() => _ColorScreenState();
}

class _ColorScreenState extends State<ColorScreen> {
  static const palette = <Color>[
    Color(0xFFE53935), Color(0xFFFF7043), Color(0xFFFFC107), Color(0xFFFFEE58),
    Color(0xFF7CB342), Color(0xFF2E7D32), Color(0xFF26C6DA), Color(0xFF1E88E5),
    Color(0xFF3949AB), Color(0xFF8E24AA), Color(0xFFEC407A), Color(0xFF8D6E63),
    Color(0xFF212121), Color(0xFFFFFFFF),
  ];

  ui.Image? _lines;
  ui.Image? _fillImg;
  Uint8List? _fill;
  late Uint8List _walls;
  final _strokes = <_Stroke>[];
  final _undo = <_Action>[];
  _Stroke? _cur;
  Color _color = palette[0];
  double _brush = 14;
  bool _bucket = true;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final res = await http.get(Uri.parse(widget.imageUrl));
      final codec = await ui.instantiateImageCodec(res.bodyBytes,
          targetWidth: N, targetHeight: N);
      final img = (await codec.getNextFrame()).image;
      final data = (await img.toByteData(format: ui.ImageByteFormat.rawRgba))!
          .buffer
          .asUint8List();
      _walls = Uint8List(N * N);
      for (var i = 0; i < N * N; i++) {
        _walls[i] = data[i * 4] < 128 ? 1 : 0; // dark pixel = black line
      }
      _fill = Uint8List(N * N * 4)..fillRange(0, N * N * 4, 255);
      _lines = img;
      await _refreshFill();
      if (mounted) setState(() => _loading = false);
    } catch (e) {
      if (mounted) setState(() => _error = 'مقدرناش نحمّل الصفحة 😢');
    }
  }

  Future<void> _refreshFill() async {
    final c = Completer<ui.Image>();
    ui.decodeImageFromPixels(_fill!, N, N, ui.PixelFormat.rgba8888, c.complete);
    _fillImg = await c.future;
  }

  void _pushUndo(_Action a) {
    _undo.add(a);
    if (_undo.length > 12) _undo.removeAt(0);
  }

  // ---- bucket fill: stays inside the black lines ----
  void _flood(int sx, int sy) {
    final v = _color.value;
    final r = (v >> 16) & 255, g = (v >> 8) & 255, b = v & 255;
    final seen = Uint8List(N * N);
    final stack = <int>[sy * N + sx];
    while (stack.isNotEmpty) {
      final i = stack.removeLast();
      if (seen[i] == 1 || _walls[i] == 1) continue;
      seen[i] = 1;
      final o = i * 4;
      _fill![o] = r;
      _fill![o + 1] = g;
      _fill![o + 2] = b;
      final x = i % N, y = i ~/ N;
      if (x > 0) stack.add(i - 1);
      if (x < N - 1) stack.add(i + 1);
      if (y > 0) stack.add(i - N);
      if (y < N - 1) stack.add(i + N);
    }
  }

  Future<void> _fillAt(Offset p, double size) async {
    final x = (p.dx * N / size).floor().clamp(0, N - 1);
    final y = (p.dy * N / size).floor().clamp(0, N - 1);
    if (_walls[y * N + x] == 1) return;
    _pushUndo(_Action.fill(Uint8List.fromList(_fill!)));
    _flood(x, y);
    await _refreshFill();
    if (mounted) setState(() {});
  }

  // ---- brush ----
  void _brushDown(Offset p, double size) {
    if (_bucket) return;
    final s = _Stroke(_color, _brush);
    final q = p * (N / size);
    s.path.moveTo(q.dx, q.dy);
    s.path.lineTo(q.dx, q.dy); // dot on tap
    _cur = s;
    _strokes.add(s);
    _pushUndo(_Action.stroke(s));
    setState(() {});
  }

  void _brushMove(Offset p, double size) {
    if (_bucket || _cur == null) return;
    final q = p * (N / size);
    _cur!.path.lineTo(q.dx, q.dy);
    setState(() {});
  }

  Future<void> _undoLast() async {
    if (_undo.isEmpty) return;
    final a = _undo.removeLast();
    if (a.stroke != null) {
      _strokes.remove(a.stroke);
    } else {
      _fill = a.prevFill;
      await _refreshFill();
    }
    if (mounted) setState(() {});
  }

  Future<void> _save() async {
    try {
      final rec = ui.PictureRecorder();
      final canvas = Canvas(rec);
      canvas.drawRect(Rect.fromLTWH(0, 0, N.toDouble(), N.toDouble()),
          Paint()..color = Colors.white);
      _Painter(_fillImg!, _lines!, _strokes).paint(canvas, Size(N.toDouble(), N.toDouble()));
      final img = await rec.endRecording().toImage(N, N);
      final bytes = (await img.toByteData(format: ui.ImageByteFormat.png))!
          .buffer
          .asUint8List();
      if (!await Gal.hasAccess()) await Gal.requestAccess();
      await Gal.putImageBytes(bytes);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('اتحفظت في الصور 🖼️')));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('مقدرناش نحفظ الصورة 😢')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('لوّن'),
        actions: [
          IconButton(onPressed: _undoLast, icon: const Icon(Icons.undo)),
          IconButton(onPressed: _loading ? null : _save, icon: const Icon(Icons.save_alt)),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _loading
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  children: [
                    Expanded(
                      child: Center(
                        child: LayoutBuilder(builder: (context, box) {
                          final size = box.biggest.shortestSide;
                          return SizedBox(
                            width: size,
                            height: size,
                            child: GestureDetector(
                              onTapUp: (d) {
                                if (_bucket) _fillAt(d.localPosition, size);
                              },
                              onPanDown: (d) => _brushDown(d.localPosition, size),
                              onPanUpdate: (d) => _brushMove(d.localPosition, size),
                              onPanEnd: (_) => _cur = null,
                              onPanCancel: () => _cur = null,
                              child: CustomPaint(
                                painter: _Painter(_fillImg!, _lines!, _strokes),
                              ),
                            ),
                          );
                        }),
                      ),
                    ),
                    SafeArea(
                      child: Column(
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              SegmentedButton<bool>(
                                segments: const [
                                  ButtonSegment(
                                      value: true,
                                      icon: Icon(Icons.format_color_fill),
                                      label: Text('جردل')),
                                  ButtonSegment(
                                      value: false,
                                      icon: Icon(Icons.brush),
                                      label: Text('فرشاة')),
                                ],
                                selected: {_bucket},
                                onSelectionChanged: (s) =>
                                    setState(() => _bucket = s.first),
                              ),
                            ],
                          ),
                          if (!_bucket)
                            Slider(
                              min: 4,
                              max: 40,
                              value: _brush,
                              onChanged: (v) => setState(() => _brush = v),
                            ),
                          SizedBox(
                            height: 56,
                            child: ListView(
                              scrollDirection: Axis.horizontal,
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              children: [
                                for (final c in palette)
                                  GestureDetector(
                                    onTap: () => setState(() => _color = c),
                                    child: Container(
                                      width: 44,
                                      height: 44,
                                      margin: const EdgeInsets.all(6),
                                      decoration: BoxDecoration(
                                        color: c,
                                        shape: BoxShape.circle,
                                        border: Border.all(
                                          color: _color == c ? Colors.black : Colors.black26,
                                          width: _color == c ? 4 : 1,
                                        ),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }
}
```

---

## الخطوة 12 — التجهيز للنشر

الحدود (rate limit، حد حجم الصوت، حذف الملفات بعد 24 ساعة، لوجات بدون بيانات الأطفال) **اتعملت فعلاً في الخطوة 5**. فاللي فاضل Docker والنشر.

```text
Step 12: Create backend/Dockerfile and backend/.dockerignore exactly as given. Then give me the exact gcloud commands to deploy to Cloud Run, as listed below, and a final testing checklist. Do not change any other file.
```

### FILE: backend/Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
```

### FILE: backend/.dockerignore
```text
venv
.env
output
__pycache__
test_*.png
test.pdf
```

**أمر النشر (Cloud Run):**
```text
gcloud run deploy tales-api --source . --region europe-west1 --allow-unauthenticated --memory 1Gi --timeout 300 --max-instances 1 --no-cpu-throttling --set-env-vars GEMINI_API_KEY=xxx,TEXT_MODEL=xxx,IMAGE_BACKEND=imagen,IMAGE_MODEL=xxx
```
- `--no-cpu-throttling` ضروري، لأن الشغل بيكمل في الخلفية بعد ما بنرد على التطبيق.
- `--max-instances 1` ضروري، لأن الـ jobs متخزنة في الذاكرة. لو عايزة أكتر من سيرفر لازم تنقليها لـ Redis أو قاعدة بيانات.
- الأحسن تحطي المفتاح في Secret Manager بدل `--set-env-vars`.
- بعد النشر غيري الـ `API_URL` في التطبيق لعنوان Cloud Run (https).

**قائمة الاختبار النهائية:**
- [ ] 10 حكايات مختلفة، كل الصور بخطوط سودا بس بدون تظليل ولا رمادي.
- [ ] الشخصية شبه بعضها في الصفحات الأربعة.
- [ ] حكاية فيها عنف أو شيء مخيف، لازم تتحول لحكاية لطيفة أو ترجع رسالة "مش مناسبة".
- [ ] PDF بالعربي متصل وصح، ويتطبع على A4 كويس.
- [ ] الجردل بيلوّن جوه الخطوط بس من غير ما يسرّب لباقي الصفحة.
- [ ] قطع الإنترنت في النص، لازم تظهر رسالة وزرار "حاول تاني".
- [ ] التسجيل أقل من ثانيتين يرجع رسالة "قصيرة قوي".
- [ ] مفيش ملفات صوت على السيرفر.
- [ ] مرور 24 ساعة وحذف الملفات القديمة.
- [ ] 6 طلبات من نفس الجهاز في ساعة، السادس لازم يترفض.
- [ ] حساب تكلفة الكتاب الواحد (طلب نص + 4 صور) قبل النشر.
- [ ] سياسة خصوصية واضحة لو هتنشري على المتجر (بيانات أطفال).
