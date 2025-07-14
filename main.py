
import os
import re
from typing import Optional, Dict, List, Tuple, Any, Union
from dotenv import load_dotenv
import asyncio
import discord
from discord.ext import commands
import json
import aiohttp
import aiosqlite
import logging
from logging import Logger
from discord.flags import Intents
from module import Facebook, TikTokv2
from module.send_component_v2 import send_facebook_video, send_facebook_image
from module.utils import json_append

# Setup discord logging
logger: Logger = logging.getLogger(name='discord')

load_dotenv()
TOKEN: str = os.environ["TOKEN"]
db_path = 'data.db'

# Load keyboard mapping
with open(file='module/keyboard_map.json', mode='r', encoding='utf-8') as f:
    EN_TO_TH: Dict[str, str] = json.load(fp=f)

intents: Intents = discord.Intents.default()
intents.message_content = True

# สร้าง ClientSession ที่ใช้ร่วมกัน
class Bot(commands.Bot):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.aiohttp_session: aiohttp.ClientSession
        self.db: aiosqlite.Connection
        self.channel_ids = []

    async def setup_hook(self) -> None:
        self.aiohttp_session = aiohttp.ClientSession()
        self.db = await aiosqlite.connect(database=db_path)
    
    async def close(self) -> None:
        if self.aiohttp_session:
            await self.aiohttp_session.close()
        if self.db:
            await self.db.close()
        await super().close()

bot: Bot = Bot(command_prefix=commands.when_mentioned, intents=intents, shard_count=2)

async def setup_table() -> None:
    """สร้างตารางเก็บ channel ID ในฐานข้อมูล SQLite"""
    async with bot.db.cursor() as cursor:
        await cursor.execute(
            sql="CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY)"
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

def translate_en_th(text: str) -> str:
    translated = []
    for char in text:
        translated.append(EN_TO_TH.get(char, char))
    return "".join(translated)

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
            json_append(data, file="debug.json", max_items=50)
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
    translated_text = translate_en_th(message.content)
    # ตอบกลับข้อความต้นฉบับ โดยไม่ mention เจ้าของข้อความ
    await message.reply(
        f"{translated_text}\n-# {interaction.user.display_name} uses the '{interaction.command.name}' command.",
        mention_author=False
    )
    # ตอบ interaction ว่าใช้งานสำเร็จ
    await interaction.response.send_message("✅ ใช้งานคำสั่งเรียบร้อย", ephemeral=True)
    await asyncio.sleep(10)
    await interaction.delete_original_response()

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

@bot.event
async def on_message(message: discord.Message) -> None:
    """Handle messages in specified channels"""
    if not message.author.bot and message.channel.id not in bot.channel_ids:
        urls = re.findall(
            r'https?://[^\s]*?(?:(?:tiktok\.com|facebook\.com|fb\.watch)/\S*)',
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
            "**Error: Can't get video url**\n-# *This message will be deleted in 30 seconds.*",
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
            if await try_embed(f"> [Video on Tiktok]({new_url})"):
                return

        if video_url := await get_video(source, url):
            await message.reply(
                f"> [Video on Tiktok]({video_url})",
                mention_author=False
            )
        else:
            await send_error()

    if source == 'Facebook':
        def is_facebook_video(url: str) -> bool:
            video_patterns = [
                "fb.watch", "/watch", "/reel/", "/videos/", "video.php", "story.php", "/share/v/", "/share/r/"
            ]
            return any(pattern in url for pattern in video_patterns)
        if is_facebook_video(url):
            video_url = await get_video(source, url)
            success, status, error_msg = await send_facebook_video(TOKEN, message, bot.aiohttp_session, video_url)
        else:
            success, status, error_msg = await send_facebook_image(TOKEN, message, bot.aiohttp_session, url)
        if success:
            await message.edit(suppress=True)
        else:
            logger.warning(f"Error {status}: {error_msg}")

async def start_bot() -> bool:  
    try:
        bot.run(TOKEN)
    except discord.errors.DiscordServerError:
        logger.error("Connection error occurred. Retrying in 10 seconds...")
        await asyncio.sleep(10)
        return True
    except Exception as e:
        logger.error("Error occurred", exc_info=e)
        await asyncio.sleep(10)
        return True
    return False

if __name__ == "__main__":
    bot.run(TOKEN)
