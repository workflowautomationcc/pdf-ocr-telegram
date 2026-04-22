"""
Handles the full unknown template flow:
- Saves OCR + PNG for the job
- Walks user through identifying prices to replace
- Renders PDF using OCR coordinates
- Offers fine-tune UI link with 60s cleanup timer + reprocess
"""

import asyncio
import json
import re
import shutil
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from processors.templates.price_overlay_processor import fit_font_to_height, format_price
from processors.pdf.pdf_combiner import main as combine_pdf
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parents[3]
UNKNOWN_TEMPLATES_DIR = BASE_DIR / "data" / "unknown_templates"
OUTPUT_BASE = BASE_DIR / "data" / "jobs"
FONT_DIR = BASE_DIR / "data" / "fonts"
UNKNOWN_UI_PORT = 8002
CLEANUP_SECONDS = 7200  # 2 hours
COMMA_COEFF = 2


def normalize_price_text(text):
    return re.sub(r"[^0-9.]", "", text.strip())


def find_currency_prefix(ocr_boxes, price_box_raw, page_width, page_height):
    px = price_box_raw["left"]
    py = price_box_raw["top"]
    ph = price_box_raw["height"]
    for box in ocr_boxes:
        text = box.get("text", "").strip().upper()
        if text not in ("$", "USD"):
            continue
        if abs(box["top"] - py) > ph * 0.5:
            continue
        gap = px - (box["left"] + box["width"])
        if 0 <= gap <= 0.03:
            return {
                "x": round(box["left"] * page_width, 2),
                "y": round(box["top"] * page_height, 2),
                "w": round(box["width"] * page_width, 2),
                "h": round(box["height"] * page_height, 2),
                "text": box["text"],
            }
    return None


def find_price_in_ocr(ocr_boxes, price_text, page_width, page_height):
    if ":" in price_text:
        return None
    target = normalize_price_text(price_text)
    try:
        target_val = float(target)
    except ValueError:
        target_val = None
    results = []
    for box in ocr_boxes:
        raw_text = box.get("text", "")
        if ":" in raw_text:
            continue
        normalized = normalize_price_text(raw_text)
        try:
            box_val = float(normalized) if normalized else None
        except ValueError:
            box_val = None
        if normalized == target or (target_val is not None and box_val is not None and target_val == box_val):
            prefix = find_currency_prefix(ocr_boxes, box, page_width, page_height)
            bx = round(box["left"] * page_width, 2)
            by = round(box["top"] * page_height, 2)
            bw = round(box["width"] * page_width, 2)
            bh = round(box["height"] * page_height, 2)
            results.append({
                "x": bx, "y": by, "w": bw, "h": bh,
                "text": box["text"],
                "prefix": prefix,
            })
    return results if results else None


def save_job_data(job_id, ocr_result, png_path, page_width, page_height):
    job_dir = UNKNOWN_TEMPLATES_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with open(job_dir / "ocr.json", "w", encoding="utf-8") as f:
        json.dump(ocr_result, f, indent=2)

    shutil.copy2(png_path, job_dir / "page_1.png")

    # candidates-format fine_tuning.json (empty candidates to start)
    ft = {
        "template": job_id,
        "page_width": page_width,
        "page_height": page_height,
        "candidates": []
    }
    with open(job_dir / "fine_tuning.json", "w", encoding="utf-8") as f:
        json.dump(ft, f, indent=2)

    return job_dir


def load_fine_tuning(job_id):
    path = UNKNOWN_TEMPLATES_DIR / job_id / "fine_tuning.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_fine_tuning(job_id, data):
    path = UNKNOWN_TEMPLATES_DIR / job_id / "fine_tuning.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_ocr(job_id):
    with open(UNKNOWN_TEMPLATES_DIR / job_id / "ocr.json") as f:
        return json.load(f)


def add_candidates(job_id, boxes, new_value):
    ft = load_fine_tuning(job_id)
    next_id = len(ft["candidates"]) + 1
    for box in boxes:
        bx, by, bw, bh = box["x"], box["y"], box["w"], box["h"]
        ft["candidates"].append({
            "id": next_id,
            "text": box["text"],
            "new_value": new_value,
            "prefix": box.get("prefix"),
            "box": {"x": bx, "y": by, "w": bw, "h": bh},
            "font": {
                "family": "Arial",
                "color": "#000000",
                "x": bx, "y": by, "w": bw, "h": bh,
                "offset_x": 0.0, "offset_y": 0.0,
                "size_px": 24,
            }
        })
        next_id += 1
    save_fine_tuning(job_id, ft)


def render_from_fine_tuning(job_id):
    ft = load_fine_tuning(job_id)
    job_dir = UNKNOWN_TEMPLATES_DIR / job_id
    png_path = job_dir / "page_1.png"

    image = Image.open(png_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    for candidate in ft["candidates"]:
        box = candidate["box"]
        font_data = candidate["font"]
        new_value = candidate["new_value"]
        prefix = candidate.get("prefix")

        x = int(round(font_data["x"] + font_data.get("offset_x", 0)))
        y = int(round(font_data["y"] + font_data.get("offset_y", 0)))
        w = int(round(font_data["w"]))
        h = int(round(font_data["h"]))

        original_has_comma = "," in candidate["text"]
        new_has_comma = float(new_value) >= 1000
        adjusted_h = h
        if original_has_comma and not new_has_comma:
            adjusted_h = h - COMMA_COEFF
        elif not original_has_comma and new_has_comma:
            adjusted_h = h + COMMA_COEFF

        SCALE = 4
        bg = int(max(0, min(255, font_data.get("background_gray", 255))))
        draw.rectangle([x, y - 2, x + w + 2, y + h + 5], fill=(bg, bg, bg))

        formatted = format_price(float(new_value), {
            "currency_symbol": "",
            "thousands_separator": ",",
            "decimal_separator": ".",
            "decimal_places": 2
        })

        # Render text at 4x scale then downsample for crisp antialiasing
        font_hi = fit_font_to_height(font_data["family"], adjusted_h * SCALE, candidate["text"])
        tile_w = (w + 4) * SCALE
        tile_h = (h + 7) * SCALE
        tile = Image.new("RGB", (tile_w, tile_h), (bg, bg, bg))
        tile_draw = ImageDraw.Draw(tile)
        tb = font_hi.getbbox(formatted)
        tw = tb[2] - tb[0]
        tile_draw.text(
            (tile_w - tw - tb[0], -tb[1]),
            formatted,
            fill=font_data.get("color", "#000000"),
            font=font_hi,
        )
        tile = tile.resize((w + 4, h + 7), Image.LANCZOS)
        image.paste(tile, (x, y - 2))

    output_dir = job_dir / "output"
    output_dir.mkdir(exist_ok=True)
    out_png = output_dir / "page_1.png"
    image.save(out_png, dpi=(300, 300))

    combine_pdf(str(output_dir))

    final_pdf = output_dir / "final.pdf"
    output_pdf_dir = OUTPUT_BASE / job_id / "output"
    output_pdf_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_pdf_dir / "final.pdf"
    if final_pdf.exists():
        shutil.move(str(final_pdf), str(output_pdf))

    return output_pdf


def cleanup_job(job_id):
    job_dir = UNKNOWN_TEMPLATES_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    output_dir = OUTPUT_BASE / job_id
    if output_dir.exists():
        shutil.rmtree(output_dir)


async def schedule_cleanup(job_id, seconds=CLEANUP_SECONDS):
    await asyncio.sleep(seconds)
    cleanup_job(job_id)


def draw_preview_image(job_id, boxes):
    """Draw numbered red rectangles on page_1.png and return path to preview image."""
    job_dir = UNKNOWN_TEMPLATES_DIR / job_id
    src = job_dir / "page_1.png"
    out = job_dir / "preview.png"

    image = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(image)

    img_w, img_h = image.size
    label_size = max(20, int(img_h * 0.018))

    try:
        font = ImageFont.truetype(str(FONT_DIR / "Arial.ttf"), label_size)
    except Exception:
        font = ImageFont.load_default()

    for i, box in enumerate(boxes):
        x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
        # Red rectangle
        draw.rectangle([x, y, x + w, y + h], outline="red", width=3)
        # Label background + number
        label = str(i + 1)
        bbox = font.getbbox(label)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 4
        lx, ly = max(0, x - lw - pad * 2), max(0, y - lh - pad * 2)
        draw.rectangle([lx, ly, lx + lw + pad * 2, ly + lh + pad * 2], fill="red")
        draw.text((lx + pad, ly + pad), label, fill="white", font=font)

    image.save(out)
    return out


# --- Bot interaction steps ---

async def start_unknown_flow(job_id, ocr_result, png_path, page_width, page_height, message):
    save_job_data(job_id, ocr_result, png_path, page_width, page_height)
    await message.reply_text(
        "Template not recognized.\n\nPlease provide the current Price 1 that needs changing."
    )


async def _ask_confirm(chat_id, user_jobs, job_id, message):
    """Send a Yes/No prompt for the current box being confirmed."""
    idx = user_jobs[chat_id]["confirm_idx"]
    boxes = user_jobs[chat_id]["pending_boxes"]
    box = boxes[idx]
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"Yes — replace ID {idx + 1}", callback_data=f"unknown_confirm_yes|{job_id}"),
        InlineKeyboardButton("No — skip", callback_data=f"unknown_confirm_no|{job_id}"),
    ]])
    await message.reply_text(
        f"ID {idx + 1} of {len(boxes)}: \"{box['text']}\" — should this be replaced?",
        reply_markup=keyboard
    )


async def resend_current_prompt(chat_id, user_jobs, message):
    """Re-send whatever the bot last asked, based on current state."""
    job = user_jobs.get(chat_id, {})
    state = job.get("unknown_state")
    job_id = job.get("unknown_job_id")

    if not state:
        # Known-template flow — waiting for price
        await message.reply_text("Send the price (e.g. 4200 or 4,200)")
        return

    if state == "awaiting_current_price":
        ft = load_fine_tuning(job_id)
        price_count = len(ft["candidates"]) if ft else 0
        await message.reply_text(
            f"Please provide the current Price {price_count + 1} that needs changing."
        )

    elif state == "confirming_boxes":
        await _ask_confirm(chat_id, user_jobs, job_id, message)

    elif state == "awaiting_new_price":
        ft = load_fine_tuning(job_id)
        price_count = len(ft["candidates"]) if ft else 0
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("All done ✓", callback_data=f"unknown_done|{job_id}")
        ]])
        await message.reply_text(
            f"What should Price {price_count + 1} be replaced with?",
            reply_markup=keyboard,
        )


async def handle_unknown_message(job_id, user_jobs, text, message, context):
    chat_id = message.chat_id
    state = user_jobs.get(chat_id, {}).get("unknown_state")
    ft = load_fine_tuning(job_id)
    if ft is None:
        return False

    ocr = load_ocr(job_id)
    ocr_boxes = ocr.get("google", {}).get("bounding_boxes", [])
    page_width = ft["page_width"]
    page_height = ft["page_height"]
    price_count = len(ft["candidates"])

    if state == "awaiting_current_price":
        boxes = find_price_in_ocr(ocr_boxes, text, page_width, page_height)
        if not boxes:
            await message.reply_text(
                f"Could not find \"{text}\" on the page. Please check and try again."
            )
            return True

        preview_path = draw_preview_image(job_id, boxes)
        user_jobs[chat_id]["pending_boxes"] = boxes
        user_jobs[chat_id]["confirm_idx"] = 0
        user_jobs[chat_id]["confirmed_boxes"] = []
        user_jobs[chat_id]["unknown_state"] = "confirming_boxes"

        with open(preview_path, "rb") as f:
            await message.reply_photo(
                photo=f,
                caption=f"Found {len(boxes)} occurrence(s). Please confirm each one."
            )

        await _ask_confirm(chat_id, user_jobs, job_id, message)
        return True

    if state == "confirming_boxes":
        idx = user_jobs[chat_id].get("confirm_idx", 0)
        total = len(user_jobs[chat_id].get("pending_boxes", []))
        await message.reply_text(
            f"Please use the buttons above to confirm ID {idx + 1} of {total}."
        )
        return True

    if state == "awaiting_new_price":
        try:
            float(text.replace(",", ""))
        except ValueError:
            await message.reply_text("Invalid price. Please enter a number like 1200 or 1,200.00")
            return True

        boxes = user_jobs[chat_id].pop("pending_boxes")
        add_candidates(job_id, boxes, text.replace(",", ""))

        ft = load_fine_tuning(job_id)
        price_count = len(ft["candidates"])
        user_jobs[chat_id]["unknown_state"] = "awaiting_current_price"

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("All done ✓", callback_data=f"unknown_done|{job_id}")
        ]])
        await message.reply_text(
            f"Got it. Any more prices to change? (Price {price_count + 1})\n\nSend the current price or tap All done.\n\nType Cancel to reset.",
            reply_markup=keyboard
        )
        return True

    return False


async def finalize_unknown(job_id, chat_id, user_jobs, message, context):
    await message.reply_text("Processing, please wait...")

    try:
        output_pdf = render_from_fine_tuning(job_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await message.reply_text(f"Error rendering: {e}")
        return

    import os as _os
    original_filename = user_jobs.get(chat_id, {}).get("original_filename", "file.pdf")
    stem = _os.path.splitext(original_filename)[0]
    output_filename = stem + "_.pdf"

    with open(output_pdf, "rb") as f:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Looks good", callback_data=f"unknown_good|{job_id}"),
            InlineKeyboardButton("✗ I don't like it", callback_data=f"unknown_bad|{job_id}"),
        ]])
        await message.reply_document(
            document=f,
            filename=output_filename,
            caption="Here is your file.",
            reply_markup=keyboard
        )


async def handle_unknown_callback(query, job_id, action, user_jobs, context):
    chat_id = query.message.chat_id

    if action == "unknown_done":
        await query.answer()
        await finalize_unknown(job_id, chat_id, user_jobs, query.message, context)

    elif action == "unknown_good":
        await query.answer("Great!")
        cleanup_job(job_id)
        user_jobs.pop(chat_id, None)

    elif action in ("unknown_confirm_yes", "unknown_confirm_no"):
        await query.answer()
        job = user_jobs.get(chat_id, {})
        boxes = job.get("pending_boxes", [])
        idx = job.get("confirm_idx", 0)

        if action == "unknown_confirm_yes":
            job.setdefault("confirmed_boxes", []).append(boxes[idx])

        idx += 1
        job["confirm_idx"] = idx

        if idx < len(boxes):
            # More boxes to confirm
            await _ask_confirm(chat_id, user_jobs, job_id, query.message)
        else:
            confirmed = job.get("confirmed_boxes", [])
            if not confirmed:
                # None selected — go back
                job["unknown_state"] = "awaiting_current_price"
                job.pop("pending_boxes", None)
                job.pop("confirmed_boxes", None)
                job.pop("confirm_idx", None)
                await query.message.reply_text(
                    "No occurrences selected. Please send the current price again."
                )
            else:
                # Move to awaiting_new_price with only confirmed boxes
                ft = load_fine_tuning(job_id)
                price_count = len(ft["candidates"])
                job["pending_boxes"] = confirmed
                job["unknown_state"] = "awaiting_new_price"
                job.pop("confirmed_boxes", None)
                job.pop("confirm_idx", None)
                await query.message.reply_text(
                    f"Got it — {len(confirmed)} occurrence(s) confirmed.\n"
                    f"What should Price {price_count + 1} be replaced with?"
                )

    elif action == "unknown_bad":
        await query.answer()
        ui_link = f"http://finetune.gtxtransportlogistics.com:{UNKNOWN_UI_PORT}/?job={job_id}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Reprocess", callback_data=f"unknown_reprocess|{job_id}"),
        ]])
        await query.message.reply_text(
            f"The result needs adjusting. Copy the address below and open it in your browser on this computer:\n\n<code>{ui_link}</code>\n\nMake your changes there, then come back here and tap Reprocess.",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        asyncio.ensure_future(schedule_cleanup(job_id))

    elif action == "unknown_reprocess":
        await query.answer()
        await finalize_unknown(job_id, chat_id, user_jobs, query.message, context)
