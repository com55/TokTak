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


def _normalize_login_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    return collapsed.replace("log in to", "log into")


_LOGIN_WALL_TITLES = frozenset({
    "log into facebook",
    "log in or sign up to view",
})


def _is_login_walled(
    og_title: Optional[str],
    og_desc: Optional[str],
    post_owner: Optional[str] = None,
    description: Optional[str] = None,
) -> bool:
    for value in (og_title, post_owner):
        if not value:
            continue
        title = _normalize_login_text(_clean_owner(value) or value)
        if title in _LOGIN_WALL_TITLES:
            return True

    for value in (og_desc, description):
        if not value:
            continue
        lowered = _normalize_login_text(value)
        if lowered.startswith("log into facebook to start sharing"):
            return True
        if lowered.startswith("you must log in to continue"):
            return True

    return False


def _extract_entity_name(html_content: str, typename: str) -> Optional[str]:
    pattern = rf'"__typename"\s*:\s*"{typename}"'
    for match in re.finditer(pattern, html_content):
        chunk = html_content[match.start(): match.start() + 800]
        name_match = re.search(r'"name"\s*:\s*"((?:[^"\\]|\\.)*)"', chunk)
        if not name_match:
            continue
        name = _decode_json_string(name_match.group(1))
        if name and name.strip():
            return name.strip()
    return None


def _extract_owning_profile_name(html_content: str) -> Optional[str]:
    match = re.search(
        r'"owning_profile"\s*:\s*\{[^}]*"name"\s*:\s*"((?:[^"\\]|\\.)*)"',
        html_content,
    )
    if not match:
        return None
    name = _decode_json_string(match.group(1))
    return name.strip() if name else None


def _resolve_post_metadata(
    og_title: Optional[str],
    og_desc: Optional[str],
    desktop_html: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return (post_owner, post_author). post_author is set for group posts."""
    owner = _clean_owner(og_title)
    if not owner:
        return None, None

    if desktop_html:
        group_name = _extract_entity_name(desktop_html, "Group")
        if group_name:
            author = _extract_owning_profile_name(desktop_html)
            if author and author != group_name:
                return group_name, author
            return group_name, None

        if og_desc and owner == og_desc.strip():
            page_name = _extract_entity_name(desktop_html, "Page")
            if page_name:
                return page_name, None

    return owner, None


def _normalize_cdn_url(url: str) -> str:
    return html.unescape(url).strip()


def _facebook_file_id(url: str) -> Optional[str]:
    match = re.search(r"/(\d+_\d+(?:_\d+)?)_", url)
    if match:
        return match.group(1)
    return url.split("?")[0]


def _dedupe_images(images: List[str]) -> List[str]:
    seen: set[str] = set()
    unique: List[str] = []
    for url in images:
        key = _facebook_file_id(url)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(_normalize_cdn_url(url))
    return unique


STICKER_PATH_TYPES = (
    "t39.1997-",
)


def _content_dimensions(url: str) -> Optional[tuple[int, int]]:
    match = re.search(r"cstp=mx(\d+)x(\d+)", url.lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _is_better_image_url(candidate: str, current: str) -> bool:
    candidate_dims = _content_dimensions(candidate)
    current_dims = _content_dimensions(current)
    candidate_max = max(candidate_dims) if candidate_dims else 0
    current_max = max(current_dims) if current_dims else 0
    if candidate_max != current_max:
        return candidate_max > current_max
    return len(candidate) > len(current)


def _delivery_dimensions(url: str) -> Optional[tuple[int, int]]:
    match = re.search(r"ctp=([sp])(\d+)x(\d+)", url.lower())
    if not match:
        return None
    return int(match.group(2)), int(match.group(3))


def _is_avatar_thumbnail(url: str) -> bool:
    dims = _delivery_dimensions(url)
    return dims is not None and max(dims) <= 64


def _is_post_image(url: str) -> bool:
    lowered = url.lower()
    if not url.startswith("http") or url.startswith("data:"):
        return False
    if "rsrc.php" in lowered or "static.xx.fbcdn.net" in lowered:
        return False
    if not ("scontent" in lowered or "/t39." in lowered or "/t31." in lowered):
        return False
    for sticker_type in STICKER_PATH_TYPES:
        if sticker_type in lowered:
            return False
    if _is_avatar_thumbnail(url):
        return False

    dimensions = _content_dimensions(url)
    if dimensions and max(dimensions) >= 300:
        return True

    for skip in (
        "s40x40", "s32x32", "s120x120", "p32x32", "p50x50", "p34x34", "s34x34",
        "jpg_s40x40", "emoji.php", ".css", ".js", "dst-webp",
    ):
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

        src = _normalize_cdn_url(img.get("src", ""))
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
    images: List[str] = []

    for match in re.finditer(pattern, html_content):
        url = _normalize_cdn_url(match.group(0).rstrip("\\"))
        if not _is_post_image(url):
            continue
        images.append(url)
        if len(_dedupe_images(images)) >= limit:
            break

    return _dedupe_images(images)[:limit]


def _register_image_candidate(
    url: str,
    position: int,
    best_url: Dict[str, str],
    first_pos: Dict[str, int],
    counts: Dict[str, int],
) -> None:
    url = _normalize_cdn_url(url)
    if not _is_post_image(url):
        return

    file_id = _facebook_file_id(url)
    if not file_id:
        return

    counts[file_id] = counts.get(file_id, 0) + 1
    first_pos.setdefault(file_id, position)
    if file_id not in best_url or _is_better_image_url(url, best_url[file_id]):
        best_url[file_id] = url


def _find_url_position(html_content: str, url: str) -> int:
    file_id = _facebook_file_id(url)
    if file_id:
        position = html_content.find(file_id)
        if position >= 0:
            return position

    bare_url = url.split("?")[0]
    position = html_content.find(bare_url)
    return position if position >= 0 else len(html_content)


def _collect_post_images_from_html(
    html_content: str,
    limit: int = 5,
    soup: Optional[BeautifulSoup] = None,
    overlay: Optional[str] = None,
) -> tuple[List[str], int]:
    best_url: Dict[str, str] = {}
    first_pos: Dict[str, int] = {}
    counts: Dict[str, int] = {}
    img_tag_ids: List[str] = []

    if soup:
        for url in _extract_images_from_img_tags(soup, limit=10):
            position = _find_url_position(html_content, url)
            _register_image_candidate(url, position, best_url, first_pos, counts)
            file_id = _facebook_file_id(url)
            if file_id:
                img_tag_ids.append(file_id)

    for match in re.finditer(r'"uri"\s*:\s*"((?:[^"\\]|\\.)*)"', html_content):
        decoded = _decode_json_string(match.group(1))
        if decoded and "scontent" in decoded:
            _register_image_candidate(decoded, match.start(), best_url, first_pos, counts)

    for match in re.finditer(r"https://scontent[^\"'<>\s\\]+", html_content):
        _register_image_candidate(
            match.group(0).rstrip("\\"),
            match.start(),
            best_url,
            first_pos,
            counts,
        )

    if not best_url:
        return [], 0

    if img_tag_ids:
        gallery_ids: set[str] = set(img_tag_ids)
        if overlay and not _is_compact_gallery_layout(len(img_tag_ids), overlay):
            cluster_min = min(first_pos[file_id] for file_id in gallery_ids)
            cluster_max = max(first_pos[file_id] for file_id in gallery_ids)
            for file_id, url in best_url.items():
                if file_id in gallery_ids:
                    continue
                dimensions = _content_dimensions(url)
                if not dimensions or max(dimensions) < 350:
                    continue
                if counts.get(file_id, 0) < 3:
                    continue
                position = first_pos.get(file_id, 0)
                if cluster_min - 5000 <= position <= cluster_max + 200000:
                    gallery_ids.add(file_id)
        candidates = sorted(gallery_ids, key=lambda file_id: first_pos[file_id])
    else:
        high_confidence = [file_id for file_id, count in counts.items() if count >= 5]
        if not high_confidence:
            high_confidence = list(best_url.keys())
        candidates = sorted(high_confidence, key=lambda file_id: first_pos[file_id])

    total = len(candidates)
    return [best_url[file_id] for file_id in candidates[:limit]], total


def _has_visible_gallery(soup: BeautifulSoup) -> bool:
    og_image = _meta_content(soup, "og:image")
    if og_image and _is_post_image(og_image):
        return True
    if _extract_images_from_img_tags(soup):
        return True
    if _extract_extra_images(soup):
        return True
    return False


def _overlay_count(overlay: Optional[str]) -> int:
    if not overlay:
        return 0
    match = re.match(r"^\+(\d+)$", overlay.strip())
    return int(match.group(1)) if match else 0


def _is_compact_gallery_layout(img_tag_count: int, overlay: Optional[str]) -> bool:
    """Vertical galleries often show only 1-2 thumbs plus a large +N badge."""
    return img_tag_count <= 2 and _overlay_count(overlay) >= 3


def _extract_extra_images(soup: BeautifulSoup) -> Optional[str]:
    for tag in soup.find_all(["div", "span"]):
        text = tag.string
        if text and re.match(r"^\+\d+$", text.strip()):
            return text.strip()
    return None


def _remaining_image_count(
    overlay: Optional[str],
    image_count: int,
    shown_count: int = 5,
) -> Optional[int]:
    remaining = max(0, image_count - shown_count)
    if remaining > 0:
        return remaining

    if not overlay:
        return None

    overlay_n = _overlay_count(overlay)
    if overlay_n <= 0:
        return None

    # The +N badge sits on the last visible thumbnail, so subtract 1 from the total.
    estimated_total = image_count + overlay_n - 1
    remaining = max(0, estimated_total - min(image_count, shown_count))
    return remaining if remaining > 0 else None


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
        is_truncated = og_desc.rstrip().endswith("...")
        if preview:
            for candidate in candidates:
                if candidate.startswith(preview):
                    return candidate
                if len(preview) >= 20 and preview in candidate:
                    return candidate
            if not is_truncated:
                return og_desc

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


def _merge_image_lists(*image_lists: List[str]) -> List[str]:
    merged: List[str] = []
    for images in image_lists:
        merged.extend(images)
    return _dedupe_images(merged)


def _extract_post_data(
    soup: BeautifulSoup,
    html_content: str,
    desktop_html: Optional[str] = None,
) -> Dict[str, Union[str, List[str], None]]:
    og_image = _meta_content(soup, "og:image")
    og_title = _meta_content(soup, "og:title")
    og_desc = _meta_content(soup, "og:description")

    mobile_images: List[str] = []
    if og_image and _is_post_image(og_image):
        mobile_images.append(_normalize_cdn_url(og_image))

    mobile_images.extend(_extract_images_from_img_tags(soup))

    if len(_dedupe_images(mobile_images)) <= 1:
        mobile_images.extend(_extract_images_from_regex(html_content))

    mobile_images = _dedupe_images(mobile_images)
    overlay = _extract_extra_images(soup)
    images = mobile_images
    has_gallery_signal = _has_visible_gallery(soup)

    if desktop_html:
        desktop_soup = _parse_soup(desktop_html)
        if not overlay:
            overlay = _extract_extra_images(desktop_soup)
        has_gallery_signal = has_gallery_signal or _has_visible_gallery(desktop_soup)

        if len(mobile_images) <= 1 and has_gallery_signal:
            desktop_images, total_image_count = _collect_post_images_from_html(
                desktop_html,
                soup=desktop_soup,
                overlay=overlay,
            )
            if overlay or total_image_count > 1:
                images = desktop_images if desktop_images else mobile_images

    shown_count = 5
    post_owner, post_author = _resolve_post_metadata(og_title, og_desc, desktop_html)
    return {
        "post_owner": post_owner,
        "post_author": post_author,
        "profile_pic_url": _extract_profile_pic(soup),
        "description": _resolve_description(og_desc, desktop_html),
        "images": images[:shown_count],
        "extra_images": _remaining_image_count(overlay, len(images), shown_count),
    }


async def _fetch_html(
    session: aiohttp.ClientSession,
    url: str,
    headers: Dict[str, str],
) -> tuple[int, str]:
    async with session.get(url, headers=headers, allow_redirects=True) as response:
        return response.status, await response.text()


FACEBOOK_CDN_HEADERS = {
    "User-Agent": MOBILE_USER_AGENT,
    "Referer": "https://www.facebook.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


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

        og_title = _meta_content(mobile_soup, "og:title")
        og_desc = _meta_content(mobile_soup, "og:description")
        login_walled = _is_login_walled(
            og_title,
            og_desc,
            result.get("post_owner"),
            result.get("description"),
        )
        if not login_walled and desktop_for_text:
            desktop_soup = _parse_soup(desktop_for_text)
            login_walled = _is_login_walled(
                _meta_content(desktop_soup, "og:title"),
                _meta_content(desktop_soup, "og:description"),
                result.get("post_owner"),
                result.get("description"),
            )

        json_append(
            data={
                "url": url,
                "output": result,
                "mobile_status": mobile_status,
                "desktop_status": desktop_status,
                "description_len": len(result["description"] or ""),
                "login_walled": login_walled,
            },
            file="debug_image.json",
            max_items=20,
        )
        if login_walled:
            return None
        return result if (result["images"] or result.get("description") or result.get("post_owner")) else None
