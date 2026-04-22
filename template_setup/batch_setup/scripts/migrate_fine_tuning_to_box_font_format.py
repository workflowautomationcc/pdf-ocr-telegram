import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
FINE_TUNING_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "fine_tuning" / "json"


def main():
    json_files = sorted(FINE_TUNING_DIR.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {FINE_TUNING_DIR}")
        return

    for json_path in json_files:
        with open(json_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        changed = False

        for candidate in data.get("candidates", []):
            if "box" in candidate:
                continue

            x = candidate.pop("x", None)
            y = candidate.pop("y", None)
            w = candidate.pop("w", None)
            h = candidate.pop("h", None)

            if None in {x, y, w, h}:
                continue

            candidate["box"] = {
                "x": x,
                "y": y,
                "w": w,
                "h": h
            }

            font = candidate.get("font", {})
            candidate["font"] = {
                "family": font.get("family", "Arial"),
                "size_px": font.get("size_px", 24),
                "color": font.get("color", "#000000"),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "offset_x": font.get("offset_x", 0),
                "offset_y": font.get("offset_y", 0)
            }

            changed = True

        if changed:
            with open(json_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            print(f"Updated: {json_path}")
        else:
            print(f"Skipped: {json_path}")

    print("Box/font format migration complete.")


if __name__ == "__main__":
    main()
