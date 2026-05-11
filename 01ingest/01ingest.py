# 01ingest/01ingest.py - FULL CLOUD READY
# GCS + Pub/Sub + Supabase

import os
import subprocess
import json
import re
import shutil
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
TOPIC_INGESTED = f"projects/{PROJECT_ID}/topics/sutta-ingested"
TOPIC_NORMALISE = f"projects/{PROJECT_ID}/topics/sutta-normalised"

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

def upload_to_gcs(local_path: Path, remote_path: str) -> str:
    """Upload file to GCS and return public URL"""
    blob = bucket.blob(remote_path)
    blob.upload_from_filename(str(local_path))
    blob.make_public()
    print(f"📤 Uploaded to gs://{GCS_BUCKET}/{remote_path}")
    return blob.public_url

def save_json_to_gcs(data: dict, remote_path: str) -> str:
    """Save JSON to GCS"""
    blob = bucket.blob(remote_path)
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
    print(f"📄 JSON saved to gs://{GCS_BUCKET}/{remote_path}")
    return blob.public_url

def publish_event(sutta_id: str, stage: str, status: str):
    """Publish event to Pub/Sub"""
    message = json.dumps({
        "sutta_id": sutta_id,
        "stage": stage,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }).encode()
    
    topic = TOPIC_NORMALISE if stage == "ingest" else TOPIC_INGESTED
    publisher.publish(topic, message)
    print(f"📤 Published to {topic}: {sutta_id}")

def emit_supabase_event(sutta_id: str, stage: str, verb: str):
    """Store event in Supabase for Plant UI"""
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

def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

# ============================================
# MAIN PROCESSING
# ============================================

def process_video(url: str, slug: str = None):
    """Download, process, upload, and trigger next stage"""
    
    emit_supabase_event(slug or "pending", "ingest", "started")
    
    try:
        # Get metadata
        result = subprocess.run(
            ["yt-dlp", "--get-id", "--get-title", "--no-playlist", url],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().split('\n')
        title = lines[0]
        video_id = lines[1] if len(lines) > 1 else lines[0]
        
        if not slug:
            slug = slugify(title)
        
        # Create Supabase record
        supabase.table("suttas").upsert({
            "id": slug,
            "title": title,
            "url": url,
            "video_id": video_id,
            "status": "downloading",
            "created_at": datetime.now().isoformat()
        }).execute()
        
        # Create temp directory
        temp_dir = Path("/tmp") / slug
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio_path = temp_dir / f"{slug}.m4a"
        
        # Download audio
        emit_supabase_event(slug, "ingest", "downloading_audio")
        subprocess.run([
            "yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio",
            "-o", str(audio_path), "--no-playlist", url
        ], check=True)
        
        # Upload audio to GCS
        audio_url = upload_to_gcs(audio_path, f"audio/{slug}.m4a")
        
        # Download captions
        emit_supabase_event(slug, "ingest", "downloading_captions")
        subprocess.run([
            "yt-dlp", "--skip-download", "--write-auto-sub", "--sub-langs", "en",
            "-o", str(temp_dir / slug), "--no-playlist", url
        ], check=False)
        
        # Extract transcript
        vtt_files = list(temp_dir.glob(f"{slug}.*.vtt"))
        transcript = ""
        if vtt_files:
            content = vtt_files[0].read_text(encoding="utf-8")
            content = re.sub(r'WEBVTT.*?\n\n', '', content, flags=re.DOTALL)
            content = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*?\n', '', content)
            content = re.sub(r'<.*?>', '', content)
            transcript = " ".join([line.strip() for line in content.splitlines() if line.strip()])
        
        # Save sutta data to GCS
        sutta_data = {
            "id": slug,
            "title": title,
            "url": url,
            "video_id": video_id,
            "transcript": transcript,
            "audio_url": audio_url,
            "status": "ingested",
            "created_at": datetime.now().isoformat()
        }
        save_json_to_gcs(sutta_data, f"suttas/{slug}.json")
        
        # Update Supabase
        supabase.table("suttas").update({
            "transcript": transcript[:10000],
            "audio_url": audio_url,
            "status": "ingested",
            "updated_at": datetime.now().isoformat()
        }).eq("id", slug).execute()
        
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Emit completion events
        emit_supabase_event(slug, "ingest", "completed")
        publish_event(slug, "ingest", "completed")
        
        print(f"✅ Completed: {slug}")
        return {"success": True, "slug": slug, "audio_url": audio_url}
        
    except Exception as e:
        error_msg = str(e)
        emit_supabase_event(slug or "failed", "ingest", "failed")
        print(f"❌ Failed: {error_msg}")
        
        if slug:
            try:
                supabase.table("suttas").update({
                    "status": "failed",
                    "error": error_msg
                }).eq("id", slug).execute()
            except:
                pass
        
        return {"success": False, "error": error_msg}

# ============================================
# CLI ENTRY POINT
# ============================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--slug", required=False)
    args = parser.parse_args()
    
    result = process_video(args.url, args.slug)
    print(json.dumps(result, indent=2))
