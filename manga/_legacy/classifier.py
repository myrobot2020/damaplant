import os
import shutil
from pathlib import Path
import cv2
import numpy as np
import urllib.request

# ================== CONFIG ==================
# Base directory where your panels are currently sitting loose
# The user's screenshot showed them in data/raw/manga/panels/buddha_v01/panels
BASE_DIR = Path("data/raw/manga/panels/buddha_v01/panels")

# Destination folders as shown in your directory tree
TEXT_FOLDER = BASE_DIR / "text panels"
IMAGE_FOLDER = BASE_DIR / "image panels"

MODEL_PATH = "frozen_east_text_detection.pb"
# Raw download link for the model
MODEL_URL = "https://raw.githubusercontent.com/oyyd/frozen_east_text_detection.pb/master/frozen_east_text_detection.pb"

os.makedirs(TEXT_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)

# Auto-download the model if you haven't yet
if not os.path.exists(MODEL_PATH):
    print(f"📥 Downloading EAST model from {MODEL_URL}...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("✅ Download complete.")
    except Exception as e:
        print(f"❌ Failed to download model: {e}")
        exit(1)

# Load model
print("🚀 Loading EAST text detector...")
try:
    net = cv2.dnn.readNet(MODEL_PATH)
except Exception as e:
    print(f"❌ Failed to load model: {e}")
    exit(1)

def has_text(image_path, net, conf_threshold=0.4):
    img = cv2.imread(str(image_path))
    if img is None:
        return False

    orig_h, orig_w = img.shape[:2]

    # EAST requires multiples of 32
    new_w = (orig_w // 32) * 32
    new_h = (orig_h // 32) * 32
    if new_w < 32 or new_h < 32:
        new_w, new_h = 320, 320

    resized = cv2.resize(img, (new_w, new_h))

    blob = cv2.dnn.blobFromImage(resized, 1.0, (new_w, new_h),
                                (123.68, 116.78, 103.94), swapRB=True, crop=False)
    net.setInput(blob)

    # Sigmoid output and geometry output
    layer_names = ["feature_fusion/Conv_7/Sigmoid", "feature_fusion/concat_3"]
    scores, _ = net.forward(layer_names)

    # If any high confidence text region is found
    num_detections = np.sum(scores[0, 0] > conf_threshold)
    return num_detections > 0

# ================== RUN ==================
# Grab all PNGs that are sitting outside the subfolders, limited to 100 for monitoring
files = sorted([f for f in BASE_DIR.glob("*.png") if f.is_file()])[:100]

print(f"📸 Found {len(files)} panels to sort in {BASE_DIR}")

text_count = 0
image_count = 0

for i, file in enumerate(files):
    try:
        is_txt = has_text(file, net)
        status = "TEXT" if is_txt else "IMAGE"
        dest_folder = TEXT_FOLDER if is_txt else IMAGE_FOLDER

        shutil.move(str(file), str(dest_folder / file.name))

        if is_txt: text_count += 1
        else: image_count += 1

        # Print status for monitoring
        icon = "💬" if is_txt else "🎨"
        if i % 10 == 0 or len(files) < 100:
             print(f"[{i+1}/{len(files)}] {file.name} -> {status} {icon}")

    except Exception as e:
        print(f"❌ Error processing {file.name}: {e}")

print("\n=== FINISHED ===")
print(f"Total panels processed: {len(files)}")
print(f"→ Moved to 'text panels':  {text_count}")
print(f"→ Moved to 'image panels': {image_count}")
