import json
import shutil
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from processors.templates.price_overlay_processor import main as overlay_main

TEMPLATE_PATH = ROOT / "data/templates/a_z_trucking_004/template.json"
PNG_SRC = ROOT / "template_setup/batch_setup/png_batches/A&Z trucking/page_1.png"
FINE_TUNING_PATH = ROOT / "template_setup/batch_setup/fine_tuning/json/A&Z trucking.json"
OUTPUT_DIR = ROOT / "template_setup/batch_setup/test_price_sizes"

PRICES = [5, 50, 500, 5000, 50000]


def load_json(path):
    with open(path) as f:
        return json.load(f)


def draw_red_boxes(image, fine_tuning):
    draw = ImageDraw.Draw(image)
    try:
        label_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 40)
    except Exception:
        label_font = ImageFont.load_default()
    for candidate in fine_tuning.get("candidates", []):
        box = candidate.get("box", {})
        x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
        draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=2)
        draw.text((x, max(0, y - 50)), f"ID {candidate['id']}", fill=(255, 0, 0), font=label_font)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    template = load_json(TEMPLATE_PATH)
    fine_tuning = load_json(FINE_TUNING_PATH)

    work_png = OUTPUT_DIR / "page_1.png"

    for price in PRICES:
        shutil.copy2(PNG_SRC, work_png)
        overlay_main(str(OUTPUT_DIR), price, template)
        image = Image.open(work_png).convert("RGB")
        draw_red_boxes(image, fine_tuning)
        image.save(OUTPUT_DIR / f"price_{price}.png")

    work_png.unlink(missing_ok=True)
    print(f"Done. Check: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
