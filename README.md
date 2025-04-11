# Discord Link Converter Bot
บอทดิสคอร์ดที่ช่วยแปลงลิงก์ TikTok และ Facebook ให้สามารถดูวิดีโอได้โดยไม่ต้องเข้าแอพ

## การติดตั้ง
1. โคลนโปรเจค:
```bash
git clone https://github.com/com55/TokTak.git
cd TokTak
```

2. ติดตั้ง dependencies:
```bash
pip install -r requirements.txt
```

3. สร้างไฟล์ `.env` และใส่โทเคนของบอท:
```
TOKEN=your_discord_bot_token
```

4. รันบอท:
```bash
python main.py
```

## วิธีใช้
1. เชิญบอทเข้าเซิร์ฟเวอร์
2. บอทจะทำงานกับทุกช่องข้อความเป็นค่าเริ่มต้น
3. ใช้งาน `/disabled` ในห้องที่ไม่ต้องการจะให้บอททำงาน
4. เมื่อมีการส่งลิงค์ TikTok หรือ Facebook ในช่องข้อความนั้น บอทจะตอบกลับด้วยลิงก์ที่สามารถดูวิดีโอในแอพดิสคอร์ดได้

### คำสั่งที่มี
- `/enabled` - เปิดใช้งานบอทในช่องข้อความนั้น
- `/disabled` - ปิดใช้งานบอทในช่องข้อความนั้น
- `/old_message` - แปลงลิงก์ TikTok ในข้อความเก่า (ย้อนหลังได้สูงสุด 10 ข้อความ)
- `ไอเชี่ยนี่ลืมเปลี่ยนภาษา` - เมนูคลิกขวาที่ข้อความเพื่อแปลงข้อความที่พิมพ์ผิดภาษา

## Credits
- [tnktok.com & tfxktok.com](https://github.com/okdargy/fxtiktok)
- [WebMedia API](https://github.com/devfemibadmus/webmedia)
