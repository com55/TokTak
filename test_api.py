import requests
from typing import Union

# กำหนด type สำหรับข้อมูลที่คาดว่าจะได้รับจาก TikTok API
class Aweme:
    def __init__(self, aweme_id: str, *args, **kwargs):
        self.aweme_id = aweme_id
        # เพิ่มฟิลด์อื่นๆ ที่ต้องการจาก API ที่นี่

class TikTokAPIResponse:
    def __init__(self, aweme_list: list):
        self.aweme_list = aweme_list

# ฟังก์ชันเพื่อดึงข้อมูลจาก TikTok API
def get_video_info(aweme_id: str) -> Union[Aweme, Exception]:
    api_url = 'https://api22-normal-c-alisg.tiktokv.com/aweme/v1/feed/'

    # สร้างพารามิเตอร์สำหรับ query string
    params = {
        'region': 'US',
        'carrier_region': 'US',
        'aweme_id': aweme_id,
        'iid': '7318518857994389254',
        'device_id': '7318517321748022790',
        'channel': 'googleplay',
        'app_name': 'musical_ly',
        'version_code': '300904',
        'device_platform': 'android',
        'device_type': 'ASUS_Z01QD',
        'os_version': '9'
    }

    # กำหนด headers สำหรับคำขอ HTTP
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36'
    }

    try:
        # ส่งคำขอ GET ไปยัง API
        response = requests.get(api_url, params=params, headers=headers)

        # ตรวจสอบสถานะของคำขอ
        if response.status_code != 200:
            raise Exception(f"API request failed with status: {response.status_code}")

        # แปลงข้อมูล JSON จากคำขอ
        json_data = response.json()
        aweme_list = json_data.get('aweme_list', [])

        # ค้นหาวิดีโอที่ตรงกับ aweme_id ที่ให้มา
        video_info = next((aweme for aweme in aweme_list if aweme['aweme_id'] == aweme_id), None)

        if video_info:
            # คืนค่าข้อมูลวิดีโอที่พบ
            return Aweme(**video_info)
        else:
            # หากไม่พบข้อมูลวิดีโอ
            return Exception("Could not find video info")

    except requests.RequestException as e:
        # จัดการข้อผิดพลาดจากคำขอ HTTP
        return Exception(f"Network request failed: {str(e)}")

# ตัวอย่างการเรียกใช้ฟังก์ชัน
aweme_id = "ZS6L15cb3"  # ใส่ ID ของวิดีโอที่ต้องการค้นหา
video_info = get_video_info(aweme_id)

if isinstance(video_info, Aweme):
    print(f"Video found: {video_info.aweme_id}")
else:
    print(f"Error: {video_info}")
