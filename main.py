import sys

# Configure UTF-8 for Windows console output to prevent UnicodeEncodeError with cp1251
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import os
import json
import asyncio
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import init_db, get_db, SessionLocal
from models import CheckIn, Reaction

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
USE_POLLING = os.getenv("USE_POLLING", "false").lower() in ("true", "1", "yes")

# Polling task handle
polling_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------
# Lifespan Context Manager (Modern FastAPI 0.100+)
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    public_url = WEBHOOK_URL or RENDER_EXTERNAL_URL
    global polling_task

    if TELEGRAM_BOT_TOKEN:
        if public_url and not USE_POLLING:
            webhook_endpoint = f"{public_url.rstrip('/')}/api/telegram-webhook"
            print(f"[Telegram Bot] Registering webhook to {webhook_endpoint}...")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
                        json={"url": webhook_endpoint, "drop_pending_updates": False}
                    )
                    print(f"[Telegram Bot] setWebhook result: {resp.json()}")
            except Exception as e:
                print(f"[Telegram Bot] Webhook registration failed: {e}")
        else:
            # Run poller in background for local testing or explicit polling
            polling_task = asyncio.create_task(telegram_polling_loop())
    else:
        print("[Telegram Bot] TELEGRAM_BOT_TOKEN is not configured. Running in standalone local mode.")

    yield

    # Shutdown
    if polling_task:
        polling_task.cancel()


app = FastAPI(
    title="Tamagotchi Girlfriend Live Monitoring TWA",
    description="Telegram Mini App for tracking girlfriend's mood, hunger, energy & thoughts with 3D avatar",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for Telegram WebApp environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------
class CheckInCreate(BaseModel):
    time_interval: str = Field(..., description="Interval, e.g. 14:00 - 15:00")
    hunger: int = Field(70, ge=0, le=100)
    energy: int = Field(70, ge=0, le=100)
    stress: int = Field(20, ge=0, le=100)
    miss_you: int = Field(85, ge=0, le=100)
    tags: List[str] = Field(default_factory=list)
    note: str = Field("", description="Checkin thought")
    is_sos: bool = False

class SosCreate(BaseModel):
    hunger: int = Field(50, ge=0, le=100)
    energy: int = Field(50, ge=0, le=100)
    stress: int = Field(50, ge=0, le=100)
    miss_you: int = Field(100, ge=0, le=100)
    note: Optional[str] = "Срочно похвали / скажи, что любишь! 🥺💖"


# ---------------------------------------------------------
# Helper Functions for Telegram Bot API
# ---------------------------------------------------------
def make_progress_bar(value: int, emoji_fill: str = "🟩", emoji_empty: str = "⬜") -> str:
    """Generates a 10-segment emoji progress bar."""
    filled = max(0, min(10, round(value / 10)))
    return (emoji_fill * filled) + (emoji_empty * (10 - filled))

async def send_telegram_message(text: str, reply_markup: Optional[dict] = None) -> Optional[dict]:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram Bot] Bot token or chat ID is not configured. (Skipping telegram notification in local mode)")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result")
            else:
                print(f"[Telegram Bot] Error sending message: {resp.status_code} - {resp.text}")
                return None
    except Exception as e:
        print(f"[Telegram Bot] Exception sending message: {e}")
        return None

async def answer_callback_query(callback_query_id: str, text: str, show_alert: bool = False):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json={
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert
            })
    except Exception as e:
        print(f"[Telegram Bot] Exception answering callback query: {e}")


def format_checkin_html(checkin: CheckIn) -> tuple[str, dict]:
    """Formats HTML message and inline keyboard for check-in."""
    hunger_bar = make_progress_bar(checkin.hunger, "🍕", "▫️")
    energy_bar = make_progress_bar(checkin.energy, "⚡", "▫️")
    stress_bar = make_progress_bar(checkin.stress, "🔥", "▫️")
    miss_bar = make_progress_bar(checkin.miss_you, "❤️", "▫️")

    tags_list = checkin.get_tags_list()
    tags_formatted = " ".join([f"#{t.replace(' ', '').replace('/', '')}" for t in tags_list]) if tags_list else "—"

    note_text = f"<i>«{checkin.note.strip()}»</i>" if checkin.note and checkin.note.strip() else "<i>(без заметки)</i>"

    # Critical alert check
    alert_warning = ""
    if checkin.hunger < 30 or checkin.energy < 20:
        alert_warning = (
            "\n\n🚨 <b>Внимание! Критический уровень истощения/голода!</b>\n"
            "<i>Срочно организуй подкрепление или заботу своей любимой!</i> 🍩💕\n"
        )
    elif checkin.stress > 70:
        alert_warning = (
            "\n\n⚠️ <b>Высокий уровень стресса!</b>\n"
            "<i>Любимой нужна пауза, тёплые слова и поддержка!</i> 💆‍♀️✨\n"
        )

    text = (
        f"🌸 <b>ЧЕКИН ЛЮБИМОЙ</b> 🌸\n"
        f"🕒 <b>Интервал:</b> <code>{checkin.time_interval}</code>\n\n"
        f"🍕 <b>Сытость:</b> {checkin.hunger}%\n{hunger_bar}\n\n"
        f"⚡ <b>Энергия:</b> {checkin.energy}%\n{energy_bar}\n\n"
        f"🤯 <b>Стресс:</b> {checkin.stress}%\n{stress_bar}\n\n"
        f"🥺 <b>Скучаю по тебе:</b> {checkin.miss_you}%\n{miss_bar}\n\n"
        f"🏷 <b>Теги:</b> {tags_formatted}\n"
        f"💭 <b>Мысль часа:</b>\n{note_text}"
        f"{alert_warning}"
    )

    # Inline Keyboard with interactive response buttons
    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "❤️ Обнять", "callback_data": f"react:hug:{checkin.id}"},
                {"text": "🍫 Заказать вкусняшку", "callback_data": f"react:treat:{checkin.id}"}
            ],
            [
                {"text": "👀 Горжусь", "callback_data": f"react:proud:{checkin.id}"},
                {"text": "💌 Чмок в носик", "callback_data": f"react:kiss:{checkin.id}"}
            ]
        ]
    }

    return text, inline_keyboard


def format_sos_html(sos_data: SosCreate, checkin_id: Optional[int]) -> tuple[str, dict]:
    """Formats HTML message and inline keyboard for SOS alert."""
    text = (
        "🚨🚨🚨 <b>ЭКСТРЕННЫЙ SOS-ПИНГ ОТ ЛЮБИМОЙ!</b> 🚨🚨🚨\n\n"
        "🥺💖 <b>«Срочно похвали / скажи, что любишь!»</b>\n\n"
        f"📊 <b>Состояние прямо сейчас:</b>\n"
        f"🍕 Сытость: <b>{sos_data.hunger}%</b> | ⚡ Энергия: <b>{sos_data.energy}%</b>\n"
        f"🤯 Стресс: <b>{sos_data.stress}%</b> | 🥺 Скучаю: <b>{sos_data.miss_you}%</b>\n\n"
        f"💬 <b>Записка:</b> <i>{sos_data.note}</i>\n\n"
        "Твоей девочке срочно требуется доза внимания и любви! Выбери реакцию ниже 👇"
    )

    cid = checkin_id if checkin_id else 0
    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "💖 Ты самая лучшая и красивая!", "callback_data": f"react:sos_praise:{cid}"},
            ],
            [
                {"text": "🍫 Заказываю вкусняшки!", "callback_data": f"react:sos_food:{cid}"},
                {"text": "💌 Миллион поцелуев!", "callback_data": f"react:kiss:{cid}"}
            ],
            [
                {"text": "📞 Срочно звоню тебе!", "callback_data": f"react:sos_call:{cid}"}
            ]
        ]
    }
    return text, inline_keyboard


# ---------------------------------------------------------
# Telegram Bot Polling / Webhook Management
# ---------------------------------------------------------
REACTION_MESSAGES = {
    "hug": ("❤️ Обнять", "Любимый крепко обнял тебя и прижал к сердцу! 💕"),
    "treat": ("🍫 Заказать вкусняшку", "Любимый отправляет тебе самую вкусную вкусняшку! 🍩✨"),
    "proud": ("👀 Горжусь", "Любимый безумно гордится тобой, ты его умница! 🌟"),
    "kiss": ("💌 Чмок в носик", "Любимый нежно чмокнул тебя прямо в носик! 💋"),
    "sos_praise": ("💖 Ты самая лучшая", "Любимый: «Ты самая лучшая, красивая и любимая девочка на свете!» 💖"),
    "sos_food": ("🍕 Еда уже в пути", "Любимый уже организует подкрепление вкусностями! 🍕"),
    "sos_call": ("📞 Звоню тебе", "Любимый уже набирает твой номер, чтобы сказать как любит! 📞💕")
}

def process_telegram_callback(callback_data: str, callback_id: str):
    """Processes reaction callback and writes to database."""
    parts = callback_data.split(":")
    if len(parts) >= 3 and parts[0] == "react":
        action_type = parts[1]
        try:
            checkin_id = int(parts[2]) if parts[2] != "0" else None
        except ValueError:
            checkin_id = None

        label, message = REACTION_MESSAGES.get(action_type, ("💖 Любовь", "Любимый послал тебе лучики тепла!"))

        db = SessionLocal()
        try:
            reaction = Reaction(
                checkin_id=checkin_id,
                action_type=action_type,
                label=label,
                message=message,
                is_read=False
            )
            db.add(reaction)
            db.commit()
            print(f"[Reaction Logged] Saved reaction: {label} -> {message}")
        finally:
            db.close()


async def telegram_polling_loop():
    """Background polling loop for local development without webhook."""
    offset = 0
    print("[Telegram Polling] Started polling loop...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=20"
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        if "callback_query" in update:
                            cb = update["callback_query"]
                            cb_id = cb["id"]
                            cb_data = cb.get("data", "")
                            process_telegram_callback(cb_data, cb_id)
                            await answer_callback_query(cb_id, "Отправлено любимой на экран! ✨")
                        elif "message" in update:
                            msg = update["message"]
                            sender_text = msg.get("text", "")
                            chat_id = str(msg.get("chat", {}).get("id", ""))
                            if chat_id == TELEGRAM_CHAT_ID and sender_text and not sender_text.startswith("/"):
                                db = SessionLocal()
                                try:
                                    reaction = Reaction(
                                        action_type="custom",
                                        label="💬 Сообщение",
                                        message=f"Любимый написал: «{sender_text}»",
                                        is_read=False
                                    )
                                    db.add(reaction)
                                    db.commit()
                                finally:
                                    db.close()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                print("[Telegram Polling] Polling task cancelled.")
                break
            except Exception as e:
                print(f"[Telegram Polling] Error: {e}")
                await asyncio.sleep(5)


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------
@app.get("/")
async def root(request: Request):
    """Serves the main Telegram Mini App Single Page Application."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
@app.get("/ping")
async def health_check():
    """Endpoint for UptimeRobot (pings every 5 mins to prevent Render instance sleep)."""
    return {
        "status": "ok",
        "service": "tamagotchi-girl",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected"
    }

@app.post("/api/checkin")
async def create_checkin(checkin_data: CheckInCreate, db: Session = Depends(get_db)):
    """Receives hourly checkin from Mini App and alerts boyfriend on Telegram."""
    checkin = CheckIn(
        time_interval=checkin_data.time_interval,
        hunger=checkin_data.hunger,
        energy=checkin_data.energy,
        stress=checkin_data.stress,
        miss_you=checkin_data.miss_you,
        tags=json.dumps(checkin_data.tags, ensure_ascii=False),
        note=checkin_data.note,
        is_sos=checkin_data.is_sos
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    # Format Telegram Message
    html_text, inline_keyboard = format_checkin_html(checkin)
    tg_result = await send_telegram_message(html_text, reply_markup=inline_keyboard)
    if tg_result and "message_id" in tg_result:
        checkin.telegram_message_id = tg_result["message_id"]
        db.commit()

    return {
        "status": "success",
        "message": "Чекин успешно сохранён и отправлен любимому!",
        "checkin": checkin.to_dict()
    }

@app.post("/api/sos")
async def create_sos_alert(sos_data: SosCreate, db: Session = Depends(get_db)):
    """Instant SOS button click: sends urgent alert to boyfriend."""
    now_hour = datetime.now().strftime("%H:00")
    checkin = CheckIn(
        time_interval=f"SOS {now_hour}",
        hunger=sos_data.hunger,
        energy=sos_data.energy,
        stress=sos_data.stress,
        miss_you=sos_data.miss_you,
        tags=json.dumps(["SOS", "Нужна забота"], ensure_ascii=False),
        note=sos_data.note or "Срочно похвали / скажи, что любишь!",
        is_sos=True
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    html_text, inline_keyboard = format_sos_html(sos_data, checkin.id)
    tg_result = await send_telegram_message(html_text, reply_markup=inline_keyboard)
    if tg_result and "message_id" in tg_result:
        checkin.telegram_message_id = tg_result["message_id"]
        db.commit()

    return {
        "status": "success",
        "message": "SOS-сигнал отправлен любимому! Он скоро ответит ❤️",
        "checkin": checkin.to_dict()
    }

@app.get("/api/checkins/recent")
async def get_recent_checkins(db: Session = Depends(get_db)):
    """Returns recent 10 checkins for history feed."""
    checkins = db.query(CheckIn).order_by(CheckIn.created_at.desc()).limit(10).all()
    return {
        "status": "success",
        "checkins": [c.to_dict() for c in checkins]
    }

@app.get("/api/reactions/latest")
async def get_latest_reactions(db: Session = Depends(get_db)):
    """Checks for newly arrived unread reactions from boyfriend, marks them read."""
    unread_reactions = db.query(Reaction).filter(Reaction.is_read == False).order_by(Reaction.created_at.asc()).all()
    
    reactions_data = [r.to_dict() for r in unread_reactions]

    # Mark as read
    for r in unread_reactions:
        r.is_read = True
    if unread_reactions:
        db.commit()

    # If no unread, return the single latest reaction for reference
    latest_reaction = None
    if not reactions_data:
        latest = db.query(Reaction).order_by(Reaction.created_at.desc()).first()
        if latest:
            latest_reaction = latest.to_dict()

    return {
        "status": "success",
        "new_reactions": reactions_data,
        "latest_reaction": latest_reaction
    }

@app.post("/api/telegram-webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Webhook endpoint for Telegram Bot API updates (used on Render)."""
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        cb_data = cb.get("data", "")
        process_telegram_callback(cb_data, cb_id)
        background_tasks.add_task(answer_callback_query, cb_id, "Отправлено любимой на экран! ✨")
    elif "message" in update:
        msg = update["message"]
        sender_text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id == TELEGRAM_CHAT_ID and sender_text and not sender_text.startswith("/"):
            db = SessionLocal()
            try:
                reaction = Reaction(
                    action_type="custom",
                    label="💬 Сообщение",
                    message=f"Любимый написал: «{sender_text}»",
                    is_read=False
                )
                db.add(reaction)
                db.commit()
            finally:
                db.close()

    return {"ok": True}


# ---------------------------------------------------------
# Local Execution Entry Point (python main.py)
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print("\n" + "=" * 60)
    print("Tamagotchi Girlfriend Live Monitoring TWA is starting...")
    print(f"Open in browser: http://localhost:{port} (or http://127.0.0.1:{port})")
    print("=" * 60 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
