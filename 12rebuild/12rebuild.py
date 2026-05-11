# 12rebuild/12rebuild.py - CLOUD READY
# Final export: collects all sutta data, creates manifest, uploads to GCS

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from google.cloud import storage, pubsub_v1
from supabase import create_client, Client

# ============================================
# CONFIGURATION
# ============================================

PROJECT_ID = "dama-492316"
GCS_BUCKET = "dama-pipeline-492316"
EXPORT_PREFIX = "exports"

# Pub/Sub Topics (final)
TOPIC_REBUILT = f"projects/{PROJECT_ID}/topics/sutta-rebuilt"

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
    publisher.publish(TOPIC_REBUILT, message)
    print(f"📤 Published to {TOPIC_REBUILT}: {sutta_id}")

def emit_supabase_event(sutta_id: str, stage: str, verb: str):
    try:
        supabase.table("pipeline_events").insert({
            "sutta_id": sutta_id or "all",
            "stage": stage,
            "verb": verb,
            "payload": {},
            "wave": 3,
            "created_at": datetime.now().isoformat()
        }).execute()
        print(f"📝 Supabase event: {stage}.{verb}")
    except Exception as e:
        print(f"⚠️ Supabase error: {e}")

def compute_hash(data: dict) -> str:
    """Compute SHA256 hash of content for sealing"""
    content = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(content).hexdigest()[:16]

# ============================================
# MAIN PROCESSING
# ============================================

def rebuild_all():
    """Export all suttas to a sealed manifest"""
    print("🚀 Starting 12rebuild pipeline...")
    emit_supabase_event("all", "rebuild", "started")
    
    try:
        # Get all sutta files from GCS
        blobs = bucket.list_blobs(prefix="suttas/")
        sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
        
        print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
        
        all_suttas = []
        stats = {
            "total": len(sutta_files),
            "with_sutta": 0,
            "with_commentary": 0,
            "with_chain": 0,
            "with_generated": 0,
            "with_translation": 0
        }
        
        for sutta_file in sutta_files:
            sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
            print(f"📖 Processing: {sutta_id}")
            
            data = read_json_from_gcs(sutta_file)
            
            # Build export record
            export_record = {
                "sutta_id": sutta_id,
                "title": data.get("title", ""),
                "sutta_name": data.get("sutta_name", ""),
                "sc_link": data.get("sc_link", ""),
                "sutta_text": data.get("sutta", ""),
                "commentary_text": data.get("commentary", ""),
                "chain": data.get("chain", {}),
                "classified_commentary": data.get("classified_commentary", {}),
                "generated_content": data.get("generated_content", {}),
                "japanese": data.get("japanese", {}),
                "hash": compute_hash(data),
                "exported_at": datetime.now().isoformat()
            }
            
            all_suttas.append(export_record)
            
            # Update stats
            stats["with_sutta"] += 1 if export_record["sutta_text"] else 0
            stats["with_commentary"] += 1 if export_record["commentary_text"] else 0
            stats["with_chain"] += 1 if export_record["chain"].get("items") else 0
            stats["with_generated"] += 1 if export_record["generated_content"] else 0
            stats["with_translation"] += 1 if export_record["japanese"] else 0
            
            print(f"   ✅ Exported")
        
        # Create manifest
        manifest = {
            "exported_at": datetime.now().isoformat(),
            "project": PROJECT_ID,
            "bucket": GCS_BUCKET,
            "total_suttas": len(all_suttas),
            "statistics": stats,
            "suttas": all_suttas
        }
        
        # Save manifest to GCS
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest_path = f"{EXPORT_PREFIX}/manifest_{timestamp}.json"
        save_json_to_gcs(manifest, manifest_path)
        
        # Also save individual sutta exports
        for sutta in all_suttas:
            sutta_path = f"{EXPORT_PREFIX}/suttas/{sutta['sutta_id']}.json"
            save_json_to_gcs(sutta, sutta_path)
        
        # Update Supabase with export info
        supabase.table("exports").insert({
            "exported_at": datetime.now().isoformat(),
            "manifest_path": manifest_path,
            "total_suttas": len(all_suttas),
            "stats": stats
        }).execute()
        
        # Emit completion events
        emit_supabase_event("all", "rebuild", "completed")
        publish_event("all", "rebuild", "completed")
        
        print(f"\n📊 Export Statistics:")
        print(f"   Total suttas: {stats['total']}")
        print(f"   With sutta text: {stats['with_sutta']}")
        print(f"   With commentary: {stats['with_commentary']}")
        print(f"   With chains: {stats['with_chain']}")
        print(f"   With generated content: {stats['with_generated']}")
        print(f"   With Japanese translation: {stats['with_translation']}")
        print(f"\n📁 Manifest: gs://{GCS_BUCKET}/{manifest_path}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        emit_supabase_event("all", "rebuild", "failed")

def main():
    rebuild_all()
    print("\n🎉 12rebuild complete!")

if __name__ == "__main__":
    main()
