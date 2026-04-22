import json
import os
import re
from itertools import combinations


def process_anchor(anchor, ocr_boxes, page_width, page_height):
    words = [word for word in re.split(r"[^A-Z0-9]+", anchor["name"].upper()) if word]

    matches = []
    for box in ocr_boxes:
        if box["text"].upper() in words:
            matches.append(box)

    lines = []
    for box in matches:
        placed = False
        for line in lines:
            if abs(box["top"] - line[0]["top"]) < 0.005:
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])

    valid_lines = []
    for line in lines:
        texts = [b["text"].upper() for b in line]
        if all(word in texts for word in words):
            valid_lines.append(line)

    if not valid_lines:
        return False

    def to_pixel_box(box):
        return {
            "x": box["left"] * page_width,
            "y": box["top"] * page_height,
            "w": box["width"] * page_width,
            "h": box["height"] * page_height,
        }

    def combine_pixel_boxes(pixel_boxes):
        min_x = min(b["x"] for b in pixel_boxes)
        min_y = min(b["y"] for b in pixel_boxes)
        max_x = max(b["x"] + b["w"] for b in pixel_boxes)
        max_y = max(b["y"] + b["h"] for b in pixel_boxes)
        return {
            "x": min_x,
            "y": min_y,
            "w": max_x - min_x,
            "h": max_y - min_y
        }

    best_combined = None
    best_score = None

    for line in valid_lines:
        if len(line) < len(words):
            continue

        for subset in combinations(line, len(words)):
            texts = [b["text"].upper() for b in subset]
            if sorted(texts) != sorted(words):
                continue

            combined = combine_pixel_boxes([to_pixel_box(b) for b in subset])
            score = (
                abs(combined["x"] - anchor["x"]) +
                abs(combined["y"] - anchor["y"]) +
                abs(combined["w"] - anchor["w"]) +
                abs(combined["h"] - anchor["h"])
            )

            if best_score is None or score < best_score:
                best_score = score
                best_combined = combined

    if best_combined is None:
        for line in valid_lines:
            combined = combine_pixel_boxes([to_pixel_box(b) for b in line])
            score = (
                abs(combined["x"] - anchor["x"]) +
                abs(combined["y"] - anchor["y"]) +
                abs(combined["w"] - anchor["w"]) +
                abs(combined["h"] - anchor["h"])
            )
            if best_score is None or score < best_score:
                best_score = score
                best_combined = combined

    combined = best_combined

    TOLERANCE = 10

    dx = abs(combined["x"] - anchor["x"])
    dy = abs(combined["y"] - anchor["y"])
    dw = abs(combined["w"] - anchor["w"])
    dh = abs(combined["h"] - anchor["h"])

    return dx <= TOLERANCE and dy <= TOLERANCE and dw <= TOLERANCE and dh <= TOLERANCE


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

        # skip invalid templates
        if "page_width" not in template or "anchors" not in template:
            continue

        if match_template(ocr, template):
            return template

    return None
