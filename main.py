import asyncio
import logging
import shutil
import time
import uuid
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

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
from services.orders_service import (
    create_order,
    get_order,
    list_orders,
    update_order_status,
    get_order_audio_path,
)
from services.single_art_service import generate_single_art
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


async def run_job(
    job_id: str,
    audio: Optional[bytes],
    mime: str,
    name: str,
    gender: str,
    age_group: str,
    imagination: str,
    art_style: str,
    text_prompt: str = "",
    order_id: Optional[str] = None,
):
    try:
        update(job_id, progress=15, step_label_ar="بنسمع حكايتك ونؤلف المشاهد... 👂")
        story = await make_story(
            audio_bytes=audio,
            mime_type=mime,
            name=name,
            gender=gender,
            age_group=age_group,
            imagination=imagination,
            art_style=art_style,
            text_prompt=text_prompt,
        )
        if audio:
            del audio  # audio is never saved to disk

        if not story.safe:
            msg = NO_STORY_MSG if story.reason == "no_story" else UNSAFE_MSG
            update(job_id, status="failed", unsafe=(story.reason != "no_story"),
                   error=msg, progress=100)
            if order_id:
                update_order_status(order_id, "failed")
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
        if order_id:
            update_order_status(order_id, "completed", result_job_id=job_id)
    except Exception:
        log.exception("job %s failed", job_id)  # no audio / child name in logs
        update(job_id, status="failed", error=ERROR_MSG, progress=100)
        if order_id:
            update_order_status(order_id, "failed")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/download-apk")
@app.get("/apk")
def download_apk():
    apk_path = Path(r"C:\Users\Asmaa\Desktop\hekayati-premium.apk")
    if not apk_path.exists():
        raise HTTPException(404, "APK not found on Desktop")
    return FileResponse(
        path=str(apk_path),
        filename="hekayati-premium.apk",
        media_type="application/vnd.android.package-archive",
    )


@app.get("/install", response_class=HTMLResponse)
def install_page():
    return """<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>تحميل تطبيق حكاياتي الملونة</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; padding: 40px 20px; background: #fdf8ff; color: #333; margin: 0; }
    .card { background: white; padding: 36px 24px; border-radius: 24px; box-shadow: 0 10px 30px rgba(126,34,206,0.12); max-width: 380px; margin: 40px auto; border: 1px solid #f3e8ff; }
    h1 { color: #6b21a8; margin: 12px 0; font-size: 24px; }
    p { color: #6b7280; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0; }
    .btn { display: block; background: linear-gradient(135deg, #9333ea, #7e22ce); color: white; padding: 16px 24px; border-radius: 14px; text-decoration: none; font-size: 17px; font-weight: bold; box-shadow: 0 6px 16px rgba(126,34,206,0.35); }
    .badge { display: inline-block; background: #faf5ff; color: #7e22ce; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: bold; margin-bottom: 16px; border: 1px solid #e9d5ff; }
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size: 64px;">🎨📖</div>
    <h1>تطبيق حكاياتي الملونة</h1>
    <div class="badge">النسخة المحدثة جاهزة للتحميل ✨</div>
    <p>تتضمن ميزة رفع الصور وتجميعها في كتيب PDF وتثبيت الشخصيات والأماكن بدقة عالية.</p>
    <a href="/download-apk" class="btn">تحميل التطبيق الآن (APK) ⬇️</a>
  </div>
</body>
</html>"""


@app.post("/create-single-art")
async def create_single_art(
    request: Request,
    age_group: str = Form("11-16"),
    gender: str = Form("boy"),
    art_style: str = Form("manga"),
    description_text: str = Form(""),
    include_text: bool = Form(False),
    audio: UploadFile = File(None),
):
    check_rate(request.client.host if request.client else "unknown")
    audio_bytes = None
    mime = ""
    if audio and audio.filename:
        audio_bytes = await audio.read()
        mime = mime_for(audio.filename)

    if not audio_bytes and not description_text.strip():
        raise HTTPException(400, "Please provide audio recording or text description")

    try:
        res = await generate_single_art(
            age_group=age_group,
            gender=gender,
            art_style=art_style,
            audio_bytes=audio_bytes,
            mime_type=mime,
            text_description=description_text,
            include_text=include_text,
        )
        return {
            "title": res.title,
            "concept_ar": res.concept_ar,
            "concept_en": res.concept_en,
            "art_style": res.art_style,
            "prompt_en": res.prompt_en,
        }
    except Exception as e:
        log.exception("create_single_art failed: %s", e)
        raise HTTPException(500, "Failed to generate single art prompt")


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


# =====================================================================
# Customer Booking & Orders Portal (الحجز المسبق من موقع المكان)
# =====================================================================

BOOKING_HTML_PATH = Path(__file__).resolve().parent / "templates" / "booking.html"


@app.get("/booking", response_class=HTMLResponse)
@app.get("/order", response_class=HTMLResponse)
def booking_page():
    if not BOOKING_HTML_PATH.exists():
        raise HTTPException(404, "Booking template not found")
    return HTMLResponse(content=BOOKING_HTML_PATH.read_text(encoding="utf-8"))


@app.post("/api/orders")
async def api_create_order(
    request: Request,
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    child_name: str = Form(...),
    child_gender: str = Form("boy"),
    child_age: str = Form("6-10"),
    order_type: str = Form("storybook"),
    art_style: str = Form("storybook"),
    story_idea: str = Form(""),
    notes: str = Form(""),
    audio: UploadFile = File(None),
):
    check_rate(request.client.host if request.client else "unknown")

    audio_bytes = None
    audio_ext = ".m4a"
    if audio and audio.filename:
        audio_bytes = await audio.read()
        audio_ext = Path(audio.filename).suffix or ".m4a"

    order = create_order(
        customer_name=customer_name,
        customer_phone=customer_phone,
        child_name=child_name,
        child_gender=child_gender,
        child_age=child_age,
        order_type=order_type,
        art_style=art_style,
        story_idea=story_idea,
        audio_bytes=audio_bytes,
        audio_ext=audio_ext,
        notes=notes,
    )
    return {
        "ok": True,
        "order_id": order["id"],
        "message": "تم استلام حجزك بنجاح وسيتواصل معك فريق العمل!",
        "order": order,
    }


@app.get("/api/orders")
def api_list_orders(status: str = "all"):
    orders = list_orders(status=status)
    return {"orders": orders, "count": len(orders)}


@app.get("/api/orders/{order_id}")
def api_get_order(order_id: str):
    order = get_order(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@app.patch("/api/orders/{order_id}/status")
async def api_update_order_status(order_id: str, request: Request):
    data = await request.json()
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(400, "status is required")
    success = update_order_status(order_id, new_status)
    if not success:
        raise HTTPException(404, "Order not found")
    return {"ok": True, "order_id": order_id, "status": new_status}


@app.get("/api/orders/{order_id}/audio")
def api_get_order_audio(order_id: str):
    audio_path = get_order_audio_path(order_id)
    if not audio_path:
        raise HTTPException(404, "Audio not found for this order")
    return FileResponse(
        path=str(audio_path),
        filename=audio_path.name,
        media_type="audio/mpeg",
    )


@app.post("/api/orders/{order_id}/process")
async def api_process_order(order_id: str, background: BackgroundTasks):
    order = get_order(order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    order_type = order.get("order_type", "storybook")
    name = order.get("child_name", "البطل")
    gender = order.get("child_gender", "boy")
    age_group = order.get("child_age", "6-10")
    art_style = order.get("art_style", "storybook")
    story_idea = order.get("story_idea", "")

    # Check for recorded audio
    audio_path = get_order_audio_path(order_id)
    audio_bytes = None
    mime = "audio/wav"
    if audio_path:
        audio_bytes = audio_path.read_bytes()
        mime = mime_for(audio_path.name)

    if order_type == "single_art":
        try:
            update_order_status(order_id, "processing")
            res = await generate_single_art(
                age_group=age_group,
                gender=gender,
                art_style=art_style,
                audio_bytes=audio_bytes,
                mime_type=mime,
                text_description=story_idea,
                include_text=False,
            )
            update_order_status(order_id, "completed")
            return {
                "ok": True,
                "order_type": "single_art",
                "single_art": {
                    "title": res.title,
                    "concept_ar": res.concept_ar,
                    "concept_en": res.concept_en,
                    "art_style": res.art_style,
                    "prompt_en": res.prompt_en,
                },
            }
        except Exception as e:
            log.exception("Process single art order failed: %s", e)
            update_order_status(order_id, "failed")
            raise HTTPException(500, "Failed to process single art")

    # Storybook order
    job_id = uuid.uuid4().hex[:12]
    (config.OUTPUT_DIR / job_id).mkdir(parents=True, exist_ok=True)
    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "step_label_ar": "بنبدأ تجهيز حكاية البطل المحجوزة... ✨",
        "title": "",
        "pages": [],
        "pdf_path": None,
        "error": None,
        "unsafe": False,
    }
    update_order_status(order_id, "processing", result_job_id=job_id)
    background.add_task(
        run_job,
        job_id,
        audio_bytes,
        mime,
        name,
        gender,
        age_group,
        "ai",
        art_style,
        text_prompt=story_idea,
        order_id=order_id,
    )
    return {"ok": True, "order_type": "storybook", "job_id": job_id}

