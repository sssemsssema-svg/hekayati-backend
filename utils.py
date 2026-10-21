from fastapi import HTTPException

AUDIO_MIME = {
    "m4a": "audio/m4a",
    "mp4": "audio/m4a",
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
