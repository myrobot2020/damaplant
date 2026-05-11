# 06images/06images_vdb.py - Match suttas to manga panels (VDB Only)
import sys
import json
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils.vdb_pipeline import get_all_suttas, save_to_vdb, stage_exists, get_stage_count
from sentence_transformers import SentenceTransformer, util

print("=" * 60)
print("06images - Match suttas to manga panels (VDB Only)")
print("=" * 60)

if not stage_exists("04names"):
    print("❌ No data in stage 04names. Run 04names first!")
    sys.exit(1)

model = SentenceTransformer('all-MiniLM-L6-v2')

# Load manga panels from VDB (stage=manga_describe)
print("📖 Loading manga panels from VDB...")
manga_results = get_all_suttas("manga_describe")  # Use existing VDB reader
print(f"   Found {len(manga_results)} manga panels\n")

# Prepare manga vectors
manga_vectors = []
manga_ids = []
manga_descs = []

for m in manga_results:
    desc = m.get('descriptions', {}).get('suttic_english') or m.get('modern', '')
    if desc:
        manga_vectors.append(model.encode(desc))
        manga_ids.append(m.get('panel_id', ''))
        manga_descs.append(desc[:200])

if manga_vectors:
    manga_vectors = np.array(manga_vectors)

# Match suttas
suttas = get_all_suttas("04names")
print(f"📖 Matching {len(suttas)} suttas from VDB\n")

for sutta in suttas:
    sutta_id = sutta.get('sutta_id') or sutta.get('id', '')
    sutta_text = sutta.get('sutta', '')[:2000]
    
    if not sutta_text or not manga_vectors:
        continue
    
    sutta_vec = model.encode(sutta_text)
    similarities = util.cos_sim(sutta_vec, manga_vectors)[0]
    top10_idx = np.argsort(-similarities)[:10]
    
    matches = []
    for idx in top10_idx:
        matches.append({
            "rank": len(matches) + 1,
            "score": float(similarities[idx]),
            "panel_id": manga_ids[idx],
            "description": manga_descs[idx]
        })
    
    match_data = {
        "sutta_id": sutta_id,
        "matches": matches
    }
    
    save_to_vdb(sutta_id, "06images", "manga_match", match_data)
    print(f"✅ {sutta_id}: {len(matches)} matches -> VDB")

print(f"\n🎉 Done! Total matches in VDB: {get_stage_count('06images')}")
