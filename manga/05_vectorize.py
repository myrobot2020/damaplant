#!/usr/bin/env python3
import json
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from _utils.lancedb_helper import LanceDBHelper

db = LanceDBHelper()

import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# Config
REPO_ROOT = Path(__file__).resolve().parents[1]
# Folder containing the image panel JSONs
PANELS_DIR = REPO_ROOT / "data" / "raw" / "manga" / "panels" / "buddha_v01" / "panels" / "image panels"
OUT_DIR = REPO_ROOT / "data" / "generated" / "embeddings"
MODEL_NAME = 'all-MiniLM-L6-v2'

def vectorize():
    if not PANELS_DIR.exists():
        print(f"❌ Error: Panels directory not found at {PANELS_DIR}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"🚀 Loading local embedding model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)

    descriptions, metadata = [], []
    json_files = sorted(list(PANELS_DIR.glob("*.json")))

    if not json_files:
        print(f"⚠️ No JSON files found in {PANELS_DIR}")
        return

    print(f"📖 Scanning {len(json_files)} panels for descriptions...")
    for p_path in tqdm(json_files):
        try:
            with open(p_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                desc = data.get('descriptions', {}).get('suttic_english') or data.get('descriptions', {}).get('modern')
                if desc:
                    descriptions.append(desc)
                    metadata.append({
                        "id": data.get("panel_id") or p_path.stem,
                        "file": p_path.stem + ".png"
                    })
        except: continue

    if not descriptions:
        print("❌ No descriptions found to vectorize.")
        return

    print(f"🧠 Vectorizing {len(descriptions)} descriptions...")
    embeddings = model.encode(descriptions, convert_to_numpy=True)

    np.save(OUT_DIR / "buddha_v01_vectors.npy", embeddings)
    
    # Upsert vectors to LanceDB
    for i, meta in enumerate(metadata):
        db.upsert(
            record_id=meta['id'],
            stage='manga_vectorize',
            record_type='manga',
            data=meta,
            vector=embeddings[i].tolist() if hasattr(embeddings[i], 'tolist') else embeddings[i]
        )
    with open(OUT_DIR / "buddha_v01_index.json", 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    print(f"\n✅ Created vectors and index in {OUT_DIR}")

if __name__ == "__main__":
    vectorize()
