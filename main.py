import os
import threading
import asyncio
import requests
from io import BytesIO

# Telegram
from telegram import Bot, InputFile
from telegram.ext import Updater, MessageHandler, Filters

# Discord
import discord

# ==== Настройки из окружения ====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
TELEGRAM_TARGET_CHAT_ID = int(os.getenv("TELEGRAM_TARGET_CHAT_ID", "0"))  # id группы/чата куда посылать из Discord
DISCORD_TARGET_CHANNEL_ID = int(os.getenv("DISCORD_TARGET_CHANNEL_ID", "0"))  # id канала где слушать

if not all([TELEGRAM_BOT_TOKEN, DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL, TELEGRAM_TARGET_CHAT_ID, DISCORD_TARGET_CHANNEL_ID]):
    raise SystemExit("Необходимые переменные окружения не установлены: TELEGRAM_BOT_TOKEN, DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL, TELEGRAM_TARGET_CHAT_ID, DISCORD_TARGET_CHANNEL_ID")

# ==== Инициализация клиентов ====
tg_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Discord intents (нужен доступ к content, чтобы читать текст сообщений)
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

discord_client = discord.Client(intents=intents)


# --------------------
#  Helper: отправка в Discord через webhook (с username + avatar + файл)
# --------------------
def send_to_discord_via_webhook(username, avatar_url=None, text=None, file_bytes=None, filename=None):
    data = {"username": username}
    if avatar_url:
        data["avatar_url"] = avatar_url
    if text:
        data["content"] = text

    if file_bytes:
        files = {"file": (filename or "file", file_bytes)}
        resp = requests.post(DISCORD_WEBHOOK_URL, data=data, files=files)
    else:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=data)

    try:
        resp.raise_for_status()
    except Exception as e:
        print("Discord webhook error:", resp.status_code, resp.text)


# --------------------
#  Telegram -> Discord
# --------------------
def forward_telegram_to_discord(update, context):
    message = update.message
    if not message:
        return

    # Игнорируем сообщения от ботов (в т.ч. нашего Telegram-бота)
    if message.from_user and message.from_user.is_bot:
        return

    username = message.from_user.full_name
    # попытка получить аватар
    avatar_url = None
    try:
        photos = context.bot.get_user_profile_photos(message.from_user.id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            f = context.bot.get_file(file_id)
            avatar_url = f.file_path
    except Exception:
        avatar_url = None

    text = message.text or message.caption or None

    # Определяем наличие медиа
    file_url = None
    file_bytes = None
    filename = None

    try:
        if message.photo:
            file_id = message.photo[-1].file_id
            tgfile = context.bot.get_file(file_id)
            file_url = tgfile.file_path
            filename = "photo.jpg"
        elif message.video:
            file_id = message.video.file_id
            tgfile = context.bot.get_file(file_id)
            file_url = tgfile.file_path
            filename = message.video.file_name or "video.mp4"
        elif message.document:
            file_id = message.document.file_id
            tgfile = context.bot.get_file(file_id)
            file_url = tgfile.file_path
            filename = message.document.file_name or "file"
        elif message.animation:
            file_id = message.animation.file_id
            tgfile = context.bot.get_file(file_id)
            file_url = tgfile.file_path
            filename = message.animation.file_name or "animation.gif"
    except Exception as e:
        print("Ошибка получения файла из Telegram:", e)
        file_url = None

    if file_url:
        try:
            r = requests.get(file_url, timeout=30)
            r.raise_for_status()
            file_bytes = r.content
        except Exception as e:
            print("Ошибка скачивания файла по file_path:", e)
            file_bytes = None

    # Отправляем в Discord через webhook
    send_to_discord_via_webhook(username=username, avatar_url=avatar_url, text=text, file_bytes=file_bytes, filename=filename)


def start_telegram_polling():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    # Ловим всё, но игнорируем ботов внутри handler
    dp.add_handler(MessageHandler(Filters.all, forward_telegram_to_discord))
    updater.start_polling()
    print("Telegram polling started")
    updater.idle()


# --------------------
#  Discord -> Telegram
# --------------------
@discord_client.event
async def on_ready():
    print(f"Discord client ready as {discord_client.user} (id={discord_client.user.id})")


@discord_client.event
async def on_message(message):
    try:
        # Игнорируем свои сообщения, ботов и webhook-сообщения
        if message.author == discord_client.user:
            return
        if message.author.bot:
            return
        # webhook-сообщения имеют webhook_id != None в некоторых версиях
        if getattr(message, "webhook_id", None) is not None:
            return
        if message.channel.id != DISCORD_TARGET_CHANNEL_ID:
            return

        # Формируем текст для Telegram
        author_name = f"{message.author.display_name}"
        text_prefix = f"[Discord] {author_name}:\n"

        text = message.content or ""
        full_text = text_prefix + text if text else text_prefix

        # Если есть вложения — скачиваем и отправляем
        if message.attachments:
            for att in message.attachments:
                url = att.url
                fname = att.filename or "file"
                # скачиваем в память
                try:
                    resp = requests.get(url, timeout=30)
                    resp.raise_for_status()
                    b = resp.content
                except Exception as e:
                    print("Ошибка скачивания attachment:", e)
                    b = None

                if b:
                    # определяем тип по расширению / content_type
                    ct = att.content_type or ""
                    # картинки
                    if ct.startswith("image") or fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        # send_photo expects file-like
                        bio = BytesIO(b)
                        bio.name = fname
                        # отправляем файл с подписью (caption)
                        await asyncio.get_event_loop().run_in_executor(None, tg_bot.send_photo, TELEGRAM_TARGET_CHAT_ID, InputFile(bio), full_text)
                    elif ct.startswith("video") or fname.lower().endswith((".mp4", ".mov", ".mkv")):
                        bio = BytesIO(b)
                        bio.name = fname
                        await asyncio.get_event_loop().run_in_executor(None, tg_bot.send_video, TELEGRAM_TARGET_CHAT_ID, InputFile(bio), full_text)
                    else:
                        # общий файл
                        bio = BytesIO(b)
                        bio.name = fname
                        await asyncio.get_event_loop().run_in_executor(None, tg_bot.send_document, TELEGRAM_TARGET_CHAT_ID, InputFile(bio), full_text)
                else:
                    # если не скачали, просто отправляем текст
                    await asyncio.get_event_loop().run_in_executor(None, tg_bot.send_message, TELEGRAM_TARGET_CHAT_ID, full_text)
        else:
            # Нет вложений — отправляем только текст
            await asyncio.get_event_loop().run_in_executor(None, tg_bot.send_message, TELEGRAM_TARGET_CHAT_ID, full_text)
    except Exception as e:
        print("Ошибка в on_message:", e)


# --------------------
#  Запуск: Telegram polling в отдельном потоке, Discord клиент в основном asyncio loop
# --------------------
def main():
    tg_thread = threading.Thread(target=start_telegram_polling, daemon=True)
    tg_thread.start()

    # Запускаем discord клиента (она блокирует текущий поток)
    discord_client.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
