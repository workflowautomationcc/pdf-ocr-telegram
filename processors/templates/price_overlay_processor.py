import os
import json
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
FONT_DIR = os.path.join(BASE_DIR, "data/fonts")


def font_file_map():
    mapping = {}
    for name in os.listdir(FONT_DIR):
        path = os.path.join(FONT_DIR, name)
        if not os.path.isfile(path):
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() not in {".ttf", ".otf"}:
            continue
        mapping[stem] = path
    return mapping


def load_font(font_family, size_px):
    font_path = font_file_map().get(font_family)
    if not font_path:
        raise FileNotFoundError(f"Font file not found for family: {font_family}")
    return ImageFont.truetype(font_path, int(round(size_px)))


def fit_font_to_height(font_family, target_h, text):
    font_path = font_file_map().get(font_family)
    if not font_path:
        raise FileNotFoundError(f"Font file not found for family: {font_family}")

    sample_text = text or "0"
    target_h = max(1, int(round(target_h)))

    low = 1
    high = max(4, target_h * 4)
    best_font = None

    while low <= high:
        mid = (low + high) // 2
        font = ImageFont.truetype(font_path, mid)
        bbox = font.getbbox(sample_text)
        visible_h = max(1, bbox[3] - bbox[1])

        if visible_h <= target_h:
            best_font = font
            low = mid + 1
        else:
            high = mid - 1

    if best_font is None:
        best_font = ImageFont.truetype(font_path, 1)

    return best_font


def format_price(value, format_config):
    value = float(value)

    decimal_places = format_config.get("decimal_places", 2)
    thousands_sep = format_config.get("thousands_separator", ",")
    decimal_sep = format_config.get("decimal_separator", ".")
    currency = format_config.get("currency_symbol", "")

    formatted = f"{value:,.{decimal_places}f}"

    if thousands_sep != ",":
        formatted = formatted.replace(",", "TMP")
        formatted = formatted.replace(".", decimal_sep)
        formatted = formatted.replace("TMP", thousands_sep)
    else:
        formatted = formatted.replace(".", decimal_sep)

    return f"{currency}{formatted}"


def main(png_job_folder, new_value, template, offset_x=0, offset_y=0, field_offsets=None):
    fields = template["price_fields"]

    img_path = os.path.join(png_job_folder, "page_1.png")
    image = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    for i, field in enumerate(fields):
        fo = (field_offsets or {}).get(i, {})
        x = int(round(field["x"] + fo.get("x", 0)))
        y = int(round(field["y"] + fo.get("y", 0)))
        w = int(round(field["w"]))
        h = int(round(field["h"] + fo.get("h", 0)))

        font_config = field["font"]
        reference_text = field.get("reference_text", "0,000.00")
        font = fit_font_to_height(font_config["family"], h, reference_text)
        font_color = font_config.get("color", "#333333")
        bg_color = field.get("background", {}).get("color", "#FFFFFF")

        # blackout
        blackout_left = x
        blackout_top = y - 2
        blackout_right = x + w + 2
        blackout_bottom = y + h + 5

        draw.rectangle(
            [blackout_left, blackout_top, blackout_right, blackout_bottom],
            fill=bg_color
        )
        """
        # DEBUG RECTANGLE (for alignment)
        draw.rectangle(
            [x, y, x + w, y + h],
            outline=(0, 0, 0),
            width=1
        )
        """

        # offsets
        Y_OFFSET = 0
        X_OFFSET = -2

        # format value using template rules
        format_config = field.get("format", {})
        formatted_value = format_price(new_value, format_config)
        text_bbox = font.getbbox(formatted_value)
        left, top, right, _bottom = text_bbox
        text_w = right - left

        stroke_width = field.get("stroke_width", 0)
        if field.get("right_align"):
            text_x = x + w - text_w
        else:
            text_x = x - left
        draw.text(
            (text_x, y - top),
            formatted_value,
            fill=font_color,
            font=font,
            stroke_width=stroke_width,
            stroke_fill=font_color
        )

    image.save(img_path)
