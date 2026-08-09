import io
import logging
import os
import tempfile
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from melo.api import TTS
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)


app = FastAPI(title="Sentientia Open Source TTS", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS", "https://sentientia-holobox-beta.web.app"
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

model = TTS(language="EN", device="cpu")
speaker_id = model.hps.data.spk2id["EN_INDIA"]
inference_lock = threading.Lock()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "MeloTTS", "speaker": "EN_INDIA"}


@app.post("/speak")
def speak(request: SpeechRequest) -> Response:
    text = " ".join(request.text.split())
    try:
        with inference_lock, tempfile.NamedTemporaryFile(suffix=".wav") as output:
            model.tts_to_file(text, speaker_id, output.name, speed=0.94)
            output.seek(0)
            audio = output.read()
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:
        logger.exception("MeloTTS synthesis failed")
        raise HTTPException(status_code=500, detail="Speech generation failed") from exc
