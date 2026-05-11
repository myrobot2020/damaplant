# 10generate/10generate.py - CLOUD READY
# Generates MCQ, Vow, Caution, Practice from sutta content

import os
import json
import re
from pathlib import Path
from datetime import datetime
from google.cloud import storage, pubsub_v1
from supabase import create_client, Client
import requests

# ============================================
# CONFIGURATION
# ============================================

PROJECT_ID = "dama-492316"
GCS_BUCKET = "dama-pipeline-492316"

# Pub/Sub Topics
TOPIC_GENERATED = f"projects/{PROJECT_ID}/topics/sutta-generated"

# Ollama (GPU in cloud)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = "llama3.2:3b"

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://dzjljzclrbsyxcfxert.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_6-Clg11T6oNPXTxIjegaJQ_FnTYeLpV")

# Initialize clients
storage_client = storage.Client(project=PROJECT_ID)
bucket = storage_client.bucket(GCS_BUCKET)
publisher = pubsub_v1.PublisherClient()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================
# HELPERS
# ============================================

def read_json_from_gcs(blob_path: str) -> dict:
    blob = bucket.blob(blob_path)
    content = blob.download_as_string()
    return json.loads(content)

def save_json_to_gcs(data: dict, remote_path: str):
    blob = bucket.blob(remote_path)
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
    print(f"📄 Saved to gs://{GCS_BUCKET}/{remote_path}")

def publish_event(sutta_id: str, stage: str, status: str):
    message = json.dumps({
        "sutta_id": sutta_id,
        "stage": stage,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }).encode()
    publisher.publish(TOPIC_GENERATED, message)
    print(f"📤 Published to {TOPIC_GENERATED}: {sutta_id}")

def emit_supabase_event(sutta_id: str, stage: str, verb: str):
    try:
        supabase.table("pipeline_events").insert({
            "sutta_id": sutta_id,
            "stage": stage,
            "verb": verb,
            "payload": {},
            "wave": 2,
            "created_at": datetime.now().isoformat()
        }).execute()
        print(f"📝 Supabase event: {stage}.{verb}")
    except Exception as e:
        print(f"⚠️ Supabase error: {e}")

def generate_mcq(sutta_text: str, sutta_name: str, chain_items: list) -> dict:
    """Generate multiple choice question using Ollama"""
    chain_context = ""
    if chain_items:
        chain_context = f"\nKey items from sutta: {', '.join(chain_items[:5])}"
    
    prompt = f"""Generate ONE multiple choice question from this Buddhist sutta.
Return ONLY JSON: {{"question": "...", "options": ["A", "B", "C", "D"], "correct": "A", "explanation": "..."}}

Sutta: {sutta_name}{chain_context}
Text: {sutta_text[:1000]}"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3}
        }, timeout=60)
        
        result = response.json().get("response", "")
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"   MCQ error: {e}")
    
    return {"question": "No question generated", "options": [], "correct": "", "explanation": ""}

def generate_text(sutta_text: str, content_type: str, sutta_name: str) -> str:
    """Generate vow, caution, or practice using Ollama"""
    prompts = {
        "vow": f"Create a ONE SENTENCE vow from this sutta. Return only the vow text:\n\n{sutta_name}\n{sutta_text[:800]}",
        "caution": f"Extract the CAUTION from this sutta. One short sentence:\n\n{sutta_name}\n{sutta_text[:800]}",
        "practice": f"Extract the PRACTICE from this sutta. One short sentence:\n\n{sutta_name}\n{sutta_text[:800]}"
    }
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompts[content_type],
            "stream": False,
            "options": {"temperature": 0.3}
        }, timeout=60)
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"   {content_type} error: {e}")
        return ""

# ============================================
# MAIN PROCESSING
# ============================================

def process_sutta(sutta_id: str):
    """Generate learning content for a sutta"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "generate", "started")
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Check if already processed
        if data.get("status") == "generated":
            print(f"   ⏭️ Already generated, skipping")
            return
        
        # Get sutta text and metadata
        sutta_text = data.get("sutta", data.get("normalised_text", ""))
        sutta_name = data.get("sutta_name", sutta_id)
        chain_items = data.get("chain", {}).get("items", [])
        
        if not sutta_text:
            print("   ⚠️ No sutta text found")
            emit_supabase_event(sutta_id, "generate", "failed")
            return
        
        print(f"   Generating content for: {sutta_name}")
        
        # Generate MCQ
        print("   Generating MCQ...")
        mcq = generate_mcq(sutta_text, sutta_name, chain_items)
        
        # Generate Vow, Caution, Practice
        print("   Generating Vow...")
        vow = generate_text(sutta_text, "vow", sutta_name)
        
        print("   Generating Caution...")
        caution = generate_text(sutta_text, "caution", sutta_name)
        
        print("   Generating Practice...")
        practice = generate_text(sutta_text, "practice", sutta_name)
        
        # Update data
        data["generated_content"] = {
            "mcq_quiz": mcq,
            "vow": vow,
            "caution": caution,
            "practice": practice,
            "generated_at": datetime.now().isoformat()
        }
        data["status"] = "generated"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "generated_mcq": json.dumps(mcq),
            "generated_vow": vow,
            "generated_caution": caution,
            "generated_practice": practice,
            "status": "generated",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "generate", "completed")
        publish_event(sutta_id, "generate", "completed")
        
        print(f"   ✅ Generated: MCQ, Vow, Caution, Practice\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "generate", "failed")

def main():
    """Process all pending suttas"""
    print("🚀 Starting 10generate pipeline...")
    
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already processed
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "generated":
            print(f"⏭️ Skipping {sutta_id} (already generated)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 10generate complete!")

if __name__ == "__main__":
    main()
