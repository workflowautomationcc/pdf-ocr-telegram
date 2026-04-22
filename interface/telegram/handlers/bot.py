from dotenv import load_dotenv
load_dotenv()

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

import requests
import json
import re
import shutil
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from processors.pdf.pdf_splitter import split_pdf_to_images
from processors.pdf.pdf_combiner import main as combine_pdf
from processors.templates.price_overlay_processor import main as overlay_main
from processors.templates.template_matcher import find_matching_template
from interface.telegram.handlers.unknown_handler import (
    start_unknown_flow,
    handle_unknown_message,
    handle_unknown_callback,
    resend_current_prompt,
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

JOBS_BASE_FOLDER = os.path.join(BASE_DIR, "data/jobs")
TEMPLATES_DIR = os.path.join(BASE_DIR, "data/templates")
LOG_FILE = os.path.join(BASE_DIR, "data/logs/jobs.json")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = 1503596202

BOT_REPLIES_FILE = os.path.join(BASE_DIR, "data/bot_replies.json")

def load_bot_replies():
    if not os.path.exists(BOT_REPLIES_FILE):
        return []
    with open(BOT_REPLIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("replies", [])

FALLBACK_REPLY = "I'm not much of a conversationalist 😄 But send me a broker PDF and I'll update the price in seconds."

def match_bot_reply(text):
    text_lower = text.lower().strip()
    for entry in load_bot_replies():
        for keyword in entry.get("keywords", []):
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                return entry["reply"]
    return FALLBACK_REPLY

LIMIT_PER_MINUTE = 10
LIMIT_PER_HOUR   = 30
LIMIT_PER_DAY    = 60
SHUTDOWN_HOURS   = 24

job_timestamps = []
shutdown_until = None

user_jobs = {}


def log_job(status, job_id):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    entry = {
        "job_id": job_id,
        "timestamp": datetime.now().isoformat(),
        "status": status
    }

    data = []

    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    if not isinstance(data, list):
                        data = []
        except Exception:
            data = []

    data.append(entry)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_valid_price(text):
    text = text.strip()

    if not text:
        return False

    if re.search(r"[^\d,.\s]", text):
        return False

    if text.count(".") > 1:
        return False

    if ",," in text:
        return False

    if " " in text:
        parts = text.split(" ")
        if len(parts) != 2:
            return False

        left, right = parts

        if not (left.isdigit() and right.isdigit()):
            return False

        if not (1 <= len(left) <= 3 and len(right) == 3):
            return False

    return True


def normalize_price(text):
    cleaned = text.replace(" ", "").replace(",", "")

    try:
        value = float(cleaned)
        return value
    except:
        return None


def generate_job_id(chat_id):
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{now}_{chat_id}"


async def try_process(chat_id, message):
    job = user_jobs.get(chat_id)

    if not job:
        return False

    if "pdf_path" not in job or "price" not in job:
        return False

    pdf_path = job["pdf_path"]
    png_job_folder = job["png_job_folder"]
    job_id = job["job_id"]
    price = job["price"]
    original_filename = job.get("original_filename", "file.pdf")
    stem = os.path.splitext(original_filename)[0]
    output_filename = stem + "_.pdf"

    user_jobs.pop(chat_id)

    await message.reply_text("Processing file, please wait...", reply_markup=ReplyKeyboardRemove())

    try:
        input_images_folder = png_job_folder
        output_images_folder = os.path.join(JOBS_BASE_FOLDER, job_id, "output", "images")

        os.makedirs(output_images_folder, exist_ok=True)

        image_paths = split_pdf_to_images(pdf_path, input_images_folder)
        page_1_path = image_paths[0]

        EDEN_API_KEY = os.getenv("EDEN_AI_API_KEY")
        url = "https://api.edenai.run/v2/ocr/ocr"

        with open(page_1_path, "rb") as f:
            files = {"file": f}
            headers = {"Authorization": f"Bearer {EDEN_API_KEY}"}
            data = {"providers": "google", "language": "en"}

            response = requests.post(url, headers=headers, files=files, data=data)

        ocr_result = response.json()

        template = find_matching_template(ocr_result, TEMPLATES_DIR)

        if not template:
            log_job("failed", job_id)
            from PIL import Image as _Image
            with _Image.open(page_1_path) as _img:
                _pw, _ph = _img.size
            user_jobs[chat_id] = {
                "unknown_job_id": job_id,
                "unknown_state": "awaiting_current_price",
                "original_filename": original_filename,
            }
            await start_unknown_flow(
                job_id, ocr_result, page_1_path,
                page_width=_pw, page_height=_ph,
                message=message,
            )
            return

        for file_name in os.listdir(input_images_folder):
            src = os.path.join(input_images_folder, file_name)
            dst = os.path.join(output_images_folder, file_name)

            if os.path.isfile(src):
                with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                    fdst.write(fsrc.read())

        overlay_main(output_images_folder, price, template)

        output_pdf_path = os.path.join(JOBS_BASE_FOLDER, job_id, "output", "final.pdf")

        combine_pdf(output_images_folder)

        temp_output = os.path.join(output_images_folder, "final.pdf")

        if os.path.exists(temp_output):
            os.rename(temp_output, output_pdf_path)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Looks good", callback_data=f"known_good|{job_id}"),
                InlineKeyboardButton("🔧 Needs fixing", callback_data=f"known_fix|{job_id}"),
            ],
            [
                InlineKeyboardButton("📩 Support", callback_data=f"known_support|{job_id}"),
            ],
        ])
        with open(output_pdf_path, "rb") as f:
            await message.reply_document(
                document=f,
                filename=output_filename,
                caption="Updated file",
                reply_markup=keyboard,
            )

        log_job("success", job_id)

        user_jobs[chat_id] = {
            "fixing_job_id": job_id,
            "fixing_template": template,
            "fixing_price": price,
            "fixing_input_folder": input_images_folder,
            "fixing_output_folder": output_images_folder,
            "field_offsets": {},
            "current_field_idx": 0,
            "original_filename": original_filename,
            "started_at": datetime.now(),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Error:", e)
        log_job("failed", job_id)

    return True


SHIFT_STEP = 5

def field_selection_keyboard(job_id, fields):
    buttons = []
    for i, field in enumerate(fields):
        buttons.append([InlineKeyboardButton(f"Adjust Price {i+1}", callback_data=f"known_select_{i}|{job_id}")])
    buttons.append([InlineKeyboardButton("✅ Send PDF", callback_data=f"known_apply|{job_id}")])
    return InlineKeyboardMarkup(buttons)

def adjustment_keyboard(job_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️5", callback_data=f"known_shift_up5|{job_id}"),
            InlineKeyboardButton("⬆️1", callback_data=f"known_shift_up1|{job_id}"),
            InlineKeyboardButton("⬇️1", callback_data=f"known_shift_down1|{job_id}"),
            InlineKeyboardButton("⬇️5", callback_data=f"known_shift_down5|{job_id}"),
        ],
        [
            InlineKeyboardButton("⬅️5", callback_data=f"known_shift_left5|{job_id}"),
            InlineKeyboardButton("⬅️1", callback_data=f"known_shift_left1|{job_id}"),
            InlineKeyboardButton("➡️1", callback_data=f"known_shift_right1|{job_id}"),
            InlineKeyboardButton("➡️5", callback_data=f"known_shift_right5|{job_id}"),
        ],
        [
            InlineKeyboardButton("➕5", callback_data=f"known_shift_taller5|{job_id}"),
            InlineKeyboardButton("➕1", callback_data=f"known_shift_taller1|{job_id}"),
            InlineKeyboardButton("➖1", callback_data=f"known_shift_shorter1|{job_id}"),
            InlineKeyboardButton("➖5", callback_data=f"known_shift_shorter5|{job_id}"),
        ],
        [InlineKeyboardButton("✅ Done with this price", callback_data=f"known_field_done|{job_id}")],
    ])


def draw_price_labels(image, template, field_offsets):
    from PIL import ImageDraw as _Draw, ImageFont as _Font
    img = image.copy()
    draw = _Draw.Draw(img)
    font_dir = os.path.join(BASE_DIR, "data/fonts")
    label_size = max(20, int(img.size[1] * 0.018))
    try:
        font = _Font.truetype(os.path.join(font_dir, "Arial.ttf"), label_size)
    except Exception:
        font = _Font.load_default()
    for i, field in enumerate(template["price_fields"]):
        fo = (field_offsets or {}).get(i, {"x": 0, "y": 0})
        x = int(round(field["x"] + fo.get("x", 0)))
        y = int(round(field["y"] + fo.get("y", 0)))
        w = int(round(field["w"]))
        h = int(round(field["h"]))
        label = str(i + 1)
        bbox = font.getbbox(label)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 4
        offset = 30
        lx, ly = max(0, x - lw - pad * 2 - offset), y + (h - lh - pad * 2) // 2
        draw.rectangle([lx, ly, lx + lw + pad * 2, ly + lh + pad * 2], fill="red")
        draw.text((lx + pad, ly + pad), label, fill="white", font=font)
    return img


async def send_adjustment_preview(chat_id, job, job_id, message):
    from PIL import Image as _Image
    import io

    input_folder = job["fixing_input_folder"]
    output_folder = job["fixing_output_folder"]
    template = job["fixing_template"]
    price = job["fixing_price"]
    field_offsets = job.get("field_offsets", {})
    current_idx = job.get("current_field_idx", 0)
    fo = field_offsets.get(current_idx, {"x": 0, "y": 0})

    src = os.path.join(input_folder, "page_1.png")
    dst = os.path.join(output_folder, "page_1.png")
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "wb") as f:
        f.write(data)

    overlay_main(output_folder, price, template, field_offsets=field_offsets)

    clean_image = _Image.open(dst).convert("RGB")
    labeled = draw_price_labels(clean_image, template, field_offsets)
    buf = io.BytesIO()
    labeled.save(buf, format="PNG")
    buf.seek(0)

    field_name = f"Price {current_idx + 1}"
    h_off = fo.get("h", 0)
    await message.reply_photo(
        photo=buf,
        caption=f"Adjusting {field_name}\nX: {fo.get('x',0):+d}  Y: {fo.get('y',0):+d}  H: {h_off:+d}",
        reply_markup=adjustment_keyboard(job_id),
    )


async def finalize_known_with_offset(chat_id, job, job_id, message):
    input_folder = job["fixing_input_folder"]
    output_folder = job["fixing_output_folder"]
    template = job["fixing_template"]
    price = job["fixing_price"]
    original_filename = job.get("original_filename", "file.pdf")
    stem = os.path.splitext(original_filename)[0]
    output_filename = stem + "_.pdf"
    field_offsets = job.get("field_offsets", {})

    for fname in os.listdir(input_folder):
        src = os.path.join(input_folder, fname)
        dst = os.path.join(output_folder, fname)
        if os.path.isfile(src):
            with open(src, "rb") as f:
                data = f.read()
            with open(dst, "wb") as f:
                f.write(data)

    overlay_main(output_folder, price, template, field_offsets=field_offsets)

    output_pdf_path = os.path.join(JOBS_BASE_FOLDER, job_id, "output", "final.pdf")
    combine_pdf(output_folder)
    temp_output = os.path.join(output_folder, "final.pdf")
    if os.path.exists(temp_output):
        os.rename(temp_output, output_pdf_path)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Looks good", callback_data=f"known_good|{job_id}"),
            InlineKeyboardButton("🔧 Needs fixing", callback_data=f"known_fix|{job_id}"),
        ],
        [
            InlineKeyboardButton("📩 Support", callback_data=f"known_support|{job_id}"),
        ],
    ])
    with open(output_pdf_path, "rb") as f:
        await message.reply_document(document=f, filename=output_filename, caption="Updated file ✅", reply_markup=keyboard)


async def check_rate_limit(message, context):
    global shutdown_until, job_timestamps

    now = datetime.now()

    if shutdown_until and now < shutdown_until:
        remaining = int((shutdown_until - now).total_seconds() / 3600)
        await message.reply_text(
            f"System is temporarily unavailable. Try again in ~{remaining}h."
        )
        return False

    # Clean up timestamps older than 24h
    job_timestamps = [t for t in job_timestamps if now - t < timedelta(hours=24)]

    last_minute = sum(1 for t in job_timestamps if now - t < timedelta(seconds=60))
    last_hour   = sum(1 for t in job_timestamps if now - t < timedelta(hours=1))
    last_day    = len(job_timestamps)

    if last_day >= LIMIT_PER_DAY:
        shutdown_until = now + timedelta(hours=SHUTDOWN_HOURS)
        await message.reply_text("System is temporarily unavailable. Try again later.")
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"⚠️ Bot shut down for {SHUTDOWN_HOURS}h — daily job limit ({LIMIT_PER_DAY}) hit.\nResumes at {shutdown_until.strftime('%Y-%m-%d %H:%M')}."
        )
        return False

    if last_hour >= LIMIT_PER_HOUR:
        await message.reply_text("Too many jobs this hour. Please try again later.")
        return False

    if last_minute >= LIMIT_PER_MINUTE:
        await message.reply_text("Too many jobs right now. Please wait a minute.")
        return False

    job_timestamps.append(now)
    return True


JOB_TTL_SECONDS = 3600  # 1 hour


async def start_pdf_job(chat_id, pdf_path, png_job_folder, job_id, message, original_filename="file.pdf"):
    user_jobs[chat_id] = {
        "pdf_path": pdf_path,
        "png_job_folder": png_job_folder,
        "job_id": job_id,
        "original_filename": original_filename,
        "started_at": datetime.now(),
    }
    processed = await try_process(chat_id, message)
    if not processed:
        await message.reply_text("Send the price (e.g. 4200 or 4,200)", reply_markup=ReplyKeyboardRemove())


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.document:
        return

    document = message.document
    if not document.file_name.lower().endswith(".pdf"):
        return

    chat_id = message.chat_id
    job_id = generate_job_id(chat_id)

    job_folder = os.path.join(JOBS_BASE_FOLDER, job_id)
    pdf_job_folder = os.path.join(job_folder, "input", "pdf")
    png_job_folder = os.path.join(job_folder, "input", "images")

    os.makedirs(pdf_job_folder, exist_ok=True)
    os.makedirs(png_job_folder, exist_ok=True)

    pdf_path = os.path.join(pdf_job_folder, "input.pdf")

    telegram_file = await document.get_file()
    await telegram_file.download_to_drive(pdf_path)

    if len(user_jobs) >= 10:
        await message.reply_text("System is busy. Please try again in a moment.")
        return

    if not await check_rate_limit(message, context):
        return

    if chat_id in user_jobs:
        existing = user_jobs[chat_id]
        started_at = existing.get("started_at")
        expired = started_at is None or (datetime.now() - started_at).total_seconds() > JOB_TTL_SECONDS
        if expired:
            user_jobs.pop(chat_id)
        else:
            # Store new job details and ask for confirmation
            user_jobs[chat_id]["pending_pdf"] = {
                "pdf_path": pdf_path,
                "png_job_folder": png_job_folder,
                "job_id": job_id,
                "original_filename": document.file_name,
            }
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Yes, start new", callback_data="new_job_confirm|yes"),
                InlineKeyboardButton("No, keep current", callback_data="new_job_confirm|no"),
            ]])
            await message.reply_text(
                "You have an active job. Start a new one and discard the current?",
                reply_markup=keyboard,
            )
            return

    await start_pdf_job(chat_id, pdf_path, png_job_folder, job_id, message, document.file_name)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat_id = message.chat_id
    raw_input = message.text.strip()

    # Cancel shortcut
    if raw_input.lower() == "cancel":
        if chat_id not in user_jobs:
            return
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes, cancel", callback_data="cancel_confirm|yes"),
            InlineKeyboardButton("No, keep going", callback_data="cancel_confirm|no"),
        ]])
        await message.reply_text(
            "Are you sure you want to cancel the current job?",
            reply_markup=keyboard,
        )
        return

    # Support description flow
    job = user_jobs.get(chat_id, {})
    if job.get("awaiting_support_description"):
        job.pop("awaiting_support_description")
        support_job_id = job.get("support_job_id", "")
        template = job.get("fixing_template", {})
        price = job.get("fixing_price", "?")
        template_name = template.get("template", "unknown")
        output_pdf_path = os.path.join(JOBS_BASE_FOLDER, support_job_id, "output", "final.pdf")
        user = message.from_user
        user_info = f"@{user.username}" if user.username else f"ID {user.id}"
        caption = f"⚠️ Support request\nUser: {user_info}\nTemplate: {template_name}\nPrice entered: {price}\nIssue: {raw_input}"
        if os.path.exists(output_pdf_path):
            with open(output_pdf_path, "rb") as f:
                await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=f, caption=caption)
        else:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=caption + "\n(PDF not found)")
        await message.reply_text("Sent to support. Someone will follow up with you shortly.")
        return

    # Unknown template flow takes priority
    job = user_jobs.get(chat_id, {})
    if job.get("unknown_state"):
        job_id = job.get("unknown_job_id")
        handled = await handle_unknown_message(job_id, user_jobs, raw_input, message, context)
        if handled:
            return

    # Static replies for common questions
    if chat_id not in user_jobs:
        reply = match_bot_reply(raw_input)
        if reply:
            await message.reply_text(reply)
        return

    if not is_valid_price(raw_input):
        await message.reply_text("Invalid format. Use 4200, 4,200 or 4 200")
        return

    normalized = normalize_price(raw_input)

    if not normalized:
        await message.reply_text("Invalid number, try again")
        return

    user_jobs[chat_id]["price"] = normalized

    await try_process(chat_id, message)



async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if "|" not in data:
        return

    action, payload = data.split("|", 1)
    chat_id = query.message.chat_id

    # Check if button belongs to the current active job — if not, ignore it
    if action not in ("cancel_confirm", "new_job_confirm"):
        job = user_jobs.get(chat_id, {})
        active_job_id = job.get("unknown_job_id") or job.get("fixing_job_id")
        if payload != active_job_id:
            await query.answer("This session has expired.")
            return

    if action == "cancel_confirm":
        await query.answer()
        if payload == "yes":
            user_jobs.pop(chat_id, None)
            await query.edit_message_text("Job cancelled. Send a new PDF to start again.")
        else:
            await query.edit_message_text("OK, your job is still active.")
        return

    if action == "new_job_confirm":
        await query.answer()
        if payload == "yes":
            pending = user_jobs.get(chat_id, {}).pop("pending_pdf", None)
            if not pending:
                await query.edit_message_text("Something went wrong. Please send the file again.")
                return
            await query.edit_message_text("Starting new job...")
            await start_pdf_job(
                chat_id,
                pending["pdf_path"],
                pending["png_job_folder"],
                pending["job_id"],
                query.message,
                pending.get("original_filename", "file.pdf"),
            )
        else:
            user_jobs.get(chat_id, {}).pop("pending_pdf", None)
            await query.edit_message_text("OK, continuing your current job.")
            job = user_jobs.get(chat_id, {})
            if job.get("fixing_job_id"):
                fixing_job_id = job["fixing_job_id"]
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Looks good", callback_data=f"known_good|{fixing_job_id}"),
                    InlineKeyboardButton("🔧 Needs fixing", callback_data=f"known_fix|{fixing_job_id}"),
                ]])
                await query.message.reply_text("Here's where we left off:", reply_markup=keyboard)
            else:
                await resend_current_prompt(chat_id, user_jobs, query.message)
        return

    job_id = payload

    if action == "known_good":
        await query.answer("Great!")
        user_jobs.pop(chat_id, None)
        job_folder = os.path.join(JOBS_BASE_FOLDER, job_id)
        if os.path.exists(job_folder):
            shutil.rmtree(job_folder)
        return

    if action == "known_support":
        await query.answer()
        job = user_jobs.get(chat_id, {})
        job["support_job_id"] = job_id
        job["awaiting_support_description"] = True
        await query.message.reply_text("Please describe the issue and I'll forward it to support.")
        return

    if action == "known_fix":
        await query.answer()
        job = user_jobs.get(chat_id, {})
        fields = job["fixing_template"]["price_fields"]
        await query.message.reply_text(
            "Which price needs adjusting?",
            reply_markup=field_selection_keyboard(job_id, fields),
        )
        return

    if action.startswith("known_select_"):
        await query.answer()
        idx = int(action.split("_")[-1])
        job = user_jobs.get(chat_id, {})
        job["current_field_idx"] = idx
        if idx not in job["field_offsets"]:
            job["field_offsets"][idx] = {"x": 0, "y": 0, "h": 0}
        await send_adjustment_preview(chat_id, job, job_id, query.message)
        return

    if action.startswith("known_shift_"):
        await query.answer()
        job = user_jobs.get(chat_id, {})
        idx = job.get("current_field_idx", 0)
        fo = job["field_offsets"].setdefault(idx, {"x": 0, "y": 0, "h": 0})
        shifts = {
            "known_shift_up5":       ("y", -5),
            "known_shift_up1":       ("y", -1),
            "known_shift_down1":     ("y",  1),
            "known_shift_down5":     ("y",  5),
            "known_shift_left5":     ("x", -5),
            "known_shift_left1":     ("x", -1),
            "known_shift_right1":    ("x",  1),
            "known_shift_right5":    ("x",  5),
            "known_shift_taller5":   ("h",  5),
            "known_shift_taller1":   ("h",  1),
            "known_shift_shorter1":  ("h", -1),
            "known_shift_shorter5":  ("h", -5),
        }
        if action in shifts:
            key, delta = shifts[action]
            fo[key] = fo.get(key, 0) + delta
        await send_adjustment_preview(chat_id, job, job_id, query.message)
        return

    if action == "known_field_done":
        await query.answer()
        job = user_jobs.get(chat_id, {})
        fields = job["fixing_template"]["price_fields"]
        await query.message.reply_text(
            "Adjust another price or send the PDF.",
            reply_markup=field_selection_keyboard(job_id, fields),
        )
        return

    if action == "known_apply":
        await query.answer()
        job = user_jobs.get(chat_id, {})
        await finalize_known_with_offset(chat_id, job, job_id, query.message)
        return

    if action.startswith("unknown_"):
        await handle_unknown_callback(query, job_id, action, user_jobs, context)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Bot listening...")
    app.run_polling()


if __name__ == "__main__":
    main()