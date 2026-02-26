from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
import yt_dlp
import os
import time
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    video_url: str
    topic: str

class AskResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str


def download_audio(video_url):
    filename = f"{uuid.uuid4()}.mp3"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": filename,
        "quiet": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    return filename


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        # 1️⃣ Download audio
        audio_file = download_audio(req.video_url)

        # 2️⃣ Upload to Gemini
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        file = client.files.upload(file=audio_file)

        # 3️⃣ Wait until ACTIVE
        while file.state.name != "ACTIVE":
            time.sleep(2)
            file = client.files.get(name=file.name)

        # 4️⃣ Ask Gemini for timestamp
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                file,
                f"""
Locate the FIRST moment in this audio where the following topic is spoken:

"{req.topic}"

Return ONLY the timestamp in HH:MM:SS format.
Example: 00:05:47
"""
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string"}
                    },
                    "required": ["timestamp"]
                }
            )
        )

        import json
        result = json.loads(response.text)

        # 5️⃣ Cleanup
        os.remove(audio_file)

        return {
            "timestamp": result["timestamp"],
            "video_url": req.video_url,
            "topic": req.topic
        }

    except Exception:
        return {
            "timestamp": "00:00:00",
            "video_url": req.video_url,
            "topic": req.topic
        }