import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parents[1]
FINE_TUNING_DIR = BASE_DIR / "batch_setup" / "fine_tuning" / "json"
UNDO_DIR = BASE_DIR / "batch_setup" / "fine_tuning" / "undo"
SOURCE_DIR = BASE_DIR / "batch_setup" / "price_review_matched"
PNG_DIR = BASE_DIR / "batch_setup" / "png_batches"
FONT_DIR = BASE_DIR.parent / "data" / "fonts"
HOST = "127.0.0.1"
PORT = 8000


def list_json_files():
    return sorted(FINE_TUNING_DIR.glob("*.json"))


def font_file_map():
    return {
        path.stem: path
        for path in sorted(FONT_DIR.iterdir())
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    }


def list_font_choices():
    return sorted(font_file_map())


def get_json_path(file_index):
    files = list_json_files()
    if not files:
        return None, [], 0
    file_index = max(0, min(file_index, len(files) - 1))
    return files[file_index], files, file_index


def normalize_data_format(data):
    for candidate in data.get("candidates", []):
        if "box" not in candidate:
            x = candidate.pop("x", None)
            y = candidate.pop("y", None)
            w = candidate.pop("w", None)
            h = candidate.pop("h", None)
            if None not in {x, y, w, h}:
                candidate["box"] = {"x": x, "y": y, "w": w, "h": h}

        box = candidate.get("box")
        if not box:
            continue

        font = candidate.get("font", {})
        candidate["font"] = {
            "family": font.get("family", "Arial"),
            "size_px": font.get("size_px", 24),
            "color": font.get("color", "#000000"),
            "x": font.get("x", box["x"]),
            "y": font.get("y", box["y"]),
            "w": font.get("w", box["w"]),
            "h": font.get("h", box["h"]),
            "offset_x": font.get("offset_x", 0),
            "offset_y": font.get("offset_y", 0),
        }
    return data


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return normalize_data_format(json.load(file))


def load_data(file_index):
    json_path, files, file_index = get_json_path(file_index)
    if json_path is None:
        return None, None, [], 0
    return load_json(json_path), json_path, files, file_index


def save_data(json_path, data):
    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def get_undo_path(json_path):
    return UNDO_DIR / json_path.name


def save_undo(json_path, data):
    with open(get_undo_path(json_path), "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_undo(json_path):
    undo_path = get_undo_path(json_path)
    if not undo_path.exists():
        return None
    return load_json(undo_path)


def load_source(json_path):
    source_path = SOURCE_DIR / json_path.name
    if not source_path.exists():
        return None
    return load_json(source_path)


def parse_delta(raw_value):
    raw_value = raw_value.strip()
    if not raw_value:
        return 0.0
    return float(raw_value)


def get_image_path(template_name):
    return PNG_DIR / template_name / "page_1.png"


def get_font_path(family):
    return font_file_map().get(family)


def load_preview_font(font_data, text):
    family = font_data["family"]
    font_path = get_font_path(family)
    target_h = max(1, int(round(font_data.get("h", font_data.get("size_px", 24)))))

    def bbox_height(size):
        font = ImageFont.truetype(str(font_path), size)
        bbox = font.getbbox(text or "0")
        return font, bbox, max(1, bbox[3] - bbox[1])

    try:
        if font_path is None:
            raise FileNotFoundError(family)
        low = 1
        high = max(4, target_h * 4)
        best_font = None
        best_bbox = None

        while low <= high:
            mid = (low + high) // 2
            font, bbox, visible_h = bbox_height(mid)
            if visible_h <= target_h:
                best_font = font
                best_bbox = bbox
                low = mid + 1
            else:
                high = mid - 1

        if best_font is None:
            best_font, best_bbox, _ = bbox_height(1)

        font_data["size_px"] = best_font.size
        return best_font, best_bbox
    except Exception:
        fallback = ImageFont.load_default()
        return fallback, fallback.getbbox(text or "0")


def build_preview_bytes(template_name, candidate, preview_mode):
    image = Image.open(get_image_path(template_name)).convert("RGB")
    draw = ImageDraw.Draw(image)

    box = candidate["box"]
    x = int(round(box["x"]))
    y = int(round(box["y"]))
    w = int(round(box["w"]))
    h = int(round(box["h"]))

    draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=1)
    try:
        label_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 50)
    except Exception:
        label_font = ImageFont.load_default()
    draw.text((x, max(0, y - 60)), f"ID {candidate['id']}", fill=(255, 0, 0), font=label_font)

    if preview_mode == "font":
        font_data = candidate["font"]
        text = candidate.get("text", "")
        preview_font, text_bbox = load_preview_font(font_data, text)
        left, top, _, _ = text_bbox
        text = candidate.get("text", "")
        text_x = int(round(font_data["x"] + font_data["offset_x"] - left))
        text_y = int(round(font_data["y"] + font_data["offset_y"] - top))
        draw.text((text_x, text_y), text, fill=font_data["color"], font=preview_font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_query(file_index, candidate_index, preview_mode):
    return urlencode({"file": file_index, "candidate": candidate_index, "mode": preview_mode})


def safe_candidate_index(data, candidate_index):
    candidates = data.get("candidates", [])
    if not candidates:
        return 0
    return max(0, min(candidate_index, len(candidates) - 1))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        valid = {"/update", "/update-font", "/undo", "/reset-original", "/match-size", "/align-x", "/align-y", "/set-font"}
        if self.path not in valid:
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))

        file_index = int(form.get("file_index", ["0"])[0])
        candidate_index = int(form.get("candidate_index", ["0"])[0])
        preview_mode = form.get("preview_mode", ["box"])[0]

        data, json_path, _, file_index = load_data(file_index)
        if data is None or json_path is None:
            self.send_response(404)
            self.end_headers()
            return

        candidate_index = safe_candidate_index(data, candidate_index)

        if self.path == "/undo":
            undo_data = load_undo(json_path)
            if undo_data is not None:
                save_data(json_path, undo_data)
            self.redirect(file_index, candidate_index, preview_mode)
            return

        if self.path == "/reset-original":
            source_data = load_source(json_path)
            if source_data is not None:
                save_undo(json_path, data)
                save_data(json_path, source_data)
            self.redirect(file_index, 0, preview_mode)
            return

        if self.path in {"/match-size", "/align-x", "/align-y"}:
            source_index = int(form.get("source_index", ["-1"])[0])
            if source_index < 0 or source_index >= len(data["candidates"]) or source_index == candidate_index:
                self.redirect(file_index, candidate_index, preview_mode)
                return

            save_undo(json_path, data)
            box = data["candidates"][candidate_index]["box"]
            source_box = data["candidates"][source_index]["box"]

            if self.path == "/match-size":
                box["w"] = source_box["w"]
                box["h"] = source_box["h"]
            elif self.path == "/align-x":
                box["x"] = source_box["x"]
            elif self.path == "/align-y":
                box["y"] = source_box["y"]

            save_data(json_path, data)
            self.redirect(file_index, candidate_index, preview_mode)
            return

        if self.path == "/set-font":
            family = form.get("font_family", [""])[0]
            if family:
                save_undo(json_path, data)
                data["candidates"][candidate_index]["font"]["family"] = family
                save_data(json_path, data)
            self.redirect(file_index, candidate_index, "font")
            return

        if self.path == "/update-font":
            save_undo(json_path, data)
            font = data["candidates"][candidate_index]["font"]
            font["h"] = max(1, round(font["h"] + parse_delta(form.get("dh", [""])[0]), 2))
            font["offset_x"] = round(font["offset_x"] + parse_delta(form.get("fdx", [""])[0]), 2)
            font["offset_y"] = round(font["offset_y"] + parse_delta(form.get("fdy", [""])[0]), 2)
            save_data(json_path, data)
            self.redirect(file_index, candidate_index, "font")
            return

        save_undo(json_path, data)
        box = data["candidates"][candidate_index]["box"]
        box["x"] = round(box["x"] + parse_delta(form.get("dx", [""])[0]), 2)
        box["y"] = round(box["y"] + parse_delta(form.get("dy", [""])[0]), 2)
        box["w"] = round(box["w"] + parse_delta(form.get("dw", [""])[0]), 2)
        box["h"] = round(box["h"] + parse_delta(form.get("dh", [""])[0]), 2)
        save_data(json_path, data)
        self.redirect(file_index, candidate_index, preview_mode)

    def redirect(self, file_index, candidate_index, preview_mode):
        self.send_response(303)
        self.send_header("Location", f"/?{build_query(file_index, candidate_index, preview_mode)}")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        file_index = int(params.get("file", ["0"])[0])
        candidate_index = int(params.get("candidate", ["0"])[0])
        preview_mode = params.get("mode", ["box"])[0]

        data, json_path, files, file_index = load_data(file_index)
        if data is None or json_path is None:
            payload = b"No fine-tuning JSON files found."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        candidate_index = safe_candidate_index(data, candidate_index)
        candidates = data.get("candidates", [])
        candidate = candidates[candidate_index]
        box = candidate["box"]
        font = candidate["font"]

        if parsed.path == "/preview.png":
            image_bytes = build_preview_bytes(data["template"], candidate, preview_mode)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(image_bytes)))
            self.end_headers()
            self.wfile.write(image_bytes)
            return

        if parsed.path != "/":
            self.send_response(404)
            self.end_headers()
            return

        tabs_html = []
        for idx, tab_candidate in enumerate(candidates):
            active = "tab active" if idx == candidate_index else "tab"
            tabs_html.append(f'<a class="{active}" href="/?{build_query(file_index, idx, preview_mode)}">Price {idx + 1} (ID {tab_candidate["id"]})</a>')

        prev_link = f"/?{build_query(file_index - 1, 0, preview_mode)}" if file_index > 0 else None
        next_link = f"/?{build_query(file_index + 1, 0, preview_mode)}" if file_index < len(files) - 1 else None
        nav_prev = f'<a class="nav-button" href="{prev_link}">Previous Template</a>' if prev_link else '<span class="nav-button disabled">Previous Template</span>'
        nav_next = f'<a class="nav-button" href="{next_link}">Next Template</a>' if next_link else '<span class="nav-button disabled">Next Template</span>'

        mode_tabs = (
            f'<a class="tab {"active" if preview_mode == "box" else ""}" href="/?{build_query(file_index, candidate_index, "box")}">Box Only</a>'
            f'<a class="tab {"active" if preview_mode == "font" else ""}" href="/?{build_query(file_index, candidate_index, "font")}">Font + Box</a>'
        )
        chooser_candidates = [{"index": idx, "id": c["id"]} for idx, c in enumerate(candidates)]
        font_choices = list_font_choices()

        box_controls_disabled = preview_mode == "font"
        font_controls_disabled = preview_mode == "box"
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Price Fine Tuning</title>
  <style>
    body {{ margin: 0; font-family: Helvetica, Arial, sans-serif; background: #f3f0e8; color: #1f1f1f; }}
    .wrap {{ display: grid; grid-template-columns: minmax(760px, 1fr) 360px; gap: 24px; padding: 24px; }}
    .panel {{ background: #fffdf8; border: 1px solid #d7d1c7; border-radius: 14px; padding: 18px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }}
    .nav, .tabs {{ display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }}
    .nav-button, .tab {{ padding: 10px 14px; border-radius: 999px; text-decoration: none; font-weight: 700; }}
    .nav-button {{ background: #d8cfbf; color: #1f1f1f; }}
    .nav-button.disabled {{ opacity: 0.45; pointer-events: none; }}
    button:disabled, .mini:disabled, input:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    .tab {{ color: #1f1f1f; background: #e7dfd2; }}
    .tab.active {{ background: #1f1f1f; color: white; }}
    img {{ max-width: 100%; display: block; border-radius: 10px; }}
    h1 {{ margin: 0 0 12px; font-size: 22px; }}
    .meta {{ margin-bottom: 16px; color: #5a5349; font-size: 14px; }}
    .row {{ display: grid; grid-template-columns: 90px 1fr; gap: 10px; margin: 10px 0; align-items: center; }}
    .label {{ font-weight: 700; }}
    .value {{ word-break: break-word; }}
    .section {{ margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5ded3; }}
    input {{ width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #c9c1b5; border-radius: 8px; font: inherit; background: white; }}
    .adjust {{ display: grid; grid-template-columns: 36px 1fr 36px; gap: 8px; align-items: center; }}
    .mini {{ width: 36px; height: 36px; padding: 0; border-radius: 999px; border: 0; background: #ddd4c6; color: #1f1f1f; font-weight: 700; }}
    .button-row {{ display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 16px; }}
    .button-row.three {{ grid-template-columns: 1fr 1fr 1fr; }}
    button {{ width: 100%; padding: 12px 14px; border: 0; border-radius: 999px; background: #1f1f1f; color: white; font: inherit; font-weight: 700; }}
    .button-secondary {{ background: #cfc6b8; color: #1f1f1f; }}
    .modal-backdrop {{ position: fixed; inset: 0; background: rgba(20,20,20,0.45); display: none; align-items: center; justify-content: center; padding: 24px; }}
    .modal {{ width: min(460px, 100%); max-height: min(80vh, 760px); background: #fffdf8; border: 1px solid #d7d1c7; border-radius: 14px; padding: 18px; box-shadow: 0 10px 30px rgba(0,0,0,0.16); display: flex; flex-direction: column; }}
    .modal h2 {{ margin: 0 0 10px; font-size: 20px; }}
    .modal-actions {{ display: grid; gap: 10px; margin-top: 14px; overflow-y: auto; padding-right: 4px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <div class="nav">{nav_prev}{nav_next}</div>
      <div class="tabs">{mode_tabs}</div>
      <div class="tabs">{''.join(tabs_html)}</div>
      <img src="/preview.png?{build_query(file_index, candidate_index, preview_mode)}" alt="preview">
    </div>
    <div class="panel">
      <h1>Price Fine Tuning</h1>
      <div class="meta">Template {file_index + 1} of {len(files)}<br>{json_path.name}</div>
      <div class="row"><div class="label">Template</div><div class="value">{data["template"]}</div></div>
      <div class="row"><div class="label">Price ID</div><div class="value">{candidate["id"]}</div></div>
      <div class="row"><div class="label">Text</div><div class="value">{candidate["text"]}</div></div>
      <div class="row"><div class="label">X</div><div class="value">{box["x"]}</div></div>
      <div class="row"><div class="label">Y</div><div class="value">{box["y"]}</div></div>
      <div class="row"><div class="label">W</div><div class="value">{box["w"]}</div></div>
      <div class="row"><div class="label">H</div><div class="value">{box["h"]}</div></div>

      <form id="update-form" class="section" method="post" action="/update">
        <input type="hidden" name="file_index" value="{file_index}">
        <input type="hidden" name="candidate_index" value="{candidate_index}">
        <input type="hidden" name="preview_mode" value="{preview_mode}">
        <div class="row"><div class="label">dX</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dx', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dx" name="dx" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dx', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="row"><div class="label">dY</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dy', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dy" name="dy" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dy', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="row"><div class="label">dW</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dw', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dw" name="dw" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dw', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="row"><div class="label">dH</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dh', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dh" name="dh" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dh', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="button-row"><button type="submit" {"disabled" if box_controls_disabled else ""}>Submit</button></div>
      </form>

      <div class="section">
        <div class="button-row three">
          <button class="button-secondary" type="button" onclick="confirmAction('match-size-form', 'Choose source price for W/H')" {"disabled" if len(candidates) <= 1 or box_controls_disabled else ""}>Match W/H</button>
          <button class="button-secondary" type="button" onclick="confirmAction('align-x-form', 'Choose source price for X')" {"disabled" if len(candidates) <= 1 or box_controls_disabled else ""}>Align X</button>
          <button class="button-secondary" type="button" onclick="confirmAction('align-y-form', 'Choose source price for Y')" {"disabled" if len(candidates) <= 1 or box_controls_disabled else ""}>Align Y</button>
        </div>
      </div>

      <div class="section">
        <div class="row"><div class="label">Font</div><div class="value">{font["family"]}</div></div>
        <div class="row"><div class="label">Font H</div><div class="value">{font["h"]}</div></div>
        <div class="row"><div class="label">size_px</div><div class="value">{font["size_px"]}</div></div>
        <div class="row"><div class="label">fX</div><div class="value">{font["offset_x"]}</div></div>
        <div class="row"><div class="label">fY</div><div class="value">{font["offset_y"]}</div></div>
        <form id="font-update-form" method="post" action="/update-font">
          <input type="hidden" name="file_index" value="{file_index}">
          <input type="hidden" name="candidate_index" value="{candidate_index}">
          <input type="hidden" name="preview_mode" value="font">
          <div class="row"><div class="label">dH</div><div class="adjust"><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_dh', -1)" {"disabled" if font_controls_disabled else ""}>-</button><input id="font_dh" name="dh" placeholder="+1 or -1" {"disabled" if font_controls_disabled else ""}><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_dh', 1)" {"disabled" if font_controls_disabled else ""}>+</button></div></div>
          <div class="row"><div class="label">f dX</div><div class="adjust"><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdx', -1)" {"disabled" if font_controls_disabled else ""}>-</button><input id="font_fdx" name="fdx" placeholder="+1 or -1" {"disabled" if font_controls_disabled else ""}><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdx', 1)" {"disabled" if font_controls_disabled else ""}>+</button></div></div>
          <div class="row"><div class="label">f dY</div><div class="adjust"><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdy', -1)" {"disabled" if font_controls_disabled else ""}>-</button><input id="font_fdy" name="fdy" placeholder="+1 or -1" {"disabled" if font_controls_disabled else ""}><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdy', 1)" {"disabled" if font_controls_disabled else ""}>+</button></div></div>
          <div class="button-row three">
            <button type="submit" {"disabled" if font_controls_disabled else ""}>Apply Font</button>
            <button class="button-secondary" type="button" onclick="openFontChooser()" {"disabled" if font_controls_disabled else ""}>Choose Font</button>
          </div>
        </form>
      </div>

      <form method="post" action="/undo">
        <input type="hidden" name="file_index" value="{file_index}">
        <input type="hidden" name="candidate_index" value="{candidate_index}">
        <input type="hidden" name="preview_mode" value="{preview_mode}">
        <div class="button-row">
          <button class="button-secondary" type="submit">Undo</button>
          <button class="button-secondary" type="button" onclick="confirmReset()">Reset To Original OCR</button>
        </div>
      </form>
    </div>
  </div>

  <form id="reset-original-form" method="post" action="/reset-original" style="display:none;">
    <input type="hidden" name="file_index" value="{file_index}">
    <input type="hidden" name="candidate_index" value="{candidate_index}">
    <input type="hidden" name="preview_mode" value="{preview_mode}">
  </form>
  <form id="match-size-form" method="post" action="/match-size" style="display:none;">
    <input type="hidden" name="file_index" value="{file_index}">
    <input type="hidden" name="candidate_index" value="{candidate_index}">
    <input type="hidden" name="preview_mode" value="{preview_mode}">
    <input type="hidden" name="source_index" value="">
  </form>
  <form id="align-x-form" method="post" action="/align-x" style="display:none;">
    <input type="hidden" name="file_index" value="{file_index}">
    <input type="hidden" name="candidate_index" value="{candidate_index}">
    <input type="hidden" name="preview_mode" value="{preview_mode}">
    <input type="hidden" name="source_index" value="">
  </form>
  <form id="align-y-form" method="post" action="/align-y" style="display:none;">
    <input type="hidden" name="file_index" value="{file_index}">
    <input type="hidden" name="candidate_index" value="{candidate_index}">
    <input type="hidden" name="preview_mode" value="{preview_mode}">
    <input type="hidden" name="source_index" value="">
  </form>
  <form id="set-font-form" method="post" action="/set-font" style="display:none;">
    <input type="hidden" name="file_index" value="{file_index}">
    <input type="hidden" name="candidate_index" value="{candidate_index}">
    <input type="hidden" name="preview_mode" value="font">
    <input type="hidden" name="font_family" value="">
  </form>

  <div id="chooser-backdrop" class="modal-backdrop">
    <div class="modal">
      <h2 id="chooser-title">Choose</h2>
      <div id="chooser-actions" class="modal-actions"></div>
      <div class="button-row" style="margin-top:14px;">
        <button class="button-secondary" type="button" onclick="closeChooser()">Cancel</button>
      </div>
    </div>
  </div>

  <script>
    const chooserCandidates = {json.dumps(chooser_candidates)};
    const fontChoices = {json.dumps(font_choices)};

    function nudgeAndSubmit(id, amount) {{
      document.getElementById(id).value = String(amount);
      document.getElementById('update-form').submit();
    }}

    function fontNudgeAndSubmit(id, amount) {{
      document.getElementById(id).value = String(amount);
      document.getElementById('font-update-form').submit();
    }}

    function confirmReset() {{
      if (window.confirm('Reset this template back to the original OCR review version?')) {{
        document.getElementById('reset-original-form').submit();
      }}
    }}

    function closeChooser() {{
      document.getElementById('chooser-backdrop').style.display = 'none';
      document.getElementById('chooser-actions').innerHTML = '';
    }}

    function submitChoice(formId, sourceIndex) {{
      document.querySelector(`#${{formId}} input[name="source_index"]`).value = String(sourceIndex);
      document.getElementById(formId).submit();
    }}

    function confirmAction(formId, title) {{
      const actions = document.getElementById('chooser-actions');
      document.getElementById('chooser-title').textContent = title;
      actions.innerHTML = '';
      const choices = chooserCandidates.filter(item => item.index !== {candidate_index});
      for (const choice of choices) {{
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = `Use Price ID ${{choice.id}}`;
        button.onclick = () => submitChoice(formId, choice.index);
        actions.appendChild(button);
      }}
      document.getElementById('chooser-backdrop').style.display = 'flex';
    }}

    function openFontChooser() {{
      const actions = document.getElementById('chooser-actions');
      document.getElementById('chooser-title').textContent = 'Choose Font';
      actions.innerHTML = '';
      for (const family of fontChoices) {{
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = family;
        button.onclick = () => {{
          document.querySelector('#set-font-form input[name="font_family"]').value = family;
          document.getElementById('set-font-form').submit();
        }};
        actions.appendChild(button);
      }}
      document.getElementById('chooser-backdrop').style.display = 'flex';
    }}
  </script>
</body>
</html>"""

        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    UNDO_DIR.mkdir(parents=True, exist_ok=True)
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
