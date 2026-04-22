import json
import re
import shutil
from pathlib import Path

from PIL import ImageFont


ROOT_DIR = Path(__file__).resolve().parents[3]
FINE_TUNING_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "fine_tuning" / "json"
DRAFT_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "templates_draft" / "matched"
PRODUCTION_DIR = ROOT_DIR / "data" / "templates"
BACKUP_DIR = ROOT_DIR / "data" / "old_templates"
FONT_DIR = ROOT_DIR / "data" / "fonts"
EXPORT_VERSION = "004"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "template"


def font_file_map():
    return {
        path.stem: path
        for path in FONT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    }


def get_font_path(family: str):
    return font_file_map().get(family)


def fit_size_px(font_family: str, target_h: float, text: str) -> int:
    font_path = get_font_path(font_family)
    if font_path is None:
        return max(1, int(round(target_h)))

    sample_text = text or "0"
    target_h = max(1, int(round(target_h)))

    def bbox_height(size: int):
        font = ImageFont.truetype(str(font_path), size)
        bbox = font.getbbox(sample_text)
        return font, bbox, max(1, bbox[3] - bbox[1])

    low = 1
    high = max(4, target_h * 4)
    best_font = None

    while low <= high:
        mid = (low + high) // 2
        font, _bbox, visible_h = bbox_height(mid)
        if visible_h <= target_h:
            best_font = font
            low = mid + 1
        else:
            high = mid - 1

    if best_font is None:
        best_font, _bbox, _visible_h = bbox_height(1)

    return int(best_font.size)


def build_draft_map():
    mapping = {}
    for path in sorted(DRAFT_DIR.glob("*.json")):
        data = load_json(path)
        template_name = data.get("template")
        if template_name:
            mapping[template_name] = data
    return mapping


def convert_candidate(candidate):
    box = candidate["box"]
    font = candidate["font"]
    text = candidate.get("text", "")
    font_x = round(font.get("x", box["x"]) + font.get("offset_x", 0), 2)
    font_y = round(font.get("y", box["y"]) + font.get("offset_y", 0), 2)
    font_h = round(font.get("h", box["h"]), 2)
    size_px = fit_size_px(font["family"], font_h, text)

    return {
        "name": f"PRICE_{candidate['id']}",
        "x": font_x,
        "y": font_y,
        "w": round(font.get("w", box["w"]), 2),
        "h": font_h,
        "reference_text": candidate.get("text", "0,000.00"),
        "alignment": "right",
        "font": {
            "family": font["family"],
            "size_px": size_px,
            "color": font.get("color", "#333333"),
        },
        "background": {
            "color": "#FFFFFF"
        },
        "format": {
            "currency_symbol": "",
            "thousands_separator": ",",
            "decimal_separator": ".",
            "decimal_places": 2
        }
    }


def archive_existing(folder_path: Path):
    if not folder_path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_target = BACKUP_DIR / folder_path.name
    if backup_target.exists():
        shutil.rmtree(backup_target)
    shutil.move(str(folder_path), str(backup_target))


def main():
    draft_map = build_draft_map()
    fine_tuning_files = sorted(FINE_TUNING_DIR.glob("*.json"))

    if not fine_tuning_files:
        print(f"No fine-tuning JSON files found in {FINE_TUNING_DIR}")
        return

    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    for fine_path in fine_tuning_files:
        fine_data = load_json(fine_path)
        template_name = fine_data.get("template")
        draft_data = draft_map.get(template_name)

        if draft_data is None:
            print(f"Skipped (no draft match): {fine_path.name}")
            continue

        anchors = draft_data.get("anchors", [])
        if not anchors:
            print(f"Skipped (no anchors): {fine_path.name}")
            continue

        candidates = fine_data.get("candidates", [])
        if not candidates:
            print(f"Skipped (no candidates): {fine_path.name}")
            continue

        folder_name = f"{slugify(template_name)}_{EXPORT_VERSION}"
        target_dir = PRODUCTION_DIR / folder_name
        archive_existing(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        production_template = {
            "template": folder_name.upper(),
            "page_width": fine_data["page_width"],
            "page_height": fine_data["page_height"],
            "anchors": [anchors[0]],
            "price_fields": [convert_candidate(candidate) for candidate in candidates],
        }

        save_json(target_dir / "template.json", production_template)
        print(f"Exported: {fine_path.name} -> {target_dir / 'template.json'}")


if __name__ == "__main__":
    main()
