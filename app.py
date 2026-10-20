# -*- coding: utf-8 -*-
"""
Тамагочи Лёли — Flask backend.
Поддерживает локальный/автономный режим (MOCK_MODE = True) без живого Telegram бота.
"""
import os
import sys
import time
import json
import threading
from datetime import datetime

# Гарантируем UTF-8 вывод в консоль Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

import requests
from flask import Flask, request, jsonify, render_template, Response
from sqlalchemy import (
    create_engine, Column, Integer, Float, Boolean, DateTime, String, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

# ──────────────────────────────────────────────────────────────────────────────
# Конфигурация и MOCK_MODE
# ──────────────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PORT               = int(os.getenv("PORT", 8000))

# По умолчанию в локальном запуске MOCK_MODE = True
# Никаких автоматических вызовов setWebhook или getUpdates при старте сервера!
MOCK_MODE = True

if TELEGRAM_BOT_TOKEN and not TELEGRAM_BOT_TOKEN.startswith("your_"):
    # Быстрая неблокирующая проверка валидности токена
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
            timeout=3.0
        )
        if r.status_code == 200 and r.json().get("ok"):
            MOCK_MODE = False
            print(f"[Telegram] Bot verified: @{r.json()['result']['username']}")
        else:
            print(f"[Telegram] Bot token invalid or 401 Unauthorized -> MOCK_MODE = True")
            MOCK_MODE = True
    except Exception as exc:
        print(f"[Telegram] Probe failed ({exc}) -> MOCK_MODE = True")
        MOCK_MODE = True
else:
    print("[Telegram] Token empty or placeholder -> MOCK_MODE = True")
    MOCK_MODE = True

print(f"[Server Config] MOCK_MODE = {MOCK_MODE} (Local standalone: all alerts printed to console)")

# ──────────────────────────────────────────────────────────────────────────────
# Flask приложение
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_AS_ASCII"] = False
app.jinja_env.cache = None  # Защита от бага кеша кортежей Jinja2 на Python 3.14+

# ──────────────────────────────────────────────────────────────────────────────
# База данных SQLite
# ──────────────────────────────────────────────────────────────────────────────
_db_url = os.getenv("DATABASE_URL", "sqlite:///./tamagotchi.db")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine       = create_engine(_db_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base         = declarative_base()


class PetState(Base):
    __tablename__ = "pet_state"
    id          = Column(Integer, primary_key=True)
    hunger      = Column(Float,   default=80.0)
    energy      = Column(Float,   default=80.0)
    hygiene     = Column(Float,   default=90.0)
    fun         = Column(Float,   default=85.0)
    is_sleeping = Column(Boolean, default=False)
    coins       = Column(Integer, default=100)
    last_update = Column(Float,   default=lambda: time.time() * 1000.0)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "hunger":     round(float(self.hunger),  1),
            "energy":     round(float(self.energy),  1),
            "hygiene":    round(float(self.hygiene), 1),
            "fun":        round(float(self.fun),     1),
            "isSleeping": bool(self.is_sleeping),
            "coins":      int(self.coins),
            "lastUpdate": float(self.last_update) if self.last_update else time.time() * 1000.0,
        }


class GiftReaction(Base):
    __tablename__ = "gift_reactions"
    id          = Column(Integer,  primary_key=True)
    action_type = Column(String(50), nullable=False)
    label       = Column(String(100), nullable=False)
    message     = Column(Text,    nullable=False)
    is_read     = Column(Boolean, default=False, index=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":          self.id,
            "action_type": self.action_type,
            "label":       self.label,
            "message":     self.message,
            "is_read":     bool(self.is_read),
            "created_at":  self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class AlertLog(Base):
    __tablename__ = "alert_logs"
    id              = Column(Integer,  primary_key=True)
    last_alert_time = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(PetState).first():
            db.add(PetState(
                hunger=85.0, energy=85.0, hygiene=90.0, fun=90.0,
                is_sleeping=False, coins=100, last_update=time.time() * 1000.0
            ))
            db.commit()
            print("[Database] Initial PetState created successfully.")
    except Exception as e:
        print(f"[Database] Seed error: {e}")
    finally:
        db.close()


@app.teardown_appcontext
def remove_session(exc=None):
    SessionLocal.remove()


# ──────────────────────────────────────────────────────────────────────────────
# Отправка сообщений (с поддержкой MOCK_MODE)
# ──────────────────────────────────────────────────────────────────────────────
def send_telegram_alert(text: str, reply_markup: dict | None = None) -> None:
    if MOCK_MODE or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[MOCK TG] Alert sent: {text.replace('<b>', '').replace('</b>', '')}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(url, json=payload, timeout=5.0)
        if resp.status_code != 200:
            print(f"[Telegram] Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Telegram] Send failed: {e}")


_ALERT_COOLDOWN = 1200  # 20 минут между алертами


def check_and_alert_if_low(hunger: float, energy: float, fun: float) -> None:
    """Если сытость, энергия или настроение < 20% — формируем алерт."""
    if hunger > 20.0 and energy > 20.0 and fun > 20.0:
        return

    db = SessionLocal()
    try:
        log = db.query(AlertLog).first()
        now = datetime.utcnow()
        if log and (now - log.last_alert_time).total_seconds() < _ALERT_COOLDOWN:
            return
        if log:
            log.last_alert_time = now
        else:
            db.add(AlertLog(last_alert_time=now))
        db.commit()
    except Exception:
        return
    finally:
        db.close()

    text = (
        "⚠️ <b>Внимание! Твоя любимая Лёля грустит или голодает!</b> 🥺💔\n\n"
        f"🍰 Сытость: <b>{int(hunger)}%</b>\n"
        f"⚡ Энергия: <b>{int(energy)}%</b>\n"
        f"🎮 Настроение: <b>{int(fun)}%</b>\n\n"
        "Пора проявить заботу и отправить подарок! 👇"
    )
    keyboard = {"inline_keyboard": [
        [
            {"text": "❤️ Погладить дистанционно", "callback_data": "gift:pet"},
            {"text": "🍕 Заказать вкусняшку",     "callback_data": "gift:food"}
        ],
        [
            {"text": "💌 Чмокнуть в щёчку",       "callback_data": "gift:kiss"}
        ]
    ]}
    threading.Thread(target=send_telegram_alert, args=(text, keyboard), daemon=True).start()


def apply_gift_reaction(cb_data: str) -> str:
    """Применяет подарок парня: восстанавливает шкалы на 100% и пишет реакцию в БД."""
    gifts = {
        "gift:pet":  ("❤️ Погладить",  "Любимый погладил тебя дистанционно и передал лучики тепла! 🥰✨"),
        "gift:food": ("🍕 Вкусняшка",  "Любимый заказал тебе самую вкусную горячую пиццу! 🍕😋"),
        "gift:kiss": ("💌 Чмок",       "Любимый нежно чмокнул тебя прямо в щёчку! 💋💖"),
    }
    label, message = gifts.get(cb_data, ("💖 Любовь", "Любимый прислал тебе океан нежности и любви! 💕"))

    db = SessionLocal()
    try:
        db.add(GiftReaction(
            action_type=cb_data.replace("gift:", ""),
            label=label,
            message=message,
            is_read=False
        ))
        state = db.query(PetState).first()
        if state:
            state.hunger     = 100.0
            state.energy     = 100.0
            state.hygiene    = 100.0
            state.fun        = 100.0
            state.is_sleeping = False
            state.last_update = time.time() * 1000.0
        db.commit()
        print(f"[Boyfriend Gift] Processed: {label} -> {message}")
        return message
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# API Маршруты
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
@app.route("/ping")
def health():
    return jsonify({
        "status": "ok",
        "service": "girlfriend-tamagotchi",
        "mock_mode": MOCK_MODE,
        "timestamp": datetime.utcnow().isoformat()
    }), 200


@app.route("/api/state", methods=["GET"])
def get_state():
    db = SessionLocal()
    try:
        s = db.query(PetState).first()
        if not s:
            s = PetState()
            db.add(s)
            db.commit()
        return jsonify({"status": "success", "state": s.to_dict()})
    finally:
        db.close()


@app.route("/api/state", methods=["POST"])
def save_state():
    data = request.get_json(force=True, silent=True) or {}
    db = SessionLocal()
    try:
        s = db.query(PetState).first()
        if not s:
            s = PetState()
            db.add(s)
        for field in ("hunger", "energy", "hygiene", "fun"):
            if field in data:
                setattr(s, field, max(0.0, min(100.0, float(data[field]))))
        if "isSleeping" in data:
            s.is_sleeping = bool(data["isSleeping"])
        if "coins" in data:
            s.coins = max(0, int(data["coins"]))
        s.last_update = float(data.get("lastUpdate", time.time() * 1000.0))
        db.commit()
        state_dict = s.to_dict()

        # Проверяем алерт при падении шкал < 20%
        threading.Thread(
            target=check_and_alert_if_low,
            args=(s.hunger, s.energy, s.fun),
            daemon=True
        ).start()

        return jsonify({"status": "success", "state": state_dict})
    finally:
        db.close()


@app.route("/api/reactions", methods=["GET"])
def get_reactions():
    db = SessionLocal()
    try:
        unread = (
            db.query(GiftReaction)
            .filter(GiftReaction.is_read == False)
            .order_by(GiftReaction.created_at.asc())
            .all()
        )
        result = [r.to_dict() for r in unread]
        for r in unread:
            r.is_read = True
        if unread:
            db.commit()
        return jsonify({"status": "success", "reactions": result})
    finally:
        db.close()


@app.route("/api/action", methods=["POST"])
def action():
    data = request.get_json(force=True, silent=True) or {}
    act = data.get("action", "").lower().strip()
    db = SessionLocal()
    try:
        s = db.query(PetState).first()
        if not s:
            s = PetState()
            db.add(s)

        msg = "Действие выполнено!"
        if act == "feed":
            food_bonus = {
                "pizza": 25.0, "apple": 15.0, "cake": 30.0,
                "coffee": 5.0, "croissant": 20.0, "watermelon": 15.0, "icecream": 20.0
            }
            food_type = data.get("food", "pizza")
            gain = food_bonus.get(food_type, 20.0)
            s.hunger = min(100.0, s.hunger + gain)
            if food_type == "coffee":
                s.energy = min(100.0, s.energy + 10.0)
            elif food_type == "watermelon":
                s.hygiene = min(100.0, s.hygiene + 5.0)
            elif food_type == "icecream":
                s.fun = min(100.0, s.fun + 10.0)
            s.coins = (s.coins or 0) + 2
            msg = "Лёля с аппетитом покушала! 🍰😋"

        elif act == "wash":
            s.hygiene = min(100.0, s.hygiene + 25.0)
            msg = "Лёля сияет чистотой! 🧼✨"

        elif act == "shower":
            s.hygiene = 100.0
            s.coins = (s.coins or 0) + 5
            msg = "Освежающий душ! 🚿💖"

        elif act == "sleep_toggle":
            s.is_sleeping = not s.is_sleeping
            msg = "Лёля уснула 🌙💤" if s.is_sleeping else "Лёля проснулась! ☀️"

        elif act in ("play", "pet", "tickle"):
            s.fun = min(100.0, s.fun + 18.0)
            s.coins = (s.coins or 0) + 3
            msg = "Лёля весело хихикает! 🎮🥰"

        elif act in ("talk", "voice", "repeat"):
            s.fun = min(100.0, s.fun + 10.0)
            s.coins = (s.coins or 0) + 2
            msg = "Лёля весело повторила твой голос! 🎙️✨"

        elif act == "minigame":
            coins_earned = max(0, int(data.get("coins", 10)))
            s.coins = (s.coins or 0) + coins_earned
            s.fun = 100.0
            msg = f"Отличная игра! Заработано +{coins_earned} монеток любви! 🎁✨"

        elif act == "buy_wallpaper":
            cost = int(data.get("cost", 30))
            if (s.coins or 0) >= cost:
                s.coins -= cost
                msg = "Новые обои успешно разблокированы! 🎨✨"
            else:
                return jsonify({"status": "error", "message": "Недостаточно монеток!"}), 400

        s.last_update = time.time() * 1000.0
        db.commit()
        return jsonify({"status": "success", "message": msg, "state": s.to_dict()})
    finally:
        db.close()


# Эмуляция реакции парня прямо из веб-интерфейса
@app.route("/api/debug/simulate-gift", methods=["POST"])
def simulate_gift():
    data = request.get_json(force=True, silent=True) or {}
    cb_data = data.get("callback_data", "gift:pet")
    msg = apply_gift_reaction(cb_data)
    print(f"[MOCK TG] Simulated boyfriend gift triggered: {cb_data}")
    return jsonify({"status": "success", "message": msg})


@app.route("/api/telegram-webhook", methods=["POST"])
def telegram_webhook():
    upd = request.get_json(force=True, silent=True) or {}
    if "callback_query" in upd:
        cb = upd["callback_query"]
        apply_gift_reaction(cb.get("data", "gift:pet"))
    return jsonify({"ok": True}), 200


# ──────────────────────────────────────────────────────────────────────────────
# Проксирование аудио в Colab RVC голосовой клон
# ──────────────────────────────────────────────────────────────────────────────
COLAB_RVC_URL = os.getenv(
    "COLAB_RVC_URL",
    "https://medication-provide-saving-humanitarian.trycloudflare.com/convert"
)

@app.route('/api/repeat_voice', methods=['POST'])
def repeat_voice():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    audio_file = request.files['audio']
    try:
        files = {
            'audio': (
                audio_file.filename or 'input.wav',
                audio_file.read(),
                audio_file.content_type or 'audio/wav'
            )
        }
        resp = requests.post(COLAB_RVC_URL, files=files, timeout=60)
        if resp.status_code == 200:
            return Response(resp.content, mimetype="audio/wav")
        else:
            return jsonify({'error': f"Colab error: {resp.text}"}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Инициализация базы данных при запуске
# ──────────────────────────────────────────────────────────────────────────────
init_db()

# ── ASGI обёртка для совместимости с uvicorn app:app на Render ──────────────
flask_app = app

try:
    from a2wsgi import WSGIMiddleware as _WSGIMiddleware

    class _DualApp:
        """Совместимость с WSGI (gunicorn) и ASGI (uvicorn app:app)."""
        def __init__(self, wsgi):
            self._wsgi = wsgi
            self._asgi = _WSGIMiddleware(wsgi)
            self.__name__ = getattr(wsgi, "__name__", "app")

        def __call__(self, *args, **kwargs):
            if len(args) == 1:
                scope = args[0]
                async def _instance(receive, send):
                    return await self._asgi(scope, receive, send)
                return _instance
            return self._wsgi(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._wsgi, name)

    app = _DualApp(flask_app)
except ImportError:
    pass


if __name__ == "__main__":
    print("=" * 60)
    print("  Тамагочи Лёли — Сервер запущен")
    print(f"  URL: http://127.0.0.1:{PORT}")
    print(f"  Режим: {'MOCK_MODE (Локальный)' if MOCK_MODE else 'Live Telegram'}")
    print("=" * 60)
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
