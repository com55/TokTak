# Discord TikTok Link Converter Bot

[🇹🇭 Thai](README.md) | [🇬🇧 English](README_EN.md)

## Description
A Discord bot that converts TikTok links to allow video viewing without the TikTok app by changing the domain from "tiktok.com" to "tnktok.com"

## Installation
1. Clone the project:
```bash
git clone https://github.com/com55/toktak.git
cd toktak
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

## Credits
- [fxTikTok (tnktok.com)](https://github.com/okdargy/fxtiktok) 