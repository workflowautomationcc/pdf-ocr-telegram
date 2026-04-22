# Server Commands

## 1. Deploy (run on Mac)
```
rsync -av --exclude='.git' --exclude='data/jobs' --exclude='data/unknown_templates' \
  '/Users/sainttom/STALEPOETRY/AI/Workflow Automation/Brokerage/pdf-ocr-telegram/' \
  root@89.167.91.131:/opt/pdf-ocr-telegram/
```

## 2. SSH into server
```
ssh root@89.167.91.131
```

## 3. Restart services after deploy
```
systemctl restart pdf-bot pdf-finetune
```

## 4. Check status
```
systemctl status pdf-bot pdf-finetune
```

## 5. View logs
```
tail -50 /opt/pdf-ocr-telegram/logs/bot.log
tail -50 /opt/pdf-ocr-telegram/logs/finetune.log
```
