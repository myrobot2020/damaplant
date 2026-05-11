# plant_server_simple.py - Simple API server (UI runs separately)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
from datetime import datetime
from typing import Optional
import json
import uvicorn

app = FastAPI()

# Enable CORS for React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GCS_BUCKET = "dama-pipeline-492316"
storage_client = storage.Client(project="dama-492316")
bucket = storage_client.bucket(GCS_BUCKET)

def read_events_from_gcs(limit: int = 200):
    events = []
    try:
        blobs = bucket.list_blobs(prefix="events/")
        for blob in blobs:
            try:
                content = blob.download_as_string()
                event = json.loads(content)
                events.append(event)
            except:
                continue
        events.sort(key=lambda x: x.get('ts', 0), reverse=True)
    except Exception as e:
        print(f"Error: {e}")
    return events[:limit]

@app.get("/events")
async def get_events(limit: int = 200):
    events = read_events_from_gcs(limit)
    formatted = []
    for e in events:
        formatted.append({
            "id": e.get("id", f"evt_{e.get('ts', 0)}"),
            "ts": e.get("ts", 0),
            "verb": e.get("verb", "unknown"),
            "job_id": e.get("sutta_id", ""),
            "sutta_id": e.get("sutta_id", ""),
            "wave": e.get("wave", 1),
            "payload": e.get("payload", {})
        })
    return formatted

@app.get("/health")
async def health():
    return {"status": "ok", "gcs_bucket": GCS_BUCKET}

@app.post("/api/ingest")
async def start_ingest(request: dict):
    url = request.get("url")
    print(f"📥 Ingest requested: {url}")
    return {"status": "started", "url": url}

if __name__ == "__main__":
    print("=" * 60)
    print("🌱 DAMA API Server")
    print("=" * 60)
    print(f"📍 API Events: http://localhost:8001/events")
    print(f"📍 Health: http://localhost:8001/health")
    print("=" * 60)
    print("\n📌 To run the Plant UI:")
    print("   cd dharma-factory-dashboard/dist/server")
    print("   node index.js")
    print("   Then open: http://localhost:3000/plant")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
