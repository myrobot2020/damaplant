import json
import numpy as np
import torch
from pathlib import Path
from sentence_transformers import SentenceTransformer, util
from _utils.lancedb_helper import LanceDBHelper

db = LanceDBHelper()

TP_DIR = Path("C:/Users/ADMIN/Desktop/mob app/ai_include")
SUTTA_DIR = TP_DIR / "tp" / "04names"
MANGA_BASE_DIR = TP_DIR / "data" / "manga" / "panels" / "buddha_v01"
MANGA_IMAGE_DIR = MANGA_BASE_DIR
MANGA_JSON_DIR = MANGA_BASE_DIR
OUTPUT_DIR = Path(__file__).parent

print("🚀 Loading embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')

print("📖 Loading manga panels...")
panel_vectors = []
panel_metadata = []

json_files = list(MANGA_JSON_DIR.glob("*.json"))
print(f"Found {len(json_files)} JSON files")

for json_file in json_files:
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        desc = None
        if 'descriptions' in data:
            desc = data['descriptions'].get('suttic_english') or data['descriptions'].get('modern')
        elif 'description' in data:
            desc = data['description']
        if desc and len(desc) > 10:
            if '_vectors' in data and 'description_vec' in data['_vectors']:
                vec = data['_vectors']['description_vec']
                if isinstance(vec, list):
                    vec = np.array(vec, dtype=np.float32)
            else:
                vec = model.encode(desc).astype(np.float32)
            image_path = MANGA_IMAGE_DIR / f"{json_file.stem}.png"
            panel_vectors.append(vec)
            panel_metadata.append({
                'panel_id': json_file.stem,
                'description': desc[:300],
                'image_path': str(image_path) if image_path.exists() else "NOT_FOUND"
            })
    except Exception as e:
        continue

panel_vectors = np.array(panel_vectors, dtype=np.float32)
print(f"✅ Loaded {len(panel_vectors)} manga panels")

print("\n🎯 Matching suttas to manga panels...")
sutta_files = list(SUTTA_DIR.glob("AN_*.json"))

for sutta_file in sutta_files:
    with open(sutta_file, 'r', encoding='utf-8') as f:
        sutta = json.load(f)
    sutta_id = sutta_file.stem
    sutta_text = sutta.get('sutta', '')[:2000]
    if not sutta_text:
        continue
    sutta_vec = model.encode(sutta_text).astype(np.float32)
    sutta_tensor = torch.from_numpy(sutta_vec).float()
    panels_tensor = torch.from_numpy(panel_vectors).float()
    similarities = util.cos_sim(sutta_tensor, panels_tensor)[0]
    if torch.is_tensor(similarities):
        similarities = similarities.cpu().numpy()
    top10_idx = np.argsort(-similarities)[:10]
    results = []
    for rank, idx in enumerate(top10_idx, 1):
        results.append({
            "rank": rank,
            "score": float(similarities[idx]),
            "panel_id": panel_metadata[idx]['panel_id'],
            "description": panel_metadata[idx]['description'],
            "image_path": panel_metadata[idx]['image_path']
        })
    
    output_data = {
        "sutta_info": {
            "id": sutta_id,
            "name": sutta.get('sutta_name', 'Unknown'),
            "sc_link": sutta.get('sc_link', '')
        },
        "top_10_matches": results
    }
    
    output_file = OUTPUT_DIR / f"{sutta_id}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # WRITE TO VDB
    try:
        db.upsert(
            record_id=sutta_id,
            stage="06images",
            record_type="manga_match",
            data=output_data,
            vector_field=None
        )
        print(f"✅ {sutta_id}: {len(results)} matches -> VDB")
    except Exception as e:
        print(f"⚠️ VDB error for {sutta_id}: {e}")

print("🎉 Done!")
