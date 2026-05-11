# container2/main.py - Translation service (qwen2.5:14b)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import storage
import json
import re
import requests
from datetime import datetime
from typing import Optional

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

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:14b"

class TranslateRequest(BaseModel):
    sutta_id: str

def save_to_gcs(data: dict, path: str):
    blob = bucket.blob(path)
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")

def translate_text(text: str, text_type: str) -> str:
    if not text or len(text) < 20:
        return ""
    prompt = f"Translate this Buddhist {text_type} from English to Japanese. Return ONLY Japanese translation.\n\nEnglish: {text[:800]}"
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}, timeout=120)
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"Translation error: {e}")
        return text

def translate_mcq(mcq: dict) -> dict:
    if not mcq:
        return mcq
    translated = {}
    if "question" in mcq:
        translated["question"] = translate_text(mcq["question"], "MCQ question")
    if "options" in mcq:
        translated["options"] = [translate_text(opt, "option") for opt in mcq["options"]]
    if "explanation" in mcq:
        translated["explanation"] = translate_text(mcq["explanation"], "explanation")
    if "correct" in mcq:
        translated["correct"] = mcq["correct"]
    return translated

@app.post("/translate")
async def translate(request: TranslateRequest):
    sutta_id = request.sutta_id
    print(f"📖 Translating: {sutta_id}")
    
    blob = bucket.blob(f"suttas/{sutta_id}.json")
    if not blob.exists():
        return {"error": "Sutta not found"}
    
    content = blob.download_as_string()
    sutta = json.loads(content)
    
    sutta["japanese"] = {
        "sutta": translate_text(sutta.get("sutta", ""), "sutta"),
        "commentary": translate_text(sutta.get("commentary", ""), "commentary"),
        "vow": translate_text(sutta.get("generated_content", {}).get("vow", ""), "vow"),
        "caution": translate_text(sutta.get("generated_content", {}).get("caution", ""), "caution"),
        "practice": translate_text(sutta.get("generated_content", {}).get("practice", ""), "practice"),
        "mcq_quiz": translate_mcq(sutta.get("generated_content", {}).get("mcq_quiz", {})),
        "translated_at": datetime.now().isoformat()
    }
    sutta["status"] = "translated"
    
    save_to_gcs(sutta, f"suttas/{sutta_id}.json")
    
    # Trigger rebuild
    import requests
    requests.post("http://dama-rebuild:8080/rebuild", json={"sutta_id": sutta_id})
    
    return {"status": "translated", "sutta_id": sutta_id}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
