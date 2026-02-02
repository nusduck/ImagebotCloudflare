import os
import time
import logging
from logging.handlers import RotatingFileHandler

import telebot
from dotenv import load_dotenv

from api.CloudImage import generate_image_sdxl
from api.NewImage import generate_image_flux_url


# --- Logging ---
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("chat_bot")
logger.setLevel(logging.INFO)

_fmt = logging.Formatter(
    fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file = RotatingFileHandler(
    os.path.join(LOG_DIR, "bot.log"),
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=10,
    encoding="utf-8",
)
_file.setFormatter(_fmt)

_console = logging.StreamHandler()
_console.setFormatter(_fmt)

logger.handlers.clear()
logger.addHandler(_file)
logger.addHandler(_console)


# --- Env / Bot ---
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)
TOKEN = os.getenv("TELEGRAM_BOT_API_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_API_TOKEN in .env")

bot = telebot.TeleBot(token=TOKEN)


def reset_menu():
    """Reset bot command menu."""
    try:
        bot.set_my_commands(
            commands=[
                telebot.types.BotCommand("start", "说明 / 帮助"),
                telebot.types.BotCommand("image", "用 SDXL 生成图片：/image 提示词"),
                telebot.types.BotCommand("flux", "用 FLUX 生成图片：/flux 提示词"),
            ]
        )
        logger.info("Bot menu (commands) reset")
    except Exception:
        logger.exception("Failed to reset bot menu")


@bot.message_handler(commands=["start"])
def handle_start(message):
    reset_menu()
    bot.reply_to(
        message,
        "\n".join(
            [
                "这是一个图片生成 Bot。",
                "\n命令：",
                "/image 关键词 - SDXL 出图（会用 DeepSeek 自动润色 prompt）",
                "/flux 关键词 - FLUX 出图",
                "\n例子：",
                "/image 抽象 大海 16:9",
                "/flux cyberpunk city night, neon, rain",
            ]
        ),
    )


@bot.message_handler(commands=["image"])
def handle_image(message):
    prompt = (message.text or "")[6:].strip()
    if not prompt:
        bot.reply_to(message, "用法：/image 提示词（例如：/image 抽象 大海 16:9）")
        return

    logger.info("/image from=%s chat=%s prompt=%r", message.from_user.id, message.chat.id, prompt)

    thinking = None
    try:
        thinking = bot.reply_to(message, "Drawing (SDXL)...")
    except Exception:
        pass

    try:
        img_bytes, meta = generate_image_sdxl(prompt)
        caption = f"SDXL | {meta.get('width')}x{meta.get('height')} | {meta.get('final_prompt','')[:120]}"
        bot.send_photo(message.chat.id, img_bytes, caption=caption)
    except Exception as e:
        logger.exception("/image failed")
        bot.reply_to(message, f"出图失败：{type(e).__name__}: {e}")
    finally:
        if thinking:
            try:
                bot.delete_message(message.chat.id, thinking.message_id)
            except Exception:
                pass


@bot.message_handler(commands=["flux"])
def handle_flux(message):
    prompt = (message.text or "")[5:].strip()
    if not prompt:
        bot.reply_to(message, "用法：/flux 提示词（例如：/flux cute dog, watercolor）")
        return

    logger.info("/flux from=%s chat=%s prompt=%r", message.from_user.id, message.chat.id, prompt)

    thinking = None
    try:
        thinking = bot.reply_to(message, "Drawing (FLUX)...")
    except Exception:
        pass

    try:
        img_url = generate_image_flux_url(prompt)
        bot.send_photo(message.chat.id, img_url, caption="FLUX")
    except Exception as e:
        logger.exception("/flux failed")
        bot.reply_to(message, f"出图失败：{type(e).__name__}: {e}")
    finally:
        if thinking:
            try:
                bot.delete_message(message.chat.id, thinking.message_id)
            except Exception:
                pass


def run_bot():
    reset_menu()
    while True:
        try:
            logger.info("Bot polling started")
            bot.polling(timeout=60, long_polling_timeout=60)
        except Exception:
            logger.exception("Bot encountered an error; restarting in 10s")
            time.sleep(10)


if __name__ == "__main__":
    run_bot()
