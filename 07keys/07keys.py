# 07keys/07keys.py - CLOUD READY
# Extracts numbered chains from sutta text, publishes to next stage

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
TOPIC_CHAINS = f"projects/{PROJECT_ID}/topics/sutta-chains"

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
    publisher.publish(TOPIC_CHAINS, message)
    print(f"📤 Published to {TOPIC_CHAINS}: {sutta_id}")

def emit_supabase_event(sutta_id: str, stage: str, verb: str):
    try:
        supabase.table("pipeline_events").insert({
            "sutta_id": sutta_id,
            "stage": stage,
            "verb": verb,
            "payload": {},
            "wave": 2,  # GPU lane
            "created_at": datetime.now().isoformat()
        }).execute()
        print(f"📝 Supabase event: {stage}.{verb}")
    except Exception as e:
        print(f"⚠️ Supabase error: {e}")

def extract_items_ollama(text: str, expected_count: int) -> list:
    """Extract numbered items using Ollama"""
    prompt = f"Extract {expected_count} items from this sutta. Return ONLY JSON array.\n\n{text[:800]}"
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=60)
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            match = re.search(r'\[.*\]', result, re.DOTALL)
            if match:
                items = json.loads(match.group())
                if isinstance(items, list):
                    return items[:expected_count]
    except Exception as e:
        print(f"   Ollama error: {e}")
    
    return []

# ============================================
# MAIN PROCESSING
# ============================================

def get_book_number(sutta_id: str) -> int:
    match = re.search(r'AN_(\d+)\.', sutta_id)
    return int(match.group(1)) if match else 0

def process_sutta(sutta_id: str):
    """Extract chains from a sutta"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "keys", "started")
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Check if already processed
        if data.get("status") == "chained":
            print(f"   ⏭️ Already processed, skipping")
            return
        
        # Get sutta text
        sutta_text = data.get("sutta", data.get("normalised_text", ""))
        if not sutta_text:
            print("   ⚠️ No sutta text found")
            emit_supabase_event(sutta_id, "keys", "failed")
            return
        
        expected = get_book_number(sutta_id)
        if expected == 0:
            print(f"   ⚠️ Unknown book number")
            return
        
        print(f"   Expecting {expected} items")
        
        # Extract items using Ollama
        items = extract_items_ollama(sutta_text, expected)
        
        # Update data with chain
        data["chain"] = {
            "category": "",
            "items": items,
            "count": len(items),
            "is_ordered": True
        }
        data["keys_extracted_at"] = datetime.now().isoformat()
        data["status"] = "chained"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "chain_items": items,
            "chain_count": len(items),
            "status": "chained",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "keys", "completed")
        publish_event(sutta_id, "keys", "completed")
        
        print(f"   ✅ Extracted {len(items)}/{expected} items\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "keys", "failed")

def main():
    """Process all pending suttas"""
    print("🚀 Starting 07keys pipeline...")
    print(f"⚡ Using Ollama: {OLLAMA_MODEL}")
    
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already processed
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "chained":
            print(f"⏭️ Skipping {sutta_id} (already chained)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 07keys complete!")

if __name__ == "__main__":
    main()
