import cv2
import pytesseract
import json
import time
import shutil
from pathlib import Path

# Configuration
BASE_INPUT_DIR = Path("data/raw/manga/panels/buddha_v01/buddha_v01")
BASE_OUTPUT_DIR = Path("data/raw/manga/segmented/buddha_v01")
MANIFEST_PATH = BASE_OUTPUT_DIR / "manifest.json"

# Threshold for text detection (adjust if needed)
TEXT_THRESHOLD = 2

# Ensure output directories exist
TEXT_DIR = BASE_OUTPUT_DIR / "text"
NO_TEXT_DIR = BASE_OUTPUT_DIR / "no_text"
TEXT_DIR.mkdir(parents=True, exist_ok=True)
NO_TEXT_DIR.mkdir(parents=True, exist_ok=True)

def is_text_panel(image_path):
    """
    OCR-based text detection logic
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return False, 0, ""

    # Preprocessing for better OCR
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    # Run OCR
    custom_config = r'--oem 3 --psm 6'
    raw_text = pytesseract.image_to_string(thresh, config=custom_config)

    # Filter meaningful words (more than 1 character, ignoring garbage)
    words = [word for word in raw_text.split() if len(word) > 1]
    score = len(words)

    return score >= TEXT_THRESHOLD, score, raw_text.strip()

def main():
    print(f"🔍 Starting Tesseract-OCR Segmentation...")

    manifest = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except: pass

    all_panels = sorted(list(BASE_INPUT_DIR.glob("*.png")))
    to_process = [p for p in all_panels if p.name not in manifest]

    print(f"📸 Volume 1: {len(all_panels)} total. Processing {len(to_process)} panels.")
    start_time = time.time()

    try:
        for i, panel_path in enumerate(to_process, 1):
            elapsed = time.time() - start_time
            avg = elapsed / i if i > 0 else 0
            eta = avg * (len(to_process) - i)

            has_text, word_count, snippet = is_text_panel(panel_path)
            category = "text" if has_text else "no_text"

            # Monitoring log
            icon = "📝" if has_text else "🖼️"
            clean_snippet = snippet.replace('\n', ' ')[:30]
            print(f"[{i}/{len(to_process)}] {panel_path.name} | Words: {word_count} | {category.upper()} {icon} | [{clean_snippet}...]")

            # Copy to folders
            dest = (TEXT_DIR if has_text else NO_TEXT_DIR) / panel_path.name
            shutil.copy(panel_path, dest)

            manifest[panel_path.name] = {
                "category": category,
                "word_count": word_count,
                "text_sample": clean_snippet
            }

            if i % 20 == 0:
                MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        t_count = sum(1 for v in manifest.values() if v['category'] == 'text')
        nt_count = sum(1 for v in manifest.values() if v['category'] == 'no_text')
        print(f"\n✅ Done! \n📝 TEXT: {t_count} \n🖼️ NO_TEXT: {nt_count}")

if __name__ == "__main__":
    main()
