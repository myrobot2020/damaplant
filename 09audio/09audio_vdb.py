# 09audio/09audio_vdb.py - Add timestamps to commentary (VDB Only)
import sys
import json
import re
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils.vdb_pipeline import get_all_suttas, get_sutta, save_to_vdb, stage_exists, get_stage_count

print("=" * 60)
print("09audio - Timestamp commentary (VDB Only)")
print("=" * 60)

if not stage_exists("08commentary"):
    print("❌ No data in stage 08commentary. Run 08commentary first!")
    sys.exit(1)

commentaries = get_all_suttas("08commentary")
print(f"📖 Processing {len(commentaries)} commentaries from VDB\n")

for comment_data in commentaries:
    sutta_id = comment_data.get('sutta_id', '')
    
    # Get original sutta for full commentary text
    sutta = get_sutta(sutta_id, "03segment")
    if not sutta:
        print(f"⚠️ {sutta_id}: No source sutta")
        continue
    
    full_commentary = sutta.get('commentary', '')
    classified = comment_data.get('classified_segments', {})
    
    print(f"📖 {sutta_id}")
    
    # Add timestamps (estimated based on text position)
    types = ['cautions', 'practices', 'sidenotes', 'interpretations']
    
    for seg_type in types:
        for seg in classified.get(seg_type, []):
            seg_text = seg.get('text', '')
            if not seg_text:
                continue
            
            # Estimate timestamp from text position
            pos = full_commentary.find(seg_text[:50])
            if pos >= 0:
                ratio = pos / max(len(full_commentary), 1)
                total_duration = 3600  # Default 1 hour
                est_sec = int(ratio * total_duration)
                seg['timestamp'] = {
                    'start': str(timedelta(seconds=est_sec)),
                    'end': str(timedelta(seconds=est_sec + 30)),
                    'start_seconds': est_sec,
                    'end_seconds': est_sec + 30,
                    'confidence': 'estimated'
                }
    
    # Save back to VDB with timestamps
    save_to_vdb(sutta_id, "09audio", "audio_timestamps", comment_data)
    print(f"   💾 Saved timestamps to VDB (stage=09audio)\n")

print(f"🎉 Done! Total audio timestamps in VDB: {get_stage_count('09audio')}")
