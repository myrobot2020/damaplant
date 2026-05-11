import subprocess
from pathlib import Path

pdfs = sorted(Path("images").glob("buddha_v*.pdf"))
output_root = Path("data/raw/manga/panels")
output_root.mkdir(parents=True, exist_ok=True)

print(f"🚀 Cave man starting bulk depanel of {len(pdfs)} volumes grunt.")

for i, pdf in enumerate(pdfs, 1):
    volume_name = pdf.stem
    print(f"\n📖 Processing {volume_name} ({i}/{len(pdfs)})")

    # Optimized for mobile: 300 DPI for sharpness, 200x200 min size for better coverage
    # --resume ensures we don't restart work already done
    cmd = [
        "python", "scripts/extract_pdf_images.py",
        "--mode", "panels",
        "--resume",
        "--input-dir", "images",
        "--pattern", pdf.name,
        "--output-dir", str(output_root / volume_name),
        "--dpi", "300",
        "--panel-min-width", "200",
        "--panel-min-height", "200",
        "--no-dedupe"
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"\n✅ Finished {volume_name} grunt.")
    except Exception as e:
        print(f"\n❌ Fail on {volume_name}: {e} grunt.")

print("\n🦴 Bulk depanel complete. All bones extracted!")

print("Bulk depanel complete. All bones extracted!")
