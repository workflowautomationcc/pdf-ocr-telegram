import argparse
import json
import re
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[3]

OCR_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "ocr_page1"
ANCHORS_PATH = ROOT_DIR / "template_setup" / "batch_setup" / "anchor_keywords.json"
PNG_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "png_batches"
MATCHED_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "templates_draft" / "matched"
UNMATCHED_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "templates_draft" / "unmatched"


def normalize_text(value):
    return " ".join(str(value).upper().split())


def compact_text(value):
    return re.sub(r"[^A-Z0-9]", "", normalize_text(value))


def load_anchor_entries():
    with open(ANCHORS_PATH, "r", encoding="utf-8") as anchor_file:
        data = json.load(anchor_file)
    return data.get("anchors", [])


def load_ocr_payload(ocr_path):
    with open(ocr_path, "r", encoding="utf-8") as ocr_file:
        data = json.load(ocr_file)
    google_data = data.get("google", {})
    return google_data.get("text", ""), google_data.get("bounding_boxes", [])


def load_page_size(template_name):
    image_path = PNG_DIR / template_name / "page_1.png"
    if not image_path.exists():
        return 2550, None

    with Image.open(image_path) as image:
        return image.width, image.height


def group_boxes_by_line(boxes, tolerance=0.01):
    lines = []

    for box in boxes:
        placed = False
        for line in lines:
            if abs(box["top"] - line[0]["top"]) <= tolerance:
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])

    for line in lines:
        line.sort(key=lambda item: item["left"])

    return lines


def find_anchor_boxes(anchor, boxes):
    target = compact_text(anchor)
    if not target:
        return None

    lines = group_boxes_by_line(boxes)

    for line in lines:
        for start_index in range(len(line)):
            combined = ""
            matched_boxes = []

            for end_index in range(start_index, len(line)):
                box = line[end_index]
                box_text = compact_text(box.get("text", ""))
                if not box_text:
                    continue

                combined += box_text
                matched_boxes.append(box)

                if combined == target or target in combined:
                    return matched_boxes

                if not target.startswith(combined) and target not in combined:
                    break

        for box in line:
            box_text = compact_text(box.get("text", ""))
            if box_text and target in box_text:
                return [box]

    return None


def combine_boxes(boxes, page_width, page_height):
    left = min(box["left"] for box in boxes) * page_width
    top = min(box["top"] for box in boxes) * page_height
    right = max((box["left"] + box["width"]) for box in boxes) * page_width
    bottom = max((box["top"] + box["height"]) for box in boxes) * page_height

    return {
        "x": round(left, 2),
        "y": round(top, 2),
        "w": round(right - left, 2),
        "h": round(bottom - top, 2)
    }


def find_anchor_match(ocr_text, boxes, anchor_entries):
    normalized_ocr = normalize_text(ocr_text)

    for entry in anchor_entries:
        anchor = entry.get("anchor", "").strip()
        if not anchor:
            continue

        if normalize_text(anchor) in normalized_ocr:
            anchor_boxes = find_anchor_boxes(anchor, boxes)
            if anchor_boxes:
                return entry, anchor_boxes

    return None, None


def build_draft(template_name, page_width, page_height, match_entry, anchor_boxes):
    draft = {
        "template": template_name,
        "page_width": page_width,
        "page_height": page_height,
        "anchors": [],
        "price_fields": []
    }

    if match_entry and anchor_boxes and page_height:
        draft["anchors"].append({
            "name": match_entry["anchor"],
            **combine_boxes(anchor_boxes, page_width, page_height)
        })
        draft["anchor_match"] = {
            "status": "matched",
            "anchor": match_entry["anchor"]
        }
        if "notes" in match_entry:
            draft["anchor_match"]["notes"] = match_entry["notes"]
    else:
        draft["anchor_match"] = {
            "status": "not_found",
            "anchor": None
        }

    return draft


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unmatched-only", action="store_true")
    return parser.parse_args()


def get_ocr_files(unmatched_only):
    if not unmatched_only:
        return sorted(OCR_DIR.glob("*.json"))

    target_names = {path.stem for path in UNMATCHED_DIR.glob("*.json")}
    return sorted(path for path in OCR_DIR.glob("*.json") if path.stem in target_names)


def main():
    args = parse_args()

    MATCHED_DIR.mkdir(parents=True, exist_ok=True)
    UNMATCHED_DIR.mkdir(parents=True, exist_ok=True)

    anchor_entries = load_anchor_entries()
    ocr_files = get_ocr_files(args.unmatched_only)

    if not ocr_files:
        print(f"No OCR files found in {OCR_DIR}")
        return

    for ocr_path in ocr_files:
        template_name = ocr_path.stem
        page_width, page_height = load_page_size(template_name)
        ocr_text, boxes = load_ocr_payload(ocr_path)
        match_entry, anchor_boxes = find_anchor_match(ocr_text, boxes, anchor_entries)
        draft = build_draft(template_name, page_width, page_height, match_entry, anchor_boxes)

        output_dir = MATCHED_DIR if match_entry else UNMATCHED_DIR
        output_path = output_dir / f"{template_name}.json"
        stale_path = (UNMATCHED_DIR if match_entry else MATCHED_DIR) / f"{template_name}.json"

        if stale_path.exists():
            stale_path.unlink()

        with open(output_path, "w", encoding="utf-8") as output_file:
            json.dump(draft, output_file, indent=2)

        print(f"Saved: {output_path}")

    print("Draft build complete.")


if __name__ == "__main__":
    main()
