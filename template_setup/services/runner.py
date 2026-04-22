import sys
from pathlib import Path

# add project root to path
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR))

import json
import shutil
from pathlib import Path
from datetime import datetime

# ===== IMPORT YOUR EXISTING PROCESSOR =====
from processors.templates.price_overlay_processor import process_images

# ===== PATHS =====
BASE_DIR = Path(__file__).resolve().parent.parent

TEMPLATE_PATH = BASE_DIR / "workspace/templates/template.json"
IMAGE_INPUT_DIR = BASE_DIR / "workspace/images"
IMAGE_OUTPUT_DIR = BASE_DIR / "workspace/output"
IMAGE_OLD_DIR = BASE_DIR / "workspace/output_old"

# ===== PREPARE OUTPUT =====
def prepare_output():
    IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_OLD_DIR.mkdir(parents=True, exist_ok=True)

    # move old outputs
    for f in IMAGE_OUTPUT_DIR.glob("*"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{f.stem}_{timestamp}{f.suffix}"
        shutil.move(str(f), IMAGE_OLD_DIR / new_name)

# ===== LOAD TEMPLATE =====
def load_template():
    with open(TEMPLATE_PATH, "r") as f:
        return json.load(f)

# ===== MODIFY TEMPLATE =====
def modify_template(data):
    # CHANGE THIS KEY IF YOUR STRUCTURE IS DIFFERENT
    if "price_1" in data:
        data["price_1"]["x"] += 50
        data["price_1"]["y"] += 10
    return data

# ===== SAVE TEMP TEMPLATE =====
def save_temp_template(data):
    temp_path = TEMPLATE_PATH.parent / "temp_template.json"
    with open(temp_path, "w") as f:
        json.dump(data, f, indent=2)
    return temp_path

# ===== RUN PIPELINE =====
def run_pipeline(temp_template_path):
    process_images(
        image_dir=str(IMAGE_INPUT_DIR),
        template_path=str(temp_template_path),
        output_dir=str(IMAGE_OUTPUT_DIR)
    )

# ===== MAIN =====
def main():
    print("Running...")

    prepare_output()

    data = load_template()
    data = modify_template(data)

    temp_template_path = save_temp_template(data)

    run_pipeline(temp_template_path)

    print("DONE. Check output folder.")

if __name__ == "__main__":
    main()