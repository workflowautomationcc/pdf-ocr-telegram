import base64
import io
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
UNKNOWN_TEMPLATES_DIR = BASE_DIR / "data" / "unknown_templates"
FONT_DIR = BASE_DIR / "data" / "fonts"
HOST = "0.0.0.0"
PORT = 8002

UI_USER = os.getenv("FINETUNE_USER", "admin")
UI_PASS = os.getenv("FINETUNE_PASS", "changeme")
COMMA_COEFF = 2


def font_file_map():
    return {
        path.stem: path
        for path in sorted(FONT_DIR.iterdir())
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    }


def list_font_choices():
    return sorted(font_file_map())


def get_font_path(family):
    return font_file_map().get(family)


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
            "background_gray": font.get("background_gray", 255),
        }
    return data


def load_job(job_id):
    path = UNKNOWN_TEMPLATES_DIR / job_id / "fine_tuning.json"
    if not path.exists():
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    data = normalize_data_format(raw)
    # Write back so any missing fields (e.g. background_gray) are persisted
    save_data(path, data)
    return data, path


def save_data(json_path, data):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_undo_path(job_id):
    return UNKNOWN_TEMPLATES_DIR / job_id / "fine_tuning_undo.json"


def save_undo(job_id, data):
    with open(get_undo_path(job_id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_undo(job_id):
    undo_path = get_undo_path(job_id)
    if not undo_path.exists():
        return None
    with open(undo_path) as f:
        return normalize_data_format(json.load(f))


def format_price(value, currency_symbol=""):
    formatted = f"{float(value):,.2f}"
    return f"{currency_symbol}{formatted}"


def parse_delta(raw_value):
    raw_value = raw_value.strip()
    if not raw_value:
        return 0.0
    return float(raw_value)


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


def build_preview_bytes(job_id, candidate, preview_mode):
    image_path = UNKNOWN_TEMPLATES_DIR / job_id / "page_1.png"
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    box = candidate["box"]
    x = int(round(box["x"]))
    y = int(round(box["y"]))
    w = int(round(box["w"]))
    h = int(round(box["h"]))

    try:
        label_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 50)
    except Exception:
        label_font = ImageFont.load_default()

    if preview_mode == "font":
        font_data = candidate["font"]
        original_text = candidate.get("text", "0")
        new_value = candidate.get("new_value", "0")
        prefix = candidate.get("prefix")

        fx = int(round(font_data["x"] + font_data.get("offset_x", 0)))
        fy = int(round(font_data["y"] + font_data.get("offset_y", 0)))
        fw = int(round(font_data["w"]))
        fh = int(round(font_data["h"]))

        original_has_comma = "," in original_text
        try:
            new_has_comma = float(str(new_value).replace(",", "")) >= 1000
        except ValueError:
            new_has_comma = False
        adjusted_h = fh
        if original_has_comma and not new_has_comma:
            adjusted_h = fh - COMMA_COEFF
        elif not original_has_comma and new_has_comma:
            adjusted_h = fh + COMMA_COEFF

        preview_font, _ = load_preview_font({**font_data, "h": adjusted_h}, original_text)

        bg = int(max(0, min(255, font_data.get("background_gray", 255))))
        draw.rectangle([fx, fy - 2, fx + fw + 2, fy + fh + 5], fill=(bg, bg, bg))

        formatted = format_price(new_value)
        text_bbox = preview_font.getbbox(formatted)
        left, top, right, _ = text_bbox
        text_width = right - left
        draw.text((fx + fw - text_width - left, fy - top), formatted, fill=font_data["color"], font=preview_font)

    # red box drawn last so it's always visible on top
    draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=1)
    draw.text((x, max(0, y - 60)), f"ID {candidate['id']}", fill=(255, 0, 0), font=label_font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_query(job_id, candidate_index, preview_mode):
    return urlencode({"job": job_id, "candidate": candidate_index, "mode": preview_mode})


def safe_candidate_index(data, candidate_index):
    candidates = data.get("candidates", [])
    if not candidates:
        return 0
    return max(0, min(candidate_index, len(candidates) - 1))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request logs

    def is_authorized(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            user, password = decoded.split(":", 1)
            return user == UI_USER and password == UI_PASS
        except Exception:
            return False

    def require_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Fine Tune"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if not self.is_authorized():
            self.require_auth()
            return

        valid = {"/update", "/update-font", "/update-bg", "/set-bg", "/undo", "/set-font", "/set-value"}
        if self.path not in valid:
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))

        job_id = form.get("job_id", [""])[0]
        candidate_index = int(form.get("candidate_index", ["0"])[0])
        preview_mode = form.get("preview_mode", ["box"])[0]

        data, json_path = load_job(job_id)
        if data is None or json_path is None:
            self.send_response(404)
            self.end_headers()
            return

        candidate_index = safe_candidate_index(data, candidate_index)

        if self.path == "/undo":
            undo_data = load_undo(job_id)
            if undo_data is not None:
                save_data(json_path, undo_data)
            self.redirect(job_id, candidate_index, preview_mode)
            return

        if self.path == "/set-value":
            new_value = form.get("new_value", [""])[0].strip().replace(",", "")
            try:
                float(new_value)
                save_undo(job_id, data)
                data["candidates"][candidate_index]["new_value"] = new_value
                save_data(json_path, data)
            except ValueError:
                pass
            self.redirect(job_id, candidate_index, "font")
            return

        if self.path == "/set-font":
            family = form.get("font_family", [""])[0]
            if family:
                save_undo(job_id, data)
                data["candidates"][candidate_index]["font"]["family"] = family
                save_data(json_path, data)
            self.redirect(job_id, candidate_index, "font")
            return

        if self.path == "/update-font":
            save_undo(job_id, data)
            font = data["candidates"][candidate_index]["font"]
            font["h"] = max(1, round(font["h"] + parse_delta(form.get("dh", [""])[0]), 2))
            font["offset_x"] = round(font["offset_x"] + parse_delta(form.get("fdx", [""])[0]), 2)
            font["offset_y"] = round(font["offset_y"] + parse_delta(form.get("fdy", [""])[0]), 2)
            save_data(json_path, data)
            self.redirect(job_id, candidate_index, "font")
            return

        if self.path == "/set-bg":
            raw = form.get("bg_value", ["255"])[0].strip()
            try:
                value = int(float(raw))
                save_undo(job_id, data)
                data["candidates"][candidate_index]["font"]["background_gray"] = max(0, min(255, value))
                save_data(json_path, data)
            except ValueError:
                pass
            self.redirect(job_id, candidate_index, "font")
            return

        if self.path == "/update-bg":
            step = parse_delta(form.get("bg_step", ["10"])[0])
            direction = form.get("bg_direction", ["lighter"])[0]
            save_undo(job_id, data)
            current = data["candidates"][candidate_index]["font"].get("background_gray", 255)
            delta = step if direction == "lighter" else -step
            data["candidates"][candidate_index]["font"]["background_gray"] = max(0, min(255, current + delta))
            save_data(json_path, data)
            self.redirect(job_id, candidate_index, "font")
            return

        # /update — box adjustment
        save_undo(job_id, data)
        box = data["candidates"][candidate_index]["box"]
        box["x"] = round(box["x"] + parse_delta(form.get("dx", [""])[0]), 2)
        box["y"] = round(box["y"] + parse_delta(form.get("dy", [""])[0]), 2)
        box["w"] = round(box["w"] + parse_delta(form.get("dw", [""])[0]), 2)
        box["h"] = round(box["h"] + parse_delta(form.get("dh", [""])[0]), 2)
        save_data(json_path, data)
        self.redirect(job_id, candidate_index, preview_mode)

    def redirect(self, job_id, candidate_index, preview_mode):
        self.send_response(303)
        self.send_header("Location", f"/?{build_query(job_id, candidate_index, preview_mode)}")
        self.end_headers()

    def do_GET(self):
        if not self.is_authorized():
            self.require_auth()
            return
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/font-preview.png":
            family = params.get("family", [""])[0]
            font_path = get_font_path(family)
            # Render at 2x for sharpness, display at half size via CSS
            W, H = 220, 72
            radius = H // 2
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=radius, fill=(255, 255, 255, 255))
            try:
                preview_font = ImageFont.truetype(str(font_path), 34) if font_path else ImageFont.load_default()
            except Exception:
                preview_font = ImageFont.load_default()
            text = "1,200.00"
            bbox = preview_font.getbbox(text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((W - tw) // 2 - bbox[0], (H - th) // 2 - bbox[1]), text, fill="#1f1f1f", font=preview_font)
            out = Image.new("RGB", (W, H), (31, 31, 31))
            out.paste(img, mask=img.split()[3])
            buf = io.BytesIO()
            out.save(buf, format="PNG")
            payload = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        job_id = params.get("job", [""])[0]
        candidate_index = int(params.get("candidate", ["0"])[0])
        preview_mode = params.get("mode", ["box"])[0]

        data, json_path = load_job(job_id)
        if data is None or json_path is None:
            payload = b"Job not found or already cleaned up."
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
            image_bytes = build_preview_bytes(job_id, candidate, preview_mode)
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
            tabs_html.append(
                f'<a class="{active}" href="/?{build_query(job_id, idx, preview_mode)}">'
                f'Price {idx + 1} &rarr; {tab_candidate.get("new_value", "?")} (ID {tab_candidate["id"]})</a>'
            )

        mode_tabs = (
            f'<a class="tab {"active" if preview_mode == "box" else ""}" href="/?{build_query(job_id, candidate_index, "box")}">Box Only</a>'
            f'<a class="tab {"active" if preview_mode == "font" else ""}" href="/?{build_query(job_id, candidate_index, "font")}">Font + Box</a>'
        )
        font_choices = list_font_choices()

        box_controls_disabled = preview_mode == "font"
        font_controls_disabled = preview_mode == "box"

        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fine Tune — {job_id}</title>
  <style>
    body {{ margin: 0; font-family: Helvetica, Arial, sans-serif; background: #f3f0e8; color: #1f1f1f; }}
    .wrap {{ display: grid; grid-template-columns: minmax(760px, 1fr) 360px; gap: 24px; padding: 24px; }}
    .panel {{ background: #fffdf8; border: 1px solid #d7d1c7; border-radius: 14px; padding: 18px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }}
    .tabs {{ display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }}
    .tab {{ padding: 10px 14px; border-radius: 999px; text-decoration: none; font-weight: 700; color: #1f1f1f; background: #e7dfd2; }}
    .tab.active {{ background: #1f1f1f; color: white; }}
    button:disabled, .mini:disabled, input:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    img {{ max-width: 100%; display: block; border-radius: 10px; }}
    h1 {{ margin: 0 0 12px; font-size: 22px; }}
    .meta {{ margin-bottom: 16px; color: #5a5349; font-size: 14px; word-break: break-all; }}
    .row {{ display: grid; grid-template-columns: 90px 1fr; gap: 10px; margin: 10px 0; align-items: center; }}
    .label {{ font-weight: 700; }}
    .value {{ word-break: break-word; }}
    .section {{ margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5ded3; }}
    input {{ width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #c9c1b5; border-radius: 8px; font: inherit; background: white; }}
    .adjust {{ display: grid; grid-template-columns: 36px 1fr 36px; gap: 8px; align-items: center; }}
    .mini {{ width: 36px; height: 36px; padding: 0; border-radius: 999px; border: 0; background: #ddd4c6; color: #1f1f1f; font-weight: 700; cursor: pointer; }}
    .button-row {{ display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 16px; }}
    .button-row.two {{ grid-template-columns: 1fr 1fr; }}
    button {{ width: 100%; padding: 12px 14px; border: 0; border-radius: 999px; background: #1f1f1f; color: white; font: inherit; font-weight: 700; cursor: pointer; }}
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
      <div class="tabs">{mode_tabs}</div>
      <div class="tabs">{''.join(tabs_html)}</div>
      <img src="/preview.png?{build_query(job_id, candidate_index, preview_mode)}" alt="preview">
    </div>
    <div class="panel">
      <h1>Fine Tune</h1>
      <div class="meta">{job_id}</div>
      <div class="row"><div class="label">Price ID</div><div class="value">{candidate["id"]}</div></div>
      <div class="row"><div class="label">OCR text</div><div class="value">{candidate["text"]}</div></div>
      <form method="post" action="/set-value" style="margin: 10px 0;">
        <input type="hidden" name="job_id" value="{job_id}">
        <input type="hidden" name="candidate_index" value="{candidate_index}">
        <input type="hidden" name="preview_mode" value="font">
        <div class="row">
          <div class="label">New value</div>
          <div class="adjust" style="grid-template-columns: 1fr 80px;">
            <input name="new_value" value="{candidate.get("new_value", "")}" placeholder="e.g. 1900">
            <button type="submit" style="border-radius: 8px; padding: 10px 0;">Save</button>
          </div>
        </div>
      </form>
      <div class="row"><div class="label">X</div><div class="value">{box["x"]}</div></div>
      <div class="row"><div class="label">Y</div><div class="value">{box["y"]}</div></div>
      <div class="row"><div class="label">W</div><div class="value">{box["w"]}</div></div>
      <div class="row"><div class="label">H</div><div class="value">{box["h"]}</div></div>

      <form id="update-form" class="section" method="post" action="/update">
        <input type="hidden" name="job_id" value="{job_id}">
        <input type="hidden" name="candidate_index" value="{candidate_index}">
        <input type="hidden" name="preview_mode" value="{preview_mode}">
        <div class="row"><div class="label">dX</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dx', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dx" name="dx" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dx', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="row"><div class="label">dY</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dy', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dy" name="dy" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dy', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="row"><div class="label">dW</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dw', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dw" name="dw" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dw', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="row"><div class="label">dH</div><div class="adjust"><button class="mini" type="button" onclick="nudgeAndSubmit('dh', -1)" {"disabled" if box_controls_disabled else ""}>-</button><input id="dh" name="dh" placeholder="+3 or -10" {"disabled" if box_controls_disabled else ""}><button class="mini" type="button" onclick="nudgeAndSubmit('dh', 1)" {"disabled" if box_controls_disabled else ""}>+</button></div></div>
        <div class="button-row"><button type="submit" {"disabled" if box_controls_disabled else ""}>Submit</button></div>
      </form>

      <div class="section">
        <div class="row"><div class="label">Font</div><div class="value">{font["family"]}</div></div>
        <div class="row"><div class="label">Font H</div><div class="value">{font["h"]}</div></div>
        <div class="row"><div class="label">size_px</div><div class="value">{font["size_px"]}</div></div>
        <div class="row"><div class="label">fX</div><div class="value">{font["offset_x"]}</div></div>
        <div class="row"><div class="label">fY</div><div class="value">{font["offset_y"]}</div></div>
        <form id="font-update-form" method="post" action="/update-font">
          <input type="hidden" name="job_id" value="{job_id}">
          <input type="hidden" name="candidate_index" value="{candidate_index}">
          <input type="hidden" name="preview_mode" value="font">
          <div class="row"><div class="label">dH</div><div class="adjust"><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_dh', -1)" {"disabled" if font_controls_disabled else ""}>-</button><input id="font_dh" name="dh" placeholder="+1 or -1" {"disabled" if font_controls_disabled else ""}><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_dh', 1)" {"disabled" if font_controls_disabled else ""}>+</button></div></div>
          <div class="row"><div class="label">f dX</div><div class="adjust"><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdx', -1)" {"disabled" if font_controls_disabled else ""}>-</button><input id="font_fdx" name="fdx" placeholder="+1 or -1" {"disabled" if font_controls_disabled else ""}><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdx', 1)" {"disabled" if font_controls_disabled else ""}>+</button></div></div>
          <div class="row"><div class="label">f dY</div><div class="adjust"><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdy', -1)" {"disabled" if font_controls_disabled else ""}>-</button><input id="font_fdy" name="fdy" placeholder="+1 or -1" {"disabled" if font_controls_disabled else ""}><button class="mini" type="button" onclick="fontNudgeAndSubmit('font_fdy', 1)" {"disabled" if font_controls_disabled else ""}>+</button></div></div>
          <div class="button-row two">
            <button type="submit" {"disabled" if font_controls_disabled else ""}>Apply Font</button>
            <button class="button-secondary" type="button" onclick="openFontChooser()" {"disabled" if font_controls_disabled else ""}>Choose Font</button>
          </div>
        </form>
      </div>

      <div class="section">
        <div class="row"><div class="label">Background</div><div class="value">{int(font.get("background_gray", 255))}</div></div>
        <form method="post" action="/set-bg" style="margin: 10px 0;">
          <input type="hidden" name="job_id" value="{job_id}">
          <input type="hidden" name="candidate_index" value="{candidate_index}">
          <input type="hidden" name="preview_mode" value="font">
          <div class="row">
            <div class="label">Value</div>
            <div class="adjust" style="grid-template-columns: 1fr 80px;">
              <input name="bg_value" value="{int(font.get("background_gray", 255))}" placeholder="0–255">
              <button type="submit" style="border-radius: 8px; padding: 10px 0;">Set</button>
            </div>
          </div>
        </form>
        <form id="bg-form" method="post" action="/update-bg">
          <input type="hidden" name="job_id" value="{job_id}">
          <input type="hidden" name="candidate_index" value="{candidate_index}">
          <input type="hidden" name="preview_mode" value="font">
          <input type="hidden" id="bg_direction" name="bg_direction" value="lighter">
          <div class="row">
            <div class="label">Step</div>
            <input id="bg_step" name="bg_step" value="10" placeholder="e.g. 10">
          </div>
          <div class="button-row two" style="margin-top:10px;">
            <button type="button" onclick="submitBg('darker')">Darker</button>
            <button type="button" onclick="submitBg('lighter')">Lighter</button>
          </div>
        </form>
        <form method="post" action="/set-bg" style="margin-top:8px;">
          <input type="hidden" name="job_id" value="{job_id}">
          <input type="hidden" name="candidate_index" value="{candidate_index}">
          <input type="hidden" name="preview_mode" value="font">
          <input type="hidden" name="bg_value" value="255">
          <div class="button-row">
            <button class="button-secondary" type="submit">Reset to White</button>
          </div>
        </form>
      </div>

      <form method="post" action="/undo">
        <input type="hidden" name="job_id" value="{job_id}">
        <input type="hidden" name="candidate_index" value="{candidate_index}">
        <input type="hidden" name="preview_mode" value="{preview_mode}">
        <div class="button-row" style="margin-top:20px;">
          <button class="button-secondary" type="submit">Undo</button>
        </div>
      </form>
    </div>
  </div>

  <form id="set-font-form" method="post" action="/set-font" style="display:none;">
    <input type="hidden" name="job_id" value="{job_id}">
    <input type="hidden" name="candidate_index" value="{candidate_index}">
    <input type="hidden" name="preview_mode" value="font">
    <input type="hidden" name="font_family" value="">
  </form>

  <div id="chooser-backdrop" class="modal-backdrop">
    <div class="modal">
      <h2>Choose Font</h2>
      <div id="chooser-actions" class="modal-actions"></div>
      <div class="button-row" style="margin-top:14px;">
        <button class="button-secondary" type="button" onclick="closeChooser()">Cancel</button>
      </div>
    </div>
  </div>

  <script>
    const fontChoices = {json.dumps(font_choices)};

    function nudgeAndSubmit(id, amount) {{
      document.getElementById(id).value = String(amount);
      document.getElementById('update-form').submit();
    }}

    function fontNudgeAndSubmit(id, amount) {{
      document.getElementById(id).value = String(amount);
      document.getElementById('font-update-form').submit();
    }}

    function submitBg(direction) {{
      document.getElementById('bg_direction').value = direction;
      document.getElementById('bg-form').submit();
    }}

    function closeChooser() {{
      document.getElementById('chooser-backdrop').style.display = 'none';
      document.getElementById('chooser-actions').innerHTML = '';
    }}

    function openFontChooser() {{
      const actions = document.getElementById('chooser-actions');
      actions.innerHTML = '';
      for (const family of fontChoices) {{
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.style.cssText = 'display:flex;align-items:center;gap:12px;text-align:left;padding:8px 12px;';
        const img = document.createElement('img');
        img.src = `/font-preview.png?family=${{encodeURIComponent(family)}}`;
        img.style.cssText = 'width:110px;height:36px;flex-shrink:0;';
        const label = document.createElement('span');
        label.textContent = family;
        label.style.cssText = 'font-size:12px;color:#888;white-space:nowrap;';
        btn.appendChild(img);
        btn.appendChild(label);
        btn.onclick = () => {{
          document.querySelector('#set-font-form input[name="font_family"]').value = family;
          document.getElementById('set-font-form').submit();
        }};
        actions.appendChild(btn);
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
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}/?job=<job_id>")
    server.serve_forever()


if __name__ == "__main__":
    main()
