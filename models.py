from datetime import datetime
import json
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    time_interval = Column(String(50), nullable=False) # e.g. "14:00 - 15:00"
    hunger = Column(Integer, default=70) # 0 to 100%
    energy = Column(Integer, default=70) # 0 to 100%
    stress = Column(Integer, default=20) # 0 to 100%
    miss_you = Column(Integer, default=85) # 0 to 100%
    tags = Column(Text, default="[]") # JSON list of string tags
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
    action_type = Column(String(50), nullable=False) # hug, treat, proud, kiss, sos_response, custom
    label = Column(String(100), nullable=False) # e.g. "❤️ Обнять"
    message = Column(Text, nullable=False) # message displayed in Mini App
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
