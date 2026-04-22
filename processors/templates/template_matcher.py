import json
import os
import re


def compact(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


def process_anchor(anchor, ocr_boxes, page_width, page_height):
    words = [w for w in re.split(r"[^A-Z0-9]+", anchor["name"].upper()) if w]
    if not words:
        return False

    pixel_boxes = []
    for box in ocr_boxes:
        c = compact(box.get("text", ""))
        if not c:
            continue
        pixel_boxes.append({
            "x": box["left"] * page_width,
            "y": box["top"] * page_height,
            "w": box["width"] * page_width,
            "h": box["height"] * page_height,
            "compact": c,
        })

    def words_consumed(box_compact, word_idx):
        accumulated = ""
        last_match = 0
        for i in range(word_idx, len(words)):
            accumulated += words[i]
            if accumulated in box_compact:
                last_match = i - word_idx + 1
        return last_match

    LINE_Y_TOLERANCE = 15       # px: same line
    ADJACENT_Y_TOLERANCE = 60   # px: one line apart
    X_MAX_GAP = 400             # px: max gap between consecutive words on same line

    def find_chains(word_idx, prev_box):
        if word_idx >= len(words):
            return [[]]
        results = []
        for box in pixel_boxes:
            consumed = words_consumed(box["compact"], word_idx)
            if consumed == 0:
                continue
            if prev_box is not None:
                dy = abs(box["y"] - prev_box["y"])
                dx = box["x"] - prev_box["x"]
                if dy <= LINE_Y_TOLERANCE:
                    if dx <= 0 or dx > X_MAX_GAP:
                        continue
                elif dy <= ADJACENT_Y_TOLERANCE:
                    pass  # adjacent line, allow any x
                else:
                    continue
            for sub in find_chains(word_idx + consumed, box):
                results.append([box] + sub)
        return results

    chains = find_chains(0, None)
    if not chains:
        return False

    def combine(boxes):
        min_x = min(b["x"] for b in boxes)
        min_y = min(b["y"] for b in boxes)
        max_x = max(b["x"] + b["w"] for b in boxes)
        max_y = max(b["y"] + b["h"] for b in boxes)
        return {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}

    best_score = None
    best_combined = None

    for chain in chains:
        combined = combine(chain)
        score = (
            abs(combined["x"] - anchor["x"]) +
            abs(combined["y"] - anchor["y"]) +
            abs(combined["w"] - anchor["w"]) +
            abs(combined["h"] - anchor["h"])
        )
        if best_score is None or score < best_score:
            best_score = score
            best_combined = combined

    TOLERANCE = 15

    return (
        abs(best_combined["x"] - anchor["x"]) <= TOLERANCE and
        abs(best_combined["y"] - anchor["y"]) <= TOLERANCE and
        abs(best_combined["w"] - anchor["w"]) <= TOLERANCE and
        abs(best_combined["h"] - anchor["h"]) <= TOLERANCE
    )


def match_template(ocr, template):
    page_width = template["page_width"]
    page_height = template["page_height"]
    ocr_boxes = ocr["google"]["bounding_boxes"]
    anchors = template["anchors"]

    for anchor in anchors:
        if not process_anchor(anchor, ocr_boxes, page_width, page_height):
            return False

    return True


def find_matching_template(ocr, templates_dir):
    for folder in os.listdir(templates_dir):
        template_path = os.path.join(templates_dir, folder, "template.json")

        if not os.path.exists(template_path):
            continue

        try:
            with open(template_path, "r") as f:
                template = json.load(f)
        except:
            continue

        if "page_width" not in template or "anchors" not in template:
            continue

        if match_template(ocr, template):
            return template

    return None
