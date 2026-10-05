import os
import sys
import time
import json
import threading
from datetime import datetime
from typing import Optional

# UTF-8 for Windows console output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

import requests
from flask import Flask, request, jsonify, render_template, send_from_directory
from sqlalchemy import create_engine, Column, Integer, Float, String, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8175363985:AAGInashhXEbZfV_Nfew2jgpDzfKO7xdwpM").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6671126368").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://girlfriend-tamagotchi.onrender.com").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
USE_POLLING = os.getenv("USE_POLLING", "false").lower() in ("true", "1", "yes")
PORT = int(os.getenv("PORT", 8000))

# Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_AS_ASCII"] = False
app.jinja_env.cache = None

# Database
DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./tamagotchi.db")
if DB_PATH.startswith("postgres://"):
    DB_PATH = DB_PATH.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DB_PATH.startswith("sqlite") else {}
engine = create_engine(DB_PATH, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()


# -----------------------------------------------------------------------------
# Database Models
# -----------------------------------------------------------------------------
class PetState(Base):
    __tablename__ = "pet_state"

    id = Column(Integer, primary_key=True)
    hunger = Column(Float, default=80.0)
    energy = Column(Float, default=80.0)
    hygiene = Column(Float, default=90.0)
    fun = Column(Float, default=85.0)
    is_sleeping = Column(Boolean, default=False)
    coins = Column(Integer, default=100)
    last_update = Column(Float, default=lambda: time.time() * 1000.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "hunger": round(float(self.hunger), 1),
            "energy": round(float(self.energy), 1),
            "hygiene": round(float(self.hygiene), 1),
            "fun": round(float(self.fun), 1),
            "isSleeping": bool(self.is_sleeping),
            "coins": int(self.coins),
            "lastUpdate": float(self.last_update) if self.last_update else time.time() * 1000.0,
            "updatedAt": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None
        }


class GiftReaction(Base):
    __tablename__ = "gift_reactions"

    id = Column(Integer, primary_key=True)
    action_type = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "action_type": self.action_type,
            "label": self.label,
            "message": self.message,
            "is_read": bool(self.is_read),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True)
    last_alert_time = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        state = db.query(PetState).first()
        if not state:
            state = PetState(
                hunger=85.0,
                energy=85.0,
                hygiene=90.0,
                fun=90.0,
                is_sleeping=False,
                coins=100,
                last_update=time.time() * 1000.0
            )
            db.add(state)
            db.commit()
            print("[Database] Initial PetState created successfully.")
    except Exception as e:
        print(f"[Database] Error seeding initial state: {e}")
    finally:
        db.close()


@app.teardown_appcontext
def remove_session(exception=None):
    SessionLocal.remove()


# -----------------------------------------------------------------------------
# Telegram Bot API Helpers
# -----------------------------------------------------------------------------
def send_telegram_message(text: str, reply_markup: Optional[dict] = None) -> Optional[dict]:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram Bot] Bot token or chat ID is missing, skipping notification.")
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
        resp = requests.post(url, json=payload, timeout=8.0)
        if resp.status_code == 200:
            return resp.json().get("result")
        else:
            print(f"[Telegram Bot] Error sending message: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"[Telegram Bot] Exception sending message: {e}")
        return None


def answer_callback_query(callback_query_id: str, text: str, show_alert: bool = False):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert
        }, timeout=5.0)
    except Exception as e:
        print(f"[Telegram Bot] Error answering callback: {e}")


def check_and_send_critical_alert(hunger: float, energy: float, fun: float):
    """Sends alert to boyfriend if critical needs drop below 20% (with cooldown)."""
    if hunger > 20.0 and energy > 20.0 and fun > 20.0:
        return

    db = SessionLocal()
    try:
        alert_log = db.query(AlertLog).first()
        now = datetime.utcnow()
        if alert_log:
            cooldown_seconds = (now - alert_log.last_alert_time).total_seconds()
            if cooldown_seconds < 1200:  # 20 minutes cooldown
                return
            alert_log.last_alert_time = now
        else:
            alert_log = AlertLog(last_alert_time=now)
            db.add(alert_log)
        db.commit()

        # Build message
        alert_text = (
            "⚠️ <b>Внимание! Твоя любимая Лёля грустит или голодает!</b> 🥺💔\n\n"
            f"🍰 Сытость: <b>{int(hunger)}%</b>\n"
            f"⚡ Энергия: <b>{int(energy)}%</b>\n"
            f"🎮 Настроение: <b>{int(fun)}%</b>\n\n"
            "Пора проявить заботу и поддержать свою девочку! Выбери подарок ниже 👇"
        )

        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "❤️ Погладить дистанционно", "callback_data": "gift:pet"},
                    {"text": "🍕 Заказать вкусняшку", "callback_data": "gift:food"}
                ],
                [
                    {"text": "💌 Чмокнуть в щёчку", "callback_data": "gift:kiss"}
                ]
            ]
        }

        # Send in background thread to avoid blocking response
        threading.Thread(target=send_telegram_message, args=(alert_text, inline_keyboard), daemon=True).start()
    except Exception as e:
        print(f"[Telegram Alert] Error checking alert: {e}")
    finally:
        db.close()


def process_telegram_callback(callback_data: str, callback_id: str):
    """Processes reaction callback from boyfriend and restores pet state."""
    db = SessionLocal()
    try:
        gift_mapping = {
            "gift:pet": ("❤️ Погладить", "Любимый погладил тебя дистанционно и передал лучики тепла! 🥰✨"),
            "gift:food": ("🍕 Вкусняшка", "Любимый заказал тебе самую вкусную горячую пиццу! 🍕😋"),
            "gift:kiss": ("💌 Чмок", "Любимый нежно чмокнул тебя прямо в щёчку! 💋💖")
        }

        label, message = gift_mapping.get(
            callback_data,
            ("💖 Любовь", "Любимый прислал тебе океан нежности и любви! 💕")
        )

        reaction = GiftReaction(
            action_type=callback_data.replace("gift:", ""),
            label=label,
            message=message,
            is_read=False
        )
        db.add(reaction)

        # Restore pet state to 100% on boyfriend's gift!
        state = db.query(PetState).first()
        if state:
            state.hunger = 100.0
            state.energy = 100.0
            state.hygiene = 100.0
            state.fun = 100.0
            state.is_sleeping = False
            state.last_update = time.time() * 1000.0

        db.commit()
        print(f"[Boyfriend Gift] Logged reaction: {label} -> {message}")

        # Send feedback to boyfriend in Telegram
        answer_callback_query(callback_id, "Твоя забота отправлена Лёле на экран! ✨")
        send_telegram_message(f"✨ <b>Твоя забота доставлена Лёле!</b>\n<i>«{message}»</i>\nНа её экране взорвался салют из сердечек! 💕🎉")
    except Exception as e:
        print(f"[Telegram Callback] Error processing callback: {e}")
    finally:
        db.close()


def telegram_polling_loop():
    """Background polling loop for Telegram updates."""
    offset = 0
    print("[Telegram Poller] Started background polling loop...")
    while True:
        try:
            if not TELEGRAM_BOT_TOKEN:
                time.sleep(10)
                continue

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=20"
            resp = requests.get(url, timeout=25.0)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    if "callback_query" in update:
                        cb = update["callback_query"]
                        cb_id = cb["id"]
                        cb_data = cb.get("data", "")
                        process_telegram_callback(cb_data, cb_id)

                    elif "message" in update:
                        msg = update["message"]
                        sender_text = msg.get("text", "")
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        if chat_id == TELEGRAM_CHAT_ID and sender_text and not sender_text.startswith("/"):
                            db = SessionLocal()
                            try:
                                reaction = GiftReaction(
                                    action_type="message",
                                    label="💬 Сообщение",
                                    message=f"Любимый написал: «{sender_text}»",
                                    is_read=False
                                )
                                db.add(reaction)
                                db.commit()
                                send_telegram_message(f"💌 Сообщение доставлено на экран Лёли: <i>«{sender_text}»</i>")
                            finally:
                                db.close()

            time.sleep(1.0)
        except Exception as e:
            print(f"[Telegram Poller] Polling cycle error: {e}")
            time.sleep(5.0)


# -----------------------------------------------------------------------------
# Web & API Endpoints
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    """Serves the main Pou-style Virtual Pet SPA."""
    return render_template("index.html")


@app.route("/health")
@app.route("/ping")
def health_check():
    """Endpoint for UptimeRobot / Render keepalive."""
    return jsonify({
        "status": "ok",
        "service": "girlfriend-tamagotchi",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected"
    }), 200


@app.route("/api/state", methods=["GET"])
def get_state():
    """Returns the latest pet state."""
    db = SessionLocal()
    try:
        state = db.query(PetState).first()
        if not state:
            state = PetState()
            db.add(state)
            db.commit()
        return jsonify({"status": "success", "state": state.to_dict()})
    finally:
        db.close()


@app.route("/api/state", methods=["POST"])
def save_state():
    """Saves pet state from client and triggers alerts if needed."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    db = SessionLocal()
    try:
        state = db.query(PetState).first()
        if not state:
            state = PetState()
            db.add(state)

        if "hunger" in data:
            state.hunger = max(0.0, min(100.0, float(data["hunger"])))
        if "energy" in data:
            state.energy = max(0.0, min(100.0, float(data["energy"])))
        if "hygiene" in data:
            state.hygiene = max(0.0, min(100.0, float(data["hygiene"])))
        if "fun" in data:
            state.fun = max(0.0, min(100.0, float(data["fun"])))
        if "isSleeping" in data:
            state.is_sleeping = bool(data["isSleeping"])
        if "coins" in data:
            state.coins = max(0, int(data["coins"]))
        if "lastUpdate" in data:
            state.last_update = float(data["lastUpdate"])
        else:
            state.last_update = time.time() * 1000.0

        db.commit()
        state_dict = state.to_dict()

        # Check critical alert condition in background
        check_and_send_critical_alert(state.hunger, state.energy, state.fun)

        return jsonify({"status": "success", "state": state_dict})
    finally:
        db.close()


@app.route("/api/reactions", methods=["GET"])
def get_reactions():
    """Returns unread gifts/reactions from boyfriend, marks them read."""
    db = SessionLocal()
    try:
        unread = db.query(GiftReaction).filter(GiftReaction.is_read == False).order_by(GiftReaction.created_at.asc()).all()
        reactions_data = [r.to_dict() for r in unread]

        for r in unread:
            r.is_read = True
        if unread:
            db.commit()

        return jsonify({
            "status": "success",
            "reactions": reactions_data
        })
    finally:
        db.close()


@app.route("/api/action", methods=["POST"])
def perform_action():
    """Direct care actions from client."""
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "").lower().strip()

    db = SessionLocal()
    try:
        state = db.query(PetState).first()
        if not state:
            state = PetState()
            db.add(state)

        msg = "Действие выполнено!"
        if action == "feed":
            food_type = data.get("food", "pizza")
            food_values = {
                "pizza": 25.0,
                "apple": 15.0,
                "cake": 30.0,
                "coffee": 5.0
            }
            gain = food_values.get(food_type, 20.0)
            state.hunger = min(100.0, state.hunger + gain)
            if food_type == "coffee":
                state.energy = min(100.0, state.energy + 10.0)
            msg = "Лёля с аппетитом покушала! 🍰😋"

        elif action == "wash":
            state.hygiene = min(100.0, state.hygiene + 25.0)
            msg = "Лёля сияет чистотой и свежестью! 🧼✨"

        elif action == "shower":
            state.hygiene = 100.0
            msg = "Освежающий душ! Все пузырьки смыты! 🚿💖"

        elif action == "sleep_toggle":
            state.is_sleeping = not state.is_sleeping
            msg = "Лёля сладко уснула под одеялком 🌙💤" if state.is_sleeping else "Лёля проснулась и потянулась! ☀️"

        elif action in ("play", "pet"):
            state.fun = min(100.0, state.fun + 20.0)
            msg = "Лёля весело хихикает и радуется! 🎮🥰"

        state.last_update = time.time() * 1000.0
        db.commit()

        return jsonify({
            "status": "success",
            "message": msg,
            "state": state.to_dict()
        })
    finally:
        db.close()


@app.route("/api/telegram-webhook", methods=["POST"])
def telegram_webhook():
    """Webhook endpoint for Telegram Bot API."""
    update = request.get_json(force=True, silent=True)
    if not update:
        return jsonify({"ok": True}), 200

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        cb_data = cb.get("data", "")
        threading.Thread(target=process_telegram_callback, args=(cb_data, cb_id), daemon=True).start()

    elif "message" in update:
        msg = update["message"]
        sender_text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id == TELEGRAM_CHAT_ID and sender_text and not sender_text.startswith("/"):
            db = SessionLocal()
            try:
                reaction = GiftReaction(
                    action_type="message",
                    label="💬 Сообщение",
                    message=f"Любимый написал: «{sender_text}»",
                    is_read=False
                )
                db.add(reaction)
                db.commit()
                send_telegram_message(f"💌 Сообщение доставлено на экран Лёли: <i>«{sender_text}»</i>")
            finally:
                db.close()

    return jsonify({"ok": True}), 200


# -----------------------------------------------------------------------------
# Startup Initializer
# -----------------------------------------------------------------------------
def setup_telegram_integration():
    """Sets up webhook or polling depending on environment."""
    if not TELEGRAM_BOT_TOKEN:
        print("[Telegram Bot] Bot token is empty. Running in standalone mode.")
        return

    public_url = WEBHOOK_URL or RENDER_EXTERNAL_URL
    if public_url and not USE_POLLING:
        webhook_endpoint = f"{public_url.rstrip('/')}/api/telegram-webhook"
        print(f"[Telegram Bot] Registering webhook at {webhook_endpoint}...")
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
                json={"url": webhook_endpoint, "drop_pending_updates": False},
                timeout=10.0
            )
            print(f"[Telegram Bot] setWebhook response: {resp.json()}")
        except Exception as e:
            print(f"[Telegram Bot] Webhook registration failed: {e}")
    else:
        # Start background polling thread
        poller_thread = threading.Thread(target=telegram_polling_loop, daemon=True)
        poller_thread.start()


# Initialize database at module load time
init_db()

# Run Telegram integration in background thread
threading.Thread(target=setup_telegram_integration, daemon=True).start()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  💖 Тамагочи Лёли (Pou / My Talking Tom Style) 💖")
    print(f"  Сервер запущен: http://localhost:{PORT}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
