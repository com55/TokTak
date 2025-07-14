# v2.0 form https://github.com/devfemibadmus/webmedia

import requests, json, re
from bs4 import BeautifulSoup
from collections.abc import Mapping, Iterable

def get_nested_value(data, key):
    if isinstance(data, Mapping):
        if key in data:
            return data[key]
        for k, v in data.items():
            result = get_nested_value(v, key)
            if result is not None:
                return result
    elif isinstance(data, Iterable) and not isinstance(data, str):
        for item in data:
            result = get_nested_value(item, key)
            if result is not None:
                return result
    return None

class Facebook:
    def __init__(self, url, cut=None):
        self.cut = cut
        self.url = url
        self.headers = {
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

    def getVideo(self):
        if any(x in self.url for x in ['fb.watch', '/watch/?v']):
            response = requests.get(self.url)
            try:
                video_id = response.url.split("/videos/")[1].split("/")[0]
                self.url = f'https://www.facebook.com/reel/{video_id}'
            except Exception as e:
                return {'error': True, 'message': 'video not found', 'error_message': str(e)}, 404

        try:
            resp = requests.get(self.url, headers=self.headers)
            soup = BeautifulSoup(resp.text, 'html.parser')
            scripts = soup.find_all('script', type='application/json')

            keywords = ["base_url", "total_comment_count"]
            preferred_thumbnail, browser_native_hd_url, data, owner, json_data = None, None, None, None, None

            for script in scripts:
                if script.string and 'preferred_thumbnail' in script.string:
                    json_data = json.loads(script.string)
                    preferred_thumbnail = get_nested_value(json_data, "preferred_thumbnail")
                    browser_native_hd_url = get_nested_value(json_data, "browser_native_hd_url")
                    break

            for script in scripts:
                if script.string and all(keyword in script.string for keyword in keywords):
                    json_data = json.loads(script.string)
                    data = get_nested_value(json_data, "data")
                    desc = data.get('title', {}).get('text', None)
                    owner = get_nested_value(json_data, "owner_as_page")
                    
                    if owner is None:
                        owner_main = get_nested_value(data, "owner")
                        if owner_main is not None:
                            owner = {'id': owner_main.get("id", None)}
                    
                    if desc is None:
                        message = get_nested_value(data, "message")
                        if message is not None:
                            desc = message.get("text", None)
                            data['title']['text'] = desc

                    if browser_native_hd_url is None:
                        representations = get_nested_value(json_data, "representations")
                        if representations is None:
                            representations = []
                        deaf_media = {}
                        for representation in representations:
                            mime_type = representation.get("mime_type", "").lower()
                            if mime_type and "video" in mime_type:
                                deaf_media["video_url"] = representation.get('base_url')
                            elif mime_type and "audio" in mime_type:
                                deaf_media["audio_url"] = representation.get('base_url')
                        browser_native_hd_url = deaf_media.get('video_url')
                        json_data['deaf_media'] = deaf_media

                    json_data['data'] = data
                    json_data['owner'] = owner
                    json_data['platform'] = 'facebook'
                    json_data['preferred_thumbnail'] = preferred_thumbnail

                    break

            if data is None or json_data is None:
                return {'error': True, 'message': 'post not found!', 'error_message': '404 try again'}, 404

            if not self.cut:
                return json_data, 200

            cut_data = {
                "author": owner,
                "content": {
                    "id": data.get('id', None),
                    "desc": data.get('title', {}).get('text', None),
                    "cover": preferred_thumbnail.get('image', {}).get('uri', None),
                    "comment": data.get('feedback', {}).get('total_comment_count', None),
                    "reactions": data.get('feedback', {}).get('reaction_count', {}).get('count', None),
                    "plays": data.get('feedback', {}).get('video_view_count_renderer', {}).get('feedback', {}).get('play_count', None),
                    "post_views": data.get('feedback', {}).get('video_view_count_renderer', {}).get('feedback', {}).get('video_post_view_count', None),
                },
                "is_video": True,
                "platform": "facebook",
                "media": [
                    {
                        "is_video": True,
                        "id": data.get('id', None),
                        "address": browser_native_hd_url,
                        "cover": preferred_thumbnail.get('image', {}).get('uri', None),
                    },
                ]
            }
            
            if 'deaf_media' in json_data:
                cut_data['deaf_media'] = json_data['deaf_media']

            return cut_data, 200

        except Exception as e:
            return {'error': True, 'message': 'something went wrong', 'error_message': str(e)}, 500

if __name__ == "__main__":
    fa = Facebook(url='https://web.facebook.com/share/v/iweQG4zGudbW3wh6/', cut=True)
    data = fa.getVideo()
    print(json.dumps(data, indent=4, ensure_ascii=False))