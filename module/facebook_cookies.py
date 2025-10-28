import asyncio
import json
from playwright.async_api import async_playwright
import os
import time

COOKIE_FILE_PATH = "facebook_cookies.json"

async def refresh_facebook_session_manual():
    """
    เปิดเบราว์เซอร์ให้ผู้ใช้ Login ด้วยมือ แล้วบันทึก Cookies ใหม่อัตโนมัติ
    """
    print("🚀 เริ่มการรีเฟรช Facebook Session (ต้อง Login ด้วยมือ)...")
    
    # ❗❗ สำคัญ: บน Raspberry Pi มึงต้องมี GUI (Desktop Environment) 
    # และ X-Server ทำงานอยู่ถึงจะเปิดหน้าจอได้ ❗❗
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=False, # 💥💥 เปิดหน้าจอให้มึงเห็นและ Login เอง 💥💥
                channel="chromium",
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            
            # 1. โหลด Session เก่าถ้ามี
            if os.path.exists(COOKIE_FILE_PATH):
                with open(COOKIE_FILE_PATH, 'r') as f:
                    cookies = json.load(f)
                context = await browser.new_context()
                await context.add_cookies(cookies)
            else:
                context = await browser.new_context()

            page = await context.new_page()
            await page.goto("https://www.facebook.com/")
            
            print("\n========================================================")
            print("🚨🚨 กรุณา Login ในหน้าต่างเบราว์เซอร์ที่เด้งขึ้นมา 🚨🚨")
            print("    หลังจาก Login สำเร็จ ให้กดปุ่ม 'Enter' ใน Terminal นี้")
            print("========================================================\n")
            
            # 2. รอผู้ใช้ Login ด้วยมือ แล้วกด Enter
            # มึงต้องกด Enter ใน Terminal เพื่อให้โค้ดรันต่อ
            await asyncio.to_thread(input, ">> กด ENTER หลังจาก Login และเข้าหน้า Home แล้ว: ")

            # 3. ดึงและบันทึก Cookies ใหม่
            cookies = await context.cookies()
            with open(COOKIE_FILE_PATH, 'w') as f:
                json.dump(cookies, f, indent=4)
            
            print(f"🎉 บันทึก Cookies ใหม่ลงใน {COOKIE_FILE_PATH} สำเร็จ! ตอนนี้ใช้ Scraper ได้ต่อ")
            
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการรีเฟรช Session: {e}")
        finally:
            if 'browser' in locals() and browser:
                await browser.close()


def load_cookies_for_aiohttp():
    """โหลด cookies จากไฟล์ที่ Playwright บันทึกไว้ เพื่อใช้กับ aiohttp"""
    if not os.path.exists(COOKIE_FILE_PATH):
        print("⚠️ ไม่พบไฟล์ Cookie, อาจจะต้องรัน refresh_facebook_session_manual() ก่อน")
        return {}
        
    # (โค้ดส่วนนี้เหมือนเดิม ใช้ดึง Cookie จากไฟล์ JSON)
    with open(COOKIE_FILE_PATH, 'r') as f:
        cookies_list = json.load(f)
        aiohttp_cookies = {}
        for cookie in cookies_list:
            aiohttp_cookies[cookie['name']] = cookie['value']
        return aiohttp_cookies

# ******************************************************************
# โค้ด Scraper (aiohttp + BeautifulSoup) ของมึง สามารถเรียกใช้ 
# load_cookies_for_aiohttp() เพื่อดึง Cookie ที่อัปเดตแล้วไปใช้ได้เลย
# ******************************************************************

# --- การรัน ---

async def run_update():
    await refresh_facebook_session_manual()

if __name__ == "__main__":
    # 1. รันฟังก์ชันนี้เมื่อ Cookie หมดอายุ หรือทุกอาทิตย์
    asyncio.run(run_update())
    
    # 2. ตัวอย่างการใช้ Cookie ที่ได้มา (มึงต้องเอาไปใส่ในโค้ด Scraper เดิมของมึง)
    updated_cookies = load_cookies_for_aiohttp()
    print("\nตัวอย่าง Cookies ที่ถูกดึงมาใช้กับ aiohttp:")
    print(list(updated_cookies.keys()))