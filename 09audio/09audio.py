# 09audio/09audio.py - CLOUD READY
# Extracts audio clips for each commentary segment with timestamps

import os
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from google.cloud import storage, pubsub_v1
from supabase import create_client, Client

# ============================================
# CONFIGURATION
# ============================================

PROJECT_ID = "dama-492316"
GCS_BUCKET = "dama-pipeline-492316"

# Pub/Sub Topics
TOPIC_AUDIO = f"projects/{PROJECT_ID}/topics/sutta-audio"

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

def download_from_gcs(remote_path: str, local_path: Path):
    """Download file from GCS to local temp"""
    blob = bucket.blob(remote_path)
    blob.download_to_filename(str(local_path))
    print(f"📥 Downloaded from gs://{GCS_BUCKET}/{remote_path}")

def upload_to_gcs(local_path: Path, remote_path: str) -> str:
    blob = bucket.blob(remote_path)
    blob.upload_from_filename(str(local_path))
    print(f"📤 Uploaded to gs://{GCS_BUCKET}/{remote_path}")
    return blob.public_url

def publish_event(sutta_id: str, stage: str, status: str):
    message = json.dumps({
        "sutta_id": sutta_id,
        "stage": stage,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }).encode()
    publisher.publish(TOPIC_AUDIO, message)
    print(f"📤 Published to {TOPIC_AUDIO}: {sutta_id}")

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

def extract_audio_segment(audio_path: Path, start_sec: int, end_sec: int, output_path: Path) -> bool:
    """Extract audio clip using ffmpeg"""
    if not audio_path.exists():
        return False
    try:
        subprocess.run([
            'ffmpeg', '-i', str(audio_path),
            '-ss', str(start_sec), '-to', str(end_sec),
            '-y', '-loglevel', 'quiet',
            str(output_path)
        ], check=True, timeout=60)
        return output_path.exists()
    except Exception as e:
        print(f"   ffmpeg error: {e}")
        return False

def estimate_timestamp(text: str, full_commentary: str, audio_duration: int) -> tuple:
    """Estimate start/end seconds based on text position"""
    if not full_commentary:
        return (0, 30)
    
    pos = full_commentary.find(text[:50])
    if pos < 0:
        return (0, 30)
    
    ratio = pos / max(len(full_commentary), 1)
    start_sec = int(ratio * audio_duration)
    end_sec = min(start_sec + int(len(text) / 2.5), audio_duration)
    return (start_sec, end_sec)

# ============================================
# MAIN PROCESSING
# ============================================

def process_sutta(sutta_id: str):
    """Extract audio clips for each commentary segment"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "audio", "started")
    
    temp_dir = None
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Check if already processed
        if data.get("status") == "audio_processed":
            print(f"   ⏭️ Already processed, skipping")
            return
        
        # Get commentary and classified segments
        commentary = data.get("commentary", data.get("commentary_text", ""))
        classified = data.get("classified_commentary", {})
        
        if not commentary or not classified:
            print("   ⚠️ No commentary or classification found")
            emit_supabase_event(sutta_id, "audio", "failed")
            return
        
        # Get audio file from GCS
        audio_blob = bucket.blob(f"audio/{sutta_id}.m4a")
        if not audio_blob.exists():
            print(f"   ⚠️ Audio file not found in GCS")
            emit_supabase_event(sutta_id, "audio", "failed")
            return
        
        # Create temp directory
        temp_dir = Path("/tmp") / sutta_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio_path = temp_dir / f"{sutta_id}.m4a"
        download_from_gcs(f"audio/{sutta_id}.m4a", audio_path)
        
        # Get audio duration using ffprobe
        audio_duration = 3600  # Default 1 hour
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                audio_duration = int(float(result.stdout.strip()))
        except:
            pass
        
        print(f"   Audio duration: {audio_duration}s")
        
        # Process each classified segment
        categories = ['cautions', 'practices', 'sidenotes', 'interpretations']
        
        for category in categories:
            segments = classified.get(category, [])
            if not segments:
                continue
            
            print(f"   Processing {category}: {len(segments)} segments")
            
            for i, seg in enumerate(segments):
                seg_text = seg.get('full_text', seg.get('text', ''))
                if not seg_text:
                    continue
                
                # Estimate timestamp
                start_sec, end_sec = estimate_timestamp(seg_text, commentary, audio_duration)
                
                # Extract audio clip
                clip_filename = f"{sutta_id}_{category}_{i}.m4a"
                clip_path = temp_dir / clip_filename
                
                if extract_audio_segment(audio_path, start_sec, end_sec, clip_path):
                    # Upload clip to GCS
                    clip_url = upload_to_gcs(clip_path, f"audio_clips/{sutta_id}/{category}_{i}.m4a")
                    
                    # Add timestamp info to segment
                    seg['timestamp'] = {
                        'start_seconds': start_sec,
                        'end_seconds': end_sec,
                        'start_formatted': str(timedelta(seconds=start_sec)),
                        'end_formatted': str(timedelta(seconds=end_sec)),
                        'audio_clip_url': clip_url
                    }
                    print(f"      Clip {i}: {start_sec}s - {end_sec}s")
        
        # Update data
        data["classified_commentary"] = classified
        data["audio_processed_at"] = datetime.now().isoformat()
        data["status"] = "audio_processed"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "audio_clips_processed": True,
            "status": "audio_processed",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "audio", "completed")
        publish_event(sutta_id, "audio", "completed")
        
        print(f"   ✅ Audio clips extracted\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "audio", "failed")
    
    finally:
        # Cleanup temp directory
        if temp_dir and temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    """Process all pending suttas"""
    print("🚀 Starting 09audio pipeline...")
    
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already processed
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "audio_processed":
            print(f"⏭️ Skipping {sutta_id} (already processed)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 09audio complete!")

if __name__ == "__main__":
    main()
