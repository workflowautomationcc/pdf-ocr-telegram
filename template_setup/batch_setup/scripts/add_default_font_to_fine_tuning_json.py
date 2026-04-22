import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
FINE_TUNING_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "fine_tuning" / "json"

DEFAULT_FONT = {
    "family": "Arial",
    "size_px": 24,
    "color": "#000000"
}


def main():
    json_files = sorted(FINE_TUNING_DIR.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {FINE_TUNING_DIR}")
        return

    for json_path in json_files:
        with open(json_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        candidates = data.get("candidates", [])
        changed = False

        for candidate in candidates:
            if "font" not in candidate:
                candidate["font"] = dict(DEFAULT_FONT)
                changed = True

        if changed:
            with open(json_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            print(f"Updated: {json_path}")
        else:
            print(f"Skipped: {json_path}")

    print("Default font update complete.")


if __name__ == "__main__":
    main()
