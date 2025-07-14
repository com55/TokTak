from typing import Literal
import json
from logging import Logger
import aiohttp
import os
from urllib.parse import urlparse
import time
import discord

from module.facebook_image import get_facebook_post_image
from .component_v2 import ComponentV2Builder

async def download_image(session: aiohttp.ClientSession, url: str) -> tuple[bytes, str] | tuple[None, None]:
    """Downloads an image from a URL and returns its bytes and filename.

    Args:
        session (aiohttp.ClientSession): Active aiohttp session for making requests
        url (str): URL of the image to download

    Returns:
        tuple[bytes, str] | tuple[None, None]: A tuple containing:
            - bytes | None: Image data in bytes if successful, None if failed
            - str | None: Filename if successful, None if failed
    """
    try:
        async with session.get(url) as response:
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
                print(f"Failed to download {url}, status: {response.status}")
                return None, None
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None, None

async def send_facebook_video(
    token: str, 
    message: discord.Message, 
    session: aiohttp.ClientSession, 
    video_url: str
) -> tuple[bool, int, str]:
    """Sends a Facebook video as a message in Discord using the Discord API.

    Args:
        token (str): Discord bot token for authentication
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
    request_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    components = ComponentV2Builder()
    components.gallery().media(video_url).end_gallery()
    payload = components.to_payload()
    payload['message_reference'] = {
        'message_id': message.id,
        'channel_id': channel_id
    }
    payload['allowed_mentions'] = {
        'replied_user': False
    }
    async with session.post(request_url, json=payload, headers=headers) as resp:
        if resp.status in [200, 201]:
            return True, resp.status, ""
        else:
            error_msg = await resp.text()
            return False, resp.status, error_msg

async def send_facebook_image(
    token: str, 
    message: discord.Message, 
    session: aiohttp.ClientSession, 
    facebook_url: str
) -> tuple[bool, int, str]:
    """Sends a Facebook image post as a message in Discord using the Discord API.

    Args:
        token (str): Discord bot token for authentication
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
    request_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}"
    }
    max_retrys = 3
    current_retrys = 0
    post_data = {}
    while not post_data and current_retrys < max_retrys:
        post_data = await get_facebook_post_image(facebook_url)
        if not post_data:
            current_retrys += 1
    
    if not post_data:
        return False, 400, "Failed to get image form Facebook link."
    
    # Download the image bytes and filename
    downloaded_files = []
    image_urls = post_data['images']    
    
    # ใช้ enumerate เพื่อให้มี index สำหรับ key `files[i]`
    for i, url in enumerate(image_urls):
        image_bytes, filename = await download_image(session, url)
        if image_bytes and filename:
            # สร้างชื่อไฟล์ที่ไม่ซ้ำกัน
            unique_filename = f"{i}_{filename}"
            downloaded_files.append((unique_filename, image_bytes))
    
    if not downloaded_files:
        return False, 400, "Failed to download any images."
    
    components = ComponentV2Builder()
    container = components.container(accent_color=0x1877F2)
    
    container.text(f"### [{post_data['post_owner']}]({facebook_url})")
    container.text(f"{post_data['description']}")

    container.separator()

    gallery = container.gallery()
    for filename, _ in downloaded_files:
        gallery.media(f"attachment://{filename}")
    gallery.end_gallery()
    
    action_row = container.action_row()
    action_row.button(
        style=5,
        label=f"And more {post_data['extra_images'][1:]} images on Facebook" if post_data['extra_images'] else "View on Facebook",
        url=facebook_url
    )
    action_row.end_action_row()

    container.end_container()

    payload = components.to_payload()
    payload['message_reference'] = {
        'message_id': message.id,
        'channel_id': channel_id
    }
    payload['allowed_mentions'] = {
        'replied_user': False
    }
    # print(json.dumps(payload, ensure_ascii=False, indent=2))
    
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
    
    async with session.post(request_url, data=form_data, headers=headers) as resp:
        if resp.status in [200, 201]:
            return True, resp.status, ""
        else:
            error_msg = await resp.text()
            return False, resp.status, error_msg