# 13dub/13dub.py - Generate Japanese voiceover from translated content
# Uses Kokoro TTS (fast, local, no API key needed)

import sys
import json
import subprocess
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils.vdb_pipeline import get_all_suttas, get_sutta, save_to_vdb

# Try to import TTS libraries
try:
    from kokoro import KPipeline
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    print("⚠️ Kokoro not installed. Run: pip install kokoro soundfile")

# Output directory for audio files
AUDIO_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "dubs"
AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Use local Ollama to call voice models (if Kokoro not available)
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

def dub_text_with_kokoro(text: str, output_path: Path, voice: str = "af_sky") -> bool:
    """Generate Japanese speech using Kokoro TTS"""
    if not KOKORO_AVAILABLE:
        return False
    
    try:
        pipeline = KPipeline(lang_code='j')  # Japanese
        audio_segments = []
        
        for _, _, audio in pipeline(text, voice=voice):
            audio_segments.append(audio)
        
        if audio_segments:
            import numpy as np
            combined = np.concatenate(audio_segments)
            sf.write(str(output_path), combined, 24000)
            return True
    except Exception as e:
        print(f"   Kokoro error: {e}")
    
    return False

def dub_text_with_ollama(text: str, output_path: Path) -> bool:
    """Generate speech using Ollama (if voice model is available)"""
    # This is a placeholder - Ollama doesn't have native TTS
    # You'd need to use a separate TTS API or service
    return False

def generate_dub(sutta_id: str, text: str, content_type: str) -> dict:
    """Generate dubbing for a piece of text"""
    
    if not text or len(text) < 20:
        return {"success": False, "error": "Text too short"}
    
    output_file = AUDIO_OUTPUT_DIR / f"{sutta_id}_{content_type}.wav"
    
    # Try Kokoro first
    success = dub_text_with_kokoro(text, output_file)
    
    if success:
        return {
            "success": True,
            "audio_path": str(output_file),
            "text": text[:200],
            "method": "kokoro"
        }
    else:
        return {
            "success": False,
            "error": "No TTS available",
            "text": text[:200]
        }

def main():
    print("=" * 60)
    print("13dub - Generate Japanese voiceover (Dubbing)")
    print("=" * 60)
    
    # Get Japanese translations from VDB
    if not KOKORO_AVAILABLE:
        print("\n⚠️ Kokoro TTS not installed!")
        print("   Run: pip install kokoro soundfile")
        print("   Or use a different TTS engine.")
        return
    
    translations = get_all_suttas("11translate")
    if not translations:
        print("❌ No Japanese translations found in VDB. Run 11translate first!")
        return
    
    print(f"\n📖 Processing {len(translations)} suttas for dubbing\n")
    
    for trans in translations:
        sutta_id = trans.get('sutta_id', '')
        print(f"📖 {sutta_id}")
        
        # Generate dub for each content piece
        contents = {
            "sutta": trans.get('sutta_jp', ''),
            "vow": trans.get('generated_content_jp', {}).get('vow', ''),
            "caution": trans.get('generated_content_jp', {}).get('caution', ''),
            "practice": trans.get('generated_content_jp', {}).get('practice', '')
        }
        
        dubs = {}
        for content_type, text in contents.items():
            if text:
                print(f"   🎙️ Dubbing {content_type}...")
                result = generate_dub(sutta_id, text, content_type)
                dubs[content_type] = result
                if result.get('success'):
                    print(f"      ✅ Saved: {Path(result['audio_path']).name}")
                else:
                    print(f"      ⚠️ Failed: {result.get('error', 'Unknown')}")
        
        # Save dubbing info to VDB
        dub_data = {
            "sutta_id": sutta_id,
            "dubs": dubs,
            "generated_at": str(Path(AUDIO_OUTPUT_DIR).absolute())
        }
        
        try:
            save_to_vdb(sutta_id, "13dub", "dubbing", dub_data)
            print(f"   💾 Saved to VDB\n")
        except Exception as e:
            print(f"   ⚠️ VDB error: {e}\n")
    
    print(f"🎉 Done! Audio dubs saved to {AUDIO_OUTPUT_DIR}")

if __name__ == "__main__":
    main()
