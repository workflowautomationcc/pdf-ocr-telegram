import json
from pathlib import Path

from PIL import Image, ImageDraw


ROOT_DIR = Path(__file__).resolve().parents[3]

DRAFTS_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "templates_draft" / "matched"
PNG_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "png_batches"
OUTPUT_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "anchor_previews"


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def find_page_image(template_name):
    direct_path = PNG_DIR / template_name / "page_1.png"
    if direct_path.exists():
        return direct_path

    candidates = list(PNG_DIR.glob("*/page_1.png"))
    for candidate in candidates:
        if candidate.parent.name == template_name:
            return candidate

    return None


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    draft_files = sorted(DRAFTS_DIR.glob("*.json"))
    if not draft_files:
        print(f"No matched draft files found in {DRAFTS_DIR}")
        return

    for draft_path in draft_files:
        draft = load_json(draft_path)
        anchors = draft.get("anchors", [])
        template_name = draft.get("template")

        if not anchors or not template_name:
            print(f"Skipping {draft_path.name}: missing template or anchors")
            continue

        image_path = find_page_image(template_name)
        if not image_path:
            print(f"Skipping {draft_path.name}: page_1.png not found for template '{template_name}'")
            continue

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        for anchor in anchors:
            x = int(round(anchor["x"]))
            y = int(round(anchor["y"]))
            w = int(round(anchor["w"]))
            h = int(round(anchor["h"]))

            draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=4)

        output_path = OUTPUT_DIR / f"{draft_path.stem}.png"
        image.save(output_path)
        print(f"Saved: {output_path}")

    print("Anchor preview batch complete.")


if __name__ == "__main__":
    main()
