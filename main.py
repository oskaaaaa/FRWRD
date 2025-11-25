import os
import logging
import discord
from discord import Intents, SyncWebhook
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

# Discord webhook sender
discord_webhook = SyncWebhook.from_url(DISCORD_WEBHOOK_URL)

# ====== Discord bot ======
intents = Intents.default()
intents.messages = True
intents.message_content = True
discord_client = discord.Client(intents=intents)


# ==========================================================
# TELEGRAM → DISCORD
# ==========================================================
def tg_to_discord(update, context):
    msg = update.message
    if msg is None:
        return

    username = msg.from_user.full_name

    # Аватарка Telegram
    avatar_url = None
    if msg.from_user.photo:
        try:
            file_id = msg.from_user.photo.big_file_id
            avatar_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_id}"
        except:
            avatar_url = None

    # ТЕКСТ
    if msg.text:
        discord_webhook.send(
            content=msg.text,
            username=username,
            avatar_url=avatar_url
        )

    # ФОТО
    if msg.photo:
        photo = msg.photo[-1].get_file()
        data = photo.download_as_bytearray()
        discord_webhook.send(
            username=username,
            avatar_url=avatar_url,
            file=discord.File(fp=data, filename="photo.jpg")
        )

    # ДОКУМЕНТ
    if msg.document:
        file = msg.document.get_file()
        data = file.download_as_bytearray()
        discord_webhook.send(
            username=username,
            avatar_url=avatar_url,
            file=discord.File(fp=data, filename=msg.document.file_name)
        )

    # ВИДЕО
    if msg.video:
        file = msg.video.get_file()
        data = file.download_as_bytearray()
        discord_webhook.send(
            username=username,
            avatar_url=avatar_url,
            file=discord.File(fp=data, filename="video.mp4")
        )


dispatcher.add_handler(MessageHandler(Filters.all, tg_to_discord))


# ==========================================================
# DISCORD → TELEGRAM
# ==========================================================
@discord_client.event
async def on_message(message):

    # анти-цикл — игнорируем сообщения, сделанные вебхуком
    if message.webhook_id is not None:
        return

    if message.author == discord_client.user:
        return

    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    username = message.author.display_name
    content = message.content
    attachments = message.attachments

    # ТЕКСТ
    if content:
        telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"{username}: {content}"
        )

    # ВЛОЖЕНИЯ
    for file in attachments:
        data = await file.read()

        # фото
        if file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            telegram_bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=data,
                caption=f"{username}:"
            )

        # видео
        elif file.filename.lower().endswith(('.mp4', '.mov', '.wmv', '.avi', '.mkv')):
            telegram_bot.send_video(
                chat_id=TELEGRAM_CHAT_ID,
                video=data,
                caption=f"{username}:"
            )

        # все остальное → документ
        else:
            telegram_bot.send_document(
                chat_id=TELEGRAM_CHAT_ID,
                document=data,
                filename=file.filename,
                caption=f"{username}:"
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
