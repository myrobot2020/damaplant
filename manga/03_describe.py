import base64
import json
sys.path.append(str(Path(__file__).parent.parent))
from _utils.lancedb_helper import LanceDBHelper

db = LanceDBHelper()

import requests
import time
from pathlib import Path
from datetime import datetime, timedelta

# --- Configuration ---
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
VISION_MODEL = "llava"
TEXT_MODEL = "qwen2.5:14b"
FORCE_OVERWRITE = False  # Set to False to skip already finished panels

# Absolute path to your image panels
IMAGE_DIR = Path("C:/Users/ADMIN/Desktop/mob app/data/raw/manga/panels/buddha_v01/panels/image panels")

def encode_image(image_path: Path) -> str:
    """Encodes image to base64 for Ollama API."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def call_ollama(model: str, prompt: str, images: list = None):
    """Generic helper to call Ollama API."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2}
    }
    if images:
        payload["images"] = images

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"   ❌ Error calling Ollama ({model}): {e}")
        return None

def describe_panel_two_pass(image_path: Path):
    """Two-step: 1. Vision Analysis -> 2. Stylistic Rewriting."""
    img_b64 = encode_image(image_path)

    # Step 1: Modern English description (Vision Pass)
    print(f"   👁️  Vision Analysis...")
    vision_prompt = """Describe this manga panel in EXACTLY one or two short sentences of plain, modern English.
    Focus only on the main characters and their immediate action. Do not describe art style or background details."""
    modern_description = call_ollama(VISION_MODEL, vision_prompt, images=[img_b64])

    if not modern_description:
        return None

    # Step 2: Sutta Stylist Pass (Stylistic Pass)
    print(f"   📜 Sutta Stylist...")
    style_prompt = f"""
Rewrite this into a very brief (max 2 sentences) archaic English style of Pali Suttas.
Use phrases like: "thus have I seen", "dwelt", "verily".

Modern Description: {modern_description}

Sutta Style:
"""
    suttic_description = call_ollama(TEXT_MODEL, style_prompt)

    return {
        "modern": modern_description,
        "suttic_english": suttic_description
    }

def main():
    if not IMAGE_DIR.exists():
        print(f"Error: {IMAGE_DIR} not found.")
        return

    # Process all PNG files in the directory
    panels = sorted(list(IMAGE_DIR.glob("*.png")))
    total = len(panels)
    start_time = time.time()
    skip_count = 0

    print(f"🚀 Found {total} panels for Volume 1. Starting Checkpointed Pipeline...")

    for i, img_path in enumerate(panels, 1):
        json_path = img_path.with_suffix(".json")
        percent = (i / total) * 100

        # --- Checkpointing Logic ---
        existing_data = {}
        if json_path.exists():
            try:
                existing_data = json.loads(json_path.read_text(encoding="utf-8"))
            except:
                pass

        if not FORCE_OVERWRITE and existing_data.get("status") == "PROCESSED_SUTTIC":
            skip_count += 1
            # Print a summary every 20 skips to show we are moving
            if skip_count % 20 == 0 or i == total:
                print(f"[{i}/{total}] {percent:4.1f}% | {img_path.name} | (Skipping already processed)")
            continue

        panels_left = total - i
        elapsed = time.time() - start_time

        # Calculate timing based on actual work done in this session
        real_processed = i - skip_count
        avg_time = elapsed / real_processed if real_processed > 0 else 0
        eta = str(timedelta(seconds=int(avg_time * panels_left))) if real_processed > 0 else "Calculating..."

        print(f"[{i}/{total}] {percent:4.1f}% | {img_path.name} | Avg: {avg_time:.1f}s/panel | ETA: {eta}")

        panel_start = time.time()
        results = describe_panel_two_pass(img_path)
        panel_duration = time.time() - panel_start

        if results:
            # Merge with existing data (preserves tags from other scripts)
            existing_data.update({
                "panel_id": img_path.stem,
                "descriptions": results,
                "status": "PROCESSED_SUTTIC",
                "pipeline": {
                    "vision_model": VISION_MODEL,
                    "stylist_model": TEXT_MODEL
                },
                "processed_at": datetime.now().isoformat()
            })

            json_path.write_text(json.dumps(existing_data, indent=2, ensure_ascii=False)
        
        # Upsert to LanceDB
        db.upsert(
            record_id=img_path.stem,
            stage='manga_describe',
            record_type='manga',
            data=results,
            vector_field='suttic_english' if results.get('suttic_english') else 'modern'
        ), encoding="utf-8")
            print(f"   ✅ Updated {json_path.name} ({panel_duration:.1f}s)")

    print(f"\n✨ Volume 1 Processing Complete.")

if __name__ == "__main__":
    main()
