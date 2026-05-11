# fix_all_imports.py
import os
import sys
from pathlib import Path

TP_DIR = Path(__file__).parent if "__file__" in dir() else Path.cwd()
UTILS_DIR = TP_DIR / "_utils"

print(f"TP_DIR: {TP_DIR}")
print(f"UTILS_DIR exists: {UTILS_DIR.exists()}")

# List all Python files that need fixing
scripts = [
    "01ingest/01ingest.py",
    "02normalise/02normalise.py", 
    "03segment/03segment.py",
    "04names/04names.py",
    "07keys/07keys_vdb.py",
    "08commentary/08commentary_vdb.py",
    "10generate/10generate.py",
    "11translate/11translate.py",
    "12rebuild/12rebuild.py"
]

# The import fix to add at top of each file
IMPORT_FIX = '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

'''

for script in scripts:
    script_path = TP_DIR / script
    if script_path.exists():
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if already has the fix
        if 'sys.path.insert(0, str(Path(__file__).parent.parent))' not in content:
            # Add the fix at the top
            new_content = IMPORT_FIX + content
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✅ Fixed: {script}")
        else:
            print(f"⏭️ Already fixed: {script}")
    else:
        print(f"❌ Not found: {script}")

print("\n🎉 All imports fixed!")
