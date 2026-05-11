# 08commentary/08commentary.py - CLOUD READY
# Classifies commentary into cautions, practices, sidenotes, interpretations

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
TOPIC_COMMENTARY = f"projects/{PROJECT_ID}/topics/sutta-commentary"

# Ollama
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
    publisher.publish(TOPIC_COMMENTARY, message)
    print(f"📤 Published to {TOPIC_COMMENTARY}: {sutta_id}")

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

def classify_segment(segment: str) -> str:
    """Classify a single commentary segment using Ollama"""
    if len(segment) < 30:
        return "other"
    
    prompt = f"Classify: caution/practice/sidenote/interpretation. Return only one word.\n\n{segment[:300]}"
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=30)
        
        result = response.json().get("response", "").strip().lower()
        for cat in ["caution", "practice", "sidenote", "interpretation"]:
            if cat in result:
                return cat
    except Exception as e:
        print(f"   Classification error: {e}")
    
    return "other"

def split_commentary(commentary: str) -> list:
    """Split commentary into segments"""
    markers = [
        r'[Ii]\s+just\s+stopped',
        r'[Ii]\'?ll\s+just\s+stop', 
        r'[Ii]\'?d\s+just\s+like\s+to\s+commend',
        r'[Ff]irstly\s+you\s+notice'
    ]
    pattern = '|'.join(markers)
    matches = list(re.finditer(pattern, commentary, re.IGNORECASE))
    
    if not matches:
        return [commentary] if commentary else []
    
    segments, prev = [], 0
    for m in matches:
        if m.start() > prev:
            seg = commentary[prev:m.start()].strip()
            if seg:
                segments.append(seg)
        prev = m.start()
    
    if prev < len(commentary):
        segments.append(commentary[prev:].strip())
    
    return segments

# ============================================
# MAIN PROCESSING
# ============================================

def process_sutta(sutta_id: str):
    """Classify commentary for a sutta"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "commentary", "started")
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Check if already processed
        if data.get("status") == "commentary_classified":
            print(f"   ⏭️ Already processed, skipping")
            return
        
        # Get commentary text
        commentary = data.get("commentary", data.get("commentary_text", ""))
        if not commentary:
            print("   ⚠️ No commentary found")
            emit_supabase_event(sutta_id, "commentary", "failed")
            return
        
        print(f"   Commentary length: {len(commentary)} chars")
        
        # Split into segments
        segments = split_commentary(commentary)
        print(f"   Split into {len(segments)} segments")
        
        # Classify each segment
        classified = {"cautions": [], "practices": [], "sidenotes": [], "interpretations": [], "other": []}
        
        for i, seg in enumerate(segments):
            if len(seg) < 30:
                continue
            cat = classify_segment(seg)
            classified[cat].append({
                "index": i,
                "text": seg[:300],  # Store preview
                "full_text": seg
            })
            print(f"   Segment {i}: {cat}")
        
        # Update data
        data["classified_commentary"] = classified
        data["commentary_classified_at"] = datetime.now().isoformat()
        data["status"] = "commentary_classified"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "commentary_classified": json.dumps(classified),
            "status": "commentary_classified",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "commentary", "completed")
        publish_event(sutta_id, "commentary", "completed")
        
        print(f"   ✅ Cautions: {len(classified['cautions'])}")
        print(f"   ✅ Practices: {len(classified['practices'])}")
        print(f"   ✅ Sidenotes: {len(classified['sidenotes'])}")
        print(f"   ✅ Interpretations: {len(classified['interpretations'])}\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "commentary", "failed")

def main():
    """Process all pending suttas"""
    print("🚀 Starting 08commentary pipeline...")
    
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already processed
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "commentary_classified":
            print(f"⏭️ Skipping {sutta_id} (already classified)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 08commentary complete!")

if __name__ == "__main__":
    main()
