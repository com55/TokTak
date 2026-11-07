"""Anonymous Threads embed checks, isolated from other platform fetchers."""
import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import aiohttp


FIXER_HOST = "fixthreads.seria.moe"
THREADS_HOSTS = {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}
POST_PATH = re.compile(r"/(?:share/[A-Za-z0-9_-]+|@[A-Za-z0-9._]+/post/[A-Za-z0-9_-]+)/?")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"}
VIDEO_KEYS = {"og:video", "og:video:secure_url", "twitter:player:stream"}


def _https_url(url: str):
    """Reject ambiguous authorities before passing URLs to the HTTP client."""
    if not url or "\\" in url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        return None
    try:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            return None
        return parsed
    except ValueError:
        return None


def get_threads_fixer_url(url: str) -> str | None:
    """Normalize only supported public post/share links to the fixed origin."""
    parsed = _https_url(url)
    if parsed is None or parsed.hostname not in THREADS_HOSTS or not POST_PATH.fullmatch(parsed.path):
        return None
    return f"https://{FIXER_HOST}{parsed.path}"


def _trusted_url(url: str, media: bool) -> bool:
    parsed = _https_url(url)
    if parsed is None:
        return False
    if not media:
        return parsed.hostname == FIXER_HOST
    return any(parsed.hostname == host or parsed.hostname.endswith("." + host)
               for host in ("cdninstagram.com", "fbcdn.net"))


class _Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.videos = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        attrs = dict(attrs)
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in VIDEO_KEYS:
            self.videos.append(attrs.get("content") or "")
        elif key == "og:image":
            self.images.append(attrs.get("content") or "")


async def _fetch(session, url: str, media_type: str | None = None):
    """Read metadata or probe media, validating each hop before requesting it."""
    headers = dict(HEADERS)
    if media_type:
        headers["Range"] = "bytes=0-0"
    for hop in range(4):
        if not _trusted_url(url, media=media_type is not None):
            return None
        async with session.get(url, headers=headers, allow_redirects=False) as response:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location or hop == 3:
                    return None
                # Validate the raw Location too: urljoin strips some controls.
                if "\\" in location or any(ord(char) <= 32 or ord(char) == 127 for char in location):
                    return None
                url = urljoin(url, location)
                continue
            if media_type:
                valid = response.status in (200, 206) and response.content_type.startswith(media_type + "/")
                response.close()
                return valid
            if response.status != 200 or response.content_type != "text/html":
                return None
            return await response.text(), url
    return None


async def _check_media(session, fixer_url: str) -> bool:
    result = await _fetch(session, fixer_url)
    if result is None:
        return False
    page, page_url = result
    metadata = _Metadata()
    metadata.feed(page)
    candidates = metadata.videos if metadata.videos else metadata.images
    if not candidates:
        return False
    # A declared video must pass as video; its poster cannot make it succeed.
    candidate = next((value for value in candidates if value), "")
    if not candidate or "\\" in candidate or any(ord(char) <= 32 or ord(char) == 127 for char in candidate):
        return False
    media_url = urljoin(page_url, candidate)
    return bool(await _fetch(session, media_url, "video" if metadata.videos else "image"))


async def threads_media_ok(fixer_url: str) -> bool:
    """Verify a real image/video within a combined 15-second anonymous budget."""
    if not _trusted_url(fixer_url, media=False):
        return False
    try:
        # A separate cookie-free session cannot inherit cookies/auth from the bot.
        async with aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar(),
            timeout=aiohttp.ClientTimeout(total=15),
            trust_env=False,
        ) as session:
            return await asyncio.wait_for(_check_media(session, fixer_url), timeout=15)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeError):
        return False
