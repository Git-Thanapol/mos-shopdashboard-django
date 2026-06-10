# สรุปงาน 2026-06-11 — Deploy ขึ้นเซิร์ฟเวอร์จริง + ปรับ UI filter bar

Repo: https://github.com/Git-Thanapol/mos-shopdashboard-django · Production: http://103.114.201.9/shopboard/

## 1. ปรับ filter bar (commit `2ce7ee3`, `ac3e4b5`)

- ช่องวันที่ From/To เคยกางเต็มแถว (เพราะ `.input { width: 100% }`) → จำกัดเป็น 140px,
  input ใน filter bar ทั้งหมดเป็น width auto
- From + "ถึง" + To ห่อใน `.filter-group.date-range` (`flex-wrap: nowrap`) ให้อยู่บรรทัดเดียวกันเสมอ
- **รายงานรายวัน**: ปุ่ม ◀ ▶ + ช่องเลือกวัน ย้ายจาก header เข้าไปอยู่ใน filter bar,
  ซ่อน preset และ From/To (ส่งต่อเป็น hidden input) — เปลี่ยนวันแล้วตัวกรองร้าน/SKU ไม่หายอีก

## 2. เตรียม repo ขึ้น GitHub (commit `8b9321b`)

- `.gitignore`: ignore ทั้งโฟลเดอร์ `shop_dashboard_Streamlit_Sample/` และ untrack ไฟล์โค้ด
  legacy 23 ไฟล์ออกจาก git (ไฟล์ยังอยู่บนดิสก์; secrets/ข้อมูลจริงไม่เคยถูก commit)
- push ขึ้น `https://github.com/Git-Thanapol/mos-shopdashboard-django.git` (branch `master`)
- หมายเหตุ: โค้ด legacy ยังอยู่ใน history commit เก่า (ไม่มี secrets ปน) —
  ถ้าต้องการลบถาวรต้องใช้ `git filter-repo` + force push

## 3. ชุด deploy: Ubuntu + nginx + gunicorn (`shopboard/deploy/` + `DEPLOY.md`)

| ไฟล์ | หน้าที่ |
|---|---|
| `deploy/setup_ubuntu.sh` | ติดตั้งครั้งแรก (idempotent): apt → user `shopboard` → clone → venv → postgres → `.env` → migrate/collectstatic/superuser → systemd → nginx |
| `deploy/deploy.sh` | อัปเดตเวอร์ชัน: git pull → pip → migrate → collectstatic → restart |
| `deploy/gunicorn.service` | systemd unit (unix socket `/run/shopboard/gunicorn.sock`, 3 workers) |
| `DEPLOY.md` | คู่มือเต็ม: ติดตั้ง, SMTP/TLS, import ข้อมูลเก่า, ops cheat-sheet, troubleshooting |

ตำแหน่งบนเซิร์ฟเวอร์: โค้ด `/srv/shopboard/app` · venv `/srv/shopboard/venv` ·
secrets `/srv/shopboard/app/shopboard/.env` · service `systemctl restart shopboard`

## 4. ปัญหาที่เจอตอน deploy จริง และวิธีแก้ (แก้ในสคริปต์แล้วทั้งหมด)

1. **Port 5432/5433 ถูก Docker ใช้แล้ว** (`jst_db`, `profit_income_db`) — สคริปต์ย้าย
   PostgreSQL ของระบบไป port ว่างแรก (ได้ **5434**) ด้วย `pg_conftool` อัตโนมัติ (commit `0caf1b1`)
2. **เซิร์ฟเวอร์มีแอพอื่นแชร์ nginx อยู่แล้ว** (`/profit/`, `/stock/`, `/shop/` — Streamlit) —
   ต้องเสิร์ฟใต้ path `/shopboard/`:
   - ❌ ห้ามใช้ `rewrite ^/shopboard(/.*)$ $1 break;` — Django จะสร้างลิงก์ไม่มี prefix แล้ว 404
   - ✅ ใช้ `proxy_set_header SCRIPT_NAME /shopboard;` (gunicorn ตัด prefix ให้ Django เอง)
   - โค้ดแก้ redirect ที่ hardcode path เป็น `reverse()` และ `STATIC_URL`/`MEDIA_URL`
     ตั้งจาก `.env` ได้ (commit `52a3b14`)
   - `setup_ubuntu.sh` รับ arg ที่ 3 เป็น url_prefix และจะ**ไม่แตะ nginx** ถ้ามี site
     อื่นตอบ server_name เดิมอยู่แล้ว — block สำเร็จรูปอยู่ใน `DEPLOY.md` §1b
3. **`git pull` ฟ้อง dubious ownership** (ไฟล์ปน root/shopboard) — `deploy.sh` pull เป็น
   root + `safe.directory` แล้ว chown คืน (commit `86d6603`)

## 5. ค่าที่ต้องมีใน `.env` บนเซิร์ฟเวอร์ (สำหรับ `/shopboard/`)

```
ALLOWED_HOSTS=103.114.201.9
CSRF_TRUSTED_ORIGINS=http://103.114.201.9
STATIC_URL=/shopboard/static/
MEDIA_URL=/shopboard/media/
GOOGLE_APPLICATION_CREDENTIALS=/srv/shopboard/service_account.json
SHEET_MASTER_URL=https://docs.google.com/spreadsheets/d/1Q3akHm1GKkDI2eilGfujsd9pO7aOjJvyYJNuXd98lzo/edit?gid=0#gid=0
```

แก้ `.env` แล้วต้อง `sudo systemctl restart shopboard` เสมอ

## 6. Google Sheet import

- ใช้ service account เดิมของแอพเก่า: `shop-bot@shop-dashboard-480113.iam.gserviceaccount.com`
  (แชร์สิทธิ์เข้าชีทตั้งค่าทุนไว้แล้ว ไม่ต้องสร้างใหม่)
- สคริปต์ `shopboard/scripts/make_service_account_json.py` แปลง `secrets.toml` →
  `shopboard/service_account.json` (gitignored) — สร้างไว้แล้วบนเครื่อง Windows
- **ค้างอยู่:** scp ไฟล์ขึ้น `/srv/shopboard/service_account.json` + chown/chmod 600 + restart

## 7. คำสั่งที่ใช้บ่อย

```bash
# อัปเดตเวอร์ชันบนเซิร์ฟเวอร์ (คำสั่งเดียวจบ)
sudo bash /srv/shopboard/app/shopboard/deploy/deploy.sh

# ดู log / สถานะ
sudo journalctl -u shopboard -f
sudo systemctl status shopboard
sudo nginx -t && sudo systemctl reload nginx

# backup ฐานข้อมูล
sudo -u postgres pg_dump shopboard | gzip > /srv/shopboard/backup_$(date +%F).sql.gz
```

## งานที่ยังค้าง

- [ ] scp `service_account.json` ขึ้นเซิร์ฟเวอร์ (ข้อ 6)
- [ ] กรอก SMTP (`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`) ใน `.env` บนเซิร์ฟเวอร์ เพื่อให้ OTP mail ทำงาน
- [ ] ตั้ง TLS (certbot) เมื่อมีโดเมน แล้วค่อยเปิด `USE_HTTPS=1`
