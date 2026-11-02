import os
import json
import logging
import asyncio
from pathlib import Path

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
APILAYER_KEY = os.getenv("APILAYER_KEY")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))

# Логи
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Папка логов
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Базовый URL apilayer
BASE_URL = "https://api.apilayer.net"

# ----------------- helpers -----------------

def make_request(endpoint: str, params: dict) -> dict:
    params["access_key"] = APILAYER_KEY
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.exception("Request failed: %s", e)
        return {"error": str(e)}


def generate_pdf(data: dict, title: str) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = LOG_DIR / f"{title}.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, title)
    y -= 30
    c.setFont("Helvetica", 10)
    for key, value in data.items():
        line = f"{key}: {value}"
        c.drawString(50, y, line)
        y -= 15
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()
    return pdf_path


def generate_txt(data: dict, title: str) -> Path:
    txt_path = LOG_DIR / f"{title}.txt"
    with txt_path.open("w", encoding="utf-8") as f:
        for key, value in data.items():
            f.write(f"{key}: {value}\n")
    return txt_path


def generate_json(data: dict, title: str) -> Path:
    json_path = LOG_DIR / f"{title}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return json_path

# ----------------- handlers -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Пакетные рейсы", callback_data="flight"),
            InlineKeyboardButton("Проверка email", callback_data="email"),
        ],
        [
            InlineKeyboardButton("Геокодинг", callback_data="geo"),
            InlineKeyboardButton("Поиск", callback_data="search"),
        ],
        [
            InlineKeyboardButton("Админ‑панель", callback_data="admin"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Выберите действие:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "flight":
        await query.edit_message_text("Введите номер рейса (пример: AA100):")
        return
    if data == "email":
        await query.edit_message_text("Введите email для проверки:")
        return
    if data == "geo":
        await query.edit_message_text("Введите координаты в формате lat,lon (пример: 40.7638435,-73.9729691):")
        return
    if data == "search":
        await query.edit_message_text("Введите запрос для поиска:")
        return
    if data == "admin":
        if query.from_user.id == SUPER_ADMIN_ID:
            await query.edit_message_text("Админ‑панель: ")
        else:
            await query.edit_message_text("Доступ запрещён.")
        return

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    # Determine context based on last command? For simplicity, use simple patterns
    if text.lower().startswith("aa") or text.lower().startswith("ua"):
        # flight number
        result = make_request("/aviationstack/v1/flights", {"flight_iata": text})
        title = f"flight_{text}"
    elif "@" in text:
        # email
        result = make_request("/mailboxlayer/api/check", {"email": text})
        title = f"email_{text}"
    elif "," in text and all(c.replace(".", "", 1).replace("-", "", 1).isdigit() for c in text.split(",")):
        # coordinates
        lat, lon = text.split(",")
        result = make_request("/positionstack/v1/reverse", {"query": f"{lat},{lon}", "limit": "10", "radius": "1000"})
        title = f"reverse_{lat}_{lon}"
    else:
        # generic search
        result = make_request("/serpstack/search", {"query": text})
        title = f"search_{text.replace(" ", "_")}"  

    # Generate reports
    pdf_path = generate_pdf(result, title)
    txt_path = generate_txt(result, title)
    json_path = generate_json(result, title)

    await update.message.reply_document(document=open(pdf_path, "rb"), caption="PDF")
    await update.message.reply_document(document=open(txt_path, "rb"), caption="TXT")
    await update.message.reply_document(document=open(json_path, "rb"), caption="JSON")

async def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    app.add_handler(MessageHandler(filters.ALL, button))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
