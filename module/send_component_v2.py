from typing import Literal
import asyncio
import html
import json
import logging
from logging import Logger
import aiohttp
import os
from urllib.parse import urlparse
import time
import discord

from module.facebook_image import FACEBOOK_CDN_HEADERS, get_facebook_post_image
from .component_v2 import ComponentV2Builder

logger: Logger = logging.getLogger("discord")

# Discord docs say 4000, but Container + MediaGallery payloads 500 above ~3615.
DISCORD_COMPONENT_TEXT_LIMIT = 3600
TRUNCATION_SUFFIX = "..."
FETCHING_MESSAGE = "> Fetching data..."
ERROR_MESSAGE = (
    "**Error: Can't get video url or post detail**\n"
    "-# *This message will be deleted in 30 seconds.*"
)
ERROR_DELETE_AFTER_SECONDS = 30
NO_MENTIONS_PAYLOAD = {
    "parse": [],
    "replied_user": False,
    "roles": [],
    "users": [],
}


def _truncate_description_for_discord(title: str, description: str | None) -> str:
    if not description:
        return ""

    max_description_len = DISCORD_COMPONENT_TEXT_LIMIT - len(title)
    if max_description_len <= len(TRUNCATION_SUFFIX):
        return TRUNCATION_SUFFIX[:max_description_len]

    if len(description) <= max_description_len:
        return description

    return description[:max_description_len - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX


def _message_edit_url(channel_id: int, message_id: int) -> str:
    return f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"


async def edit_facebook_error_reply(reply_message: discord.Message) -> None:
    await reply_message.edit(
        content=ERROR_MESSAGE,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    await asyncio.sleep(ERROR_DELETE_AFTER_SECONDS)
    await reply_message.delete()

async def download_image(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, str] | tuple[None, None]:
    """Downloads an image from a URL and returns its bytes and filename.

    Args:
        session (aiohttp.ClientSession): Active aiohttp session for making requests
        url (str): URL of the image to download
        headers (dict[str, str] | None): Optional request headers

    Returns:
        tuple[bytes, str] | tuple[None, None]: A tuple containing:
            - bytes | None: Image data in bytes if successful, None if failed
            - str | None: Filename if successful, None if failed
    """
    url = html.unescape(url).strip()
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                # ดึงข้อมูลรูปภาพเป็น bytes
                image_bytes = await response.read()
                # พยายามดึงชื่อไฟล์จาก URL
                path = urlparse(url).path
                filename = os.path.basename(path).split('?')[0] # เอาแค่ชื่อไฟล์ ตัด query string ออก
                if not filename: # ถ้าไม่มีชื่อไฟล์ใน URL ก็ตั้งชื่อเอง
                    filename = f"downloaded_image_{int(time.time())}.jpg"
                return image_bytes, filename
            else:
                logger.warning("Failed to download image: status=%s url=%s", response.status, url[:120])
                return None, None
    except Exception as e:
        logger.warning("Failed to download image: %s url=%s", e, url[:120])
        return None, None

async def send_facebook_video(
    discord_bot_token: str, 
    message: discord.Message,
    reply_message: discord.Message,
    session: aiohttp.ClientSession, 
    video_url: str
) -> tuple[bool, int, str]:
    """Sends a Facebook video as a message in Discord using the Discord API.

    Args:
        discord_bot_token (str): Discord bot token for authentication
        message (discord.Message): The Discord message to reply to
        session (aiohttp.ClientSession): Active aiohttp session for making requests
        video_url (str): URL of the Facebook video to send

    Returns:
        tuple[bool, int, str]: A tuple containing:
            - bool: Success status of the request
            - int: HTTP status code
            - str: Error message if request failed, empty string if successful
    """
    channel_id = message.channel.id
    headers = {
        "Authorization": f"Bot {discord_bot_token}",
        "Content-Type": "application/json"
    }
    components = ComponentV2Builder()
    components.gallery().media(video_url).end_gallery()
    payload = components.to_payload()
    payload["content"] = ""
    payload["allowed_mentions"] = NO_MENTIONS_PAYLOAD
    request_url = _message_edit_url(channel_id, reply_message.id)
    async with session.patch(request_url, json=payload, headers=headers) as resp:
        if resp.status in [200, 201]:
            return True, resp.status, ""
        error_msg = await resp.text()
        logger.error(
            "Discord API rejected Facebook video: status=%s url=%s response=%s",
            resp.status,
            video_url[:120],
            error_msg[:500],
        )
        return False, resp.status, error_msg

async def send_facebook_image(
    discord_bot_token: str, 
    message: discord.Message,
    reply_message: discord.Message,
    session: aiohttp.ClientSession, 
    facebook_url: str
) -> tuple[bool, int, str]:
    """Sends a Facebook image post as a message in Discord using the Discord API.

    Args:
        discord_bot_token (str): Discord bot token for authentication
        message (discord.Message): The Discord message to reply to
        session (aiohttp.ClientSession): Active aiohttp session for making requests
        facebook_url (str): URL of the Facebook post containing images

    Returns:
        tuple[bool, int, str]: A tuple containing:
            - bool: Success status of the request
            - int: HTTP status code
            - str: Error message if request failed, empty string if successful
    """
    channel_id = message.channel.id
    request_url = _message_edit_url(channel_id, reply_message.id)
    headers = {
        "Authorization": f"Bot {discord_bot_token}"
    }
    max_retrys = 3
    current_retrys = 0
    post_data = {}
    while not post_data and current_retrys < max_retrys:
        post_data = await get_facebook_post_image(facebook_url)
        if not post_data:
            current_retrys += 1
            logger.warning(
                "Facebook image scrape returned no data: url=%s retry=%s/%s",
                facebook_url,
                current_retrys,
                max_retrys,
            )

    if not post_data:
        logger.error("Facebook image scrape failed after retries: url=%s", facebook_url)
        return False, 400, "Failed to get image form Facebook link."
    
    # Download the image bytes and filename
    downloaded_files = []
    image_urls = post_data['images']    
    
    # ใช้ enumerate เพื่อให้มี index สำหรับ key `files[i]`
    for i, url in enumerate(image_urls):
        image_bytes, filename = await download_image(session, url, FACEBOOK_CDN_HEADERS)
        if image_bytes and filename:
            # สร้างชื่อไฟล์ที่ไม่ซ้ำกัน
            unique_filename = f"{i}_{filename}"
            downloaded_files.append((unique_filename, image_bytes))
    
    if not downloaded_files:
        logger.error(
            "Facebook image download failed: url=%s image_urls=%s",
            facebook_url,
            len(image_urls),
        )
        return False, 400, "Failed to download any images."

    title_text = f"### [{post_data['post_owner']}]({facebook_url})"
    description_text = _truncate_description_for_discord(title_text, post_data.get('description'))
    logger.info(
        "Sending Facebook image post: url=%s images=%s desc_len=%s total_text=%s",
        facebook_url,
        len(downloaded_files),
        len(description_text),
        len(title_text) + len(description_text),
    )

    components = ComponentV2Builder()
    container = components.container(accent_color=0x1877F2)

    container.text(title_text)
    container.text(description_text)

    container.separator()

    gallery = container.gallery()
    for filename, _ in downloaded_files:
        gallery.media(f"attachment://{filename}")
    gallery.end_gallery()
    
    remaining_images = post_data.get("extra_images") or 0
    if remaining_images > 0:
        image_word = "image" if remaining_images == 1 else "images"
        button_label = f"And more {remaining_images} {image_word} on Facebook"
    else:
        button_label = "View on Facebook"

    action_row = container.action_row()
    action_row.button(
        style=5,
        label=button_label,
        url=facebook_url
    )
    action_row.end_action_row()

    container.end_container()

    payload = components.to_payload()
    payload["content"] = ""
    payload["allowed_mentions"] = NO_MENTIONS_PAYLOAD
    
    form_data = aiohttp.FormData()
    
    form_data.add_field(
        'payload_json',
        json.dumps(payload),
        content_type='application/json'
    )
    
    for i, (filename, image_bytes) in enumerate(downloaded_files):
        form_data.add_field(
            f'files[{i}]',
            image_bytes,
            filename=filename,
            content_type='image/jpeg' # หรือ image/png, image/gif ตามความเหมาะสม
        )
    
    async with session.patch(request_url, data=form_data, headers=headers) as resp:
        if resp.status in [200, 201]:
            return True, resp.status, ""
        error_msg = await resp.text()
        logger.error(
            "Discord API rejected Facebook image post: status=%s url=%s response=%s",
            resp.status,
            facebook_url,
            error_msg[:500],
        )
        return False, resp.status, error_msg