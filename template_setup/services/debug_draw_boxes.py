import json
from pathlib import Path
from PIL import Image, ImageDraw

# ===== PATHS =====
BASE_DIR = Path(__file__).resolve().parent.parent

TEMPLATE_PATH = BASE_DIR / "workspace/templates/template.json"
IMAGE_PATH = BASE_DIR / "workspace/images/page_1.png"
OUTPUT_DIR = BASE_DIR / "workspace/debug"

# ===== LOAD =====
def load_template():
    with open(TEMPLATE_PATH, "r") as f:
        return json.load(f)

# ===== DRAW BOXES =====
def draw_boxes(template):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    image = Image.open(IMAGE_PATH).convert("RGB")
    draw = ImageDraw.Draw(image)

    fields = template.get("price_fields", [])

    for i, field in enumerate(fields):
        x = int(round(field["x"]))
        y = int(round(field["y"]))
        w = int(round(field["w"]))
        h = int(round(field["h"]))

        # draw rectangle
        draw.rectangle(
            [x, y, x + w, y + h],
            outline=(255, 0, 0),
            width=3
        )

        # label
        draw.text((x, y - 15), f"{i}", fill=(255, 0, 0))

    output_path = OUTPUT_DIR / "debug_boxes.png"
    image.save(output_path)

    print(f"Saved: {output_path}")

# ===== MAIN =====
def main():
    template = load_template()
    draw_boxes(template)

if __name__ == "__main__":
    main()