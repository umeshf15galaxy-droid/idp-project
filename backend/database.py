"""
database.py — SQLAlchemy ORM models + DB connection for IDP.

Supports:
  - SQLite for local development
  - PostgreSQL in production (set DATABASE_URL env var on Render)

Tables:
  - cities             : city metadata
  - population_history : historical + ETL-fetched population points
  - infrastructure     : current infrastructure baselines
  - predictions_cache  : pre-trained model results per city
  - etl_runs           : log of every ETL run
"""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, Float, String,
    DateTime, ForeignKey, Boolean, Text, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ── Connection ──────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # Local fallback: SQLite in the backend folder
    "sqlite:///" + os.path.join(os.path.dirname(__file__), "idp.db")
)

# Render gives postgres:// but SQLAlchemy 2.x needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Reconnect if connection drops
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── ORM Models ───────────────────────────────────────────────────

class City(Base):
    __tablename__ = "cities"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(64), unique=True, nullable=False, index=True)
    state      = Column(String(64))
    tier       = Column(String(8), default="tier2")   # tier1 | tier2
    latitude   = Column(Float, default=0.0)
    longitude  = Column(Float, default=0.0)
    area_km2   = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    population    = relationship("PopulationHistory", back_populates="city", cascade="all, delete")
    infrastructure = relationship("Infrastructure", back_populates="city", uselist=False, cascade="all, delete")
    predictions   = relationship("PredictionCache", back_populates="city", cascade="all, delete")


class PopulationHistory(Base):
    __tablename__ = "population_history"
    __table_args__ = (UniqueConstraint("city_id", "year", name="uq_city_year"),)

    id         = Column(Integer, primary_key=True)
    city_id    = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    year       = Column(Integer, nullable=False)
    population = Column(Float, nullable=False)
    source     = Column(String(32), default="csv")   # csv | worldbank | manual
    fetched_at = Column(DateTime, default=datetime.utcnow)

    city = relationship("City", back_populates="population")


class Infrastructure(Base):
    __tablename__ = "infrastructure"

    id         = Column(Integer, primary_key=True)
    city_id    = Column(Integer, ForeignKey("cities.id"), nullable=False, unique=True, index=True)
    schools    = Column(Integer, default=0)
    hospitals  = Column(Integer, default=0)
    buses      = Column(Integer, default=0)
    roads_km   = Column(Integer, default=0)
    pop_2025   = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    city = relationship("City", back_populates="infrastructure")


class PredictionCache(Base):
    __tablename__ = "predictions_cache"
    __table_args__ = (UniqueConstraint("city_id", "target_year", name="uq_city_target"),)

    id                   = Column(Integer, primary_key=True)
    city_id              = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    target_year          = Column(Integer, nullable=False)
    predicted_population = Column(Float)
    model_used           = Column(String(32))
    model_r2             = Column(Float)
    test_mape            = Column(Float)
    confidence_low       = Column(Float)
    confidence_high      = Column(Float)
    trained_at           = Column(DateTime, default=datetime.utcnow)
    pickle_path          = Column(String(256))  # path to saved .pkl model file

    city = relationship("City", back_populates="predictions")


class ETLRun(Base):
    __tablename__ = "etl_runs"

    id              = Column(Integer, primary_key=True)
    started_at      = Column(DateTime, default=datetime.utcnow)
    finished_at     = Column(DateTime)
    status          = Column(String(16), default="running")   # running | success | error
    source          = Column(String(32))                      # worldbank | csv | both
    cities_updated  = Column(Integer, default=0)
    records_added   = Column(Integer, default=0)
    error_message   = Column(Text)


# ── Helpers ──────────────────────────────────────────────────────

def get_db():
    """Dependency-injection helper for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables created/verified.")
