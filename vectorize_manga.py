import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

MANGA_DIR = Path("C:/Users/ADMIN/Desktop/mob app/ai_include/data/manga/panels/buddha_v01")
print(f"📂 Scanning: {MANGA_DIR}")

model = SentenceTransformer('all-MiniLM-L6-v2')

json_files = list(MANGA_DIR.rglob("*.json"))
print(f"Found {len(json_files)} JSON files")

vectorized = 0
for json_file in json_files:
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if already vectorized
        if '_vectors' in data and 'description_vec' in data['_vectors']:
            print(f"⏭️  Skipping {json_file.name} (already vectorized)")
            continue
        
        # Get description text
        desc = None
        if 'descriptions' in data:
            desc = data['descriptions'].get('suttic_english') or data['descriptions'].get('modern')
        elif 'description' in data:
            desc = data['description']
        elif 'sutta' in data:
            desc = data['sutta'][:500]
        
        if desc and len(desc) > 10:
            # Vectorize
            vec = model.encode(desc).tolist()
            
            # Add to data
            if '_vectors' not in data:
                data['_vectors'] = {}
            data['_vectors']['description_vec'] = vec
            
            # Save back
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            vectorized += 1
            print(f"✅ Vectorized: {json_file.name}")
    except Exception as e:
        print(f"❌ Error: {json_file.name} - {e}")

print(f"\n🎉 Done! Vectorized {vectorized} panels")
