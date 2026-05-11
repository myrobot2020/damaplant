import json
import re
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SEGMENT_DIR = BASE_DIR.parent / "03segment"
OUTPUT_DIR = BASE_DIR

OLLAMA_MODEL = "qwen2.5:14b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

def safe_json_parse(text):
    """Strict JSON parsing without regex fallback"""
    try:
        data = json.loads(text)
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data
    except:
        pass
    return []

def extract_items(text, sutta_id, expected, source_type):
    """Strict extractor: NO summarization allowed"""

    if not text or len(text) < 100:
        return []

    # HARD RULE: commentary is not valid extraction source
    if source_type == "commentary":
        return []

    prompt = f"""
You are a STRICT extraction engine.

TASK:
Extract ONLY explicit list items from Buddhist sutta text.

ABSOLUTE RULES:
- Do NOT summarize
- Do NOT explain
- Do NOT infer meaning
- Do NOT rewrite
- ONLY extract items that are explicitly stated as list-like content
- If no explicit list exists, return []

OUTPUT FORMAT:
Return ONLY a JSON array of strings.
No markdown. No text. No commentary.

SUTTA ID: {sutta_id}

TEXT:
{text[:1200]}
"""

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=120
        )

        result = resp.json().get("response", "").strip()
        return safe_json_parse(result)[:expected]

    except Exception as e:
        print(f"   Error: {e}")
        return []

print("=" * 60)
print("07keys - Strict Extraction (No Commentary, No Summarization)")
print("=" * 60)
print()

sutta_dirs = [d for d in SEGMENT_DIR.iterdir() if d.is_dir()]
print(f"📁 Found {len(sutta_dirs)} sutta folders\n")

for sutta_dir in sutta_dirs:
    sutta_json = sutta_dir / "sutta.json"
    if not sutta_json.exists():
        continue
    
    with open(sutta_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    sutta_id = sutta_dir.name
    sutta_text = data.get("sutta", "")
    commentary = data.get("commentary", "")
    
    match = re.search(r'AN_(\d+)\.', sutta_id)
    expected = int(match.group(1)) if match else 0
    
    print(f"📖 {sutta_id} (expecting {expected} items)")
    
    # Strict extraction from sutta only
    items = extract_items(sutta_text, sutta_id, expected, "sutta")
    source = "sutta"
    
    # Commentary is ignored for chain extraction
    if commentary:
        print(f"   📝 Commentary exists ({len(commentary)} chars) - IGNORED for extraction")
    
    print(f"   Source: {source}")
    print(f"   Found: {len(items)}/{expected} items")
    
    if items:
        for i, item in enumerate(items[:3], 1):
            preview = item[:80] + "..." if len(item) > 80 else item
            print(f"      {i}. {preview}")
    else:
        print(f"   ⚠️ No items extracted - sutta may not have explicit list")
    
    output = {
        "sutta_id": sutta_id,
        "extraction_source": source,
        "chain": {
            "category": "",
            "items": items,
            "count": len(items),
            "is_ordered": True
        }
    }
    
    output_file = OUTPUT_DIR / f"{sutta_id}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print()

print(f"🎉 Done! Results saved in {OUTPUT_DIR}")
