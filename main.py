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

# Множества для отслеживания уже пересланных сообщений
forwarded_telegram_ids = set()
forwarded_discord_ids = set()

def telegram_to_discord(update: Update, context: CallbackContext):
    msg_id = update.message.message_id
    if msg_id in forwarded_telegram_ids:  # Уже переслали
        return
    forwarded_telegram_ids.add(msg_id)

    user = update.effective_user
    if user.is_bot:
        return

    text = update.message.text or ""

    # Отправка текста в Discord
    if text:
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": text,
            "username": user.username or user.full_name
        })

    # Отправка файлов
    files = update.message.photo or [update.message.document] if update.message.document else []
    for f in files:
        file_obj = telegram_bot.get_file(f.file_id)
        url = file_obj.file_path
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": url,
            "username": user.username or user.full_name
        })

def start_telegram_polling():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    updater.dispatcher.add_handler(
        MessageHandler(Filters.chat(chat_id=TELEGRAM_CHAT_ID), telegram_to_discord)
    )
    updater.start_polling()
    # Railway: idle() нельзя, просто держим цикл
    while True:
        time.sleep(60)

# ====== Discord бот ======
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

@discord_client.event
async def on_ready():
    logging.info(f'Discord client ready. Logged in as {discord_client.user}')

@discord_client.event
async def on_message(message):
    msg_id = message.id
    if msg_id in forwarded_discord_ids:  # Уже переслали
        return
    forwarded_discord_ids.add(msg_id)

    if message.author == discord_client.user:
        return
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    content = message.content
    files = [attachment.url for attachment in message.attachments]

    # Отправка в Telegram
    if content:
        telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=content)
    for f in files:
        telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f)

# ====== Основной запуск ======
def main():
    # Запуск Telegram в отдельном потоке
    t = threading.Thread(target=start_telegram_polling, daemon=True)
    t.start()

    # Запуск Discord
    discord_client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
