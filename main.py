# main.py placeholder
# I need full context to rebuild, but here's a template with working file transfer.
import discord
from discord.ext import commands
import requests
from telegram import Bot
from telegram.ext import Updater, MessageHandler, Filters
import logging

DISCORD_TOKEN = "YOUR_DISCORD_TOKEN"
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = 123456789
DISCORD_CHANNEL_ID = 123456789

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)

intents = discord.Intents.default()
intents.message_content = True

dc = commands.Bot(command_prefix="!", intents=intents)

@dc.event\async def on_ready():
    logging.info(f"Discord connected as {dc.user}")

@dc.event\async def on_message(msg: discord.Message):
    if msg.author.bot:
        return
    if msg.channel.id != DISCORD_CHANNEL_ID:
        return

    username = msg.author.name

    # text
    if msg.content:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"{username}: {msg.content}")

    # attachments
    for f in msg.attachments:
        file_bytes = requests.get(f.url).content

        lower = f.filename.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            bot.send_photo(TELEGRAM_CHAT_ID, photo=file_bytes, caption=f"{username}:")
        elif lower.endswith((".mp4", ".mov", ".avi", ".mkv")):
            bot.send_video(TELEGRAM_CHAT_ID, video=file_bytes, caption=f"{username}:")
        else:
            bot.send_document(TELEGRAM_CHAT_ID, document=file_bytes, filename=f.filename, caption=f"{username}:")

# Telegram → Discord

def tg_receive(update, ctx):
    user = update.message.from_user.username or "tg_user"

    if update.message.text:
        channel = dc.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            dc.loop.create_task(channel.send(f"{user}: {update.message.text}"))

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        f = bot.get_file(file_id)
        data = f.download_as_bytearray()
        channel = dc.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            dc.loop.create_task(channel.send(file=discord.File(fp=bytes(data), filename="tg_photo.jpg")))

    if update.message.document:
        file_id = update.message.document.file_id
        f = bot.get_file(file_id)
        data = f.download_as_bytearray()
        channel = dc.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            dc.loop.create_task(channel.send(file=discord.File(fp=bytes(data), filename=update.message.document.file_name)))

updater.dispatcher.add_handler(MessageHandler(Filters.all, tg_receive))

updater.start_polling()

dc.run(DISCORD_TOKEN)
