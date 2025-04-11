import sqlite3
import os
import re
from typing import Optional, Dict, List, Tuple, Any, Union
from dotenv import load_dotenv
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import datetime
import json
import aiohttp
import aiosqlite
import logging
from module import Facebook, TikTokv2

# Setup discord logging
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)

load_dotenv()
TOKEN = os.getenv("TOKEN")
db_path = 'data.db'

# Load keyboard mapping
with open('module/keyboard_map.json', 'r', encoding='utf-8') as f:
    EN_TO_TH: Dict[str, str] = json.load(f)

intents = discord.Intents.default()
intents.message_content = True

# สร้าง ClientSession ที่ใช้ร่วมกัน
class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: Optional[aiohttp.ClientSession] = None
        self.db: Optional[aiosqlite.Connection] = None
    
    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        self.db = await aiosqlite.connect(db_path)
    
    async def close(self) -> None:
        if self.session:
            await self.session.close()
        if self.db:
            await self.db.close()
        await super().close()

bot = Bot(command_prefix=commands.when_mentioned, intents=intents, shard_count=2)

async def setup_table() -> None:
    """สร้างตารางเก็บ channel ID ในฐานข้อมูล SQLite"""
    async with bot.db.cursor() as cursor:
        await cursor.execute(
            "CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY)"
        )
        await bot.db.commit()

async def load_channels() -> None:
    """โหลด channel ID จากฐานข้อมูลเข้าสู่ตัวแปร bot.channel_ids"""
    async with bot.db.cursor() as cursor:
        await cursor.execute("SELECT channel_id FROM channels")
        rows = await cursor.fetchall()
        bot.channel_ids = [row[0] for row in rows]

class Validator:
    tiktok_pattern = r'tiktok\.com/.*/'
    instag_pattern = r'instagram\.com/(p|reel|tv)/([A-Za-z0-9_-]+)/?'
    facebook_pattern = r'(facebook\.com/.*/|fb\.watch/.*/)'
    @staticmethod
    def validate(url: str) -> Tuple[str, Optional[str]]:
        if re.search(Validator.tiktok_pattern, url):
            return "TikTok", url
        if re.search(Validator.facebook_pattern, url):
            return "Facebook", url
        insta_match = re.search(Validator.instag_pattern, url)
        if insta_match:
            return "Instagram", insta_match.group(2)
        
        return "Invalid URL", None
    
async def get_video(source: str, url: str) -> Optional[str]:
    """Fetch video details from URL"""
    try:
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
            logger.error(f"Error: {status}")
            logger.error(f"Details: {data}")
    except Exception as e:
        logger.error("Error fetching video", exc_info=e)
    return None

@bot.event
async def on_ready() -> None:
    """ฟังก์ชั่นที่ทำงานเมื่อบอทพร้อมใช้งาน"""
    logger.info(f'{bot.user} has connected to Discord!')
    await setup_table()
    await load_channels()
    
    # Sync commands
    logger.info("Syncing commands...")
    try:
        synced = await bot.tree.sync()
        logger.info(f'Synced {len(synced)} command(s)')
    except Exception as e:
        logger.error("Failed to sync commands", exc_info=e)


@bot.tree.context_menu(name="ไอเชี่ยนี่ลืมเปลี่ยนภาษา")
async def translate_command(interaction: discord.Interaction, message: discord.Message) -> None:
    def translate_en_th(text: str) -> str:
        translated = []
        for char in text.lower():
            translated.append(EN_TO_TH.get(char, char))
        return "".join(translated)
    translated_text = translate_en_th(message.content)
    await interaction.response.send_message(
        f"{message.content}\t**>\t{translated_text}**\n> {message.jump_url}"
    )
    
@bot.tree.command(name="enabled", description="Enabled this message channel")
async def enabled_channel(interaction: discord.Interaction) -> None:
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

@bot.tree.command(name="disabled", description="Disabled this message channel")
async def disabled_channel(interaction: discord.Interaction) -> None:
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
) -> None:
    channel = interaction.channel

    messages = []
    async for msg in channel.history(limit=100):
        if not msg.author.bot and "http" in msg.content and "tiktok" in msg.content:
            messages.append(msg)
            if len(messages) >= 10:
                break

    if not messages:
        await interaction.response.send_message("ไม่พบข้อความที่มีลิงก์", ephemeral=True)
        return

    if message >= len(messages):
        await interaction.response.send_message("ไม่พบข้อความที่เลือก", ephemeral=True)
        return

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
) -> List[app_commands.Choice[int]]:
    channel = interaction.channel
    
    messages = []
    async for msg in channel.history(limit=100):
        if not msg.author.bot and "http" in msg.content and "tiktok" in msg.content:
            messages.append(msg)
            if len(messages) >= 10:
                break

    choices = []
    for idx, msg in enumerate(messages):
        content = msg.content
        
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
        if len(choice_name) > 100:
            choice_name = choice_name[:97] + "..."
        choices.append(app_commands.Choice(name=choice_name, value=idx))
    
    return choices

@bot.event
async def on_message(message: discord.Message) -> None:
    """Handle messages in specified channels"""
    if not message.author.bot and message.channel.id not in bot.channel_ids:
        urls = re.findall(
            f"https?://\\S*(?:{Validator.tiktok_pattern}|{Validator.facebook_pattern})\\S+", 
            message.content
        )
        for url in urls:
            logger.info(f"url detected: {url}")
            await send_reply(message, url)
    await bot.process_commands(message)

async def send_reply(message: discord.Message, url: str) -> None:
    """Handle video URL replies"""
    async def send_error() -> None:
        error_msg = await message.reply(
            "**Error: Can't get video url**\n*This message will be deleted in 30 seconds.*",
            mention_author=False
        )
        await asyncio.sleep(30)
        await error_msg.delete()

    async def try_embed(content: str) -> bool:
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
    
    source, item_id = Validator.validate(url)
    
    if source == 'TikTok':
        for domain in ["a.tnktok.com", "tfxktok.com"]:
            new_url = '/'.join(url.split('/', 3)[:2] + [domain] + url.split('/', 3)[3:])
            if await try_embed(f"{message.jump_url}\n> [Video on Tiktok]({new_url})"):
                return
        
        if video_url := await get_video(source, url):
            await message.reply(
                f"{message.jump_url}\n> [Video on Tiktok]({video_url})",
                mention_author=False
            )
        else:
            await send_error()
            
    if source == 'Facebook':
        if video_url := await get_video(source, url):
            if not await try_embed(f"{message.jump_url}\n> [Video on Facebook]({video_url})"):
                await send_error()
        else:
            await send_error()

async def start_bot() -> bool:  
    try:
        await bot.start(TOKEN)
    except discord.errors.DiscordServerError:
        logger.error("Connection error occurred. Retrying in 10 seconds...")
        await asyncio.sleep(10)
        return True
    except Exception as e:
        logger.error("Error occurred", exc_info=e)
        await asyncio.sleep(10)
        return True
    return False

async def cleanup() -> None:
    """ทำความสะอาดการเชื่อมต่อทั้งหมด"""
    try:
        if not bot.is_closed():
            await bot.close()
        if bot.session and not bot.session.closed:
            await bot.session.close()
        if bot.db:
            await bot.db.close()
    except Exception as e:
        logger.error("Error during cleanup", exc_info=e)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        logger.info("Starting bot...")
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        loop.run_until_complete(cleanup())
    finally:
        loop.close()
        logger.info("Bot has been stopped gracefully.")
