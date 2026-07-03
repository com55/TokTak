# v2.0 form https://github.com/devfemibadmus/webmedia

import json
import re
from collections.abc import Iterable, Mapping
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def get_nested_value(data, key):
    if isinstance(data, Mapping):
        if key in data:
            return data[key]
        for value in data.values():
            result = get_nested_value(value, key)
            if result is not None:
                return result
    elif isinstance(data, Iterable) and not isinstance(data, str):
        for item in data:
            result = get_nested_value(item, key)
            if result is not None:
                return result
    return None


def _meta_content(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", {"property": prop})
    if tag and tag.get("content"):
        return tag["content"]
    return None


def _extract_from_open_graph(soup: BeautifulSoup) -> dict | None:
    video_url = _meta_content(soup, "og:video") or _meta_content(soup, "og:video:url")
    image_url = _meta_content(soup, "og:image")
    title = _meta_content(soup, "og:title")
    description = _meta_content(soup, "og:description")

    if not video_url and not image_url:
        return None

    if title:
        title = re.sub(r"\s*\|\s*Facebook\s*$", "", title).strip()

    return {
        "author": None,
        "content": {
            "id": None,
            "desc": description or title,
            "cover": image_url,
            "comment": None,
            "reactions": None,
            "plays": None,
            "post_views": None,
        },
        "is_video": bool(video_url),
        "platform": "facebook",
        "media": [
            {
                "is_video": bool(video_url),
                "id": None,
                "address": video_url or image_url,
                "cover": image_url,
            }
        ],
    }


class Facebook:
    def __init__(self, url, cut=None):
        self.cut = cut
        self.url = url
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": MOBILE_USER_AGENT,
        }

    def _resolve_watch_url(self) -> str | None:
        response = requests.get(self.url, headers=self.headers, allow_redirects=True)
        final_url = str(response.url)

        if "/videos/" in final_url:
            try:
                return f"https://www.facebook.com/reel/{final_url.split('/videos/')[1].split('/')[0]}"
            except (IndexError, ValueError):
                return None

        parsed = urlparse(final_url)
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            return f"https://www.facebook.com/reel/{video_id}"

        return final_url if "facebook.com" in final_url else None

    def getVideo(self):
        if any(x in self.url for x in ["fb.watch", "/watch/?v", "/watch?"]):
            resolved_url = self._resolve_watch_url()
            if not resolved_url:
                return {"error": True, "message": "video not found", "error_message": "unable to resolve watch url"}, 404
            self.url = resolved_url

        try:
            resp = requests.get(self.url, headers=self.headers, allow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")
            scripts = soup.find_all("script", type="application/json")

            keywords = ["base_url", "total_comment_count"]
            preferred_thumbnail, browser_native_hd_url, data, owner, json_data = None, None, None, None, None

            for script in scripts:
                if script.string and "preferred_thumbnail" in script.string:
                    json_data = json.loads(script.string)
                    preferred_thumbnail = get_nested_value(json_data, "preferred_thumbnail")
                    browser_native_hd_url = get_nested_value(json_data, "browser_native_hd_url")
                    break

            for script in scripts:
                if script.string and all(keyword in script.string for keyword in keywords):
                    json_data = json.loads(script.string)
                    data = get_nested_value(json_data, "data")
                    title = (data or {}).get("title") or {}
                    desc = title.get("text") if isinstance(title, dict) else None
                    owner = get_nested_value(json_data, "owner_as_page")

                    if owner is None:
                        owner_main = get_nested_value(data, "owner")
                        if owner_main is not None:
                            owner = {"id": owner_main.get("id", None)}

                    if desc is None:
                        message = get_nested_value(data, "message")
                        if message is not None:
                            desc = message.get("text", None)
                            if isinstance(data.get("title"), dict):
                                data["title"]["text"] = desc
                            else:
                                data["title"] = {"text": desc}

                    if browser_native_hd_url is None:
                        representations = get_nested_value(json_data, "representations") or []
                        deaf_media = {}
                        for representation in representations:
                            mime_type = representation.get("mime_type", "").lower()
                            if mime_type and "video" in mime_type:
                                deaf_media["video_url"] = representation.get("base_url")
                            elif mime_type and "audio" in mime_type:
                                deaf_media["audio_url"] = representation.get("base_url")
                        browser_native_hd_url = deaf_media.get("video_url")
                        json_data["deaf_media"] = deaf_media

                    json_data["data"] = data
                    json_data["owner"] = owner
                    json_data["platform"] = "facebook"
                    json_data["preferred_thumbnail"] = preferred_thumbnail
                    break

            if data is None or json_data is None:
                og_data = _extract_from_open_graph(soup)
                if og_data is None:
                    return {"error": True, "message": "post not found!", "error_message": "404 try again"}, 404
                return og_data, 200

            if not self.cut:
                return json_data, 200

            title = (data or {}).get("title") or {}
            title_text = title.get("text") if isinstance(title, dict) else None
            thumbnail_image = {}
            if isinstance(preferred_thumbnail, dict):
                thumbnail_image = preferred_thumbnail.get("image") or {}

            cut_data = {
                "author": owner,
                "content": {
                    "id": data.get("id", None),
                    "desc": title_text,
                    "cover": thumbnail_image.get("uri", None),
                    "comment": data.get("feedback", {}).get("total_comment_count", None),
                    "reactions": data.get("feedback", {}).get("reaction_count", {}).get("count", None),
                    "plays": data.get("feedback", {}).get("video_view_count_renderer", {}).get("feedback", {}).get("play_count", None),
                    "post_views": data.get("feedback", {}).get("video_view_count_renderer", {}).get("feedback", {}).get("video_post_view_count", None),
                },
                "is_video": True,
                "platform": "facebook",
                "media": [
                    {
                        "is_video": True,
                        "id": data.get("id", None),
                        "address": browser_native_hd_url,
                        "cover": thumbnail_image.get("uri", None),
                    },
                ],
            }

            if "deaf_media" in json_data:
                cut_data["deaf_media"] = json_data["deaf_media"]

            if not cut_data["media"][0]["address"]:
                og_data = _extract_from_open_graph(soup)
                if og_data and og_data["media"][0]["address"]:
                    cut_data["media"][0]["address"] = og_data["media"][0]["address"]
                    if not cut_data["content"]["cover"]:
                        cut_data["content"]["cover"] = og_data["content"]["cover"]
                    if not cut_data["content"]["desc"]:
                        cut_data["content"]["desc"] = og_data["content"]["desc"]

            if not cut_data["media"][0]["address"]:
                return {"error": True, "message": "post not found!", "error_message": "video url missing"}, 404

            return cut_data, 200

        except Exception as error:
            return {"error": True, "message": "something went wrong", "error_message": str(error)}, 500


if __name__ == "__main__":
    fa = Facebook(url="https://web.facebook.com/share/v/iweQG4zGudbW3wh6/", cut=True)
    data = fa.getVideo()
    print(json.dumps(data, indent=4, ensure_ascii=False))
