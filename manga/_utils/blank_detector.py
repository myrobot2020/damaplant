import cv2
import os
from pathlib import Path
from tqdm import tqdm
import shutil

BASE_DIR = Path("data/raw/manga/panels")
PRUNED_DIR = Path("data/raw/manga/panels_pruned")

def is_mostly_blank(image_path, threshold=0.98):
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None: return False

    # Calculate percentage of white/black pixels
    # Manga often has white or black backgrounds
    _, thresh_white = cv2.threshold(img, 240, 255, cv2.THRESH_BINARY)
    white_ratio = cv2.countNonZero(thresh_white) / (img.shape[0] * img.shape[1])

    if white_ratio > threshold:
        return True, f"White ({white_ratio:.2%})"

    _, thresh_black = cv2.threshold(img, 15, 255, cv2.THRESH_BINARY_INV)
    black_ratio = cv2.countNonZero(thresh_black) / (img.shape[0] * img.shape[1])

    if black_ratio > threshold:
        return True, f"Black ({black_ratio:.2%})"

    return False, ""

def main():
    all_images = list(BASE_DIR.rglob("*.png"))
    print(f"Checking {len(all_images)} panels for blanks...")

    blanks = 0
    for img_path in tqdm(all_images):
        blank, reason = is_mostly_blank(img_path)
        if blank:
            # Construct destination path
            rel_path = img_path.relative_to(BASE_DIR)
            dest_path = PRUNED_DIR / "blanks" / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(img_path), str(dest_path))
            blanks += 1

    print(f"Done! Moved {blanks} blank panels to {PRUNED_DIR / 'blanks'}")

if __name__ == "__main__":
    main()
