# Discord TikTok Link Converter Bot

## คำอธิบาย
บอทดิสคอร์ดที่ช่วยแปลงลิงก์ TikTok ให้สามารถดูวิดีโอได้โดยไม่ต้องเข้าแอพ TikTok โดยจะเปลี่ยน domain จาก "tiktok.com" เป็น "tnktok.com"

## การติดตั้ง
1. โคลนโปรเจค:
```bash
git clone https://github.com/com55/toktak.git
cd toktak
```

2. ติดตั้ง dependencies:
```bash
pip install -r requirements.txt
```

3. สร้างไฟล์ `.env` และใส่โทเคนของบอท:
```
TOKEN=your_discord_bot_token
```

## วิธีใช้
1. เชิญบอทเข้าเซิร์ฟเวอร์
2. ใช้งาน `/set` ในห้องที่ต้องการจะให้บอททำงาน
3. เมื่อมีการส่งลิงค์ TikTok ในช่องข้อความนั้น บอทจะตอบกลับด้วยลิงก์ที่สามารถดูวิดิโอในแอพดิสคอร์ดได้

### คำสั่งที่มี
- `/set` - ตั้งค่าให้บอททำงานในช่องข้อความนั้น
- `/unset` - ยกเลิกให้บอททำงานในช่องข้อความนั้น
