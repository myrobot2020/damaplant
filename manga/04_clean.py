import cv2
import pytesseract
import shutil
import time
import json
import sys
import os
from pathlib import Path

# --- TESSERACT PATH AUTO-DETECTION ---
def fix_tesseract():
    # If it's already in PATH, we're good
    try:
        pytesseract.get_tesseract_version()
        return True
    except: pass

    # Common locations to check
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        os.path.join(os.getenv('LOCALAPPDATA', ''), r'Tesseract-OCR\tesseract.exe'),
        r'C:\Users\ADMIN\Miniconda3\Library\bin\tesseract.exe',
        r'C:\Python314\Scripts\tesseract.exe'
    ]

    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return True
    return False

# Configuration
BASE_DIR = Path("data/raw/manga/panels")

def get_text_folder(image_folder):
    return image_folder.parent / "text panels"

def is_texty(image_path):
    img = cv2.imread(str(image_path))
    if img is None: return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    # Using PSM 11 for strict "stray text" detection
    custom_config = r'--oem 3 --psm 11'
    raw_text = pytesseract.image_to_string(thresh, config=custom_config)
    words = [w for w in raw_text.split() if len(w) >= 1]
    return len(words) > 0

def main():
    if not fix_tesseract():
        print("❌ Error: Tesseract engine not found.")
        print("Since it was working earlier, try running this command in your terminal first:")
        print("   set PATH=%PATH%;C:\\Program Files\\Tesseract-OCR")
        return

    image_folders = [p for p in BASE_DIR.rglob("image panels") if p.is_dir()]
    all_tasks = []
    manifests = {}

    for folder in image_folders:
        m_path = folder / "strict_check_manifest.json"
        checked = set()
        if m_path.exists():
            try: checked = set(json.loads(m_path.read_text()))
            except: pass
        manifests[folder] = checked

        images = [img for img in folder.glob("*.png") if img.name not in checked]
        vol = next((part for part in folder.parts if part.startswith("buddha_v")), "Unknown")
        for img in images:
            all_tasks.append({'path': img, 'folder': folder, 'vol': vol})

    total = len(all_tasks)
    if total == 0:
        print("✨ All panels verified!")
        return

    print(f"🚀 Tesseract Second-Pass: {total} panels remaining...")
    start_time = time.time()
    moved_count = 0

    try:
        for i, task in enumerate(all_tasks, 1):
            img_path, folder, vol = task['path'], task['folder'], task['vol']

            if is_texty(img_path):
                text_folder = get_text_folder(folder)
                text_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(img_path), str(text_folder / img_path.name))
                moved_count += 1
            else:
                manifests[folder].add(img_path.name)

            if i % 10 == 0 or i == total:
                # Update progress
                for fld, chk_set in manifests.items():
                    if chk_set: (fld / "strict_check_manifest.json").write_text(json.dumps(list(chk_set)))

                elapsed = time.time() - start_time
                avg = elapsed / i
                eta = avg * (total - i)
                eta_str = time.strftime("%H:%M:%S", time.gmtime(eta))
                sys.stdout.write(f"\r[{vol}] [{(i/total)*100:4.1f}%] [{i}/{total}] | Moved: {moved_count} | ETA: {eta_str}  ")
                sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\n⚠️ Paused.")
    finally:
        print(f"\n✅ Finished. Moved: {moved_count}")

if __name__ == "__main__":
    main()
