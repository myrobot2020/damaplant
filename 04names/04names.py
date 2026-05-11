# 04names/04names.py - CLOUD READY
# Adds Pali names and SuttaCentral links, publishes to next stage

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
TOPIC_NAMED = f"projects/{PROJECT_ID}/topics/sutta-named"

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
    publisher.publish(TOPIC_NAMED, message)
    print(f"📤 Published to {TOPIC_NAMED}: {sutta_id}")

def emit_supabase_event(sutta_id: str, stage: str, verb: str):
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

def sutta_id_to_sc_id(sutta_id: str) -> str:
    """Convert AN_8.2.11 -> an8.11"""
    without_an = sutta_id.replace('AN_', '')
    parts = without_an.split('.')
    if len(parts) >= 3:
        return f"{parts[0]}.{parts[2]}".lower()
    return without_an.lower()

def sutta_id_to_name(sutta_id: str) -> str:
    """Generate readable name from ID"""
    parts = sutta_id.replace('AN_', '').split('.')
    return f"AN Book {parts[0]}, Chapter {parts[1]}, Sutta {parts[2]}"

# ============================================
# MAIN PROCESSING
# ============================================

def process_sutta(sutta_id: str):
    """Add names and SC links to a sutta"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "names", "started")
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Check if already processed
        if data.get("status") == "named":
            print(f"   ⏭️ Already named, skipping")
            return
        
        # Generate SC ID and link from sutta ID
        sc_id = sutta_id_to_sc_id(sutta_id)
        sc_link = f"https://suttacentral.net/{sc_id}/en/sujato"
        sutta_name = sutta_id_to_name(sutta_id)
        
        # Add to data
        data["sutta_name"] = sutta_name
        data["sc_id"] = sc_id
        data["sc_link"] = sc_link
        data["named_at"] = datetime.now().isoformat()
        data["status"] = "named"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "sutta_name": sutta_name,
            "sc_id": sc_id,
            "sc_link": sc_link,
            "status": "named",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "names", "completed")
        publish_event(sutta_id, "names", "completed")
        
        print(f"   ✅ Named: {sutta_name}")
        print(f"   🔗 SC Link: {sc_link}\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "names", "failed")

def main():
    """Process all pending suttas"""
    print("🚀 Starting 04names pipeline...")
    
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already named
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "named":
            print(f"⏭️ Skipping {sutta_id} (already named)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 04names complete!")

if __name__ == "__main__":
    main()
