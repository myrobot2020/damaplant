# plant_server.py - Updated for Nitro build structure

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from google.cloud import storage
import uvicorn

# ============================================
# CONFIGURATION
# ============================================

GCS_BUCKET = "dama-pipeline-492316"
PROJECT_ID = "dama-492316"

storage_client = storage.Client(project=PROJECT_ID)
bucket = storage_client.bucket(GCS_BUCKET)

app = FastAPI()

active_connections: List[WebSocket] = []

# Path to React build (Nitro output)
UI_PATH = Path(r"C:\Users\ADMIN\Desktop\mob app\dharma-factory-dashboard\dist\client")

# ============================================
# STATIC FILES (Nitro build)
# ============================================

if UI_PATH.exists():
    # Mount assets folder if it exists
    assets_path = UI_PATH / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
    # Serve index.html at root
    index_path = UI_PATH / "index.html"
    if index_path.exists():
        @app.get("/")
        @app.get("/plant")
        @app.get("/plant/{path:path}")
        async def serve_plant_ui():
            return FileResponse(index_path)
    else:
        print(f"⚠️ index.html not found at {index_path}")
else:
    print(f"⚠️ UI path not found: {UI_PATH}")

# ============================================
# HELPER FUNCTIONS
# ============================================

def read_events_from_gcs(limit: int = 200) -> List[dict]:
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
        print(f"Error reading events: {e}")
    return events[:limit]

def get_jobs_from_gcs() -> List[dict]:
    jobs = []
    try:
        blobs = bucket.list_blobs(prefix="suttas/")
        for blob in blobs:
            try:
                content = blob.download_as_string()
                sutta = json.loads(content)
                job = {
                    "id": sutta.get("id", ""),
                    "sutta_id": sutta.get("id", ""),
                    "title": sutta.get("title", ""),
                    "source": "youtube",
                    "status": sutta.get("status", "discovered"),
                    "current_wave": get_wave_from_status(sutta.get("status", "")),
                    "started_at": parse_timestamp(sutta.get("created_at")),
                    "updated_at": parse_timestamp(sutta.get("updated_at")),
                }
                jobs.append(job)
            except:
                continue
    except Exception as e:
        print(f"Error reading jobs: {e}")
    return jobs

def get_wave_from_status(status: str) -> int:
    wave_map = {
        "ingested": 1, "normalised": 1, "segmented": 1, "named": 1,
        "chained": 2, "commentary_classified": 2, "generated": 2, "translated": 2,
        "dubbed": 3, "sealed": 3
    }
    return wave_map.get(status, 0)

def parse_timestamp(ts_str: Optional[str]) -> int:
    if not ts_str:
        return 0
    try:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return int(dt.timestamp() * 1000)
    except:
        return 0

# ============================================
# API ENDPOINTS
# ============================================

@app.get("/events")
async def get_events(limit: int = Query(200)):
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

@app.get("/jobs")
async def get_jobs():
    return get_jobs_from_gcs()

@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    try:
        blob = bucket.blob(f"suttas/{job_id}.json")
        if not blob.exists():
            return None
        content = blob.download_as_string()
        sutta = json.loads(content)
        
        job = {
            "id": job_id,
            "sutta_id": job_id,
            "title": sutta.get("title", ""),
            "source": "youtube",
            "status": sutta.get("status", "discovered"),
            "current_wave": get_wave_from_status(sutta.get("status", "")),
            "started_at": parse_timestamp(sutta.get("created_at")),
            "updated_at": parse_timestamp(sutta.get("updated_at"))
        }
        
        artifacts = []
        events = [e for e in read_events_from_gcs(500) if e.get("sutta_id") == job_id]
        return {"job": job, "artifacts": artifacts, "events": events}
    except Exception as e:
        print(f"Error: {e}")
        return None

@app.get("/waves")
async def get_waves():
    jobs = get_jobs_from_gcs()
    
    wave1_jobs = [j for j in jobs if j.get("current_wave") == 1]
    wave1_slots = []
    for i in range(8):
        if i < len(wave1_jobs):
            j = wave1_jobs[i]
            wave1_slots.append({
                "index": i, "busy": True, "task": "process",
                "job_id": j.get("id"), "sutta_title": j.get("title"),
                "started_at": j.get("started_at")
            })
        else:
            wave1_slots.append({"index": i, "busy": False})
    
    wave2_jobs = [j for j in jobs if j.get("current_wave") == 2]
    wave2_locked = len(wave2_jobs) > 0
    
    wave3_jobs = [j for j in jobs if j.get("current_wave") == 3]
    
    return {
        "wave1": wave1_slots,
        "wave2": {
            "locked": wave2_locked,
            "job_id": wave2_jobs[0].get("id") if wave2_jobs else None,
            "sutta_title": wave2_jobs[0].get("title") if wave2_jobs else None,
            "stage": "gen",
            "vram_loaded": wave2_locked,
            "queue_depth": len(wave2_jobs),
            "started_at": wave2_jobs[0].get("started_at") if wave2_jobs else None
        },
        "wave3": {"pipeline": {}, "ready_to_seal": len(wave3_jobs)},
        "throughput_per_hour": len([j for j in jobs if j.get("status") == "sealed"]),
        "errors_last_hour": 0
    }

@app.get("/artifacts")
async def get_artifacts(hash_prefix: Optional[str] = None):
    jobs = get_jobs_from_gcs()
    artifacts = []
    for job in jobs:
        if job.get("status") == "sealed":
            artifacts.append({
                "id": f"art_{job['id']}",
                "job_id": job["id"],
                "sutta_id": job["sutta_id"],
                "kind": "seal",
                "hash_id": job["id"][:8],
                "size_bytes": 1024,
                "created_at": job.get("updated_at", 0),
                "golden": True
            })
    artifacts.sort(key=lambda x: x["created_at"], reverse=True)
    return artifacts

@app.post("/api/ingest")
async def start_ingest(request: dict):
    url = request.get("url")
    print(f"📥 Ingest requested: {url}")
    return {"status": "started", "url": url}

@app.get("/health")
async def health():
    return {"status": "ok"}

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🌱 DAMA Plant Server")
    print("=" * 60)
    print(f"📍 UI Path: {UI_PATH}")
    print(f"📍 API: http://localhost:8001/events")
    print(f"📍 Plant UI: http://localhost:8001/plant")
    print("=" * 60)
    
    # Use port 8001 instead of 8000 to avoid conflict
    uvicorn.run(app, host="0.0.0.0", port=8001)
