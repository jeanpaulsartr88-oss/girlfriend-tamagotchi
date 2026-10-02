import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./tamagotchi.db")

# Ensure sqlite URL compatibility if deployed with postgres or sqlite
if DB_PATH.startswith("postgres://"):
    DB_PATH = DB_PATH.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DB_PATH.startswith("sqlite") else {}

engine = create_engine(DB_PATH, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        from models import TamagotchiState
        state = db.query(TamagotchiState).first()
        if not state:
            state = TamagotchiState(energy=85, hunger=80, happiness=90, love=95)
            db.add(state)
            db.commit()
            print("Initial TamagotchiState seeded.")
    except Exception as e:
        print(f"Error seeding initial state: {e}")
    finally:
        db.close()
    print("Database tables initialized successfully.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
