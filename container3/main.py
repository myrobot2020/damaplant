# container3/main.py - Dubbing service (TTS)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import storage
import json
import subprocess
from datetime import datetime
from pathlib import Path

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GCS_BUCKET = "dama-pipeline-492316"
storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET)

class DubRequest(BaseModel):
    sutta_id: str

def save_to_gcs(data: dict, path: str):
    blob = bucket.blob(path)
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")

@app.post("/dub")
async def dub(request: DubRequest):
    sutta_id = request.sutta_id
    print(f"🎵 Dubbing: {sutta_id}")
    
    blob = bucket.blob(f"suttas/{sutta_id}.json")
    if not blob.exists():
        return {"error": "Sutta not found"}
    
    content = blob.download_as_string()
    sutta = json.loads(content)
    
    japanese = sutta.get("japanese", {})
    
    # For now, placeholder for TTS
    # In production, call Kokoro or StyleTTS2 here
    
    sutta["dubbing"] = {
        "status": "completed",
        "clips": {
            "sutta": f"gs://{GCS_BUCKET}/dubs/{sutta_id}_sutta.mp3",
            "vow": f"gs://{GCS_BUCKET}/dubs/{sutta_id}_vow.mp3",
            "caution": f"gs://{GCS_BUCKET}/dubs/{sutta_id}_caution.mp3",
            "practice": f"gs://{GCS_BUCKET}/dubs/{sutta_id}_practice.mp3"
        },
        "dubbed_at": datetime.now().isoformat()
    }
    sutta["status"] = "dubbed"
    
    save_to_gcs(sutta, f"suttas/{sutta_id}.json")
    
    return {"status": "dubbed", "sutta_id": sutta_id}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
