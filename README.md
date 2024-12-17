<a name="english"></a>
# Discord TikTok Link Converter Bot

[🇹🇧 English](#english) | [🇹🇭 Thai](#thai)

## Description
A Discord bot that converts TikTok links to allow video viewing without the TikTok app by changing the domain from "tiktok.com" to "tnktok.com"

## Installation
1. Clone the project:
```bash
git clone https://github.com/com55/TokTak.git
cd TokTak
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file and add your bot token:
```
TOKEN=your_discord_bot_token
```

## Usage
1. Invite the bot to your server
2. Use `/set` in the channel where you want the bot to operate
3. When a TikTok link is sent in that channel, the bot will reply with a link that allows video viewing directly in Discord

### Available Commands
- `/set` - Enable bot operation in the current channel
- `/unset` - Disable bot operation in the current channel
- `/old_message` - Convert TikTok links in previous messages (up to 10 messages)

## Credits
- [fxTikTok (tnktok.com)](https://github.com/okdargy/fxtiktok)
---
<a name="thai"></a>
# Discord TikTok Link Converter Bot

[🇹🇧 English](#english) | [🇹🇭 Thai](#thai)


## คำอธิบาย
บอทดิสคอร์ดที่ช่วยแปลงลิงก์ TikTok ให้สามารถดูวิดีโอได้โดยไม่ต้องเข้าแอพ TikTok โดยจะเปลี่ยน domain จาก "tiktok.com" เป็น "tnktok.com"

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

## วิธีใช้
1. เชิญบอทเข้าเซิร์ฟเวอร์
2. ใช้งาน `/set` ในห้องที่ต้องการจะให้บอททำงาน
3. เมื่อมีการส่งลิงค์ TikTok ในช่องข้อความนั้น บอทจะตอบกลับด้วยลิงก์ที่สามารถดูวิดิโอในแอพดิสคอร์ดได้

### คำสั่งที่มี
- `/set` - ตั้งค่าให้บอททำงานในช่องข้อความนั้น
- `/unset` - ยกเลิกให้บอททำงานในช่องข้อความนั้น
- `/old_message` - แปลงลิงก์ TikTok ในข้อความเก่า (ย้อนหลังได้สูงสุด 10 ข้อความ)

## Credits
- [fxTikTok (tnktok.com)](https://github.com/okdargy/fxtiktok)
