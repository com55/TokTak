import sqlite3
import os
import re
from dotenv import load_dotenv
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import datetime
import json
import aiohttp
import aiosqlite

load_dotenv()
TOKEN = os.getenv("TOKEN")
db_path = 'data/data.db'

intents = discord.Intents.default()
intents.message_content = True

# สร้าง ClientSession ที่ใช้ร่วมกัน
class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.db_pool = None
    
    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        # สร้าง connection pool สำหรับ SQLite
        self.db_pool = aiosqlite.Pool(db_path, max_size=10)
    
    async def close(self):
        if self.session:
            await self.session.close()
        if self.db_pool:
            await self.db_pool.close()
        await super().close()

bot = Bot(command_prefix=commands.when_mentioned, intents=intents, shard_count=2)

async def setup_table():
    """สร้างตารางเก็บ channel ID ในฐานข้อมูล SQLite"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

async def load_channels():
    """โหลด channel ID จากฐานข้อมูลเข้าสู่ตัวแปร bot.channel_ids"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id FROM channels")
    bot.channel_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

# use api form https://github.com/devfemibadmus/webmedia
async def get_video(url):
    """
    Fetch video details and metadata from a given URL with improved error handling.
    """
    api = "https://mediasaver.link/webmedia/api/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = aiohttp.FormData()
    payload.add_field("url", url)
    payload.add_field("cut", "true")

    try:
        async with bot.session.post(api, headers=headers, data=payload, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                
                # ใช้ dict mapping แทน match-case
                platform_handlers = {
                    'tiktok': lambda d: d['data']['videos'][0]['quality_0']['address'],
                    'facebook': lambda d: d['data']['media'][0]['address']
                }
                
                platform = data['data']['platform']
                handler = platform_handlers.get(platform)
                return handler(data) if handler else None
                
            return None
    except asyncio.TimeoutError:
        print(f"Timeout while fetching video from {url}")
        return None
    except Exception as e:
        print(f"Error fetching video: {str(e)}")
        return None

@bot.event
async def on_ready():
    """ฟังก์ชั่นที่ทำงานเมื่อบอทพร้อมใช้งาน"""
    print(f'{bot.user} has connected to Discord!')
    await setup_table()
    await load_channels()
    
    # Sync commands
    print("Syncing commands...")
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f"Failed to sync commands: {str(e)}")

@bot.tree.command(name="set", description="Set this message channel")
async def set_channel(interaction: discord.Interaction):
    """เพิ่ม channel ID ปัจจุบันเข้าสู่ฐานข้อมูล"""
    channel_id = interaction.channel.id
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", (channel_id,))
        conn.commit()
    await load_channels()
    await interaction.response.send_message(f"Channel {channel_id} has been set!", ephemeral=True)

@bot.tree.command(name="unset", description="Unset this message channel")
async def unset_channel(interaction: discord.Interaction):
    """ลบ channel ID ปัจจุบันออกจากฐานข้อมูล"""
    channel_id = interaction.channel.id
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        conn.commit()
    await load_channels()
    await interaction.response.send_message(f"Channel {channel_id} has been unset!", ephemeral=True)

@bot.tree.command(name="old_message", description="แปลงลิงก์ TikTok ในข้อความที่เลือก")
@app_commands.describe(message="เลือกข้อความที่ต้องการแปลง")
async def convert_old_message(
    interaction: discord.Interaction,
    message: int
):
    """แปลงลิงก์ TikTok ในข้อความที่เลือก"""
    channel = interaction.channel
    
    # ตรวจสอบว่าเป็นช่องที่กำหนดไว้หรือไม่
    if channel.id not in bot.channel_ids:
        await interaction.response.send_message("คำสั่งนี้ใช้ได้เฉพาะในช่องที่กำหนดเท่านั้น", ephemeral=True)
        return

    # ดึงข้อความที่ไม่ใช่ของบอทและมีลิงค์ TikTok
    messages = []
    async for msg in channel.history(limit=100):
        if not msg.author.bot and "http" in msg.content and "tiktok" in msg.content:
            messages.append(msg)
            if len(messages) >= 10:
                break

    if not messages:
        await interaction.response.send_message("ไม่พบข้อความที่มีลิงก์ TikTok", ephemeral=True)
        return

    if message >= len(messages):
        await interaction.response.send_message("ไม่พบข้อความที่เลือก", ephemeral=True)
        return

    # เลือกข้อความตามลำดับที่ผู้ใช้เลือก
    selected_msg = messages[message]
    
    urls = re.findall(r'https?://\S+', selected_msg.content)
    
    if urls:
        updated_urls = [url.replace("tiktok", "tnktok") for url in urls]
        await selected_msg.edit(suppress=True)
        if len(updated_urls) > 1:
            for url in updated_urls:
                await selected_msg.reply(f"[-]({url}?addDesc=true)", mention_author=False)
            await interaction.response.send_message("Done!")
        else:
            await interaction.response.send_message(
                f"[-]({updated_urls[0]}?addDesc=true) {selected_msg.jump_url}"
            )
    else:
        await interaction.response.send_message("No TikTok links found in the message", ephemeral=True)

@convert_old_message.autocomplete('message')
async def message_number_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    channel = interaction.channel
    
    # ดึงข้อความที่ไม่ใช่ของบอทและมีลิงค์ TikTok
    messages = []
    async for msg in channel.history(limit=100):
        # ตรวจสอบว่าไม่ใช่ข้อความของบอทและมีลิงค์ TikTok
        if not msg.author.bot and "http" in msg.content and "tiktok" in msg.content:
            messages.append(msg)
            if len(messages) >= 10:  # เก็บแค่ 10 ข้อความ
                break

    choices = []
    for idx, msg in enumerate(messages):
        # ตัดข้อความให้สั้นลงถ้ายาวเกินไป
        content = msg.content
        
        # คำนวณเวลาที่ผ่านมา
        now = datetime.datetime.now(msg.created_at.tzinfo)
        delta = now - msg.created_at
        
        if delta.days > 0:
            time_text = f"{delta.days} วันที่แล้ว"
        elif delta.seconds >= 3600:
            time_text = f"{delta.seconds // 3600} ชั่วโมงที่แล้ว"
        elif delta.seconds >= 60:
            time_text = f"{delta.seconds // 60} นาทีที่แล้ว"
        else:
            time_text = f"{delta.seconds} วินาทีที่แล้ว"
            
        choice_name = f"{msg.author.display_name} [{time_text}]: {content}"
        # จำกัดความยาวของ name ตาม Discord API
        if len(choice_name) > 100:
            choice_name = choice_name[:97] + "..."
        choices.append(app_commands.Choice(name=choice_name, value=idx))
    
    return choices

@bot.event
async def on_message(message):
    """จัดการข้อความที่ส่งมาในช่องที่กำหนด"""
    if message.author.bot:
        return

    if message.channel.id in bot.channel_ids:
        urls = re.findall(r'https?://\S*(?:tiktok|facebook\.com/share/(?:r|v))\S+', message.content)
        
        if urls:
            for url in urls:
                print(f"URL: {url}")
                await send_reply(message,url)

    await bot.process_commands(message)

async def send_reply(message, url):
    if 'tiktok' in url:
        await handle_tiktok_reply(message, url)
    elif 'facebook' in url:
        await handle_facebook_reply(message, url)

async def handle_tiktok_reply(message, url):
    fix_domains = ["a.tnktok.com", "tfxktok.com"]
    
    for domain in fix_domains:
        updated_url = '/'.join(url.split('/', 3)[:2] + [domain] + url.split('/', 3)[3:])
        bot_reply = await message.reply(
            f"{message.jump_url}\n> [Video on Tiktok]({updated_url})", 
            mention_author=False
        )
        
        if await wait_for_embed(message, bot_reply):
            await message.edit(suppress=True)
            return
            
        await bot_reply.delete()
    
    # ถ้าไม่สำเร็จ ลองใช้ API
    video_url = await get_video(url)
    if video_url:
        await message.reply(
            f"{message.jump_url}\n> [Video on Tiktok]({video_url})", 
            mention_author=False
        )
    else:
        error_msg = await message.reply(
            "**Error: Can't get video url**\n*This message will be deleted in 30 seconds.*",
            mention_author=False
        )
        await asyncio.sleep(30)
        await error_msg.delete()

async def handle_facebook_reply(message, url):
    video_url = await get_video(url)
    if not video_url:
        error_msg = await message.reply(
            "**Error: Can't get video url**\n*This message will be deleted in 30 seconds.*",
            mention_author=False
        )
        await asyncio.sleep(30)
        await error_msg.delete()
        return
        
    bot_reply = await message.reply(
        f"{message.jump_url}\n> [Video on Facebook]({video_url})",
        mention_author=False
    )
    
    if await wait_for_embed(message, bot_reply):
        await message.edit(suppress=True)
    else:
        await bot_reply.delete()

async def wait_for_embed(message, reply, timeout=10):
    """รอให้ embed โหลดเสร็จ"""
    end_time = asyncio.get_event_loop().time() + timeout
    
    while asyncio.get_event_loop().time() <= end_time:
        reply = await message.channel.fetch_message(reply.id)
        if reply.embeds:
            return True
        await asyncio.sleep(0.5)
    
    return False

async def start_bot():  
    while True:
        try:
            await bot.start(TOKEN)
        except discord.errors.DiscordServerError:
            print(f"Connection error occurred. Retrying in 10 seconds...")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            await asyncio.sleep(10) 
            pass

try:
    print("Starting bot...")
    asyncio.run(start_bot())
except KeyboardInterrupt:
    print("Bot has been stopped.")
