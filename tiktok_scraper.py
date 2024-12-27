import requests
import json
from bs4 import BeautifulSoup
from typing import Union

class Cookie:
    def __init__(self):
        self.cookies = {}

    def set_cookies(self, cookies):
        # ตรวจสอบว่า cookies ที่ได้รับเป็น dictionary หรือไม่
        if isinstance(cookies, dict):
            for cookie_name, cookie_value in cookies.items():
                self.cookies[cookie_name] = cookie_value
        else:
            print("Expected dictionary for cookies, got:", type(cookies))

    def get_cookies_as_string(self):
        # สร้าง string ที่สามารถใช้เป็น header Cookie
        return '; '.join([f'{key}={value}' for key, value in self.cookies.items()])

cookie = Cookie()

def grab_video_id(video_id: str) -> str:
    # ทำการร้องขอไปยัง TikTok Video URL
    res = requests.get(f'https://vm.tiktok.com/{video_id}')
    return res.url.split('/')[-1].split('?')[0]

def scrape_video_data(aweme_id: str, author: str = 'i') -> dict:
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0'
    }

    # ทำการร้องขอไปยัง URL ของ TikTok Video
    url = f'https://www.tiktok.com/@{author}/video/{aweme_id}'
    res = requests.get(url, headers=headers)

    if res.status_code != 200:
        print("Error fetching the page:", res.status_code)
        return {"error": "Failed to fetch the page"}

    html = res.text

    # ตรวจสอบว่า HTML มีข้อมูล <script> ที่เราต้องการหรือไม่
    if '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"' not in html:
        print("No script tag found for video data")
        return {"error": "No script tag found for video data"}

    # แยกคุกกี้จาก header response
    cookies = res.cookies.get_dict()  # รับคุกกี้เป็น dictionary
    cookie.set_cookies(cookies)  # ตั้งคุกกี้ให้กับ Cookie instance

    try:
        # หาข้อมูล JSON ที่ฝังใน <script> tag
        script_tag = html.split('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">')

        if len(script_tag) < 2:
            raise Exception("Could not find the necessary script tag containing video data")

        script_json = script_tag[1].split('</script>')[0]

        if not script_json.strip():
            raise Exception("Script JSON is empty")

        json_data = json.loads(script_json)

        if '__DEFAULT_SCOPE__' not in json_data or 'webapp.video-detail' not in json_data['__DEFAULT_SCOPE__']:
            raise Exception('Could not find video data')

        video_info = json_data['__DEFAULT_SCOPE__']['webapp.video-detail']['itemInfo']['itemStruct']
        return video_info
    except Exception as e:
        print(f"Error while parsing video data: {e}")
        return {"error": str(e)}

def scrape_live_data(author: str) -> dict:
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0'
    }

    # ทำการร้องขอไปยัง URL ของ TikTok Live
    url = f'https://www.tiktok.com/@{author}/live'
    res = requests.get(url, headers=headers)

    if res.status_code != 200:
        print("Error fetching the page:", res.status_code)
        return {"error": "Failed to fetch the page"}

    html = res.text

    # ตรวจสอบว่า HTML มีข้อมูล <script> ที่เราต้องการหรือไม่
    if '<script id="SIGI_STATE"' not in html:
        print("No script tag found for live data")
        return {"error": "No script tag found for live data"}

    # แยกคุกกี้จาก header response
    cookies = res.cookies.get_dict()  # รับคุกกี้เป็น dictionary
    cookie.set_cookies(cookies)  # ตั้งคุกกี้ให้กับ Cookie instance

    try:
        script_tag = html.split('<script id="SIGI_STATE" type="application/json">')

        if len(script_tag) < 2:
            raise Exception("Could not find the necessary script tag containing live data")

        script_json = script_tag[1].split('</script>')[0]

        if not script_json.strip():
            raise Exception("Script JSON is empty")

        json_data = json.loads(script_json)

        if 'LiveRoom' not in json_data:
            raise Exception('Could not find live data')

        return json_data['LiveRoom']
    except Exception as e:
        print(f"Error while parsing live data: {e}")
        return {"error": str(e)}