import sqlite3
import os
import re
from dotenv import load_dotenv
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Select, View
import datetime
import json

from sympy import Domain

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents, shard_count=2)

fix_domain = {
        0: "a.tnktok.com",
        1: "tfxktok.com",
        2: "vxtiktok.com"
    }

async def setup_table():
    """สร้างตารางเก็บ channel ID ในฐานข้อมูล SQLite"""
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

async def load_channels():
    """โหลด channel ID จากฐานข้อมูลเข้าสู่ตัวแปร bot.channel_ids"""
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id FROM channels")
    bot.channel_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

@bot.event
async def on_ready():
    """ฟังก์ชั่นที่ทำงานเมื่อบอทพร้อมใช้งาน"""
    print(f'{bot.user} has connected to Discord!')
    await setup_table()
    await load_channels()
    
    # Sync commands
    print("Syncing commands...")
    try:
        bot.tree.add_command(SettingCommand(name="setting", description="Setting command"))
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f"Failed to sync commands: {str(e)}")

class SettingCommand(app_commands.Group):
    @bot.tree.command(name="set", description="Set this message channel")
    async def set_channel(interaction: discord.Interaction):
        """เพิ่ม channel ID ปัจจุบันเข้าสู่ฐานข้อมูล"""
        channel_id = interaction.channel.id
        with sqlite3.connect("data.db") as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", (channel_id,))
            conn.commit()
        await load_channels()
        await interaction.response.send_message(f"Channel {channel_id} has been set!", ephemeral=True)

    @bot.tree.command(name="unset", description="Unset this message channel")
    async def unset_channel(interaction: discord.Interaction):
        """ลบ channel ID ปัจจุบันออกจากฐานข้อมูล"""
        channel_id = interaction.channel.id
        with sqlite3.connect("data.db") as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            conn.commit()
        await load_channels()
        await interaction.response.send_message(f"Channel {channel_id} has been unset!", ephemeral=True)

@bot.tree.command(name="old_message", description="แปลงลิงก์ TikTok ในข้อความที่เลือก")
@app_commands.describe(message="เลือกข้อความที่ต้องการแปลง")
async def convert_old_message(
    interaction: discord.Interaction,
    message: int
):
    """แปลงลิงก์ TikTok ในข้อความที่เลือก"""
    channel = interaction.channel
    
    # ตรวจสอบว่าเป็นช่องที่กำหนดไว้หรือไม่
    if channel.id not in bot.channel_ids:
        await interaction.response.send_message("คำสั่งนี้ใช้ได้เฉพาะในช่องที่กำหนดเท่านั้น", ephemeral=True)
        return

    # ดึงข้อความตี่ไม่ใช่ของบอทและมีลิงค์ TikTok
    messages = []
    async for msg in channel.history(limit=100):
        if not msg.author.bot and "http" in msg.content and "tiktok" in msg.content:
            messages.append(msg)
            if len(messages) >= 10:
                break

    if not messages:
        await interaction.response.send_message("ไม่พบข้อความที่มีลิงก์ TikTok", ephemeral=True)
        return

    if message >= len(messages):
        await interaction.response.send_message("ไม่พบข้อความที่เลือก", ephemeral=True)
        return

    # เลือกข้อความตามลำดับที่ผู้ใช้เลือก
    selected_msg = messages[message]
    
    urls = re.findall(r'https?://\S+', selected_msg.content)
    
    if urls:
        updated_urls = [url.replace("tiktok", "tnktok") for url in urls]
        await selected_msg.edit(suppress=True)
        if len(updated_urls) > 1:
            for url in updated_urls:
                await selected_msg.reply(f"[-]({url}?addDesc=true)", mention_author=False)
            await interaction.response.send_message("Done!")
        else:
            await interaction.response.send_message(
                f"[-]({updated_urls[0]}?addDesc=true) {selected_msg.jump_url}"
            )
    else:
        await interaction.response.send_message("No TikTok links found in the message", ephemeral=True)

@convert_old_message.autocomplete('message')
async def message_number_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    channel = interaction.channel
    
    # ดึงข้อความที่ไม่ใช่ของบอทและมีลิงค์ TikTok
    messages = []
    async for msg in channel.history(limit=100):
        # ตรวจสอบว่าไม่ใช่ข้อความของบอทและมีลิงค์ TikTok
        if not msg.author.bot and "http" in msg.content and "tiktok" in msg.content:
            messages.append(msg)
            if len(messages) >= 10:  # เก็บแค่ 10 ข้อความ
                break

    choices = []
    for idx, msg in enumerate(messages):
        # ตัดข้อความให้สั้นลงถ้ายาวเกินไป
        content = msg.content
        
        # คำนวณเวลาที่ผ่านมา
        now = datetime.datetime.now(msg.created_at.tzinfo)
        delta = now - msg.created_at
        
        if delta.days > 0:
            time_text = f"{delta.days} วันที่แล้ว"
        elif delta.seconds >= 3600:
            time_text = f"{delta.seconds // 3600} ชั่วโมงที่แล้ว"
        elif delta.seconds >= 60:
            time_text = f"{delta.seconds // 60} นาทีที่แล้ว"
        else:
            time_text = f"{delta.seconds} วินาทีที่แล้ว"
            
        choice_name = f"{msg.author.display_name} [{time_text}]: {content}"
        # จำกัดความยาวของ name ตาม Discord API
        if len(choice_name) > 100:
            choice_name = choice_name[:97] + "..."
        choices.append(app_commands.Choice(name=choice_name, value=idx))
    
    return choices

@bot.event
async def on_message(message):
    """จัดการข้อความที่ส่งมาในช่องที่กำหนด"""
    if message.author.bot:
        return

    if message.channel.id in bot.channel_ids:
        # print(f"Content: {message.content!r}")
        urls = re.findall(r'https?://\S*tiktok\S+', message.content)
        print(f"URL: {urls}")
        
        if len(urls) > 0:
            url = urls[0]
            fix_domain_index = 0
            updated_url = '/'.join(url.split('/', 3)[:2] + [fix_domain[fix_domain_index]] + url.split('/', 3)[3:])
            bot_reply = await message.reply(f"[-]({updated_url})", mention_author=False)

            end_time = asyncio.get_event_loop().time() + 5
            embed_detect = False
            while not embed_detect:
                
                bot_reply = await message.channel.fetch_message(bot_reply.id)
                
                Failed = False
                
                if bot_reply.embeds:
                    embed_data = []
                    for embed in bot_reply.embeds:
                        embed_data.append(embed.to_dict())
                    with open("debug.json", "w") as f:
                        json.dump(embed_data, f, indent=4)
                    try:
                        if embed_data[0]['description'] == 'Failed to get video data from TikTok':
                            Failed = True
                            print('Failed')
                        else:
                            embed_detect = True
                    except KeyError:
                        print("Embed detected in the reply!")
                        await message.edit(suppress=True)  # แก้ไขข้อความ
                        embed_detect = True
                
                if asyncio.get_event_loop().time() > end_time or Failed:
                    print('No embed detected in the reply!')
                    fix_domain_index += 1
                    url = bot_reply.content.split('](')[1][:-1]
                    try:
                        updated_url = '/'.join(url.split('/', 3)[:2] + [fix_domain[fix_domain_index]] + url.split('/', 3)[3:])
                    except KeyError:
                        print("No more domain to fix")
                        await bot_reply.delete()
                        break
                    await bot_reply.delete()
                    bot_reply = await message.reply(f"[-]({updated_url})", mention_author=False)
                    
                    end_time = asyncio.get_event_loop().time() + 5
                    
                await asyncio.sleep(0.5)

    await bot.process_commands(message)

async def start_bot():  
    while True:
        try:
            await bot.start(TOKEN)
        except discord.errors.DiscordServerError:
            print(f"Connection error occurred. Retrying in 10 seconds...")
            await asyncio.sleep(10)
        except Exception:
            pass

asyncio.run(start_bot())
