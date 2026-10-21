import asyncio
import logging
import shutil
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from services.image_service import _mock_image
from services.pdf_service import build_pdf
from services.prompts import (
    AGE_GROUPS,
    ART_STYLES,
    DEFAULT_ART_STYLE,
    DEFAULT_IMAGINATION,
    GENDERS,
    IMAGINATION,
    clean_name,
)
from services.story_service import make_story
from utils import mime_for

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tales")

JOBS: dict = {}
RATE: dict = {}  # ip -> list of timestamps

UNSAFE_MSG = "الفكرة دي مش مناسبة للأطفال 🌈 جرّب حكاية تانية حلوة!"
NO_STORY_MSG = "مسمعناش حكاية واضحة 🎤 جرّب تسجّل تاني بصوت أعلى شوية!"
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


async def run_job(job_id: str, audio: bytes, mime: str, name: str, gender: str,
                  age_group: str, imagination: str, art_style: str):
    try:
        update(job_id, progress=15, step_label_ar="بنسمع حكايتك ونؤلف المشاهد... 👂")
        story = await make_story(audio, mime, name, gender, age_group, imagination, art_style)
        del audio  # audio is never saved to disk

        if not story.safe:
            msg = NO_STORY_MSG if story.reason == "no_story" else UNSAFE_MSG
            update(job_id, status="failed", unsafe=(story.reason != "no_story"),
                   error=msg, progress=100)
            return

        update(job_id, progress=50, title=story.title, step_label_ar="بنجهّز صفحات القصة والبرومبتات... ✨")

        job_dir = config.OUTPUT_DIR / job_id
        pages = []
        pages_resp = []

        # Generate instant clean page previews using the local generator so the book is ready immediately
        for i, scene in enumerate(story.scenes, 1):
            preview_png = _mock_image(f"{scene.narration_ar} - {scene.image_prompt_en}")
            page_png_path = job_dir / f"page_{i}.png"
            page_png_path.write_bytes(preview_png)

            pages.append({"png": preview_png, "narration": scene.narration_ar})
            pages_resp.append({
                "page_number": i,
                "image_path": f"/files/{job_id}/page_{i}.png",
                "narration_ar": scene.narration_ar,
                "image_prompt_en": scene.image_prompt_en,
                "art_style": scene.art_style,
            })

        update(job_id, progress=90, step_label_ar="بنجهّز صفحات الكتاب... 📖")
        pdf_path = job_dir / "book.pdf"
        await asyncio.to_thread(build_pdf, story.title, pages, str(pdf_path),
                                name, gender, age_group)

        update(
            job_id,
            status="done",
            progress=100,
            step_label_ar="الكتاب والبرومبتات جاهزة! 🎉",
            title=story.title,
            transcript_ar=story.transcript_ar,
            art_style=story.art_style,
            character_description=story.character_description,
            pages=pages_resp,
            pdf_path=f"/files/{job_id}/book.pdf",
        )
    except Exception:
        log.exception("job %s failed", job_id)  # no audio / child name in logs
        update(job_id, status="failed", error=ERROR_MSG, progress=100)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/create-book")
async def create_book(
    request: Request,
    background: BackgroundTasks,
    audio: UploadFile = File(...),
    child_name: str = Form(...),
    gender: str = Form(...),                        # boy | girl
    age_group: str = Form(...),                     # 3-5 | 6-10 | 11-16
    art_style: str = Form(DEFAULT_ART_STYLE),       # classic | manga | mandala | sketch | random
    imagination: str = Form(DEFAULT_IMAGINATION),   # exact | ai
):
    check_rate(request.client.host if request.client else "unknown")

    name = clean_name(child_name)
    if not name:
        raise HTTPException(400, "Child name is required")
    if gender not in GENDERS:
        raise HTTPException(400, "gender must be boy or girl")
    if age_group not in AGE_GROUPS:
        age_group = "6-10"
    if art_style not in ART_STYLES:
        art_style = DEFAULT_ART_STYLE
    if imagination not in IMAGINATION:
        imagination = DEFAULT_IMAGINATION

    mime = mime_for(audio.filename)
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio")
    if len(data) > config.MAX_AUDIO_MB * 1024 * 1024:
        raise HTTPException(413, "Audio too large")

    job_id = uuid.uuid4().hex[:12]
    (config.OUTPUT_DIR / job_id).mkdir(parents=True, exist_ok=True)
    JOBS[job_id] = {
        "status": "processing", "progress": 0, "step_label_ar": "بنسمع حكايتك... ✨",
        "title": "", "pages": [], "pdf_path": None, "error": None, "unsafe": False,
    }
    background.add_task(run_job, job_id, data, mime, name, gender, age_group, imagination, art_style)
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
        "title": job.get("title", ""),
        "transcript_ar": job.get("transcript_ar", ""),
        "art_style": job.get("art_style", ""),
        "character_description": job.get("character_description", ""),
        "pages": [
            {
                "page_number": p.get("page_number", idx),
                "image_url": base + p["image_path"],
                "narration_ar": p["narration_ar"],
                "image_prompt_en": p.get("image_prompt_en", ""),
                "art_style": p.get("art_style", ""),
            }
            for idx, p in enumerate(job.get("pages", []), 1)
        ],
        "pdf_url": (base + job["pdf_path"]) if job.get("pdf_path") else None,
        "error": job.get("error"),
        "unsafe": job.get("unsafe", False),
    }
