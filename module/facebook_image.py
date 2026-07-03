import html
import json
import re
from typing import Dict, List, Optional, Union

import aiohttp
from bs4 import BeautifulSoup

from .utils import json_append

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

FACEBOOK_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

DESKTOP_HEADERS = {
    **FACEBOOK_HEADERS,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Dnt": "1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-User": "?1",
    "User-Agent": DESKTOP_USER_AGENT,
}


def _build_headers(user_agent: str) -> Dict[str, str]:
    return {**FACEBOOK_HEADERS, "User-Agent": user_agent}


def _parse_soup(html_content: str) -> BeautifulSoup:
    pre_soup = BeautifulSoup(html_content, "html.parser")
    return BeautifulSoup(html.unescape(pre_soup.prettify()), "html.parser")


def _meta_content(soup: BeautifulSoup, prop: str) -> Optional[str]:
    tag = soup.find("meta", {"property": prop})
    if tag and tag.get("content"):
        return tag["content"]
    tag = soup.find("meta", {"name": prop})
    if tag and tag.get("content"):
        return tag["content"]
    return None


def _clean_owner(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    return re.sub(r"\s*\|\s*Facebook\s*$", "", title).strip() or title


def _image_key(url: str) -> str:
    return url.split("?")[0]


def _dedupe_images(images: List[str]) -> List[str]:
    seen: set[str] = set()
    unique: List[str] = []
    for url in images:
        key = _image_key(url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(url)
    return unique


def _is_post_image(url: str) -> bool:
    lowered = url.lower()
    if not url.startswith("http") or url.startswith("data:"):
        return False
    if "rsrc.php" in lowered or "static.xx.fbcdn.net" in lowered:
        return False
    if not ("scontent" in lowered or "/t39." in lowered or "/t31." in lowered):
        return False
    for skip in ("s40x40", "s32x32", "p50x50", "jpg_s40x40", "emoji.php", ".css", ".js"):
        if skip in lowered:
            return False
    return True


def _extract_images_from_img_tags(soup: BeautifulSoup, limit: int = 5) -> List[str]:
    images: List[str] = []
    first_pattern: Optional[str] = None

    for img in soup.find_all("img"):
        parent = img.parent
        if not parent or parent.name != "div" or parent.parent is None or parent.parent.name == "a":
            continue

        src = img.get("src", "")
        if not _is_post_image(src):
            continue

        try:
            pattern = "/".join(src.split("/")[2:5])
        except (IndexError, ValueError):
            pattern = None

        if first_pattern and pattern != first_pattern:
            break

        if not first_pattern:
            first_pattern = pattern

        if src not in images:
            images.append(src)

        if len(images) >= limit:
            break

    return images


def _extract_images_from_regex(html_content: str, limit: int = 5) -> List[str]:
    pattern = r"https://scontent[^\"'<>\s\\]+"
    matches = re.findall(pattern, html_content)
    images: List[str] = []

    for url in matches:
        url = url.rstrip("\\")
        if not _is_post_image(url):
            continue
        if url not in images:
            images.append(url)
        if len(images) >= limit:
            break

    return images


def _extract_extra_images(soup: BeautifulSoup) -> Optional[str]:
    for tag in soup.find_all(["div", "span"]):
        text = tag.string
        if text and re.match(r"^\+\d+$", text.strip()):
            return text.strip()
    return None


def _extract_profile_pic(soup: BeautifulSoup) -> Optional[str]:
    for link in soup.find_all("link", {"as": "image"}):
        href = link.get("href", "")
        if href and "jpg_s40x40" in href:
            return href
    return None


def _decode_json_string(value: str) -> Optional[str]:
    try:
        return json.loads(f'"{value}"')
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_text_candidates(html_content: str) -> List[str]:
    candidates: List[str] = []
    seen: set[str] = set()

    for match in re.findall(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', html_content):
        decoded = _decode_json_string(match)
        if not decoded or len(decoded) < 20:
            continue
        if decoded in seen:
            continue
        seen.add(decoded)
        candidates.append(decoded)

    return sorted(candidates, key=len, reverse=True)


def _pick_post_text(candidates: List[str], og_desc: Optional[str]) -> Optional[str]:
    if not candidates:
        return None

    if og_desc:
        preview = og_desc.removesuffix("...").strip()
        if preview:
            for candidate in candidates:
                if candidate.startswith(preview) or preview in candidate:
                    return candidate

    return candidates[0]


def _resolve_description(
    og_desc: Optional[str],
    desktop_html: Optional[str],
) -> Optional[str]:
    if desktop_html:
        full_text = _pick_post_text(_extract_text_candidates(desktop_html), og_desc)
        if full_text:
            return full_text

    return og_desc


def _extract_post_data(
    soup: BeautifulSoup,
    html_content: str,
    desktop_html: Optional[str] = None,
) -> Dict[str, Union[str, List[str], None]]:
    og_image = _meta_content(soup, "og:image")
    og_title = _meta_content(soup, "og:title")
    og_desc = _meta_content(soup, "og:description")

    images: List[str] = []
    if og_image and _is_post_image(og_image):
        images.append(og_image)

    for src in _extract_images_from_img_tags(soup):
        if src not in images:
            images.append(src)

    if len(images) <= 1:
        for src in _extract_images_from_regex(html_content):
            if src not in images:
                images.append(src)

    return {
        "post_owner": _clean_owner(og_title),
        "profile_pic_url": _extract_profile_pic(soup),
        "description": _resolve_description(og_desc, desktop_html),
        "images": _dedupe_images(images)[:5],
        "extra_images": _extract_extra_images(soup),
    }


async def _fetch_html(
    session: aiohttp.ClientSession,
    url: str,
    headers: Dict[str, str],
) -> tuple[int, str]:
    async with session.get(url, headers=headers, allow_redirects=True) as response:
        return response.status, await response.text()


async def get_facebook_post_image(url: str) -> Optional[Dict[str, Union[str, List[str], None]]]:
    """
    Scrapes image and post information from a Facebook post URL.

    Uses mobile User-Agent for images/metadata and desktop HTML for full post text.
    """
    async with aiohttp.ClientSession() as session:
        mobile_status, mobile_html = await _fetch_html(
            session, url, _build_headers(MOBILE_USER_AGENT)
        )
        mobile_soup = _parse_soup(mobile_html)

        desktop_status, desktop_html = await _fetch_html(session, url, DESKTOP_HEADERS)
        desktop_for_text = desktop_html if desktop_status == 200 else None

        result = _extract_post_data(mobile_soup, mobile_html, desktop_for_text)

        json_append(
            data={
                "url": url,
                "output": result,
                "mobile_status": mobile_status,
                "desktop_status": desktop_status,
                "description_len": len(result["description"] or ""),
            },
            file="debug_image.json",
            max_items=20,
        )
        return result if result["images"] else None
