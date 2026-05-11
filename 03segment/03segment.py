# 03segment/03segment.py - CLOUD READY
# Splits sutta vs commentary, publishes to next stage

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
TOPIC_SEGMENTED = f"projects/{PROJECT_ID}/topics/sutta-segmented"

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
    publisher.publish(TOPIC_SEGMENTED, message)
    print(f"📤 Published to {TOPIC_SEGMENTED}: {sutta_id}")

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

# ============================================
# SEGMENTATION LOGIC
# ============================================

SUTTA_START_RE = re.compile(r"(?i)\bthus\s+have\s+i\s+heard\b")
SUTTA_END_RE = re.compile(r"(?i)\b(?:that'?s\s+)?the\s+end\s+of\s+the\s+sut(?:ta|a|e|i)\b")
COMMENTARY_START_RE = re.compile(
    r"(?i)\b("
    r"i\s+just\s+stopped\s+here"
    r"|i'?ll\s+just\s+stop\s+here"
    r"|i'd\s+just\s+like\s+to\s+commend"
    r"|i\s+would\s+just\s+like\s+to\s+commend"
    r")\b"
)

def split_text(text: str) -> tuple:
    """Split into sutta and commentary"""
    blk = (text or "").strip()
    if not blk:
        return "", "", "empty"
    
    start_match = SUTTA_START_RE.search(blk)
    end_matches = list(SUTTA_END_RE.finditer(blk))
    commentary_matches = list(COMMENTARY_START_RE.finditer(blk))
    
    # Priority 1: Clear End Marker
    if len(end_matches) == 1:
        cut = end_matches[0].end()
        return blk[:cut].strip(), blk[cut:].strip(), "end_marker"
    
    # Priority 2: Clear Commentary Start Cue
    if len(commentary_matches) == 1:
        cut = commentary_matches[0].start()
        return blk[:cut].strip(), blk[cut:].strip(), "cue_marker"
    
    # Priority 3: Start Marker found
    if start_match:
        start_pos = start_match.start()
        later_cues = [m for m in commentary_matches if m.start() > start_pos + 500]
        if later_cues:
            cut = later_cues[0].start()
            return blk[start_pos:cut].strip(), (blk[:start_pos] + " " + blk[cut:]).strip(), "start_with_later_cue"
        
        cut = min(start_pos + 4000, len(blk))
        return blk[start_pos:cut].strip(), (blk[:start_pos] + " " + blk[cut:]).strip(), "start_heuristic"
    
    # Fallback
    if len(blk) > 600:
        return blk[:600].strip(), blk[600:].strip(), "length_heuristic"
    
    return blk, "", "no_marker"

# ============================================
# MAIN PROCESSING
# ============================================

def process_sutta(sutta_id: str):
    """Segment a single sutta"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "segment", "started")
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Get normalized text
        text = data.get("normalised_text", data.get("transcript", ""))
        if not text:
            print("   ⚠️ No text found")
            emit_supabase_event(sutta_id, "segment", "failed")
            return
        
        # Split into sutta and commentary
        sutta_text, commentary_text, rule = split_text(text)
        print(f"   Split using: {rule}")
        print(f"   Sutta: {len(sutta_text)} chars")
        print(f"   Commentary: {len(commentary_text)} chars")
        
        # Update data
        data["sutta"] = sutta_text
        data["commentary"] = commentary_text
        data["segment_rule"] = rule
        data["segmented_at"] = datetime.now().isoformat()
        data["status"] = "segmented"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "sutta_text": sutta_text[:10000],
            "commentary_text": commentary_text[:10000],
            "status": "segmented",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "segment", "completed")
        publish_event(sutta_id, "segment", "completed")
        
        print(f"   ✅ Segmented {sutta_id}\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "segment", "failed")

def main():
    """Process all pending suttas"""
    print("🚀 Starting 03segment pipeline...")
    
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already segmented
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "segmented":
            print(f"⏭️ Skipping {sutta_id} (already segmented)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 03segment complete!")

if __name__ == "__main__":
    main()
