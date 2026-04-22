import json
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
DRAFTS_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "templates_draft" / "matched"


def safe_name(value):
    value = value.strip()
    value = re.sub(r'[\\/:*?"<>|]', "", value)
    return value


def main():
    draft_files = sorted(DRAFTS_DIR.glob("*.json"))

    if not draft_files:
        print(f"No matched draft files found in {DRAFTS_DIR}")
        return

    for draft_path in draft_files:
        with open(draft_path, "r", encoding="utf-8") as draft_file:
            data = json.load(draft_file)

        anchor_name = data.get("anchor_match", {}).get("anchor")
        if not anchor_name:
            print(f"Skipping {draft_path.name}: no anchor_match.anchor")
            continue

        base_name = safe_name(anchor_name)
        new_name = base_name + ".json"
        new_path = draft_path.with_name(new_name)

        if new_path == draft_path:
            continue

        if draft_path.name.lower() == new_name.lower():
            temp_path = draft_path.with_name(f"{draft_path.stem}.__tmp_rename__.json")
            if temp_path.exists():
                raise FileExistsError(f"Temporary rename path already exists: {temp_path}")
            draft_path.rename(temp_path)
            temp_path.rename(new_path)
            print(f"Renamed: {draft_path.name} -> {new_name}")
            continue

        if new_path.exists():
            new_name = f"{base_name}__{safe_name(draft_path.stem)}.json"
            new_path = draft_path.with_name(new_name)
            if new_path.exists():
                raise FileExistsError(f"Target already exists: {new_path}")

        draft_path.rename(new_path)
        print(f"Renamed: {draft_path.name} -> {new_name}")

    print("Draft JSON rename complete.")


if __name__ == "__main__":
    main()
