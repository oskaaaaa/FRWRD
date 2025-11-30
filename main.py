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
BOT_ID = telegram_bot.get_me().id

# Множество для отслеживания уже пересланных текстовых сообщений
forwarded_telegram_hashes = set()


def get_telegram_avatar_url(user_id):
    """Возвращает URL аватарки Telegram пользователя"""
    photos = telegram_bot.get_user_profile_photos(user_id, limit=1)
    if photos.total_count > 0:
        file_id = photos.photos[0][-1].file_id
        file_obj = telegram_bot.get_file(file_id)
        return file_obj.file_path
    return None


def telegram_to_discord(update: Update, context: CallbackContext):
    user = update.effective_user

    # игнорируем свои сообщения
    if user.is_bot or user.id == BOT_ID:
        return

    text = update.message.text or ""
    msg_hash = hash(text)

    if text and msg_hash not in forwarded_telegram_hashes:
        forwarded_telegram_hashes.add(msg_hash)

        avatar_url = get_telegram_avatar_url(user.id)

        # Текст → Discord
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": text,
            "username": user.username or user.full_name,
            "avatar_url": avatar_url
        })

    # Фото → Discord (как binary file, без битых ссылок)
    if update.message.photo:
        photo = update.message.photo[-1]
        file = telegram_bot.get_file(photo.file_id)
        file_bytes = requests.get(file.file_path).content

        requests.post(
            DISCORD_WEBHOOK_URL,
            files={"file": ("photo.jpg", file_bytes)},
            data={"username": user.username or user.full_name}
        )

    # Документы → Discord
    if update.message.document:
        file = telegram_bot.get_file(update.message.document.file_id)
        file_bytes = requests.get(file.file_path).content

        requests.post(
            DISCORD_WEBHOOK_URL,
            files={"file": (update.message.document.file_name, file_bytes)},
            data={"username": user.username or user.full_name}
        )


def start_telegram_polling():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    updater.dispatcher.add_handler(
        MessageHandler(Filters.chat(chat_id=TELEGRAM_CHAT_ID), telegram_to_discord)
    )

    updater.start_polling()
    while True:
        time.sleep(60)


# ====== Discord бот ======
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)


@discord_client.event
async def on_ready():
    logging.info(f"Discord client ready. Logged in as {discord_client.user}")


@discord_client.event
async def on_message(message):
    # игнорируем себя и вебхуки
    if message.author == discord_client.user or message.webhook_id is not None:
        return

    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    username = message.author.display_name

    # Текст → Telegram, добавляем username в начале
    if message.content:
        telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"{username}: {message.content}"
        )

    # Файлы → Telegram
    for f in message.attachments:
        if f.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
            telegram_bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=f.url)
        else:
            telegram_bot.send_document(chat_id=TELEGRAM_CHAT_ID, document=f.url)


# ====== Основной запуск ======
def main():
    t = threading.Thread(target=start_telegram_polling, daemon=True)
    t.start()
    discord_client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
