# System Schematic

## Infrastructure

- **Server:** Hetzner Ubuntu 24.04, IP 89.167.91.131
- **Domain:** finetune.gtxtransportlogistics.com → points to server IP
- **Bot:** Telegram bot, token hardcoded in bot.py
- **OCR:** Eden AI API (Google provider), paid per call, key in .env

---

## User Limits

- Max **10 concurrent users** at any time (hard limit)
- Max **10 jobs per minute** (rate limit)
- Max **30 jobs per hour** (rate limit)
- Max **60 jobs per day** → system shuts down for **24 hours**, admin notified via Telegram (chat ID: 1503596202)

---

## Known Template Flow

```
User sends PDF via Telegram
        ↓
data/jobs/<job_id>/input/pdf/input.pdf        ← original PDF saved here
data/jobs/<job_id>/input/images/page_N.png    ← split into PNGs
        ↓
Page 1 sent to Eden AI OCR API
        ↓
Matched against data/templates/*/template.json
        ↓
Price overlay rendered
→ data/jobs/<job_id>/output/images/           ← rendered PNGs
→ data/jobs/<job_id>/output/final.pdf         ← final PDF
        ↓
PDF sent to user via Telegram
        ↓
data/jobs/<job_id>/ DELETED immediately
```

---

## Unknown Template Flow

```
Template not matched
        ↓
data/unknown_templates/<job_id>/ocr.json          ← OCR result
data/unknown_templates/<job_id>/page_1.png        ← page image
data/unknown_templates/<job_id>/fine_tuning.json  ← price boxes + font settings
data/unknown_templates/<job_id>/preview.png       ← highlighted box preview (temp)
        ↓
User confirms price boxes via Telegram buttons
        ↓ (optional)
User opens fine-tune UI at finetune.gtxtransportlogistics.com:8002
(password protected — credentials in .env: FINETUNE_USER / FINETUNE_PASS)
        ↓
Rendered:
→ data/unknown_templates/<job_id>/output/page_1.png
→ data/jobs/<job_id>/output/final.pdf
        ↓
PDF sent to user
        ↓
User taps "Looks good"  → DELETED immediately (both folders)
User taps "I don't like it" → 2 hour timer starts
    → If user reprocesses and approves → DELETED immediately
    → If abandoned → DELETED after 2 hours automatically
```

---

## Permanent Storage (never deleted)

| Folder | Contents |
|--------|----------|
| `data/templates/` | Known broker templates (JSON files) |
| `data/fonts/` | Fonts used for rendering |
| `data/logs/jobs.json` | Log of every job (success/failed) |

---

## Adding a New Template

1. Fine-tune locally
2. Copy the folder to `data/templates/` on the server
3. No restart needed — bot picks it up on next job

---

## Running the Services

### Telegram Bot

No systemd service set up yet. To run manually:

```bash
cd /opt/pdf-ocr-telegram
python3 interface/telegram/handlers/bot.py
```

To keep it running after terminal closes:

```bash
nohup python3 interface/telegram/handlers/bot.py > logs/bot.log 2>&1 &
```

### Fine-tune UI

Run manually when needed (not always on):

```bash
cd /opt/pdf-ocr-telegram
python3 template_setup/unknown_ui/app.py
```

Accessible at: http://finetune.gtxtransportlogistics.com:8002  
Login: FINETUNE_USER / FINETUNE_PASS from .env

---

## Deploying Updates

From your Mac:

```bash
rsync -av --exclude='.git' --exclude='data/jobs' --exclude='data/unknown_templates' \
  '/Users/sainttom/STALEPOETRY/AI/Workflow Automation/Brokerage/pdf-ocr-telegram/' \
  root@89.167.91.131:/opt/pdf-ocr-telegram/
```

Then restart the bot on the server.
