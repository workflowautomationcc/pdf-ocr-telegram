import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT_DIR))

load_dotenv()

PNG_BATCHES_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "png_batches"
OCR_OUTPUT_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "ocr_page1"
EDEN_API_URL = "https://api.edenai.run/v2/ocr/ocr"


def iter_batch_folders():
    if not PNG_BATCHES_DIR.exists():
        return []
    return sorted(path for path in PNG_BATCHES_DIR.iterdir() if path.is_dir())


def run_ocr(image_path):
    api_key = os.getenv("EDEN_AI_API_KEY")
    if not api_key:
        raise RuntimeError("EDEN_AI_API_KEY is not set")

    with open(image_path, "rb") as image_file:
        files = {"file": image_file}
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {"providers": "google", "language": "en"}
        response = requests.post(EDEN_API_URL, headers=headers, files=files, data=data, timeout=120)

    response.raise_for_status()
    return response.json()


def main():
    OCR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    batch_folders = iter_batch_folders()
    if not batch_folders:
        print(f"No PNG folders found in {PNG_BATCHES_DIR}")
        return

    for batch_folder in batch_folders:
        page_1_path = batch_folder / "page_1.png"
        output_path = OCR_OUTPUT_DIR / f"{batch_folder.name}.json"

        if not page_1_path.exists():
            print(f"Skipping {batch_folder.name}: page_1.png not found")
            continue

        print(f"OCR: {batch_folder.name}")

        try:
            ocr_result = run_ocr(page_1_path)
        except Exception as exc:
            print(f"Failed: {batch_folder.name} ({exc})")
            continue

        with open(output_path, "w", encoding="utf-8") as output_file:
            json.dump(ocr_result, output_file, indent=2)

        print(f"Saved: {output_path}")

    print("Batch OCR complete.")


if __name__ == "__main__":
    main()
