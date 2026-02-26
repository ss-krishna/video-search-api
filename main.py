from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
import re
from fastapi.middleware.cors import CORSMiddleware

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


def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([^&]+)", url)
    if not match:
        raise ValueError("Invalid YouTube URL")
    return match.group(1)


def seconds_to_hhmmss(seconds: float) -> str:
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        video_id = extract_video_id(req.video_url)

        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id)

        for entry in transcript:
            if req.topic.lower() in entry.text.lower():
                timestamp = seconds_to_hhmmss(entry.start)
                return {
                    "timestamp": timestamp,
                    "video_url": req.video_url,
                    "topic": req.topic
                }

        raise HTTPException(status_code=404, detail="Topic not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))