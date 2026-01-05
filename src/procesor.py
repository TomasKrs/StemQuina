import os
import shutil
import subprocess
import sys
from pathlib import Path

# Set base directory to the script's location for portability
BASE_DIR = Path(__file__).parent

def process_file(mp3_path, db_dir, temp_dir):
    mp3_path = Path(mp3_path)
    name = mp3_path.stem
    final_folder = db_dir / name
    stems_folder = final_folder / "stems"
    stems_folder.mkdir(parents=True, exist_ok=True)

    print(f"\n💎 AI Separation (Demucs): {name}")
    
    # Run Demucs via subprocess
    try:
        subprocess.run([
            sys.executable, "-m", "demucs.separate",
            "--mp3", "--mp3-bitrate", "256",
            "-o", str(temp_dir),
            "-n", "htdemucs",
            str(mp3_path)
        ], check=True)

        results_dir = temp_dir / "htdemucs" / name
        mapping = {"vocals.mp3": "vocals.mp3", "drums.mp3": "drums.mp3", 
                   "bass.mp3": "bass.mp3", "other.mp3": "other.mp3"}

        for old, new in mapping.items():
            source = results_dir / old
            if source.exists():
                shutil.move(str(source), str(stems_folder / new))

        target_original = final_folder / mp3_path.name
        if mp3_path.resolve() != target_original.resolve():
            shutil.copy(str(mp3_path), str(target_original))
        
        print(f"✅ Completed: {name}")
    except Exception as e:
        print(f"❌ Error processing {name}: {e}")

def main():
    db_dir = BASE_DIR / "database"
    temp_dir = BASE_DIR / "demucs_temp"
    db_dir.mkdir(exist_ok=True)

    if len(sys.argv) > 1:
        process_file(sys.argv[1], db_dir, temp_dir)
    else:
        input_dir = BASE_DIR / "mp3"
        input_dir.mkdir(exist_ok=True)
        for mp3_path in input_dir.glob("*.mp3"):
            process_file(mp3_path, db_dir, temp_dir)

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()