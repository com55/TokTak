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
from module import Facebook, TikTokv2

load_dotenv()
TOKEN = os.getenv("TOKEN")
db_path = 'data.db'

# Mapping EN → TH
EN_TO_TH = {
    '1': 'ๅ', '!': '+', '@': '๑', '2': '/', '3': '-', '#': '๒', 
    '4': 'ภ', '$': '๓', '5': 'ถ', '%': '๔', '6': 'ุ', '^': 'ู', 
    '7': 'ึ', '&': '฿', '8': 'ค', '*': '๕', '9': 'ต', '(': '๖', 
    '0': 'จ', ')': '๗', '-': 'ข', '_': '๘', '=': 'ช', '+': '๙', 
    'q': 'ๆ', 'Q': '๐', 'w': 'ไ', 'W': '"', 'e': 'ำ', 'E': 'ฎ', 
    'r': 'พ', 'R': 'ฑ', 't': 'ะ', 'T': 'ธ', 'y': 'ั', 'Y': 'ํ', 
    'u': 'ี', 'U': '๊', 'i': 'ร', 'I': 'ณ', 'o': 'น', 'O': 'ฯ', 
    'p': 'ย', 'P': 'ญ', '[': 'บ', '{': 'ฐ', ']': 'ล', '}': '|', 
    '\\': 'ฃ', '|': 'ฅ', 'a': 'ฟ', 'A': 'ฤ', 's': 'ห', 'S': 'ฆ', 
    'd': 'ก', 'D': 'ฏ', 'f': 'ด', 'F': 'โ', 'g': 'เ', 'G': 'ฌ', 
    'h': '้', 'H': '็', 'j': '่', 'J': '๋', 'k': 'า', 'K': 'ษ', 
    'l': 'ส', 'L': 'ศ', ';': 'ว', ':': 'ซ', "'": 'ง', '"': '.', 
    'z': 'ผ', 'Z': '(', 'x': 'ป', 'X': ')', 'c': 'แ', 'C': 'ฉ', 
    'v': 'อ', 'V': 'ฮ', 'b': 'ิ', 'B': 'ฺ', 'n': 'ื', 'N': '์', 
    'm': 'ท', 'M': '?', ',': 'ม', '<': 'ฒ', '.': 'ใ', '>': 'ฬ', 
    '/': 'ฝ', '?': 'ฦ'
}

intents = discord.Intents.default()
intents.message_content = True

# สร้าง ClientSession ที่ใช้ร่วมกัน
class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.db = None
    
    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        # เชื่อมต่อ SQLite แบบ async
        self.db = await aiosqlite.connect(db_path)
    
    async def close(self):
        if self.session:
            await self.session.close()
        if self.db:
            await self.db.close()
        await super().close()

bot = Bot(command_prefix=commands.when_mentioned, intents=intents, shard_count=2)

async def setup_table():
    """สร้างตารางเก็บ channel ID ในฐานข้อมูล SQLite"""
    async with bot.db.cursor() as cursor:
        await cursor.execute(
            "CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY)"
        )
        await bot.db.commit()

async def load_channels():
    """โหลด channel ID จากฐานข้อมูลเข้าสู่ตัวแปร bot.channel_ids"""
    async with bot.db.cursor() as cursor:
        await cursor.execute("SELECT channel_id FROM channels")
        rows = await cursor.fetchall()
        bot.channel_ids = [row[0] for row in rows]

# use api form https://github.com/devfemibadmus/webmedia
async def get_video(url):
    """Fetch video details from URL"""
    class Validator:
        tiktok_pattern = r'tiktok\.com/.*/'
        instag_pattern = r'instagram\.com/(p|reel|tv)/([A-Za-z0-9_-]+)/?'
        facebook_pattern = r'(facebook\.com/.*/|fb\.watch/.*/)'
        @staticmethod
        def validate(url):
            if re.search(Validator.tiktok_pattern, url):
                return "TikTok", url
            if re.search(Validator.facebook_pattern, url):
                return "Facebook", url
            insta_match = re.search(Validator.instag_pattern, url)
            if insta_match:
                return "Instagram", insta_match.group(2)
            
            return "Invalid URL", None
    
    try:
        source, item_id = Validator.validate(url)
        
        if source == "TikTok":
            tiktok = TikTokv2(url=url, cut=True)
            data, status = tiktok.getData()
        elif source == "Facebook":
            facebook = Facebook(url=url, cut=True)
            data, status = facebook.getVideo()
   
        if status == 200:
            with open("debug.json", "w") as debug_file:
                json.dump(data, debug_file, indent=4)
            if 'tiktok' in data['platform']:
                return data['videos'][0]['quality_0']['address']
            elif 'facebook' in data['platform']:
                return data['media'][0]['address']
        else:
            print(f"Error: {status}")
            print(f"Details: {data}")
    except Exception as e:
        print(f"Error fetching video: {e.__traceback__}")
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

# ฟังก์ชันแปลงข้อความ EN → TH
def translate_en_th(text: str) -> str:
    translated = []
    for char in text.lower():  # แปลงเป็นตัวพิมพ์เล็กเพื่อลดความซับซ้อน
        translated.append(EN_TO_TH.get(char, char))  # ถ้าไม่มีใน mapping ให้ใช้ตัวเดิม
    return "".join(translated)

# Context Menu Command (คลิกขวาที่ข้อความ)
@bot.tree.context_menu(name="ไอเชี่ยนี่ลืมเปลี่ยนภาษา")
async def translate_command(interaction: discord.Interaction, message: discord.Message):
    translated_text = translate_en_th(message.content)
    await interaction.response.send_message(
        f"{message.content}\t**>\t{translated_text}**\n> {message.jump_url}"
    )
    
@bot.tree.command(name="set", description="Set this message channel")
async def set_channel(interaction: discord.Interaction):
    """เพิ่ม channel ID ปัจจุบันเข้าสู่ฐานข้อมูล"""
    channel_id = interaction.channel.id
    async with bot.db.cursor() as cursor:
        await cursor.execute(
            "DELETE FROM channels WHERE channel_id = ?",
            (channel_id,)
        )
        await bot.db.commit()
    await load_channels()
    await interaction.response.send_message(
        f"Channel {channel_id} has been set!", 
        ephemeral=True
    )

@bot.tree.command(name="unset", description="Unset this message channel")
async def unset_channel(interaction: discord.Interaction):
    """ลบ channel ID ปัจจุบันออกจากฐานข้อมูล"""
    channel_id = interaction.channel.id
    async with bot.db.cursor() as cursor:
        await cursor.execute(
            "INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", 
            (channel_id,)
        )
        await bot.db.commit()
    await load_channels()
    await interaction.response.send_message(
        f"Channel {channel_id} has been unset!",
        ephemeral=True
    )

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
    """Handle messages in specified channels"""
    if not message.author.bot and message.channel.id not in bot.channel_ids:
        urls = re.findall(r'https?://\S*(?:tiktok|facebook\.com/share/(?:r|v))\S+', message.content)
        for url in urls:
            print(f"url detected: {url}")
            await send_reply(message, url)
    await bot.process_commands(message)

async def send_reply(message, url):
    """Handle video URL replies"""
    async def send_error():
        error_msg = await message.reply(
            "**Error: Can't get video url**\n*This message will be deleted in 30 seconds.*",
            mention_author=False
        )
        await asyncio.sleep(30)
        await error_msg.delete()

    async def try_embed(content):
        reply = await message.reply(content, mention_author=False)
        end_time = asyncio.get_event_loop().time() + 10
        
        while asyncio.get_event_loop().time() <= end_time:
            reply = await message.channel.fetch_message(reply.id)
            if reply.embeds:
                await message.edit(suppress=True)
                return True
            await asyncio.sleep(0.5)
        
        await reply.delete()
        return False

    if 'tiktok' in url:
        # ลองใช้ domain ที่กำหนดก่อน
        for domain in ["a.tnktok.com", "tfxktok.com"]:
            new_url = '/'.join(url.split('/', 3)[:2] + [domain] + url.split('/', 3)[3:])
            if await try_embed(f"{message.jump_url}\n> [Video on Tiktok]({new_url})"):
                return
        
        # ถ้าไม่สำเร็จ ลองใช้ API
        if video_url := await get_video(url):
            await message.reply(
                f"{message.jump_url}\n> [Video on Tiktok]({video_url})",
                mention_author=False
            )
        else:
            await send_error()
            
    elif 'facebook' in url:
        if video_url := await get_video(url):
            if not await try_embed(f"{message.jump_url}\n> [Video on Facebook]({video_url})"):
                await send_error()
        else:
            await send_error()

async def start_bot():  
    try:
        await bot.start(TOKEN)
    except discord.errors.DiscordServerError:
        print(f"Connection error occurred. Retrying in 10 seconds...")
        await asyncio.sleep(10)
        return True
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        await asyncio.sleep(10)
        return True
    return False

async def cleanup():
    """ทำความสะอาดการเชื่อมต่อทั้งหมด"""
    try:
        if not bot.is_closed():
            await bot.close()
        if bot.session and not bot.session.closed:
            await bot.session.close()
        if bot.db:
            await bot.db.close()
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        print("Starting bot...")
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        print("\nShutting down...")
        loop.run_until_complete(cleanup())
    finally:
        loop.close()
        print("Bot has been stopped gracefully.")
