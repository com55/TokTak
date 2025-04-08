#!/bin/bash

# ดึง path ของไฟล์ script นี้เอง
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# กำหนดชื่อ session
session="TokTak"
command="cd $DIR && python main.py"

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
