# chat_bot (Image Generator Bot)

A minimal Telegram image generation bot with two commands:

- `/image <prompt>`: generates an image using **SDXL** on **Cloudflare Workers AI**. The user prompt is expanded into an English SDXL prompt by **DeepSeek**.
- `/flux <prompt>`: generates an image using **FLUX** via an OpenAI-compatible endpoint and returns an image URL.

## Setup

### 1) Create local env files (DO NOT commit)

```bash
cp .env.example .env
cp api/.env.example api/.env
cp api_config.example.json api_config.json
```

Fill in:
- `.env`: `TELEGRAM_BOT_API_TOKEN`
- `api/.env`: `account_id`, `gateway_id`, `cloudflare_token`
- `api_config.json`: provider keys for `deepseek` and `flux`

### 2) Install deps

This project uses Python 3.

```bash
pip install -r requirements.txt
```

(If you don't have `requirements.txt`, install at least: `pyTelegramBotAPI python-dotenv openai requests`.)

### 3) Run

```bash
python3 main.py
```

## systemd

Example service file is created as `/etc/systemd/system/chat-bot.service` (server specific).

Useful commands:

```bash
systemctl daemon-reload
systemctl enable --now chat-bot.service
journalctl -u chat-bot.service -f
```

## Security

Never commit `.env`, `api/.env`, or `api_config.json` (they contain secrets). Use the provided `*.example` files.
