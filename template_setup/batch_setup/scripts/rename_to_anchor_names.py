import json
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]

DRAFTS_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "templates_draft" / "matched"
OCR_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "ocr_page1"
PNG_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "png_batches"


def safe_name(value):
    value = value.strip()
    value = re.sub(r'[\\/:*?"<>|]', "", value)
    return value


def load_anchor_name(draft_path):
    with open(draft_path, "r", encoding="utf-8") as draft_file:
        data = json.load(draft_file)
    return data.get("anchor_match", {}).get("anchor")


def rename_path(old_path, new_path):
    if not old_path.exists():
        return
    if old_path == new_path:
        return
    if new_path.exists():
        raise FileExistsError(f"Target already exists: {new_path}")
    old_path.rename(new_path)


def main():
    draft_files = sorted(DRAFTS_DIR.glob("*.json"))

    if not draft_files:
        print(f"No matched draft files found in {DRAFTS_DIR}")
        return

    for draft_path in draft_files:
        anchor_name = load_anchor_name(draft_path)
        if not anchor_name:
            print(f"Skipping {draft_path.name}: no anchor_match.anchor")
            continue

        new_stem = safe_name(anchor_name)
        old_stem = draft_path.stem

        rename_path(draft_path, draft_path.with_name(f"{new_stem}.json"))
        rename_path(OCR_DIR / f"{old_stem}.json", OCR_DIR / f"{new_stem}.json")
        rename_path(PNG_DIR / old_stem, PNG_DIR / new_stem)

        print(f"Renamed: {old_stem} -> {new_stem}")

    print("One-time rename complete.")


if __name__ == "__main__":
    main()
