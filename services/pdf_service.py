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

# font size range per age group (3-5 = bigger text, fewer words)
FONT_SIZES = {"3-5": (30, 20), "6-10": (22, 14)}  # (start, minimum)


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


def _fit(text: str, max_w: float, max_h: float, start: int, minimum: int):
    """Largest font size (start..minimum) whose wrapped text fits the box. Returns (size, lines, leading)."""
    size = start
    while True:
        lines = _wrap(text, size, max_w)
        leading = size * 1.7
        if len(lines) * leading <= max_h or size <= minimum:
            return size, lines, leading
        size -= 1


def _png(b: bytes) -> ImageReader:
    return ImageReader(io.BytesIO(b))


def build_pdf(title: str, pages: list, out_path: str,
              child_name: str = "", gender: str = "girl", age_group: str = "3-5"):
    """Portrait A4. Cover + one page per scene: top half = story text, bottom half = coloring image.
    pages = [{"png": bytes, "narration": str}, ...]"""
    _ensure_font()
    W, H = A4
    m = 1.5 * cm
    half = H / 2
    start, minimum = FONT_SIZES[age_group]

    c = canvas.Canvas(out_path, pagesize=A4)
    c.setTitle(title)

    # ---- cover ----
    c.setFont(FONT, 40)
    c.drawCentredString(W / 2, H - 3.5 * cm, _shape(title))
    c.setFont(FONT, 18)
    c.drawCentredString(W / 2, H - 5 * cm, _shape("حكاياتي الملونة"))
    size = 14 * cm
    c.drawImage(_png(pages[0]["png"]), (W - size) / 2, H - 6 * cm - size, size, size)
    if child_name:
        dedication = ("إهداء إلى البطل " if gender == "boy" else "إهداء إلى البطلة ") + child_name
        c.setFont(FONT, 22)
        c.drawCentredString(W / 2, 4.2 * cm, _shape(dedication))
    c.setFont(FONT, 16)
    c.drawCentredString(W / 2, 2.8 * cm, _shape("لوّن حكايتك وخلّيها حقيقية!"))
    c.showPage()

    # ---- story pages ----
    img_size = min(W - 2 * m, half - 2 * cm)  # square image inside the bottom half
    text_top = H - m
    text_bottom = half + 0.8 * cm
    for i, p in enumerate(pages, 1):
        # TOP HALF: text, vertically centered in the half
        fsize, lines, leading = _fit(p["narration"], W - 2 * m - 0.6 * cm,
                                     text_top - text_bottom, start, minimum)
        block_h = len(lines) * leading
        y = text_bottom + (text_top - text_bottom + block_h) / 2 - fsize
        c.setFont(FONT, fsize)
        for line in lines:
            c.drawCentredString(W / 2, y, _shape(line))
            y -= leading

        # cut / fold guide between the halves
        c.setStrokeGray(0.75)
        c.setDash(4, 4)
        c.setLineWidth(0.6)
        c.line(m, half, W - m, half)
        c.setDash()

        # page number
        c.setFont(FONT, 12)
        c.setFillGray(0.5)
        c.drawCentredString(W / 2, 0.8 * cm, str(i))
        c.setFillGray(0)

        # BOTTOM HALF: coloring image, centered
        x = (W - img_size) / 2
        c.drawImage(_png(p["png"]), x, (half - img_size) / 2 + 0.3 * cm, img_size, img_size)
        c.setStrokeGray(0)
        c.showPage()

    c.save()
