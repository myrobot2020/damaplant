# 08commentary/08commentary_vdb.py - Classify commentary, store in VDB
import sys
import json
import re
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils.vdb_pipeline import get_all_suttas, save_to_vdb, stage_exists, get_stage_count

OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

def classify_segment(text):
    if len(text) < 30:
        return "other"
    prompt = f"Classify: caution/practice/sidenote/interpretation. Return only one word.\n\n{text[:300]}"
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}, timeout=30)
        result = resp.json().get("response", "").strip().lower()
        for cat in ["caution", "practice", "sidenote", "interpretation"]:
            if cat in result:
                return cat
    except:
        pass
    return "other"

def split_commentary(commentary):
    markers = [r'[Ii]\s+just\s+stopped', r'[Ii]\'?ll\s+just\s+stop', r'[Ii]\'?d\s+just\s+like\s+to\s+commend', r'[Ff]irstly\s+you\s+notice']
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

print("=" * 60)
print("08commentary - Classify commentary (VDB Only)")
print("=" * 60)

if not stage_exists("03segment"):
    print("❌ No data in stage 03segment. Run 03segment first!")
    sys.exit(1)

suttas = get_all_suttas("03segment")
print(f"📖 Processing {len(suttas)} suttas from VDB\n")

for sutta in suttas:
    sutta_id = sutta.get('sutta_id') or sutta.get('id', '')
    commentary = sutta.get('commentary', '')
    
    if not commentary:
        print(f"⚠️ {sutta_id}: No commentary")
        continue
    
    print(f"📖 {sutta_id}")
    
    segments = split_commentary(commentary)
    classified = {"cautions": [], "practices": [], "sidenotes": [], "interpretations": [], "other": []}
    
    for seg in segments:
        if len(seg) < 30:
            continue
        cat = classify_segment(seg)
        classified[cat].append({"text": seg[:300], "full_text": seg})
        print(f"   → {cat}: {seg[:50]}...")
    
    comment_data = {
        "sutta_id": sutta_id,
        "classified_segments": classified,
        "total_segments": len(segments)
    }
    
    save_to_vdb(sutta_id, "08commentary", "commentary", comment_data)
    print(f"   💾 Saved to VDB (stage=08commentary)\n")

print(f"🎉 Done! Total commentaries in VDB: {get_stage_count('08commentary')}")
