"""
Compares fine-tuning JSON price candidates against production template price fields.
Reports matches and mismatches in coordinates and font size.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
FINE_TUNING_DIR = ROOT / "template_setup" / "batch_setup" / "fine_tuning" / "json"
TEMPLATES_DIR = ROOT / "data" / "templates"

COORD_TOLERANCE = 2   # px — box position/size
SIZE_TOLERANCE = 2    # px — font size_px


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def find_production_template(template_name):
    slug = slugify(template_name)
    candidates = []
    for folder in TEMPLATES_DIR.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        folder_slug = re.sub(r"_0+\d+$", "", folder.name)
        if folder_slug == slug:
            t_path = folder / "template.json"
            if t_path.exists():
                candidates.append(folder)
    if not candidates:
        return None, None
    # pick highest version number
    best = sorted(candidates, key=lambda f: f.name)[-1]
    return load_json(best / "template.json"), best.name


def compare_price_fields(fine_path):
    fine = load_json(fine_path)
    template_name = fine.get("template")
    candidates = fine.get("candidates", [])

    production, folder_name = find_production_template(template_name)
    if not production:
        return None, template_name, "no production template found"

    price_fields = {pf["name"]: pf for pf in production.get("price_fields", [])}
    results = []

    for candidate in candidates:
        cid = candidate["id"]
        name = f"PRICE_{cid}"
        prod_field = price_fields.get(name)

        if not prod_field:
            results.append({"name": name, "status": "MISSING in production"})
            continue

        box = candidate.get("box", {})
        font = candidate.get("font", {})

        fine_x = round(font.get("x", box.get("x", 0)) + font.get("offset_x", 0), 2)
        fine_y = round(font.get("y", box.get("y", 0)) + font.get("offset_y", 0), 2)
        fine_w = box.get("w")
        fine_h = font.get("h", box.get("h"))

        issues = []

        for k, fine_val, prod_val in [
            ("x",  fine_x,  prod_field.get("x")),
            ("y",  fine_y,  prod_field.get("y")),
            ("w",  fine_w,  prod_field.get("w")),
            ("h",  fine_h,  prod_field.get("h")),
        ]:
            if fine_val is None or prod_val is None:
                continue
            delta = abs(fine_val - prod_val)
            if delta > COORD_TOLERANCE:
                issues.append(f"{k}: fine={fine_val} prod={prod_val} Δ={delta:.1f}")

        fine_family = font.get("family")
        prod_family = prod_field.get("font", {}).get("family")
        if fine_family and prod_family and fine_family != prod_family:
            issues.append(f"family: fine={fine_family!r} prod={prod_family!r}")

        fine_color = font.get("color", "").upper()
        prod_color = prod_field.get("font", {}).get("color", "").upper()
        if fine_color and prod_color and fine_color != prod_color:
            issues.append(f"color: fine={fine_color} prod={prod_color}")

        if issues:
            results.append({"name": name, "status": "MISMATCH", "issues": issues})
        else:
            results.append({"name": name, "status": "OK"})

    return results, folder_name, None


def main():
    fine_files = sorted(FINE_TUNING_DIR.glob("*.json"))
    if not fine_files:
        print(f"No fine-tuning files found in {FINE_TUNING_DIR}")
        return

    total_fields = 0
    total_ok = 0
    total_mismatch = 0
    total_missing = 0
    no_template = []
    mismatch_report = []

    for fine_path in fine_files:
        results, folder_name, error = compare_price_fields(fine_path)
        if error:
            no_template.append(f"{fine_path.name}: {error}")
            continue

        template_issues = []
        for r in results:
            total_fields += 1
            if r["status"] == "OK":
                total_ok += 1
            elif r["status"] == "MISSING in production":
                total_missing += 1
                template_issues.append(f"    {r['name']}: MISSING in production")
            else:
                total_mismatch += 1
                template_issues.append(f"    {r['name']}:")
                for issue in r["issues"]:
                    template_issues.append(f"      {issue}")

        if template_issues:
            mismatch_report.append((folder_name, fine_path.name, template_issues))

    failures = mismatch_report + [(None, f, [f"  {e}"]) for f, e in [(m.split(":")[0], ":".join(m.split(":")[1:])) for m in no_template]]

    if not failures:
        print(f"\nAll {total_fields} price fields OK.\n")
        return

    print(f"\n{'='*60}")
    print(f"  FAILURES: {total_mismatch} mismatched, {total_missing} missing, {len(no_template)} no template")
    print(f"{'='*60}")

    for folder_name, fine_name, issues in mismatch_report:
        print(f"\n  [{folder_name}]")
        for line in issues:
            print(line)

    if no_template:
        print(f"\n  NO PRODUCTION TEMPLATE:")
        for msg in no_template:
            print(f"    {msg}")

    print()


if __name__ == "__main__":
    main()
