# container1/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import storage, pubsub_v1
import subprocess
import json
import re
import os
from datetime import datetime
from typing import Optional, List
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GCS_BUCKET = "dama-pipeline-492316"
PROJECT_ID = "dama-492316"

storage_client = storage.Client(project=PROJECT_ID)
bucket = storage_client.bucket(GCS_BUCKET)
publisher = pubsub_v1.PublisherClient()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

class IngestRequest(BaseModel):
    url: str
    slug: Optional[str] = None

def save_to_gcs(data: dict, path: str):
    blob = bucket.blob(path)
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")

def emit_event(sutta_id: str, verb: str, wave: int = 1):
    event = {
        "id": f"evt_{int(datetime.now().timestamp() * 1000)}",
        "ts": int(datetime.now().timestamp() * 1000),
        "verb": verb,
        "job_id": sutta_id,
        "sutta_id": sutta_id,
        "wave": wave,
        "payload": {}
    }
    save_to_gcs(event, f"events/{event['id']}.json")
    print(f"📡 Event: {verb} - {sutta_id}")

def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

def extract_items_ollama(text: str, expected: int) -> list:
    prompt = f"Extract {expected} items from this sutta. Return ONLY JSON array.\n\n{text[:800]}"
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}, timeout=60)
        result = resp.json().get("response", "")
        match = re.search(r'\[.*\]', result, re.DOTALL)
        if match:
            return json.loads(match.group())[:expected]
    except:
        pass
    return []

@app.post("/ingest")
async def ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    """Start pipeline for YouTube URL"""
    background_tasks.add_task(process_ingest, request.url, request.slug)
    return {"status": "started", "url": request.url}

def process_ingest(url: str, slug: str = None):
    """01ingest - Download and process video"""
    emit_event(slug or "pending", "ingest.started", wave=1)
    try:
        # Get metadata
        result = subprocess.run(["yt-dlp", "--get-id", "--get-title", "--no-playlist", url], capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        title = lines[0]
        video_id = lines[1] if len(lines) > 1 else lines[0]
        
        if not slug:
            slug = slugify(title)
        
        # Create temp dir and download
        temp_dir = f"/tmp/{slug}"
        os.makedirs(temp_dir, exist_ok=True)
        audio_path = f"{temp_dir}/{slug}.m4a"
        
        subprocess.run(["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio", "-o", audio_path, "--no-playlist", url], check=True)
        
        # Upload audio to GCS
        blob = bucket.blob(f"audio/{slug}.m4a")
        blob.upload_from_filename(audio_path)
        
        # Download captions
        subprocess.run(["yt-dlp", "--skip-download", "--write-auto-sub", "--sub-langs", "en", "-o", f"{temp_dir}/{slug}", "--no-playlist", url], check=False)
        
        # Extract transcript
        import glob
        vtt_files = glob.glob(f"{temp_dir}/{slug}.*.vtt")
        transcript = ""
        if vtt_files:
            with open(vtt_files[0], 'r', encoding='utf-8') as f:
                content = f.read()
                content = re.sub(r'WEBVTT.*?\n\n', '', content, flags=re.DOTALL)
                content = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*?\n', '', content)
                content = re.sub(r'<.*?>', '', content)
                transcript = " ".join([line.strip() for line in content.splitlines() if line.strip()])
        
        # Save sutta data
        sutta_data = {
            "id": slug, "title": title, "url": url, "video_id": video_id,
            "transcript": transcript, "audio_url": f"gs://{GCS_BUCKET}/audio/{slug}.m4a",
            "status": "ingested", "created_at": datetime.now().isoformat()
        }
        save_to_gcs(sutta_data, f"suttas/{slug}.json")
        
        # Normalize text
        emit_event(slug, "normalise.started", wave=1)
        norm_text = normalize_text(transcript)
        sutta_data["normalised_text"] = norm_text
        sutta_data["status"] = "normalised"
        save_to_gcs(sutta_data, f"suttas/{slug}.json")
        emit_event(slug, "normalise.completed", wave=1)
        
        # Segment
        emit_event(slug, "segment.started", wave=1)
        sutta_text, commentary_text = split_text(norm_text)
        sutta_data["sutta"] = sutta_text
        sutta_data["commentary"] = commentary_text
        sutta_data["status"] = "segmented"
        save_to_gcs(sutta_data, f"suttas/{slug}.json")
        emit_event(slug, "segment.completed", wave=1)
        
        # Add SC link
        emit_event(slug, "names.started", wave=1)
        sc_id = sutta_id_to_sc_id(slug)
        sutta_data["sutta_name"] = sutta_id_to_name(slug)
        sutta_data["sc_id"] = sc_id
        sutta_data["sc_link"] = f"https://suttacentral.net/{sc_id}/en/sujato"
        sutta_data["status"] = "named"
        save_to_gcs(sutta_data, f"suttas/{slug}.json")
        emit_event(slug, "names.completed", wave=1)
        
        # Extract chains (GPU)
        emit_event(slug, "keys.started", wave=2)
        book_num = get_book_number(slug)
        items = extract_items_ollama(sutta_text, book_num)
        sutta_data["chain"] = {"category": "", "items": items, "count": len(items), "is_ordered": True}
        sutta_data["status"] = "chained"
        save_to_gcs(sutta_data, f"suttas/{slug}.json")
        emit_event(slug, "keys.completed", wave=2)
        
        # Classify commentary (GPU)
        emit_event(slug, "commentary.started", wave=2)
        classified = classify_commentary(commentary_text)
        sutta_data["classified_commentary"] = classified
        sutta_data["status"] = "commentary_classified"
        save_to_gcs(sutta_data, f"suttas/{slug}.json")
        emit_event(slug, "commentary.completed", wave=2)
        
        # Generate content (GPU)
        emit_event(slug, "generate.started", wave=2)
        mcq = generate_mcq(sutta_text, sutta_data["sutta_name"])
        vow = generate_text(sutta_text, "vow")
        caution = generate_text(sutta_text, "caution")
        practice = generate_text(sutta_text, "practice")
        sutta_data["generated_content"] = {"mcq_quiz": mcq, "vow": vow, "caution": caution, "practice": practice}
        sutta_data["status"] = "generated"
        save_to_gcs(sutta_data, f"suttas/{slug}.json")
        emit_event(slug, "generate.completed", wave=2)
        
        # Trigger translation (call Container 2)
        requests.post("http://dama-translate:8080/translate", json={"sutta_id": slug})
        
        emit_event(slug, "ingest.completed", wave=1)
        
    except Exception as e:
        print(f"Error: {e}")
        emit_event(slug or "failed", f"ingest.failed", wave=1)

def normalize_text(text: str) -> str:
    NUM_MAP = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
               "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
    words = text.lower().split()
    new_words = []
    for w in words:
        clean_w = re.sub(r'[^\w]', '', w)
        new_words.append(NUM_MAP.get(clean_w, w))
    return " ".join(new_words)

def split_text(text: str) -> tuple:
    markers = [r'[Ii]\s+just\s+stopped', r'[Ii]\'?d\s+just\s+like\s+to\s+commend', r'[Ff]irstly\s+you\s+notice']
    pattern = '|'.join(markers)
    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    if not matches:
        return text, ""
    cut = matches[0].start()
    return text[:cut].strip(), text[cut:].strip()

def sutta_id_to_sc_id(sutta_id: str) -> str:
    without_an = sutta_id.replace('AN_', '')
    parts = without_an.split('.')
    if len(parts) >= 3:
        return f"{parts[0]}.{parts[2]}".lower()
    return without_an.lower()

def sutta_id_to_name(sutta_id: str) -> str:
    parts = sutta_id.replace('AN_', '').split('.')
    return f"AN Book {parts[0]}, Chapter {parts[1]}, Sutta {parts[2]}"

def get_book_number(sutta_id: str) -> int:
    match = re.search(r'AN_(\d+)\.', sutta_id)
    return int(match.group(1)) if match else 0

def classify_commentary(commentary: str) -> dict:
    classified = {"cautions": [], "practices": [], "sidenotes": [], "interpretations": []}
    markers = [r'[Ii]\s+just\s+stopped', r'[Ii]\'?ll\s+just\s+stop', r'[Ii]\'?d\s+just\s+like\s+to\s+commend']
    pattern = '|'.join(markers)
    segments = re.split(pattern, commentary, flags=re.IGNORECASE)
    for seg in segments:
        if len(seg) < 30:
            continue
        if any(word in seg.lower() for word in ["warning", "danger", "avoid", "not"]):
            classified["cautions"].append(seg[:200])
        elif any(word in seg.lower() for word in ["practice", "do", "should", "meditate"]):
            classified["practices"].append(seg[:200])
        elif any(word in seg.lower() for word in ["just", "notice", "see", "commend"]):
            classified["sidenotes"].append(seg[:200])
        else:
            classified["interpretations"].append(seg[:200])
    return classified

def generate_mcq(text: str, name: str) -> dict:
    prompt = f"Generate MCQ from this sutta. Return JSON: {{\"question\": \"\", \"options\": [], \"correct\": \"A\"}}\n\n{text[:800]}"
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=60)
        result = resp.json().get("response", "")
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            return json.loads(match.group())
    except:
        pass
    return {"question": "No question", "options": ["A", "B", "C", "D"], "correct": "A"}

def generate_text(text: str, content_type: str) -> str:
    prompt = f"Generate ONE SENTENCE {content_type} from this sutta:\n\n{text[:500]}"
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=60)
        return resp.json().get("response", "").strip()
    except:
        return ""

@app.get("/events")
async def get_events(limit: int = 200):
    events = []
    blobs = bucket.list_blobs(prefix="events/")
    for blob in blobs:
        try:
            content = blob.download_as_string()
            events.append(json.loads(content))
        except:
            continue
    events.sort(key=lambda x: x.get('ts', 0), reverse=True)
    return events[:limit]

@app.get("/health")
async def health():
    return {"status": "ok", "gcs_bucket": GCS_BUCKET}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
