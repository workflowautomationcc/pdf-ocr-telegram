"""
Test script for Tyger PRICE_1 stroke width.
Generates 6 versions with stroke_width 0-5 so you can pick the best match.
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from processors.templates.price_overlay_processor import fit_font_to_height, format_price

PNG_SRC = ROOT / "template_setup/batch_setup/png_batches/Tyger/page_1.png"
OUTPUT_DIR = ROOT / "template_setup/batch_setup/test_tyger_stroke"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FONT_DIR = ROOT / "data/fonts"

FIELD = {
    "x": 940, "y": 1798, "w": 149, "h": 35,
    "font": {"family": "SegoeUI-Regular", "color": "#000000"},
    "background": {"color": "#FFFFFF"},
    "format": {"currency_symbol": "", "thousands_separator": ",", "decimal_separator": ".", "decimal_places": 2}
}

TEST_PRICE = 1234.56
REFERENCE_TEXT = "0,000.00"
STROKE_WIDTHS = [0, 1, 2, 3, 4, 5]


def get_font_path(family):
    for p in FONT_DIR.iterdir():
        if p.stem == family and p.suffix.lower() in {".ttf", ".otf"}:
            return p
    return None


def main():
    font_path = get_font_path(FIELD["font"]["family"])
    font = fit_font_to_height(FIELD["font"]["family"], FIELD["h"], REFERENCE_TEXT)
    formatted = format_price(TEST_PRICE, FIELD["format"])

    for stroke in STROKE_WIDTHS:
        image = Image.open(PNG_SRC).convert("RGB")
        draw = ImageDraw.Draw(image)

        x = FIELD["x"]
        y = FIELD["y"]
        w = FIELD["w"]
        h = FIELD["h"]

        # whitebox
        draw.rectangle([x - 2, y - 4, x + w + 4, y + h + 7], fill=FIELD["background"]["color"])

        # draw text with stroke
        text_bbox = font.getbbox(formatted)
        left, top = text_bbox[0], text_bbox[1]
        draw.text(
            (x - left, y - top),
            formatted,
            fill=FIELD["font"]["color"],
            font=font,
            stroke_width=stroke,
            stroke_fill=FIELD["font"]["color"]
        )

        # red box for reference
        draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=1)

        out = OUTPUT_DIR / f"stroke_{stroke}.png"
        image.save(out)
        print(f"Saved: {out.name}")

    print(f"\nOutput: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
