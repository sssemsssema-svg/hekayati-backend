import json
from google import genai
from google.genai import types
from pydantic import BaseModel

import config
from services.prompts import (
    build_single_art_prompt,
    pick_style_for_story,
)

client = genai.Client(api_key=config.GEMINI_API_KEY)


class SingleArtResult(BaseModel):
    title: str = ""
    concept_ar: str = ""
    concept_en: str = ""
    art_style: str = ""
    prompt_en: str = ""


SYSTEM_INSTRUCTION = """You are an expert coloring book art director for kids, teens, and adults.
A user will provide an idea (either via voice audio or text description) for a single coloring page artwork.
Analyze their idea, age group, gender, and requested style.
Return ONLY this JSON format:
{
  "title": "Short catchy Arabic title for the artwork (e.g. ماندالا الذئب الأسطوري, بطل الأنمي الخارق)",
  "concept_ar": "Warm concise Arabic summary of the scene (1-2 sentences)",
  "concept_en": "Rich, detailed visual scene description in English for the coloring page illustrator (setting, characters, details, composition, poses). CRITICAL: NEVER include color words (NO red, blue, green, yellow, black, brown) - describe only shapes, lines, objects, and subjects."
}
"""


async def generate_single_art(
    age_group: str,
    gender: str,
    art_style: str,
    audio_bytes: bytes = None,
    mime_type: str = "",
    text_description: str = "",
    include_text: bool = False,
) -> SingleArtResult:
    chosen_style = pick_style_for_story(age_group, art_style)

    contents = []
    if audio_bytes and len(audio_bytes) > 0:
        contents.append(types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/m4a"))
        prompt_text = f"User voice request for a single coloring page. Target audience: {age_group} years old ({gender}). Art style: {chosen_style}."
        if text_description:
            prompt_text += f" Additional notes: {text_description}"
        contents.append(prompt_text)
    else:
        contents.append(
            f"User text request for a single coloring page: '{text_description}'. Target audience: {age_group} years old ({gender}). Art style: {chosen_style}."
        )

    resp = await client.aio.models.generate_content(
        model=config.TEXT_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.6,
        ),
    )

    data = json.loads(resp.text)
    title = data.get("title", "لوحة تلوين فنية")
    concept_ar = data.get("concept_ar", text_description or "لوحة تلوين مخصصة")
    concept_en = data.get("concept_en", text_description)

    prompt_en = build_single_art_prompt(
        age_group=age_group,
        gender=gender,
        art_style=chosen_style,
        concept_description=concept_en,
        include_text_banner=include_text,
        text_to_print=concept_ar,
    )

    return SingleArtResult(
        title=title,
        concept_ar=concept_ar,
        concept_en=concept_en,
        art_style=chosen_style,
        prompt_en=prompt_en,
    )
