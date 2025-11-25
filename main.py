import os
import logging
import discord
from discord import Intents
from discord_webhook import DiscordWebhook
from telegram.ext import Updater, MessageHandler, Filters
from telegram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== ENV ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

# ====== Telegram bot ======
telegram_bot = Bot(token=TELEGRAM_TOKEN)
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# ====== Discord bot ======
intents = Intents.default()
intents.messages = True
intents.message_content = True
discord_client = discord.Client(intents=intents)


# ==========================================================
# TELEGRAM -> DISCORD
# ==========================================================
def tg_to_discord(update, context):
    msg = update.message
    if msg is None:
        return

    sender_name = msg.from_user.full_name

    # TEXT
    if msg.text:
        webhook = DiscordWebhook(
            url=DISCORD_WEBHOOK_URL,
            content=msg.text,
            username=sender_name,
            avatar_url=msg.from_user.photo.big_file_id if msg.from_user else None
        )
        webhook.execute()

    # PHOTO
    if msg.photo:
        photo = msg.photo[-1].get_file()
        data = photo.download_as_bytearray()
        webhook = DiscordWebhook(
            url=DISCORD_WEBHOOK_URL,
            username=sender_name
        )
        webhook.add_file(file=data, filename="photo.jpg")
        webhook.execute()

    # DOCUMENT / VIDEO / ETC
    if msg.document:
        file = msg.document.get_file()
        data = file.download_as_bytearray()
        webhook = DiscordWebhook(
            url=DISCORD_WEBHOOK_URL,
            username=sender_name
        )
        webhook.add_file(file=data, filename=msg.document.file_name)
        webhook.execute()

    if msg.video:
        file = msg.video.get_file()
        data = file.download_as_bytearray()
        webhook = DiscordWebhook(
            url=DISCORD_WEBHOOK_URL,
            username=sender_name
        )
        webhook.add_file(file=data, filename="video.mp4")
        webhook.execute()


dispatcher.add_handler(MessageHandler(Filters.all, tg_to_discord))


# ==========================================================
# DISCORD -> TELEGRAM
# ==========================================================
@discord_client.event
async def on_message(message):

    # ———— FIX ЦИКЛА: игнорируем сообщения, пришедшие от самого вебхука ————
    if message.webhook_id is not None:
        return  # сообщение отправил наш Telegram→Discord вебхук

    # игнорируем свои сообщения
    if message.author == discord_client.user:
        return

    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    username = message.author.display_name  # красивый ник на сервере
    content = message.content
    attachments = message.attachments

    # ТЕКСТ
    if content:
        telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"{username}: {content}"
        )

    # ФАЙЛЫ — как вложения, а не ссылки
    for file in attachments:
        data = await file.read()

        # фото
        if file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            telegram_bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=data,
                caption=f"{username}:" if not content else None
            )

        # видео
        elif file.filename.lower().endswith(('.mp4', '.mov', '.wmv', '.avi', '.mkv')):
            telegram_bot.send_video(
                chat_id=TELEGRAM_CHAT_ID,
                video=data,
                caption=f"{username}:" if not content else None
            )

        # документы
        else:
            telegram_bot.send_document(
                chat_id=TELEGRAM_CHAT_ID,
                document=data,
                filename=file.filename,
                caption=f"{username}:" if not content else None
            )


# ==========================================================
# START
# ==========================================================
def start_all():
    logger.info("Starting Telegram polling...")
    updater.start_polling()

    logger.info("Starting Discord client...")
    discord_client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    start_all()
