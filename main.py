import sqlite3
import os
import re
from dotenv import load_dotenv
import asyncio
import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("TOKEN")

channel_ids = []  # ตัวแปรสำหรับเก็บ ID ช่องจาก data.db

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

async def setup_table():
    # สร้างตารางในฐานข้อมูลถ้ายังไม่มี
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            channel_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

async def load_channels():
    # โหลดข้อมูลช่องจากฐานข้อมูลไปยังตัวแปร channel_ids
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id FROM channels")
    bot.channel_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await setup_table()  # สร้างตารางถ้ายังไม่มี
    await load_channels()  # โหลดข้อมูลช่องจากฐานข้อมูล
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(e)

@bot.tree.command(name="set", description="Set this message channel")
async def set_channel(interaction: discord.Interaction):
    channel_id = interaction.channel.id
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    conn.close()
    await load_channels()  # อัพเดตตัวแปร channel_ids
    await interaction.response.send_message(f"Channel {channel_id} has been set!", ephemeral=True)

@bot.tree.command(name="unset", description="Unset this message channel")
async def unset_channel(interaction: discord.Interaction):
    channel_id = interaction.channel.id
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()
    await load_channels()  # อัพเดตตัวแปร channel_ids
    await interaction.response.send_message(f"Channel {channel_id} has been unset!", ephemeral=True)

@bot.event
async def on_message(message):
    print(f"Content: {message.content!r}")

    if message.author.bot:
        return

    if message.channel.id in bot.channel_ids:  # ตรวจสอบว่า ID ช่องอยู่ใน channel_ids
        # ใช้ regex เพื่อหาลิงค์ที่เป็น http:// หรือ https://
        urls = re.findall(r'https?://\S+', message.content)

        if "http" in message.content and "tiktok" in message.content:
            # แก้ไขลิงค์ที่พบ
            updated_urls = [url.replace("tiktok", "tnktok") for url in urls]

            # ลบ Embed
            await message.edit(suppress=True)

            # ตอบกลับลิงค์ที่แก้ไขแล้ว
            for url in updated_urls:
                await message.reply(f"[-]({url})", mention_author=False)

    await bot.process_commands(message)

try:
    bot.run(TOKEN)
except discord.errors.DiscordServerError as e:
    print(f"Server error: {e}")
    asyncio.sleep(10)
    bot.run(TOKEN)
