"""
Bulk overlay test.
For each _003 production template:
  - copies page_1.png from png_batches
  - runs the production price_overlay_processor (same as bot uses)
  - draws red boxes from fine-tuning JSON on top
  - saves result to test_overlay_output/
"""

import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

TEMPLATES_DIR = ROOT / "data" / "templates"
PNG_BATCHES_DIR = ROOT / "template_setup" / "batch_setup" / "png_batches"
FINE_TUNING_DIR = ROOT / "template_setup" / "batch_setup" / "fine_tuning" / "json"
OUTPUT_DIR = ROOT / "template_setup" / "batch_setup" / "test_overlay_output"

TEST_PRICE = 5


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def find_fine_tuning(template_name):
    slug = slugify(re.sub(r"_0+\d+$", "", template_name))
    for path in FINE_TUNING_DIR.glob("*.json"):
        if slugify(path.stem) == slug:
            return load_json(path)
    return None


def find_png(template_name):
    slug = slugify(re.sub(r"_0+\d+$", "", template_name))
    for folder in PNG_BATCHES_DIR.iterdir():
        if slugify(folder.name) == slug:
            p = folder / "page_1.png"
            if p.exists():
                return p
    return None


def draw_red_boxes(image, fine_tuning):
    draw = ImageDraw.Draw(image)
    try:
        label_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 40)
    except Exception:
        label_font = ImageFont.load_default()

    for candidate in fine_tuning.get("candidates", []):
        box = candidate.get("box", {})
        x = int(round(box.get("x", 0)))
        y = int(round(box.get("y", 0)))
        w = int(round(box.get("w", 0)))
        h = int(round(box.get("h", 0)))
        cid = candidate.get("id", "?")
        draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=2)
        draw.text((x, max(0, y - 50)), f"ID {cid}", fill=(255, 0, 0), font=label_font)


def main():
    from processors.templates.price_overlay_processor import main as overlay_main

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    template_folders = sorted(
        f for f in TEMPLATES_DIR.iterdir()
        if f.is_dir() and not f.name.startswith("_")
    )

    ok = []
    skipped = []

    for folder in template_folders:
        t_path = folder / "template.json"
        if not t_path.exists():
            continue

        template = load_json(t_path)
        template_name = folder.name

        png_src = find_png(template_name)
        if not png_src:
            skipped.append(f"{template_name}: no page_1.png found")
            continue

        fine_tuning = find_fine_tuning(template_name)
        if not fine_tuning:
            skipped.append(f"{template_name}: no fine-tuning JSON found")
            continue

        # copy png to output folder as working file
        work_png = OUTPUT_DIR / "page_1.png"
        shutil.copy2(png_src, work_png)

        # run production overlay (modifies work_png in place)
        try:
            overlay_main(str(OUTPUT_DIR), TEST_PRICE, template)
        except Exception as e:
            skipped.append(f"{template_name}: overlay error — {e}")
            continue

        # draw red boxes on top and save as named result
        image = Image.open(work_png).convert("RGB")
        draw_red_boxes(image, fine_tuning)
        out_path = OUTPUT_DIR / f"{template_name}.png"
        image.save(out_path)
        work_png.unlink()  # remove temp page_1.png
        ok.append(template_name)

    print(f"\nDone: {len(ok)} overlays generated, {len(skipped)} skipped")
    if skipped:
        print("\nSkipped:")
        for s in skipped:
            print(f"  {s}")
    print(f"\nOutput: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
