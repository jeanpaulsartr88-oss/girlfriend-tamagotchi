from datetime import datetime
import json
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class TamagotchiState(Base):
    __tablename__ = "tamagotchi_state"

    id = Column(Integer, primary_key=True, index=True)
    energy = Column(Integer, default=80)     # 0 to 100
    hunger = Column(Integer, default=75)     # 0 to 100 (Сытость: 100=сыта, 0=голодна)
    happiness = Column(Integer, default=85)  # 0 to 100 (Настроение/Счастье)
    love = Column(Integer, default=90)       # 0 to 100 (Уровень любви)
    last_updated_at = Column(DateTime, default=datetime.utcnow)
    last_hug_at = Column(DateTime, nullable=True)

    def apply_decay(self, now=None):
        """Calculates natural metric degradation over time."""
        if now is None:
            now = datetime.utcnow()
        if not self.last_updated_at:
            self.last_updated_at = now
            return

        delta_seconds = (now - self.last_updated_at).total_seconds()
        if delta_seconds < 5:
            return

        # Decay rates per hour:
        # Hunger (сытость падает): -10 points / hour
        # Energy (энергия падает): -7 points / hour
        # Love (любовь снижается): -4 points / hour
        # Happiness (счастье падает быстрее при голоде или усталости)
        decay_hunger = (delta_seconds / 3600.0) * 10.0
        decay_energy = (delta_seconds / 3600.0) * 7.0
        decay_love = (delta_seconds / 3600.0) * 4.0
        
        extra_penalty = 1.0
        if self.hunger < 35 or self.energy < 30:
            extra_penalty = 2.5
        decay_happiness = (delta_seconds / 3600.0) * 6.0 * extra_penalty

        self.hunger = max(0, min(100, int(round(self.hunger - decay_hunger))))
        self.energy = max(0, min(100, int(round(self.energy - decay_energy))))
        self.happiness = max(0, min(100, int(round(self.happiness - decay_happiness))))
        self.love = max(0, min(100, int(round(self.love - decay_love))))
        self.last_updated_at = now

    def perform_action(self, action: str, now=None):
        """Applies action (feed, sleep, hug, kiss, miss) with cooldowns."""
        if now is None:
            now = datetime.utcnow()
        self.apply_decay(now)

        action = action.lower().strip()
        if action == "feed":
            self.hunger = min(100, self.hunger + 25)
            self.happiness = min(100, self.happiness + 8)
            message = "Любимая с удовольствием скушала вкусняшку! 🍰✨"
            return True, message

        elif action == "sleep":
            self.energy = min(100, self.energy + 35)
            self.happiness = min(100, self.happiness + 5)
            message = "Любимая сладко поспала и набралась сил! 🌙💤"
            return True, message

        elif action in ("hug", "kiss", "miss"):
            # Cooldown check: 20 seconds
            if self.last_hug_at:
                cooldown_remaining = 20 - (now - self.last_hug_at).total_seconds()
                if cooldown_remaining > 0:
                    return False, f"Любимая ещё тает от прошлых объятий! Подожди {int(cooldown_remaining)} сек 💕"

            self.last_hug_at = now
            if action == "hug":
                self.happiness = min(100, self.happiness + 20)
                self.love = min(100, self.love + 15)
                message = "Крепкие объятия! Любимая улыбается и светится от счастья! ❤️🥰"
            elif action == "kiss":
                self.happiness = min(100, self.happiness + 18)
                self.love = min(100, self.love + 18)
                message = "Нежный поцелуй! Щёчки горят от радости! 💋✨"
            else: # miss
                self.happiness = min(100, self.happiness + 15)
                self.love = min(100, self.love + 20)
                message = "Любимая почувствовала, как сильно ты по ней скучаешь! 🥺💖"
            return True, message

        return False, "Неизвестное действие"

    def get_status_info(self):
        """Returns readable status text and avatar mood based on current stats."""
        if self.energy < 25:
            return "Очень хочет спать 😴💤", "tired"
        elif self.hunger < 30:
            return "Проголодалась, хочет вкусняшку 🍰🥺", "sad"
        elif self.happiness < 35 or self.love < 35:
            return "Скучает по твоим объятиям 🥺💔", "sad"
        elif self.happiness >= 75 and self.hunger >= 70:
            return "Сыта, счастлива и полна любви! ✨🥰", "happy"
        else:
            return "Всё хорошо, занимается делами и думает о тебе 🌸", "idle"

    def to_dict(self):
        status_text, mood = self.get_status_info()
        return {
            "energy": self.energy,
            "hunger": self.hunger,
            "happiness": self.happiness,
            "love": self.love,
            "status_text": status_text,
            "mood": mood,
            "last_updated_at": self.last_updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_updated_at else None
        }


class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    time_interval = Column(String(50), nullable=False)
    hunger = Column(Integer, default=70)
    energy = Column(Integer, default=70)
    stress = Column(Integer, default=20)
    miss_you = Column(Integer, default=85)
    tags = Column(Text, default="[]")
    note = Column(Text, default="")
    is_sos = Column(Boolean, default=False)
    telegram_message_id = Column(Integer, nullable=True)

    reactions = relationship("Reaction", back_populates="checkin", cascade="all, delete-orphan", order_by="desc(Reaction.created_at)")

    def get_tags_list(self):
        try:
            return json.loads(self.tags) if self.tags else []
        except Exception:
            return [t.strip() for t in self.tags.split(",") if t.strip()]

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "time_interval": self.time_interval,
            "hunger": self.hunger,
            "energy": self.energy,
            "stress": self.stress,
            "miss_you": self.miss_you,
            "tags": self.get_tags_list(),
            "note": self.note,
            "is_sos": self.is_sos,
            "reactions": [r.to_dict() for r in self.reactions]
        }


class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True, index=True)
    checkin_id = Column(Integer, ForeignKey("checkins.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    action_type = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, index=True)

    checkin = relationship("CheckIn", back_populates="reactions")

    def to_dict(self):
        return {
            "id": self.id,
            "checkin_id": self.checkin_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "action_type": self.action_type,
            "label": self.label,
            "message": self.message,
            "is_read": self.is_read
        }
