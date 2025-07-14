import json
import os


def json_append(data, file, indent=4, ensure_ascii=False, max_items=None):
    try:
        # โหลดข้อมูลเก่าถ้ามี
        existing = json.load(open(file, encoding='utf-8')) if os.path.exists(file) else []
    except Exception:
        existing = []

    # ถ้าไม่ใช่ list ให้ wrap เป็น list
    if not isinstance(existing, list):
        existing = [existing]

    existing.append(data)

    # หากกำหนด max_items ให้ตัดข้อมูลให้อยู่ภายในขนาดที่กำหนด
    if max_items is not None:
        existing = existing[-max_items:]

    # เขียนกลับลงไฟล์
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=indent, ensure_ascii=ensure_ascii)