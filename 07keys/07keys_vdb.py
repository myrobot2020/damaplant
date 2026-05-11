# 07keys/07keys_vdb.py - Extract chains, store in VDB
import sys
import json
import re
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils.vdb_pipeline import get_all_suttas, save_to_vdb, stage_exists, get_stage_count

OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

def extract_items(text, expected_count):
    if not text or len(text) < 100:
        return []
    prompt = f"Extract {expected_count} items from this sutta. Return JSON array.\n\n{text[:800]}"
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}, timeout=60)
        result = resp.json().get("response", "")
        match = re.search(r'\[.*\]', result, re.DOTALL)
        if match:
            items = json.loads(match.group())
            return items[:expected_count] if isinstance(items, list) else []
    except:
        pass
    return []

print("=" * 60)
print("07keys - Extract chains (VDB Only)")
print("=" * 60)

if not stage_exists("03segment"):
    print("❌ No data in stage 03segment. Run 03segment first!")
    sys.exit(1)

suttas = get_all_suttas("03segment")
print(f"📖 Processing {len(suttas)} suttas from VDB\n")

for sutta in suttas:
    sutta_id = sutta.get('sutta_id') or sutta.get('id', '')
    sutta_text = sutta.get('sutta', '')
    commentary = sutta.get('commentary', '')
    
    match = re.search(r'AN_(\d+)\.', sutta_id)
    expected = int(match.group(1)) if match else 0
    
    print(f"📖 {sutta_id} (expecting {expected} items)")
    
    items = extract_items(sutta_text, expected)
    source = "sutta"
    
    if len(items) < expected and commentary:
        items = extract_items(commentary, expected)
        source = "commentary"
    
    chain_data = {
        "sutta_id": sutta_id,
        "chain": {"category": "", "items": items, "count": len(items), "is_ordered": True},
        "source": source
    }
    
    save_to_vdb(sutta_id, "07keys", "chain", chain_data)
    print(f"   ✅ {len(items)}/{expected} items -> VDB (stage=07keys)\n")

print(f"🎉 Done! Total chains in VDB: {get_stage_count('07keys')}")
