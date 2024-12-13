import sqlite3
import os
import re
from dotenv import load_dotenv
import asyncio
import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents, shard_count=2)

async def setup_table():
    """สร้างตารางเก็บ channel ID ในฐานข้อมูล SQLite"""
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

async def load_channels():
    """โหลด channel ID จากฐานข้อมูลเข้าสู่ตัวแปร bot.channel_ids"""
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id FROM channels")
    bot.channel_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

@bot.event
async def on_ready():
    """ฟังก์ชั่นที่ทำงานเมื่อบอทพร้อมใช้งาน"""
    print(f'{bot.user} has connected to Discord!')
    await setup_table()
    await load_channels()
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(e)

@bot.tree.command(name="set", description="Set this message channel")
async def set_channel(interaction: discord.Interaction):
    """เพิ่ม channel ID ปัจจุบันเข้าสู่ฐานข้อมูล"""
    channel_id = interaction.channel.id
    with sqlite3.connect("data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", (channel_id,))
        conn.commit()
    await load_channels()
    await interaction.response.send_message(f"Channel {channel_id} has been set!", ephemeral=True)

@bot.tree.command(name="unset", description="Unset this message channel")
async def unset_channel(interaction: discord.Interaction):
    """ลบ channel ID ปัจจุบันออกจากฐานข้อมูล"""
    channel_id = interaction.channel.id
    with sqlite3.connect("data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        conn.commit()
    await load_channels()
    await interaction.response.send_message(f"Channel {channel_id} has been unset!", ephemeral=True)

@bot.event
async def on_message(message):
    """จัดการข้อความที่ส่งมาในช่องที่กำหนด"""
    if message.author.bot:
        return

    if message.channel.id in bot.channel_ids:
        print(f"Content: {message.content!r}")
        urls = re.findall(r'https?://\S+', message.content)

        if "http" in message.content and "tiktok" in message.content:
            updated_urls = [url.replace("tiktok", "tnktok") for url in urls]
            await message.edit(suppress=True)
            for url in updated_urls:
                await message.reply(f"[-]({url}?addDesc=true)", mention_author=False)

    await bot.process_commands(message)

try:
    bot.run(TOKEN)
except discord.errors.DiscordServerError as e:
    print(f"Server error: {e}")
    asyncio.sleep(10)
    bot.run(TOKEN)
