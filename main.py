import threading
import logging
import requests
import time
import os

from telegram import Bot, Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

import discord

logging.basicConfig(level=logging.INFO)

# ====== Переменные окружения ======
TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = int(os.environ['TELEGRAM_TARGET_CHAT_ID'])

DISCORD_TOKEN = os.environ['DISCORD_BOT_TOKEN']
DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']
DISCORD_CHANNEL_ID = int(os.environ['DISCORD_TARGET_CHANNEL_ID'])

# ====== Telegram бот ======
telegram_bot = Bot(token=TELEGRAM_TOKEN)
BOT_ID = telegram_bot.get_me().id  # ID самого бота

# — Хранилище хэшей, чтобы не дублировать сообщения —
forwarded_telegram_hashes = set()


# ====== Получение аватарки Telegram ======
def get_telegram_avatar_url(user_id):
    try:
        photos = telegram_bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            file_obj = telegram_bot.get_file(file_id)
            return file_obj.file_path
    except:
        pass
    return None


# ==========================================================
# TELEGRAM → DISCORD
# ==========================================================
def telegram_to_discord(update: Update, context: CallbackContext):
    user = update.effective_user

    # Игнорируем свои же сообщения и других ботов
    if user.is_bot or user.id == BOT_ID:
        return

    # ---- Text ----
    text = update.message.text or ""
    msg_hash = hash(text)

    # Анти-дублирование
    if text and msg_hash in forwarded_telegram_hashes:
        return
    forwarded_telegram_hashes.add(msg_hash)

    username = user.username or user.full_name
    avatar_url = get_telegram_avatar_url(user.id)

    # ----- ТЕКСТ -----
    if text:
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": text,
            "username": username,
            "avatar_url": avatar_url
        })

    # ----- ФАЙЛЫ -----
    file = None

    # Фото
    if update.message.photo:
        file = update.message.photo[-1]

    # Документ
    elif update.message.document:
        file = update.message.document

    if file:
        file_info = telegram_bot.get_file(file.file_id)

        # Правильная прямая ссылка
        telegram_file_url = (
            f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        )

        file_bytes = requests.get(telegram_file_url).content

        filename = "file"
        if update.message.document:
            filename = update.message.document.file_name
        else:
            filename = "photo.jpg"

        requests.post(
            DISCORD_WEBHOOK_URL,
            files={"file": (filename, file_bytes)},
            data={
                "username": username,
                "avatar_url": avatar_url,
                "content": ""
            }
        )


# — Telegram polling —
def start_telegram_polling():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    updater.dispatcher.add_handler(
        MessageHandler(Filters.chat(chat_id=TELEGRAM_CHAT_ID), telegram_to_discord)
    )
    updater.start_polling()

    while True:
        time.sleep(60)


# ==========================================================
# DISCORD → TELEGRAM
# ==========================================================
intents = discord.Intents.default()
intents.message_content = True

discord_client = discord.Client(intents=intents)


@discord_client.event
async def on_ready():
    logging.info(f"Discord client ready. Logged in as {discord_client.user}")


@discord_client.event
async def on_message(message):
    # Игнорируем свои же сообщения и webhook-сообщения (фикс циклов)
    if message.author == discord_client.user or message.webhook_id is not None:
        return

    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    username = message.author.display_name
    content = message.content
    files = message.attachments

    # ----- ТЕКСТ -----
    if content:
        telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"{username}: {content}"
        )

    # ----- ФАЙЛЫ -----
    for f in files:
        data = await f.read()

        # Изображения
        if f.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
            telegram_bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=data,
                caption=f"{username}:"
            )

        # Видео
        elif f.filename.lower().endswith(('.mp4', '.mov', '.wmv', '.avi', '.mkv')):
            telegram_bot.send_video(
                chat_id=TELEGRAM_CHAT_ID,
                video=data,
                caption=f"{username}:"
            )

        # Документы
        else:
            telegram_bot.send_document(
                chat_id=TELEGRAM_CHAT_ID,
                document=data,
                filename=f.filename,
                caption=f"{username}:"
            )


# ==========================================================
# START
# ==========================================================
def main():
    # Телеграм-поллинг в отдельном потоке
    t = threading.Thread(target=start_telegram_polling, daemon=True)
    t.start()

    # Дискорд
    discord_client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
