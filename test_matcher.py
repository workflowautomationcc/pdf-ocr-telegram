"""
Diagnostic matcher: runs all production templates against ocr_page1 files.
For each template, finds the best-matching OCR file by name, runs the anchor
matching logic, and reports pass/fail. For failures, shows stored anchor box
vs best candidate box found so you can see how far off it is.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

TEMPLATES_DIR = ROOT / "data" / "templates"
OCR_DIR = ROOT / "template_setup" / "batch_setup" / "ocr_page1"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compact(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


def words_consumed(words, box_compact, word_idx):
    accumulated = ""
    last_match = 0
    for i in range(word_idx, len(words)):
        accumulated += words[i]
        if accumulated in box_compact:
            last_match = i - word_idx + 1
    return last_match


def find_chains(words, pixel_boxes, word_idx, prev_box,
                LINE_Y=15, ADJ_Y=60, X_GAP=400):
    if word_idx >= len(words):
        return [[]]
    results = []
    for box in pixel_boxes:
        consumed = words_consumed(words, box["compact"], word_idx)
        if consumed == 0:
            continue
        if prev_box is not None:
            dy = abs(box["y"] - prev_box["y"])
            dx = box["x"] - prev_box["x"]
            if dy <= LINE_Y:
                if dx <= 0 or dx > X_GAP:
                    continue
            elif dy <= ADJ_Y:
                pass
            else:
                continue
        for sub in find_chains(words, pixel_boxes, word_idx + consumed, box):
            results.append([box] + sub)
    return results


def combine(boxes):
    min_x = min(b["x"] for b in boxes)
    min_y = min(b["y"] for b in boxes)
    max_x = max(b["x"] + b["w"] for b in boxes)
    max_y = max(b["y"] + b["h"] for b in boxes)
    return {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}


def diagnose_anchor(anchor, ocr_boxes, page_width, page_height, tolerance=15):
    words = [w for w in re.split(r"[^A-Z0-9]+", anchor["name"].upper()) if w]
    if not words:
        return False, None, None

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

    chains = find_chains(words, pixel_boxes, 0, None)
    if not chains:
        return False, None, words

    best_score = None
    best_combined = None
    for chain in chains:
        c = combine(chain)
        score = (
            abs(c["x"] - anchor["x"]) +
            abs(c["y"] - anchor["y"]) +
            abs(c["w"] - anchor["w"]) +
            abs(c["h"] - anchor["h"])
        )
        if best_score is None or score < best_score:
            best_score = score
            best_combined = c

    passed = (
        abs(best_combined["x"] - anchor["x"]) <= tolerance and
        abs(best_combined["y"] - anchor["y"]) <= tolerance and
        abs(best_combined["w"] - anchor["w"]) <= tolerance and
        abs(best_combined["h"] - anchor["h"]) <= tolerance
    )
    return passed, best_combined, words


def find_ocr_for_template(template_folder_name):
    """Find the best-matching OCR file for a template folder using compact name comparison."""
    slug = compact(re.sub(r"_0+\d+$", "", template_folder_name))  # strip _001 suffix
    best_match = None
    best_score = 0
    for ocr_path in OCR_DIR.glob("*.json"):
        ocr_slug = compact(ocr_path.stem)
        # score by longest common prefix or substring
        if ocr_slug == slug:
            return ocr_path
        # partial match: one contains the other
        shorter, longer = sorted([ocr_slug, slug], key=len)
        if shorter in longer and len(shorter) > best_score:
            best_score = len(shorter)
            best_match = ocr_path
    return best_match


def main():
    template_folders = sorted(
        f for f in TEMPLATES_DIR.iterdir()
        if f.is_dir() and not f.name.startswith("_")
    )

    matched = []
    unmatched = []
    no_ocr = []

    for folder in template_folders:
        t_path = folder / "template.json"
        if not t_path.exists():
            continue

        template = load_json(t_path)
        if "anchors" not in template or "page_width" not in template:
            continue

        anchor = template["anchors"][0]
        page_width = template["page_width"]
        page_height = template["page_height"]

        ocr_path = find_ocr_for_template(folder.name)
        if ocr_path is None:
            no_ocr.append(folder.name)
            continue

        ocr = load_json(ocr_path)
        ocr_boxes = ocr.get("google", {}).get("bounding_boxes", [])

        passed, best_box, words = diagnose_anchor(anchor, ocr_boxes, page_width, page_height)

        if passed:
            matched.append(folder.name)
        else:
            unmatched.append({
                "folder": folder.name,
                "ocr_file": ocr_path.name,
                "anchor_name": anchor["name"],
                "words": words,
                "stored": {"x": anchor["x"], "y": anchor["y"], "w": anchor["w"], "h": anchor["h"]},
                "found": best_box,
            })

    # --- Report ---
    total = len(matched) + len(unmatched) + len(no_ocr)
    print(f"\n{'='*60}")
    print(f"  RESULTS: {len(matched)} matched / {len(unmatched)} unmatched / {len(no_ocr)} no OCR file")
    print(f"  Total templates: {total}")
    print(f"{'='*60}")

    if matched:
        print(f"\n MATCHED ({len(matched)}):")
        for name in matched:
            print(f"    OK  {name}")

    if unmatched:
        print(f"\n UNMATCHED ({len(unmatched)}):")
        for item in unmatched:
            print(f"\n    FAIL  {item['folder']}")
            print(f"          OCR file : {item['ocr_file']}")
            print(f"          Anchor   : \"{item['anchor_name']}\"")
            print(f"          Words    : {item['words']}")
            stored = item["stored"]
            print(f"          Stored   : x={stored['x']}  y={stored['y']}  w={stored['w']}  h={stored['h']}")
            if item["found"]:
                f = item["found"]
                dx = abs(f["x"] - stored["x"])
                dy = abs(f["y"] - stored["y"])
                dw = abs(f["w"] - stored["w"])
                dh = abs(f["h"] - stored["h"])
                print(f"          Found    : x={f['x']:.1f}  y={f['y']:.1f}  w={f['w']:.1f}  h={f['h']:.1f}")
                print(f"          Delta    : dx={dx:.1f}  dy={dy:.1f}  dw={dw:.1f}  dh={dh:.1f}  (tolerance=15)")
            else:
                print(f"          Found    : NO CHAIN FOUND (words not found in OCR at all)")
                # Show OCR boxes that partially contain any of the words
                ocr_path = OCR_DIR / item["ocr_file"]
                ocr = load_json(ocr_path)
                boxes = ocr.get("google", {}).get("bounding_boxes", [])
                target = item["words"][0] if item["words"] else ""
                hints = [b for b in boxes if target[:6] in compact(b.get("text","")) or compact(b.get("text","")) in target]
                if hints:
                    print(f"          OCR hints (partial matches):")
                    for b in hints[:5]:
                        print(f"            text={b['text']!r:40s} compact={compact(b['text'])}")

    if no_ocr:
        print(f"\n NO OCR FILE ({len(no_ocr)}):")
        for name in no_ocr:
            print(f"    ?   {name}")

    print()


if __name__ == "__main__":
    main()
