import json
import re
from pathlib import Path

from PIL import Image, ImageDraw


ROOT_DIR = Path(__file__).resolve().parents[3]

OCR_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "ocr_page1"
PNG_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "png_batches"
MATCHED_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "price_review_matched"
UNMATCHED_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "price_review_unmatched"


PRICE_RE = re.compile(r"^\$?\d[\d,]*\.?\d{0,2}$")


def load_ocr(path):
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    google = data.get("google", {})
    return google.get("bounding_boxes", [])


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


def is_price_like(text):
    cleaned = text.strip().replace(" ", "")
    return bool(PRICE_RE.match(cleaned))


def has_usd_context(text):
    upper = text.upper()
    return "$" in text or "USD" in upper


def normalize_number(text):
    cleaned = text.strip().upper().replace("USD", "").replace("$", "").replace(" ", "")
    cleaned = cleaned.replace(",", "")
    if not cleaned:
        return None
    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return None


def build_candidate(box, idx, page_width, page_height, line_text, normalized_value):
    return {
        "id": idx,
        "text": box["text"],
        "normalized_value": normalized_value,
        "line_text": line_text,
        "x": round(box["left"] * page_width, 2),
        "y": round(box["top"] * page_height, 2),
        "w": round(box["width"] * page_width, 2),
        "h": round(box["height"] * page_height, 2)
    }


def add_candidate(candidates, seen_keys, box, page_width, page_height, line_text, normalized_value):
    key = (
        normalized_value,
        round(box["left"], 6),
        round(box["top"], 6),
        round(box["width"], 6),
        round(box["height"], 6),
    )
    if key in seen_keys:
        return

    seen_keys.add(key)
    candidates.append(
        build_candidate(
            box,
            len(candidates) + 1,
            page_width,
            page_height,
            line_text,
            normalized_value,
        )
    )


def find_candidates(boxes, page_width, page_height):
    candidates = []
    seen_keys = set()
    lines = group_boxes_by_line(boxes)
    seed_values = set()

    for line in lines:
        line_text = " ".join(box.get("text", "") for box in line)
        for idx, box in enumerate(line):
            text = box.get("text", "")
            if not has_usd_context(text):
                continue

            normalized_value = normalize_number(text)
            if normalized_value:
                seed_values.add(normalized_value)
                add_candidate(candidates, seen_keys, box, page_width, page_height, line_text, normalized_value)
                continue

            neighbor_indexes = [idx - 1, idx + 1]
            for neighbor_idx in neighbor_indexes:
                if neighbor_idx < 0 or neighbor_idx >= len(line):
                    continue

                neighbor_box = line[neighbor_idx]
                neighbor_value = normalize_number(neighbor_box.get("text", ""))
                if not neighbor_value:
                    continue

                seed_values.add(neighbor_value)
                add_candidate(
                    candidates,
                    seen_keys,
                    neighbor_box,
                    page_width,
                    page_height,
                    line_text,
                    neighbor_value,
                )

    if not seed_values:
        return candidates

    for line in lines:
        line_text = " ".join(box.get("text", "") for box in line)
        for box in line:
            text = box.get("text", "")
            if has_usd_context(text):
                continue

            normalized_value = normalize_number(text)
            if not normalized_value or normalized_value not in seed_values:
                continue

            add_candidate(
                candidates,
                seen_keys,
                box,
                page_width,
                page_height,
                line_text,
                normalized_value,
            )

    return candidates


def draw_candidates(image_path, candidates, output_path):
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    for candidate in candidates:
        x = int(round(candidate["x"]))
        y = int(round(candidate["y"]))
        w = int(round(candidate["w"]))
        h = int(round(candidate["h"]))
        label_y = max(0, y - 18)

        draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=4)
        draw.text((x, label_y), str(candidate["id"]), fill=(255, 0, 0))

    image.save(output_path)


def main():
    MATCHED_DIR.mkdir(parents=True, exist_ok=True)
    UNMATCHED_DIR.mkdir(parents=True, exist_ok=True)

    ocr_files = sorted(OCR_DIR.glob("*.json"))
    if not ocr_files:
        print(f"No OCR files found in {OCR_DIR}")
        return

    for ocr_path in ocr_files:
        stem = ocr_path.stem
        image_path = PNG_DIR / stem / "page_1.png"

        if not image_path.exists():
            print(f"Skipping {stem}: page_1.png not found")
            continue

        with Image.open(image_path) as image:
            page_width, page_height = image.width, image.height

        boxes = load_ocr(ocr_path)
        candidates = find_candidates(boxes, page_width, page_height)

        output_dir = MATCHED_DIR if candidates else UNMATCHED_DIR
        png_output = output_dir / f"{stem}.png"
        json_output = output_dir / f"{stem}.json"

        draw_candidates(image_path, candidates, png_output)

        payload = {
            "template": stem,
            "page_width": page_width,
            "page_height": page_height,
            "candidates": candidates
        }

        with open(json_output, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

        print(f"Saved: {png_output}")
        print(f"Saved: {json_output}")

    print("Price review batch complete.")


if __name__ == "__main__":
    main()
