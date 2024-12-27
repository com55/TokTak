# tiktok_scraper.py

from tiktok_scraper import grab_aweme_id, scrape_video_data, scrape_live_data
import json

# 1. ใช้ฟังก์ชัน grab_aweme_id เพื่อดึง URL ของวิดีโอจาก TikTok
video_id = 'ZS6L15cb3'  # แทนที่ด้วย videoId ที่คุณต้องการ
aweme_url = grab_aweme_id(video_id)
print(f'Video URL: {aweme_url}')

# 2. ใช้ฟังก์ชัน scrape_video_data เพื่อดึงข้อมูลวิดีโอ
aweme_id = aweme_url.split('/')[-1].split('?')[0] # ดึง awemeId จาก URL ที่ได้
print(f'Aweme ID: {aweme_id}')
author = aweme_url.split('/')[3]  # ชื่อผู้ใช้งาน TikTok (Optional: ถ้าไม่ระบุจะใช้ 'i' เป็นค่าเริ่มต้น)
print(f'Author: {author}')

try:
    video_data = scrape_video_data(aweme_id, author)
    with open('debug-scrape.json', 'w', encoding='utf-8') as f:
        json.dump(video_data, f, ensure_ascii=False, indent=4)
except Exception as e:
    print('Error scraping video data:', e)
