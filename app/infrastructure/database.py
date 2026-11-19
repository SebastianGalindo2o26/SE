import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


load_dotenv()


def secure_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgresql+psycopg://"):
        mode = make_url(raw_url).query.get("sslmode")
        if mode not in ("require", "verify-ca", "verify-full"):
            raise ValueError("PostgreSQL requiere sslmode=require (o verify-ca/verify-full) en DATABASE_URL.")
    return raw_url


DATABASE_URL = secure_database_url(os.getenv("DATABASE_URL", "sqlite:///./api_expert.db"))
engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
