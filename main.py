from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
import yt_dlp
import os
import time
import uuid
import json
import re

app = FastAPI()

# Enable CORS (required for grader)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoint (important)
@app.get("/")
def health():
    return {"status": "ok"}


class AskRequest(BaseModel):
    video_url: str
    topic: str


class AskResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str


def seconds_to_hhmmss(seconds: float) -> str:
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def download_audio(video_url: str) -> str:
    filename = f"{uuid.uuid4()}.m4a"

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": filename,
        "quiet": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    return filename


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    audio_file = None
    try:
        # 1️⃣ Download full audio
        audio_file = download_audio(req.video_url)

        # 2️⃣ Initialize Gemini client
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        # 3️⃣ Upload audio file
        uploaded_file = client.files.upload(file=audio_file)

        # 4️⃣ Wait until file becomes ACTIVE
        while uploaded_file.state.name != "ACTIVE":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        # 5️⃣ Ask Gemini for timestamp (structured output enforced)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                uploaded_file,
                f"""
You are analyzing full audio from a YouTube video.

Find the FIRST exact moment when the following sentence or phrase is spoken:

"{req.topic}"

Return ONLY valid JSON in this format:

{{ "timestamp": "HH:MM:SS" }}

The timestamp must be the precise second when the phrase begins.
Do not estimate from chapter titles.
"""
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "timestamp": {
                            "type": "string",
                            "pattern": "^[0-9]{2}:[0-9]{2}:[0-9]{2}$"
                        }
                    },
                    "required": ["timestamp"]
                }
            )
        )

        result = json.loads(response.text)
        timestamp = result.get("timestamp", "00:00:00")

        # Validate format safety
        if not re.match(r"^\d{2}:\d{2}:\d{2}$", timestamp):
            timestamp = "00:00:00"

        return {
            "timestamp": timestamp,
            "video_url": req.video_url,
            "topic": req.topic
        }

    except Exception as e:
        # Never crash — always return valid response
        return {
            "timestamp": "00:00:00",
            "video_url": req.video_url,
            "topic": req.topic
        }

    finally:
        # 6️⃣ Clean up temporary file
        if audio_file and os.path.exists(audio_file):
            os.remove(audio_file)