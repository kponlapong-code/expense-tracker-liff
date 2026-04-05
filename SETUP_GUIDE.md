# 🚀 คู่มือการตั้งค่าและ Deploy

## สิ่งที่ต้องเตรียม

| สิ่ง | ที่ได้มา |
|------|---------|
| LINE Channel Secret | LINE Developers Console |
| LINE Channel Access Token | LINE Developers Console |
| Anthropic API Key | console.anthropic.com |
| GitHub Account | github.com |
| Render Account | render.com (ฟรี) |

---

## ขั้นตอนที่ 1: เตรียม GitHub Repo

```bash
# 1. สร้าง repo ใหม่บน GitHub
# 2. Upload โฟลเดอร์ expense-tracker ทั้งหมด
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/expense-tracker.git
git push -u origin main
```

---

## ขั้นตอนที่ 2: Deploy บน Render

1. ไปที่ https://render.com → New → Web Service
2. เชื่อมต่อ GitHub repo ที่สร้างไว้
3. ตั้งค่า:
   - **Name**: expense-tracker (หรือชื่ออื่น)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. เพิ่ม **Environment Variables**:
   ```
   LINE_CHANNEL_SECRET = (ค่าจาก LINE Developers)
   LINE_CHANNEL_ACCESS_TOKEN = (ค่าจาก LINE Developers)
   ANTHROPIC_API_KEY = (ค่าจาก Anthropic Console)
   ```
5. คลิก **Create Web Service**
6. รอ deploy เสร็จ → ได้ URL เช่น `https://expense-tracker-xxxx.onrender.com`

---

## ขั้นตอนที่ 3: ตั้งค่า LINE Webhook

1. ไปที่ https://developers.line.biz
2. เลือก Channel ของคุณ → **Messaging API**
3. หา **Webhook URL** → ใส่:
   ```
   https://YOUR_RENDER_URL.onrender.com/webhook
   ```
4. เปิด **Use webhook**: ON
5. คลิก **Verify** → ต้องได้ "Success"

---

## ขั้นตอนที่ 4: ทดสอบ

### ทดสอบ Web App
เปิด browser ไปที่ URL ของ Render เลย

### ทดสอบ LINE Bot
1. เพิ่มเพื่อน LINE Bot ด้วย QR Code จาก LINE Developers Console
2. ส่งรูปสลิปใน LINE
3. รอสักครู่ → Bot จะตอบกลับพร้อมข้อมูลที่อ่านได้

### คำสั่ง LINE
```
ยอดวันนี้   → ดูยอดรวมวันนี้
สรุปเดือน   → ดูสรุปรายเดือน
ดูรายการ    → รายการล่าสุด 5 รายการ
help        → คำสั่งทั้งหมด
```

---

## โครงสร้างโปรเจกต์

```
expense-tracker/
├── main.py           ← FastAPI entry point
├── database.py       ← SQLite database
├── models.py         ← Pydantic models
├── api.py            ← REST API (CRUD + reports)
├── line_handler.py   ← LINE Bot webhook
├── claude_ocr.py     ← อ่านสลิปด้วย Claude Vision
├── requirements.txt
├── Procfile          ← สำหรับ Render deploy
├── .env.example      ← ตัวอย่าง environment variables
└── static/
    └── index.html    ← Web App (single page)
```

---

## การทดสอบใน Local (ถ้าต้องการ)

```bash
# 1. Copy .env.example เป็น .env แล้วใส่ค่า
cp .env.example .env

# 2. ติดตั้ง dependencies
pip install -r requirements.txt

# 3. รัน server
python main.py

# 4. เปิด browser ที่ http://localhost:8000
```

สำหรับ LINE Bot ต้อง expose localhost ด้วย ngrok:
```bash
ngrok http 8000
# ใช้ URL ที่ได้เป็น Webhook URL ใน LINE Developers Console
```

---

## ⚠️ หมายเหตุสำคัญ

- **Render Free Tier**: Server จะ sleep หลังไม่มีคนใช้ 15 นาที แต่จะตื่นเองเมื่อมี request ใหม่ (อาจช้า ~30 วินาทีครั้งแรก)
- **SQLite**: เหมาะสำหรับการใช้งานส่วนตัว ถ้าต้องการ production จริงแนะนำให้ใช้ PostgreSQL
- **LINE Webhook**: ต้องเป็น HTTPS เท่านั้น (Render มีให้อัตโนมัติ)
