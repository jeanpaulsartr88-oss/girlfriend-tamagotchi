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
TELEGRAM_BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "Lelya8_bot").strip().lstrip("@")
TELEGRAM_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PORT                  = int(os.getenv("PORT", 5000))

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


class UserTamagotchi(Base):
    __tablename__ = "user_tamagotchi"
    telegram_id            = Column(Integer, primary_key=True)
    hunger                 = Column(Integer, default=80)
    energy                 = Column(Integer, default=80)
    hygiene                = Column(Integer, default=90)
    fun                    = Column(Integer, default=85)
    coins                  = Column(Integer, default=100)
    last_active_at         = Column(DateTime, default=datetime.utcnow)
    last_notification_type = Column(String(50), nullable=True)
    last_notification_time = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "telegram_id": self.telegram_id,
            "hunger": int(self.hunger) if self.hunger is not None else 80,
            "energy": int(self.energy) if self.energy is not None else 80,
            "hygiene": int(self.hygiene) if self.hygiene is not None else 90,
            "fun": int(self.fun) if self.fun is not None else 85,
            "coins": int(self.coins) if self.coins is not None else 100,
            "last_active_at": self.last_active_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_active_at else None,
            "last_notification_type": self.last_notification_type,
            "last_notification_time": self.last_notification_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_notification_time else None,
        }


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

    # Запуск фонового планировщика уведомлений
    threading.Thread(target=background_notification_worker, daemon=True).start()


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


# ──────────────────────────────────────────────────────────────────────────────
# Фоновые push-уведомления и правила потребностей
# ──────────────────────────────────────────────────────────────────────────────
NOTIFICATION_CONFIGS = {
    "fun": {
        "priority": 1,
        "text": "Мне скучно, хочется движухи! Зайдём в игровой клуб погонять? 🎮✨",
        "btn_text": "🎮 В игровой клуб",
        "room": "living"
    },
    "hunger": {
        "priority": 2,
        "text": "В животике урчит... Я так проголодалась, пойдём покушаем вкусняшек? 🍕🍓",
        "btn_text": "🍕 Покормить на кухне",
        "room": "kitchen"
    },
    "hygiene": {
        "priority": 3,
        "text": "Я кажется испачкалась... Пойдём примем теплую пенную ванну? 🛁🫧",
        "btn_text": "🚿 В ванную",
        "room": "bathroom"
    },
    "energy": {
        "priority": 4,
        "text": "Глазки слипаются... Уложи меня баиньки, пожалуйста 🌙😴",
        "btn_text": "🛏️ В спальню",
        "room": "bedroom"
    }
}


def send_tamagotchi_push(telegram_id: int, notif_type: str) -> dict:
    cfg = NOTIFICATION_CONFIGS.get(notif_type, NOTIFICATION_CONFIGS["fun"])
    deep_link_url = f"https://t.me/{TELEGRAM_BOT_USERNAME}/app?startapp={cfg['room']}"
    keyboard = {
        "inline_keyboard": [
            [{"text": cfg["btn_text"], "url": deep_link_url}]
        ]
    }
    payload = {
        "chat_id": telegram_id,
        "text": cfg["text"],
        "parse_mode": "HTML",
        "reply_markup": keyboard
    }

    if MOCK_MODE or not TELEGRAM_BOT_TOKEN:
        print(f"[MOCK PUSH] Sent to {telegram_id} | Type: {notif_type} | Text: {cfg['text']} | URL: {deep_link_url}")
        return {
            "ok": True,
            "mock": True,
            "telegram_id": telegram_id,
            "type": notif_type,
            "text": cfg["text"],
            "url": deep_link_url
        }

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json=payload, timeout=6.0)
        res_json = resp.json() if resp.status_code == 200 else {}
        if resp.status_code != 200:
            print(f"[Telegram Push API Error {resp.status_code}] {resp.text}")
            return {
                "ok": False,
                "status_code": resp.status_code,
                "telegram_id": telegram_id,
                "type": notif_type,
                "error": resp.text,
                "text": cfg["text"],
                "url": deep_link_url
            }
        print(f"[Telegram Push Success] Sent to {telegram_id} ({notif_type})")
        return {
            "ok": True,
            "status_code": 200,
            "telegram_id": telegram_id,
            "type": notif_type,
            "text": cfg["text"],
            "url": deep_link_url,
            "telegram_response": res_json
        }
    except Exception as e:
        print(f"[Telegram Push Exception] {e}")
        return {
            "ok": False,
            "error": str(e),
            "telegram_id": telegram_id,
            "type": notif_type,
            "text": cfg["text"],
            "url": deep_link_url
        }


def background_notification_worker():
    """Фоновый поток проверки потребностей пользователей каждые 2 минуты."""
    print("[Notification Worker] Background thread running.")
    while True:
        try:
            time.sleep(120)  # проверка каждые 2 минуты
            
            # «Тихий режим»: не отправлять сообщения с 23:30 до 08:30 (по времени сервера)
            now_local = datetime.now()
            cur_min = now_local.hour * 60 + now_local.minute
            if cur_min >= (23 * 60 + 30) or cur_min < (8 * 60 + 30):
                continue

            db = SessionLocal()
            try:
                now_utc = datetime.utcnow()
                users = db.query(UserTamagotchi).all()
                for u in users:
                    if not u.last_active_at:
                        continue
                    
                    elapsed_sec = (now_utc - u.last_active_at).total_seconds()
                    # Не заходили более 2 часов (7200 сек)
                    if elapsed_sec < 7200:
                        continue

                    # Cooldown: не чаще 1 раза в 3 часа (10800 сек)
                    if u.last_notification_time:
                        if (now_utc - u.last_notification_time).total_seconds() < 10800:
                            continue

                    # Расчет спада потребностей:
                    # - Сытость: -15% каждые 2 часа (7.5% / час)
                    # - Энергия: -10% каждые 2 часа (5.0% / час)
                    # - Гигиена: -10% каждые 2.5 часа (4.0% / час)
                    # - Настроение (fun): -15% каждые 1.5 часа (10.0% / час)
                    elapsed_hours = elapsed_sec / 3600.0
                    decayed_hunger  = max(0, int(u.hunger  - elapsed_hours * 7.5))
                    decayed_energy  = max(0, int(u.energy  - elapsed_hours * 5.0))
                    decayed_hygiene = max(0, int(u.hygiene - elapsed_hours * 4.0))
                    decayed_fun     = max(0, int(u.fun     - elapsed_hours * 10.0))

                    needed_type = None
                    if decayed_fun < 30:
                        needed_type = "fun"
                    elif decayed_hunger < 25:
                        needed_type = "hunger"
                    elif decayed_hygiene < 25:
                        needed_type = "hygiene"
                    elif decayed_energy < 20:
                        needed_type = "energy"

                    if needed_type:
                        res = send_tamagotchi_push(u.telegram_id, needed_type)
                        u.last_notification_type = needed_type
                        u.last_notification_time = now_utc
                        db.commit()
            except Exception as e:
                print(f"[Notification Worker Error] {e}")
            finally:
                db.close()
        except Exception as outer_e:
            print(f"[Notification Worker Outer Error] {outer_e}")
            time.sleep(30)

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


@app.route("/api/sync_state", methods=["POST"])
def sync_state():
    data = request.get_json(force=True, silent=True) or {}
    tid = data.get("telegram_id")
    if not tid:
        return jsonify({"status": "error", "message": "telegram_id is required"}), 400
    
    try:
        tid = int(tid)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "invalid telegram_id"}), 400

    db = SessionLocal()
    try:
        user = db.query(UserTamagotchi).filter(UserTamagotchi.telegram_id == tid).first()
        if not user:
            user = UserTamagotchi(telegram_id=tid)
            db.add(user)

        if "hunger" in data:
            user.hunger = max(0, min(100, int(float(data["hunger"]))))
        if "energy" in data:
            user.energy = max(0, min(100, int(float(data["energy"]))))
        if "hygiene" in data:
            user.hygiene = max(0, min(100, int(float(data["hygiene"]))))
        if "fun" in data:
            user.fun = max(0, min(100, int(float(data["fun"]))))
        if "coins" in data:
            user.coins = max(0, int(float(data["coins"])))

        user.last_active_at = datetime.utcnow()
        db.commit()
        return jsonify({"status": "success", "user": user.to_dict()})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/test_notification", methods=["GET", "POST"])
def test_notification():
    tid = request.args.get("telegram_id") or (request.get_json(silent=True) or {}).get("telegram_id")
    notif_type = request.args.get("type") or (request.get_json(silent=True) or {}).get("type") or "fun"

    if not tid:
        tid = TELEGRAM_CHAT_ID
        if not tid:
            db = SessionLocal()
            try:
                first_user = db.query(UserTamagotchi).first()
                if first_user:
                    tid = first_user.telegram_id
            finally:
                db.close()

    if not tid:
        return jsonify({
            "status": "error",
            "message": "Параметр telegram_id обязателен (например, /api/test_notification?telegram_id=6671126368&type=fun)"
        }), 400

    try:
        tid = int(tid)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Некорректный telegram_id"}), 400

    if notif_type not in NOTIFICATION_CONFIGS:
        return jsonify({
            "status": "error",
            "message": f"Неизвестный тип уведомления '{notif_type}'. Доступные: {list(NOTIFICATION_CONFIGS.keys())}"
        }), 400

    result = send_tamagotchi_push(tid, notif_type)
    return jsonify({
        "status": "success" if result.get("ok") else "warning",
        "result": result
    })

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
# Проксирование аудио в локальный RVC голосовой сервис (http://127.0.0.1:5050/convert)
# ──────────────────────────────────────────────────────────────────────────────
LOCAL_RVC_URL = os.getenv("LOCAL_RVC_URL", "http://127.0.0.1:5050/convert")
LOCAL_RVC_TIMEOUT = float(os.getenv("LOCAL_RVC_TIMEOUT", "30.0"))

@app.route('/api/repeat_voice', methods=['POST'])
def repeat_voice():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    audio_file = request.files['audio']
    try:
        raw_bytes = audio_file.read()
        print(f"[FLASK] Получено аудио от клиента ({len(raw_bytes)} байт)")

        # Режим повторялки: по умолчанию passthrough / direct_echo (чистое оригинальное эхо без искажений)
        mode = request.form.get("mode", request.args.get("mode", "passthrough")).strip().lower()
        use_rvc_val = str(request.form.get("use_rvc", request.args.get("use_rvc", "false"))).strip().lower()
        use_rvc = use_rvc_val in ("1", "true", "yes") or mode == "rvc"

        # ── 1. РЕЖИМ ЧЕСТНОЙ ПОВТОРЯЛКИ (PASSTHROUGH ECHO) ПО УМОЛЧАНИЮ ──
        if not use_rvc:
            print("[FLASK] Режим 'Pass-through Echo': мгновенный возврат оригинального голоса без искажений.")
            
            # Если передан чистый WAV (заголовок RIFF....WAVE), возвращаем сразу
            if len(raw_bytes) >= 12 and raw_bytes[:4] == b'RIFF' and raw_bytes[8:12] == b'WAVE':
                return Response(raw_bytes, mimetype="audio/wav")
            
            # Иначе перекодируем через soundfile в чистый PCM 16-bit WAV
            try:
                import io
                import soundfile as sf
                data, samplerate = sf.read(io.BytesIO(raw_bytes))
                out_io = io.BytesIO()
                sf.write(out_io, data, samplerate, format='WAV', subtype='PCM_16')
                return Response(out_io.getvalue(), mimetype="audio/wav")
            except Exception as conv_err:
                print(f"[FLASK] Предупреждение soundfile ({conv_err}), возврат raw_bytes")
                content_type = audio_file.content_type or "audio/wav"
                return Response(raw_bytes, mimetype=content_type)

        # ── 2. РЕЗЕРВНЫЙ КОНВЕЙЕР RVC (ЕСЛИ ЯВНО ПЕРЕДАН use_rvc: true) ──
        print(f"[FLASK] Режим RVC активирован, отправка на {LOCAL_RVC_URL}...")
        f0_up_key = request.form.get("f0_up_key", request.args.get("f0_up_key", "12"))
        f0_method = request.form.get("f0_method", request.args.get("f0_method", "rmvpe"))
        index_rate = request.form.get("index_rate", request.args.get("index_rate", "0.45"))
        filter_radius = request.form.get("filter_radius", request.args.get("filter_radius", "5"))
        rms_mix_rate = request.form.get("rms_mix_rate", request.args.get("rms_mix_rate", "0.0"))
        protect = request.form.get("protect", request.args.get("protect", "0.5"))

        payload = {
            "f0_up_key": f0_up_key,
            "f0up_key": f0_up_key,
            "pitch": f0_up_key,
            "f0_method": f0_method,
            "index_rate": index_rate,
            "filter_radius": filter_radius,
            "rms_mix_rate": rms_mix_rate,
            "protect": protect
        }

        files = {
            'audio': (
                audio_file.filename or 'input.wav',
                raw_bytes,
                audio_file.content_type or 'audio/wav'
            )
        }
        resp = requests.post(
            LOCAL_RVC_URL,
            files=files,
            data=payload,
            timeout=LOCAL_RVC_TIMEOUT
        )
        print("[FLASK] Ответ от RVC:", resp.status_code)

        if resp.status_code == 200 and 'audio' in resp.headers.get('content-type', ''):
            print(f"[FLASK] Успешная конвертация RVC: получено {len(resp.content)} байт WAV.")
            return Response(resp.content, mimetype="audio/wav")
        else:
            print(f"[FLASK] Ошибка ответа RVC {resp.status_code}: {resp.text[:200]}")
            # Откат на чистый оригинал при ошибке RVC
            return Response(raw_bytes, mimetype="audio/wav")
    except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
        print(f"[FLASK] RVC недоступен ({e}), возврат оригинального аудио")
        return Response(raw_bytes, mimetype="audio/wav")
    except Exception as e:
        print(f"[FLASK] Ошибка в repeat_voice ({e}), возврат оригинального аудио")
        return Response(raw_bytes, mimetype="audio/wav")


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
    use_ssl = os.getenv("USE_SSL", "false").lower() in ("true", "1", "yes")
    ssl_context = None
    protocol = "http"
    if use_ssl and os.path.exists("cert.pem") and os.path.exists("key.pem"):
        ssl_context = ("cert.pem", "key.pem")
        protocol = "https"

    print("=" * 60)
    print("  Тамагочи Лёли — Сервер запущен")
    print(f"  Локальный URL (ПК):  {protocol}://localhost:{PORT}")
    print(f"  В сети (Wi-Fi/LAN):  {protocol}://192.168.8.31:{PORT}")
    print(f"  Режим:               {'MOCK_MODE (Локальный)' if MOCK_MODE else 'Live Telegram'}")
    if protocol == "https":
        print("  SSL (HTTPS):         ВКЛЮЧЕН (Микрофон доступен по сети Wi-Fi)")
    else:
        print("  Микрофон:            Открывайте http://localhost:5000 (разрешен без HTTPS)")
    print("=" * 60)
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, ssl_context=ssl_context)
