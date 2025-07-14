import html
import re
from bs4 import BeautifulSoup
import aiohttp
import asyncio
from typing import Optional, Dict, List, Union

from module.utils import json_append

async def get_facebook_post_image(url: str) -> Optional[Dict[str, Union[str, List[str], None]]]:
    """
    Scrapes image and post information from a Facebook post URL.

    Args:
        url (str): The Facebook post URL to scrape.

    Returns:
        Optional[Dict[str, Union[str, List[str], None]]]: A dictionary containing:
            - post_owner (str): Name of the post owner
            - profile_pic_url (str): URL of the profile picture
            - description (str): Post description
            - images (List[str]): List of image URLs in the post
            - extra_images (str): Additional images indicator (e.g., "+5")
        Returns None if no images are found.
    """
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Dnt': '1',
        'Dpr': '1.3125',
        'Priority': 'u=0, i',
        'Sec-Ch-Prefers-Color-Scheme': 'dark',
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Full-Version-List': '"Chromium";v="124.0.6367.156", "Google Chrome";v="124.0.6367.156", "Not-A.Brand";v="99.0.0.0"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Model': '""',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Ch-Ua-Platform-Version': '"15.0.0"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'Viewport-Width': '1463',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            html_content = await response.text()
            pre_soup = BeautifulSoup(html_content, 'html.parser')
            soup = BeautifulSoup(html.unescape(pre_soup.prettify()), 'html.parser')
            json_append(data={url: f"{soup}"}, file="debug_soup.json", max_items=20)

            # 1. post_owner (ชื่อเจ้าของโพสต์)
            post_owner = None
            meta_title = soup.find('meta', {'property': 'og:title'})
            if meta_title:
                post_owner = meta_title.get('content', None)

            # 2. profile_pic_url (URL รูปโปรไฟล์เจ้าของโพสต์)
            profile_pic_url = None
            for link in soup.find_all('link', {'as': 'image'}):
                href = link.get('href', '')
                if href and 'jpg_s40x40' in href:
                    profile_pic_url = href
                    break

            # 3. description (คำอธิบาย)
            description = None
            meta_desc = soup.find('meta', {'property': 'og:description'})
            if not meta_desc:
                meta_desc = soup.find('meta', {'name': 'description'})
            if meta_desc:
                description = meta_desc.get('content', None)

            # 4. images (URL ของรูปในโพสต์)
            images = []
            first_pattern = None
            for img in soup.find_all('img'):
                parent = img.parent
                if parent.name == 'div' and parent.parent.name != 'a':
                    src = img.get('src', '')
                    if src.startswith('http') and not src.startswith('data:') and len(src) > 100:
                        try:
                            pattern = '/'.join(src.split('/')[2:5])
                        except Exception:
                            pattern = None
                        if not first_pattern:
                            first_pattern = pattern
                        elif pattern != first_pattern:
                            break
                        images.append(src)
                if len(images) >= 5:
                    break
            images = images[:5]

            # 5. extra_images (ข้อความที่บอกจำนวนรูปเพิ่มเติม เช่น +25)
            extra_images = None
            for tag in soup.find_all(['div', 'span']):
                if tag.string and re.match(r"^\+\d+$", tag.string.strip()):
                    extra_images = tag.string.strip()
                    break

            result = {
                'post_owner': post_owner,
                'profile_pic_url': profile_pic_url,
                'description': description,
                'images': images,
                'extra_images': extra_images
            }
            json_append(data={"url": url,"output": result}, file="debug_image.json", max_items=20)
            return result if images else None

if __name__ == "__main__":
    res = asyncio.run(get_facebook_post_image("https://www.facebook.com/share/p/1ByefZhf7P/"))
    print(res)