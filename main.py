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
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import init_db, get_db, SessionLocal
from models import CheckIn, Reaction, TamagotchiState

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8175363985:AAGInashhXEbZfV_Nfew2jgpDzfKO7xdwpM").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6671126368").strip()
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
# Disable Jinja2 cache to prevent Python 3.14 unhashable cache_key tuple bug on Render
templates.env.cache = None


# ---------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------
class TamagotchiActionRequest(BaseModel):
    action: str = Field(..., description="Action name: feed, sleep, hug, kiss, miss")

class CheckInCreate(BaseModel):
    time_interval: str = Field("14:00 - 15:00", description="Interval, e.g. 14:00 - 15:00")
    hunger: int = Field(70, ge=0, le=100)
    energy: int = Field(70, ge=0, le=100)
    happiness: int = Field(85, ge=0, le=100)
    love: int = Field(90, ge=0, le=100)
    stress: Optional[int] = Field(20, ge=0, le=100)
    miss_you: Optional[int] = Field(85, ge=0, le=100)
    tags: List[str] = Field(default_factory=list)
    note: Optional[str] = Field("", description="Checkin thought")
    is_sos: bool = False

class SosCreate(BaseModel):
    hunger: int = Field(50, ge=0, le=100)
    energy: int = Field(50, ge=0, le=100)
    happiness: Optional[int] = Field(50, ge=0, le=100)
    love: Optional[int] = Field(90, ge=0, le=100)
    stress: Optional[int] = Field(80, ge=0, le=100)
    miss_you: Optional[int] = Field(100, ge=0, le=100)
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


def format_checkin_html(checkin: CheckIn, status_text: str = "") -> tuple[str, dict]:
    """Formats HTML message and inline keyboard for check-in."""
    note_text = f"\n💭 <b>Мысль:</b> <i>«{checkin.note.strip()}»</i>" if checkin.note and checkin.note.strip() else ""
    tags_list = checkin.get_tags_list()
    tags_text = ("\n🏷 <b>Теги:</b> " + " ".join([f"#{t.replace(' ', '').replace('/', '')}" for t in tags_list])) if tags_list else ""

    text = (
        "💌 <b>Новый чекин от Лёли!</b>\n"
        f"🍰 <b>Сытость:</b> {checkin.hunger}%\n"
        f"⚡ <b>Энергия:</b> {checkin.energy}%\n"
        f"✨ <b>Настроение:</b> {checkin.happiness}%\n"
        f"❤️ <b>Любовь:</b> {checkin.love}%\n"
        f"<b>Статус:</b> {status_text}"
        f"{note_text}"
        f"{tags_text}"
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
        "🚨🚨🚨 <b>ЭКСТРЕННЫЙ SOS-ПИНГ ОТ ЛЁЛИ!</b> 🚨🚨🚨\n\n"
        "🥺💖 <b>«Срочно похвали / скажи, что любишь!»</b>\n\n"
        f"📊 <b>Состояние Лёли прямо сейчас:</b>\n"
        f"🍰 Сытость: <b>{sos_data.hunger}%</b> | ⚡ Энергия: <b>{sos_data.energy}%</b>\n"
        f"✨ Настроение: <b>{sos_data.happiness or 50}%</b> | ❤️ Любовь: <b>{sos_data.love or 90}%</b>\n\n"
        f"💬 <b>Записка:</b> <i>{sos_data.note}</i>\n\n"
        "Твоей Лёле срочно требуется доза внимания и любви! Выбери реакцию ниже 👇"
    )

    cid = checkin_id if checkin_id else 0
    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "💖 Лёля самая лучшая и красивая!", "callback_data": f"react:sos_praise:{cid}"},
            ],
            [
                {"text": "🍫 Заказываю вкусняшки для Лёли!", "callback_data": f"react:sos_food:{cid}"},
                {"text": "💌 Миллион поцелуев!", "callback_data": f"react:kiss:{cid}"}
            ],
            [
                {"text": "📞 Срочно звоню Лёле!", "callback_data": f"react:sos_call:{cid}"}
            ]
        ]
    }
    return text, inline_keyboard


# ---------------------------------------------------------
# Telegram Bot Polling / Webhook Management
# ---------------------------------------------------------
REACTION_MESSAGES = {
    "hug": ("❤️ Обнять", "Любимый крепко обнял Лёлю и прижал к сердцу! 💕"),
    "treat": ("🍫 Заказать вкусняшку", "Любимый отправляет Лёле самую вкусную вкусняшку! 🍩✨"),
    "proud": ("👀 Горжусь", "Любимый безумно гордится Лёлей, ты его умница! 🌟"),
    "kiss": ("💌 Чмок в носик", "Любимый нежно чмокнул Лёлю прямо в носик! 💋"),
    "sos_praise": ("💖 Ты самая лучшая", "Любимый: «Лёля — самая лучшая, красивая и любимая на свете!» 💖"),
    "sos_food": ("🍕 Еда уже в пути", "Любимый уже организует подкрепление вкусностями для Лёли! 🍕"),
    "sos_call": ("📞 Звоню тебе", "Любимый уже набирает Лёлю, чтобы сказать как любит! 📞💕")
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

            # Sync Telegram action with Tamagotchi state
            tg_to_action = {
                "hug": "hug",
                "treat": "feed",
                "proud": "hug",
                "kiss": "kiss",
                "sos_praise": "hug",
                "sos_food": "feed",
                "sos_call": "miss"
            }
            if action_type in tg_to_action:
                t_state = db.query(TamagotchiState).first()
                if t_state:
                    t_state.perform_action(tg_to_action[action_type])

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
                            await answer_callback_query(cb_id, "Отправлено Лёле на экран! ✨")
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
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serves the main Telegram Mini App Single Page Application."""
    index_path = os.path.join("templates", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return templates.TemplateResponse(request=request, name="index.html")

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

@app.get("/api/status")
async def get_tamagotchi_status(db: Session = Depends(get_db)):
    """Returns current Tamagotchi metrics (with time decay), status text, and mood."""
    state = db.query(TamagotchiState).first()
    if not state:
        state = TamagotchiState()
        db.add(state)
        db.commit()
        db.refresh(state)

    state.apply_decay()
    db.commit()
    db.refresh(state)

    return {
        "status": "success",
        "data": state.to_dict()
    }

@app.post("/api/action")
async def perform_tamagotchi_action(action_data: TamagotchiActionRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Performs care action on Tamagotchi (feed, sleep, hug, kiss, miss)."""
    state = db.query(TamagotchiState).first()
    if not state:
        state = TamagotchiState()
        db.add(state)
        db.commit()
        db.refresh(state)

    success, message = state.perform_action(action_data.action)
    db.commit()
    db.refresh(state)

    if success:
        act = action_data.action.lower().strip()
        action_notifications = {
            "hug": "❤️ Лёлю только что крепко обняли!",
            "feed": "🍰 Лёлю только что вкусно покормили! 😋",
            "sleep": "🌙 Лёлю только что уложили спать! 💤",
            "miss": "💌 Лёле передали, как сильно по ней скучают! 🥺💖",
            "kiss": "💋 Лёлю только что нежно чмокнули! ✨"
        }
        tg_text = action_notifications.get(act, f"✨ Действие: {message}")
        background_tasks.add_task(send_telegram_message, tg_text)

    return {
        "status": "success" if success else "cooldown",
        "message": message,
        "data": state.to_dict()
    }

@app.post("/api/checkin")
async def create_checkin(checkin_data: CheckInCreate, db: Session = Depends(get_db)):
    """Receives hourly checkin from Mini App, syncs Tamagotchi state and alerts boyfriend on Telegram."""
    stress_val = checkin_data.stress if checkin_data.stress is not None else max(0, 100 - checkin_data.happiness)
    miss_val = checkin_data.miss_you if checkin_data.miss_you is not None else checkin_data.love

    checkin = CheckIn(
        time_interval=checkin_data.time_interval,
        hunger=checkin_data.hunger,
        energy=checkin_data.energy,
        happiness=checkin_data.happiness,
        love=checkin_data.love,
        stress=stress_val,
        miss_you=miss_val,
        tags=json.dumps(checkin_data.tags, ensure_ascii=False),
        note=checkin_data.note or "",
        is_sos=checkin_data.is_sos
    )
    db.add(checkin)

    # Sync Tamagotchi state with checkin values
    state = db.query(TamagotchiState).first()
    if not state:
        state = TamagotchiState()
        db.add(state)
    state.hunger = checkin_data.hunger
    state.energy = checkin_data.energy
    state.happiness = checkin_data.happiness
    state.love = checkin_data.love
    state.last_updated_at = datetime.utcnow()

    db.commit()
    db.refresh(checkin)
    db.refresh(state)

    status_text, _ = state.get_status_info()

    # Format Telegram Message
    html_text, inline_keyboard = format_checkin_html(checkin, status_text)
    tg_result = await send_telegram_message(html_text, reply_markup=inline_keyboard)
    if tg_result and "message_id" in tg_result:
        checkin.telegram_message_id = tg_result["message_id"]
        db.commit()

    return {
        "status": "success",
        "message": "Чекин Лёли успешно сохранён и отправлен в Telegram!",
        "checkin": checkin.to_dict(),
        "tamagotchi": state.to_dict()
    }

@app.post("/api/sos")
async def create_sos_alert(sos_data: SosCreate, db: Session = Depends(get_db)):
    """Instant SOS button click: sends urgent alert to boyfriend."""
    now_hour = datetime.now().strftime("%H:00")
    checkin = CheckIn(
        time_interval=f"SOS {now_hour}",
        hunger=sos_data.hunger,
        energy=sos_data.energy,
        happiness=sos_data.happiness or 50,
        love=sos_data.love or 90,
        stress=sos_data.stress or 80,
        miss_you=sos_data.miss_you or 100,
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
        background_tasks.add_task(answer_callback_query, cb_id, "Отправлено Лёле на экран! ✨")
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
