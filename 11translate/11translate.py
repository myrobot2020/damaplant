# 11translate/11translate.py - CLOUD READY
# Translates all sutta content to Japanese

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
TOPIC_TRANSLATED = f"projects/{PROJECT_ID}/topics/sutta-translated"

# Ollama (GPU in cloud - use best model for Japanese)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = "qwen2.5:14b"  # Best for Japanese

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
    publisher.publish(TOPIC_TRANSLATED, message)
    print(f"📤 Published to {TOPIC_TRANSLATED}: {sutta_id}")

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

def translate_text(text: str, text_type: str, max_length: int = 1500) -> str:
    """Translate English text to Japanese using Ollama"""
    if not text or len(text) < 20:
        return ""
    
    prompt = f"""Translate this Buddhist {text_type} from English to Japanese.
Return ONLY the Japanese translation, no explanations.

English: {text[:max_length]}

Japanese translation:"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=120)
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"   Translation error: {e}")
        return text

def translate_mcq(mcq: dict) -> dict:
    """Translate MCQ question, options, and explanation"""
    if not mcq:
        return mcq
    
    translated = {}
    
    if "question" in mcq:
        translated["question"] = translate_text(mcq["question"], "MCQ question", 500)
    
    if "options" in mcq and isinstance(mcq["options"], list):
        translated["options"] = []
        for opt in mcq["options"]:
            translated["options"].append(translate_text(opt, "MCQ option", 200))
    
    if "explanation" in mcq:
        translated["explanation"] = translate_text(mcq["explanation"], "MCQ explanation", 500)
    
    if "correct" in mcq:
        translated["correct"] = mcq["correct"]
    
    return translated

# ============================================
# MAIN PROCESSING
# ============================================

def process_sutta(sutta_id: str):
    """Translate all content for a sutta to Japanese"""
    print(f"📖 Processing: {sutta_id}")
    emit_supabase_event(sutta_id, "translate", "started")
    
    try:
        # Read from GCS
        gcs_path = f"suttas/{sutta_id}.json"
        data = read_json_from_gcs(gcs_path)
        
        # Check if already translated
        if data.get("status") == "translated":
            print(f"   ⏭️ Already translated, skipping")
            return
        
        # Get content to translate
        sutta_text = data.get("sutta", data.get("normalised_text", ""))
        commentary = data.get("commentary", data.get("commentary_text", ""))
        chain = data.get("chain", {})
        generated = data.get("generated_content", {})
        
        print(f"   Translating sutta text...")
        sutta_jp = translate_text(sutta_text, "sutta", 1500)
        
        print(f"   Translating commentary...")
        commentary_jp = translate_text(commentary, "commentary", 1500)
        
        print(f"   Translating chain items...")
        chain_items = chain.get("items", [])
        chain_jp = []
        for item in chain_items:
            chain_jp.append(translate_text(item, "chain item", 200))
        
        print(f"   Translating generated content...")
        generated_jp = {
            "mcq_quiz": translate_mcq(generated.get("mcq_quiz", {})),
            "vow": translate_text(generated.get("vow", ""), "vow", 300),
            "caution": translate_text(generated.get("caution", ""), "caution", 300),
            "practice": translate_text(generated.get("practice", ""), "practice", 300)
        }
        
        # Update data with Japanese translations
        data["japanese"] = {
            "sutta": sutta_jp,
            "commentary": commentary_jp,
            "chain_items": chain_jp,
            "generated_content": generated_jp,
            "translated_at": datetime.now().isoformat()
        }
        data["status"] = "translated"
        
        # Save back to GCS
        save_json_to_gcs(data, gcs_path)
        
        # Update Supabase
        supabase.table("suttas").update({
            "sutta_jp": sutta_jp[:10000],
            "commentary_jp": commentary_jp[:10000],
            "chain_jp": chain_jp,
            "generated_jp": json.dumps(generated_jp),
            "status": "translated",
            "updated_at": datetime.now().isoformat()
        }).eq("id", sutta_id).execute()
        
        # Emit completion events
        emit_supabase_event(sutta_id, "translate", "completed")
        publish_event(sutta_id, "translate", "completed")
        
        print(f"   ✅ Japanese translation complete\n")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        emit_supabase_event(sutta_id, "translate", "failed")

def main():
    """Process all pending suttas"""
    print("🚀 Starting 11translate pipeline...")
    print(f"⚡ Using Ollama: {OLLAMA_MODEL}")
    
    blobs = bucket.list_blobs(prefix="suttas/")
    sutta_files = [b.name for b in blobs if b.name.endswith(".json")]
    
    print(f"📁 Found {len(sutta_files)} suttas in GCS\n")
    
    for sutta_file in sutta_files:
        sutta_id = sutta_file.replace("suttas/", "").replace(".json", "")
        
        # Check if already translated
        data = read_json_from_gcs(sutta_file)
        if data.get("status") == "translated":
            print(f"⏭️ Skipping {sutta_id} (already translated)")
            continue
        
        process_sutta(sutta_id)
    
    print("🎉 11translate complete!")

if __name__ == "__main__":
    main()
