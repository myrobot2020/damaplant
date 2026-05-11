# 02normalise/02normalise.py - CLOUD READY
# Reads from GCS, normalizes text, publishes to next stage

import os
import json
import re
from pathlib import Path
from datetime import datetime
from google.cloud import storage, pubsub_v1
from supabase import create_client, Client

# ============================================
# CONFIGURATION
# ============================================

PROJECT_ID = "dama-492316"
GCS_BUCKET = "dama-pipeline-492316"

# Pub/Sub Topics
TOPIC_NORMALISED = f"projects/{PROJECT_ID}/topics/sutta-normalised"

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

NUM_MAP = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
    "point": ".", "period": "."
}

def read_json_from_gcs(blob_path: str) -> dict:
    """Read JSON from GCS"""
    blob = bucket.blob(blob_path)
    content = blob.download_as_string()
    return json.loads(content)

def save_json_to_gcs(data: dict, remote_path: str):
    """Save JSON to GCS"""
    blob = bucket.blob(remote_path)
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
    print(f"📄 Saved to gs://{GCS_BUCKET}/{remote_path}")

def publish_event(sutta_id: str, stage: str, status: str):
    """Publish event to Pub/Sub"""
    message = json.dumps({
        "sutta_id": sutta_id,
        "stage": stage,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }).encode()
    publisher.publish(TOPIC_NORMALISED, message)
    print(f"📤 Published to {TOPIC_NORMALISED}: {sutta_id}")

def emit_supabase_event(sutta_id: str, stage: str, verb: str):
    """Store event in Supabase"""
    try:
        supabase.table("pipeline_events").insert({
            "sutta_id": sutta_id,
            "stage": stage,
            "verb": verb,
            "payload": {},
            "wave": 1,
            "created_at": datetime.now().isoformat()
        }).execute()
        print(f"📝 Supabase event: {stage}.{verb}")
    except Exception as e:
        print(f"⚠️ Supabase error: {e}")

def normalize_text(text: str) -> str:
    """Convert word numbers to digits"""
    words = text.lower().split()
    new_words = []
    for w in words:
        clean_w = re.sub(r'[^\w]', '', w)
        if clean_w in NUM_MAP:
            new_words.append(NUM_MAP[clean_w])
        else:
            new_words.append(w)
    text = " ".join(new_words)
    for _ in range(3):
        text = re.sub(r'(\d+)\s*\.\s*(\d+)', r'\1.\2', text)
    text = re.sub(r'\.\s+(\d+)', r'.\1', text)
    text = re.sub(r'(\d+)\s+\.', r'\1.', text)
    return text

def find_sutta_markers(text: str) -> list:
    """Find sutta IDs like 8.2.11"""
    pattern = r'\b(?:AN|SN|MN|DN)?\s*(\d+\.\d+(?:\.\d+)?)\b'
    return list(re.finditer(pattern, text, re.IGNORECASE))

# ============================================
# MAIN PROCESSING
# ============================================

def process_sutta(sutta_id: str):
    """Normalize a single sutta"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "normalise", "started")
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Get raw transcript
        raw_text = data.get("transcript", "")
        if not raw_text:
            print("   ⚠️ No transcript found")
            emit_supabase_event(sutta_id, "normalise", "failed")
            return
        
        # Normalize text
        norm_text = normalize_text(raw_text)
        
        # Find sutta markers
        matches = find_sutta_markers(norm_text)
        print(f"   Found {len(matches)} sutta markers")
        
        # Add normalized text to data
        data["normalised_text"] = norm_text
        data["normalised_at"] = datetime.now().isoformat()
        data["status"] = "normalised"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "normalised_text": norm_text[:10000],
            "status": "normalised",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "normalise", "completed")
        publish_event(sutta_id, "normalise", "completed")
        
        print(f"   ✅ Normalised {sutta_id}\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "normalise", "failed")
        
        try:
            supabase.table("suttas").update({
                "status": "normalise_failed",
                "error": error_msg
            }).eq("id", sutta_id).execute()
        except:
            pass

def main():
    """Process all pending suttas"""
    print("🚀 Starting 02normalise pipeline...")
    
    # Get all sutta JSONs from GCS
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already normalised
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "normalised":
            print(f"⏭️ Skipping {sutta_id} (already normalised)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 02normalise complete!")

if __name__ == "__main__":
    main()
