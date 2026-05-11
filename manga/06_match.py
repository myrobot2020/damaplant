#!/usr/bin/env python3
import argparse
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

# Config
REPO_ROOT = Path(__file__).resolve().parents[1]
EMBED_DIR = REPO_ROOT / "data" / "generated" / "embeddings"
SEGMENT_DIR = REPO_ROOT / "tp" / "03segment"
MODEL_NAME = 'all-MiniLM-L6-v2'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sutta", default="AN_8.2.11", help="Sutta folder name in tp/03segment")
    parser.add_argument("--top", type=int, default=5, help="Number of top matches")
    args = parser.parse_args()

    # 1. Load Database
    vec_path = EMBED_DIR / "buddha_v01_vectors.npy"
    idx_path = EMBED_DIR / "buddha_v01_index.json"

    if not vec_path.exists() or not idx_path.exists():
        print(f"❌ Error: Embedding files not found. Run scripts2/17_vectorize_panels.py first.")
        return

    vectors = np.load(vec_path)
    with open(idx_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # 2. Load Sutta
    sutta_path = SEGMENT_DIR / args.sutta / "sutta.json"
    if not sutta_path.exists():
        print(f"❌ Error: Sutta file not found at {sutta_path}")
        return

    with open(sutta_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        sutta_text = data.get('sutta', '')

    if not sutta_text:
        print("❌ Error: Sutta text is empty.")
        return

    # 3. Match
    print(f"🚀 Matching {args.sutta} against {len(vectors)} panels...")
    model = SentenceTransformer(MODEL_NAME)

    # Heuristic: split sutta by large sentences to find more granular matches
    sentences = [s.strip() for s in sutta_text.split('.') if len(s.strip()) > 30]

    s_vecs = model.encode(sentences, convert_to_numpy=True)

    # Calculate similarity matrix (sentences x panels)
    sim_matrix = util.cos_sim(s_vecs, vectors).numpy()

    print(f"\n🎯 Top Granular Matches for {args.sutta}:")
    print("-" * 60)

    # Find top matches across all sentences
    # We'll take the best sentence match for each panel to avoid duplicates
    panel_best_scores = np.max(sim_matrix, axis=0)
    panel_best_sent_idx = np.argmax(sim_matrix, axis=0)

    top_panel_indices = np.argsort(-panel_best_scores)[:args.top]

    for idx in top_panel_indices:
        score = panel_best_scores[idx]
        sent = sentences[panel_best_sent_idx[idx]]
        print(f"[{score:.4f}] {meta[idx]['file']}")
        print(f"   Context: \"{sent[:80]}...\"")
        print("-" * 20)

if __name__ == "__main__":
    main()
