# api_server.py - Simple FastAPI server for UI

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
from datetime import datetime
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory event store (replace with Supabase later)
events = []
event_id = 0

class IngestRequest(BaseModel):
    url: str
    slug: Optional[str] = None

@app.post("/api/ingest")
async def start_ingest(request: IngestRequest):
    global event_id
    try:
        event_id += 1
        event = {
            "id": event_id,
            "sutta_id": request.slug or "pending",
            "stage": "ingest",
            "verb": "started",
            "payload": {"url": request.url},
            "wave": 1,
            "created_at": datetime.now().isoformat()
        }
        events.append(event)
        
        print(f"✅ Received: {request.url}")
        
        # Simulate completion
        import threading
        def complete():
            import time
            time.sleep(5)
            global event_id
            event_id += 1
            events.append({
                "id": event_id,
                "sutta_id": request.slug or "test-sutta",
                "stage": "ingest",
                "verb": "completed",
                "payload": {"message": "Audio downloaded, transcript extracted"},
                "wave": 1,
                "created_at": datetime.now().isoformat()
            })
            print(f"✅ Simulated completion for {request.url}")
        
        threading.Thread(target=complete).start()
        
        return {
            "status": "published",
            "message": f"Pipeline started for {request.url}",
            "event_id": event["id"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/events")
async def get_events(limit: int = 50):
    return events[-limit:]

@app.get("/api/health")
async def health():
    return {"status": "ok", "events_count": len(events)}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting API server at http://localhost:8000")
    print("📡 Events endpoint: http://localhost:8000/api/events")
    print("🌱 Ingest endpoint: http://localhost:8000/api/ingest")
    uvicorn.run(app, host="0.0.0.0", port=8000)
