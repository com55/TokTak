
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
import requests
import html
from urllib.parse import urljoin, urlparse
from module import Facebook, TikTokv2
from module.facebook import get_facebook_video_url
from module.send_component_v2 import (
    FETCHING_MESSAGE,
    send_facebook_video,
    send_facebook_image,
)
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
    facebook_pattern = r'(facebook\.com/|fb\.watch/)'
    @staticmethod
    def _host_in(url: str, *domains: str) -> bool:
        host = urlparse(url).hostname or ''
        return any(host == d or host.endswith('.' + d) for d in domains)

    @staticmethod
    def validate(url: str) -> Tuple[str, Optional[str]]:
        if Validator._host_in(url, 'tiktok.com') and re.search(Validator.tiktok_pattern, url):
            return "TikTok", url
        if Validator._host_in(url, 'facebook.com', 'fb.watch') and re.search(Validator.facebook_pattern, url):
            return "Facebook", url
        insta_match = re.search(Validator.instag_pattern, url)
        if Validator._host_in(url, 'instagram.com') and insta_match:
            return "Instagram", insta_match.group(2)
        return "Invalid URL", None

def translate_en_th(text: str) -> str:
    translated = []
    for char in text:
        translated.append(EN_TO_TH.get(char, char))
    return "".join(translated)

def translate_with_preserving_syntax(text: str) -> str:
    # 1. Regex for Discord Syntax (<@123>, <:emoji:123>, <t:123>, etc.)
    discord_syntax = r'<[a-z]?@?&?!?#?\d+>|<[a-z]?:[a-zA-Z0-9_]+:\d+>|<t:\d+(?::[tTdDfFR])?>|</[a-zA-Z0-9_-]+:\d+>'
    
    # 2. Regex for Code Blocks (```code``` or `code`)
    code_blocks = r'```.*?```|`.*?`'
    
    # 3. Regex for URLs (http, https)
    urls = r'https?://[^\s<>]+'
    
    # Combine all patterns using OR (|)
    # We use flags=re.DOTALL to make sure '.' matches newlines in code blocks
    combined_pattern = f'({discord_syntax}|{code_blocks}|{urls})'
    
    # Split text while keeping the matched patterns
    parts = re.split(combined_pattern, text, flags=re.DOTALL)
    translated_parts = []
    
    for part in parts:
        # Check if the part matches any of our "protected" patterns
        if re.fullmatch(combined_pattern, part, flags=re.DOTALL):
            translated_parts.append(part)
        else:
            # Translate only the parts that are plain text
            translated_parts.append(translate_en_th(part))
            
    return "".join(translated_parts)

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
                media = (data.get('media') or [{}])[0]
                if data.get('is_video') is True and media.get('is_video') is True:
                    return media.get('address')
                logger.info("Facebook scraper returned image-only metadata; trying video fallback")
                return None
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
    translated_text = translate_with_preserving_syntax(message.content)
    # ตอบกลับข้อความต้นฉบับ โดยไม่ mention เจ้าของข้อความ
    await message.reply(
        f"{translated_text}\n-# {interaction.user.display_name} uses the '{interaction.command.name}' command.",
        mention_author=False
    )
    # ตอบ interaction ว่าใช้งานสำเร็จ
    await interaction.response.send_message("✅ ใช้งานคำสั่งเรียบร้อย", ephemeral=True, delete_after=10)

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
            r'https?://[^\s]*?(?:(?:tiktok\.com|tt\.site|facebook\.com|fb\.watch|instagram\.com)/\S*)',
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
            "**Error: Can't get video url or post detail**\n-# *This message will be deleted in 30 seconds.*",
            mention_author=False
        )
        await asyncio.sleep(30)
        await error_msg.delete()

    async def try_embed(content: str, placeholder: Optional[discord.Message] = None) -> bool:
        """Post content (or edit it into placeholder) and wait for Discord to embed it"""
        if placeholder:
            reply = await placeholder.edit(content=content, allowed_mentions=discord.AllowedMentions.none())
        else:
            reply = await message.reply(content, mention_author=False)
        end_time = asyncio.get_event_loop().time() + 10
        embedded = False
        
        while asyncio.get_event_loop().time() <= end_time:
            reply = await message.channel.fetch_message(reply.id)
            if reply.embeds:
                embedded = not any(embed.title == "Log in or sign up to view" for embed in reply.embeds)
                break
            await asyncio.sleep(0.5)

        if embedded:
            await message.edit(suppress=True)
        elif placeholder:
            await placeholder.edit(content=FETCHING_MESSAGE)
        else:
            await reply.delete()
        return embedded

    async def embed_media_ok(fixer_url: str) -> bool:
        """Fetch fixer_url as Discord's crawler would and check it yields real media"""
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)'}
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with bot.aiohttp_session.get(fixer_url, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    return False
                if resp.content_type.startswith(('image/', 'video/')):
                    return True
                page = await resp.text()
                page_url = str(resp.url)
            video = re.search(
                r'<meta[^>]+(?:og:video|twitter:player:stream)"[^>]+content="([^"]+)"', page
            )
            if not video:
                return bool(re.search(r'<meta[^>]+og:image"', page))
            video_url = urljoin(page_url, html.unescape(video.group(1)))
            async with bot.aiohttp_session.get(video_url, headers=headers, timeout=timeout) as resp:
                return resp.status in (200, 206) and resp.content_type.startswith('video/')
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def try_facebed_embed(facebook_url: str) -> bool:
        if "facebook.com" not in facebook_url:
            return False
        facebed_url = re.sub(
            r'https://(www\.)?facebook\.com/(.*)',
            r'https://facebed.com/\2',
            facebook_url,
        )
        if await embed_media_ok(facebed_url):
            logger.info("Try to embed with facebed url: %s", facebed_url)
            return await try_embed(
                f"> [Facebook](<{facebook_url}>) - [facebed]({facebed_url})"
            )
        return False

    async def facebook_media_is_video(video_url: Optional[str]) -> bool:
        if not video_url:
            return False
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with bot.aiohttp_session.get(
                video_url,
                headers={"Range": "bytes=0-0"},
                timeout=timeout,
            ) as resp:
                return resp.status in (200, 206) and resp.content_type.startswith("video/")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def handle_facebook_failure(
        placeholder: discord.Message,
        allow_facebed: bool = True,
    ) -> None:
        await placeholder.delete()
        if allow_facebed and await try_facebed_embed(url):
            return
        await send_error()

    if urlparse(url).hostname in ('tt.site', 'www.tt.site'):
        async with bot.aiohttp_session.get(url) as resp:
            url = str(resp.url)

    source, item_id = Validator.validate(url)
    
    if source in ('TikTok', 'Instagram'):
        placeholder = await message.reply(
            FETCHING_MESSAGE,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        try:
            if source == 'TikTok':
                for domain in ["a.tnktok.com", "tfxktok.com"]:
                    new_url = '/'.join(url.split('/', 3)[:2] + [domain] + url.split('/', 3)[3:])
                    if not await embed_media_ok(new_url):
                        continue
                    if await try_embed(f"> [Video on Tiktok]({new_url})", placeholder):
                        return

                if video_url := await get_video(source, url):
                    await placeholder.edit(content=f"> [Video on Tiktok]({video_url})")
                    return

            if source == 'Instagram':
                for domain in ["zzinstagram.com", "eeinstagram.com"]:
                    fixer_url = urlparse(url)._replace(netloc=domain, query='').geturl()
                    if await embed_media_ok(fixer_url):
                        logger.info("Try to embed with instagram fixer: %s", fixer_url)
                        if await try_embed(f"> [Post on Instagram]({fixer_url})", placeholder):
                            return
        except Exception:
            logger.error("%s reply crashed: url=%s", source, url, exc_info=True)

        await placeholder.delete()
        await send_error()

    if source == 'Facebook':
        def is_facebook_video(url: str) -> bool:
            video_patterns = [
                "fb.watch", "/watch", "/reel/", "/videos/", "video.php", "story.php", "/share/v/", "/share/r/"
            ]
            return any(pattern in url for pattern in video_patterns)
        
        host = urlparse(url).hostname or ''
        is_facebook_host = host == 'facebook.com' or host.endswith('.facebook.com')
        if host in ('fb.watch', 'www.fb.watch') or (is_facebook_host and '/watch/?v' in url):
            async with bot.aiohttp_session.get(url) as resp:
                redirected_url = str(resp.url)
            try:
                video_id = redirected_url.split("/videos/")[1].split("/")[0]
                url = f'https://www.facebook.com/reel/{video_id}'
            except Exception:
                pass

        is_video = is_facebook_video(url)

        placeholder = await message.reply(
            FETCHING_MESSAGE,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        try:
            if is_video:
                video_url = await get_video(source, url)
                if not await facebook_media_is_video(video_url):
                    logger.info("Facebook scraper did not return a playable video; trying yt-dlp: url=%s", url)
                    try:
                        video_url = await asyncio.to_thread(get_facebook_video_url, url)
                    except Exception:
                        logger.error("Facebook yt-dlp fallback failed: url=%s", url, exc_info=True)
                        video_url = None

                if not await facebook_media_is_video(video_url):
                    logger.error("No playable Facebook video found: url=%s", url)
                    await handle_facebook_failure(placeholder, allow_facebed=False)
                    return

                success, status, error_msg = await send_facebook_video(
                    TOKEN, message, placeholder, bot.aiohttp_session, video_url, url
                )
            else:
                success, status, error_msg = await send_facebook_image(
                    TOKEN, message, placeholder, bot.aiohttp_session, url
                )
            if success:
                await message.edit(suppress=True)
                return

            logger.error(
                "Facebook reply failed: url=%s type=%s status=%s error=%s",
                url,
                "video" if is_video else "image",
                status,
                error_msg[:500],
            )
            await handle_facebook_failure(placeholder, allow_facebed=not is_video)
        except Exception:
            logger.error("Facebook reply crashed: url=%s", url, exc_info=True)
            await handle_facebook_failure(placeholder, allow_facebed=not is_video)

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
