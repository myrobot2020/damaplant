import json
import re
from pathlib import Path
import requests
from _utils.lancedb_helper import LanceDBHelper

db = LanceDBHelper()


BASE_DIR = Path(__file__).resolve().parent
SEGMENT_DIR = BASE_DIR.parent / "03segment"
OUTPUT_DIR = BASE_DIR

# FASTEST MODEL: llama3.2:3b (2GB, fast responses)
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

print("=" * 60)
print("07keys - Extract chains (FASTEST model)")
print("=" * 60)
print(f"🚀 Using: {OLLAMA_MODEL}")
print(f"📂 Segment dir: {SEGMENT_DIR}")
print()

def extract_items(text: str, expected_count: int, text_type: str) -> list:
    """Fast extraction with small model."""
    
    # Shorter prompt for speed
    prompt = f"Extract {expected_count} items from this {text_type}. Return ONLY JSON array.\n\n{text[:600]}"
    
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
        print(f"   Error: {e}")
    
    return []

def get_book_number(sutta_id: str) -> int:
    match = re.search(r'AN_(\d+)\.', sutta_id)
    return int(match.group(1)) if match else 0

# Process suttas
sutta_dirs = [d for d in SEGMENT_DIR.iterdir() if d.is_dir()]
print(f"📁 Found {len(sutta_dirs)} sutta folders\n")

for sutta_dir in sutta_dirs:
    sutta_json = sutta_dir / "sutta.json"
    if not sutta_json.exists():
        continue
    
    with open(sutta_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    sutta_id = sutta_dir.name
    sutta_text = data.get('sutta', '')
    commentary = data.get('commentary', '')
    
    expected = get_book_number(sutta_id)
    if expected == 0:
        print(f"⚠️ {sutta_id}: Unknown book number")
        continue
    
    print(f"📖 {sutta_id} (expecting {expected} items)")
    
    # Try sutta first
    items = extract_items(sutta_text, expected, "sutta")
    source = "sutta"
    
    # Fallback to commentary if needed
    if len(items) < expected and commentary:
        items = extract_items(commentary, expected, "commentary")
        source = "commentary"
    
    chain = {
        "category": "",
        "items": items,
        "count": len(items),
        "is_ordered": True
    }
    
    output = {
        "sutta_id": sutta_id,
        "chain": chain,
        "source": source
    }
    
    output_file = OUTPUT_DIR / f"{sutta_id}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    if items:
        print(f"   ✅ Found {len(items)}/{expected} items")
        for i, item in enumerate(items[:2], 1):
            preview = item[:50] + "..." if len(item) > 50 else item
            print(f"      {i}. {preview}")
    else:
        print(f"   ⚠️ No items")
    print()

print(f"🎉 Done! Results in {OUTPUT_DIR}")
