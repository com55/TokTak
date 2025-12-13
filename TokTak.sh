#!/bin/bash

# ดึง path ของไฟล์ script นี้เอง
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==========================================
# ส่วนที่เพิ่ม: เช็คเน็ตก่อน ถ้าไม่มี เน็ตไม่เดินสคริปต์ต่อ
# ==========================================
echo "Checking internet connection..."
# วนลูปยิง Ping ไป Google (8.8.8.8)
# ถ้า Ping ไม่เจอ (! ping ...) ให้ sleep 5 วิ แล้ววนใหม่
while ! ping -c 1 -W 1 8.8.8.8 &> /dev/null; do
    echo "Waiting for internet connection..."
    sleep 5
done
echo "Internet OK! Proceeding..."
# ==========================================

# กำหนดชื่อ session
session="TokTak"
command="cd $DIR && .venv/bin/python main.py"

# ตรวจสอบว่า session มีอยู่หรือไม่
tmux has-session -t $session 2>/dev/null

# ใช้ค่า $? เพื่อตรวจสอบสถานะของคำสั่งก่อนหน้า
if [ $? != 0 ]; then
    # ถ้าไม่มี session เดิม สร้าง session ใหม่
    echo "Creating new tmux session '$session'..."
    tmux new-session -d -s $session
    tmux send-keys -t $session "$command" C-m
    
    # แสดงข้อความแนะนำ
    echo "$session is now running in tmux session '$session'."
    echo "To attach to the session, run: tmux attach -t $session"
else
    # ถ้ามี session เดิมอยู่แล้ว ให้เข้าไปใน session นั้น
    echo "Session '$session' already exists."
    echo "To attach to the session, run: tmux attach -t $session"
fi
