from shared_python import sqlite_tuning
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./gifts.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
sqlite_tuning.tune(engine)  # WAL, a 5 s busy timeout and a lighter sync on every connection - see shared_python/sqlite_tuning.py
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
