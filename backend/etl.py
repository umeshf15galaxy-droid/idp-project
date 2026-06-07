"""
etl.py — Extract, Transform, Load Pipeline for IDP.

Sources (in order of priority):
  1. World Bank API — free, global urban agglomeration data
     Endpoint: https://api.worldbank.org/v2/country/IND/indicator/SP.URB.TOTL
  2. CSV files     — existing curated data (fallback if API unreachable)

Runs automatically via APScheduler every Sunday at 2am UTC.
Can also be triggered manually via POST /etl/run.

Process:
  Extract  → Fetch raw data from World Bank JSON API
  Transform → Normalize city names, convert thousands → millions, filter India
  Load     → Upsert into PostgreSQL via SQLAlchemy ORM
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from database import (
    SessionLocal, init_db,
    City, PopulationHistory, Infrastructure, ETLRun,
)

# ── Config ───────────────────────────────────────────────────────

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(BASE_DIR, "data")

# World Bank API for India urban agglomeration populations
WB_BASE   = "https://api.worldbank.org/v2"
WB_INDICATOR = "SP.URB.TOTL"  # Urban population (all India agglomerations)

REQUEST_TIMEOUT = 10   # seconds

# Mapping of our city names → World Bank city search strings
# World Bank doesn't have individual city-level API; we use country-level
# and supplement from the curated CSV which is our ground truth.
CITY_METADATA = {
    "Delhi":         {"state": "Delhi",         "tier": "tier1", "lat": 28.6139, "lon": 77.2090, "area": 1484},
    "Mumbai":        {"state": "Maharashtra",   "tier": "tier1", "lat": 19.0760, "lon": 72.8777, "area": 603},
    "Bangalore":     {"state": "Karnataka",     "tier": "tier1", "lat": 12.9716, "lon": 77.5946, "area": 741},
    "Kolkata":       {"state": "West Bengal",   "tier": "tier1", "lat": 22.5726, "lon": 88.3639, "area": 205},
    "Chennai":       {"state": "Tamil Nadu",    "tier": "tier1", "lat": 13.0827, "lon": 80.2707, "area": 426},
    "Hyderabad":     {"state": "Telangana",     "tier": "tier1", "lat": 17.3850, "lon": 78.4867, "area": 650},
    "Ahmedabad":     {"state": "Gujarat",       "tier": "tier2", "lat": 23.0225, "lon": 72.5714, "area": 464},
    "Pune":          {"state": "Maharashtra",   "tier": "tier2", "lat": 18.5204, "lon": 73.8567, "area": 331},
    "Surat":         {"state": "Gujarat",       "tier": "tier2", "lat": 21.1702, "lon": 72.8311, "area": 326},
    "Jaipur":        {"state": "Rajasthan",     "tier": "tier2", "lat": 26.9124, "lon": 75.7873, "area": 485},
    "Lucknow":       {"state": "Uttar Pradesh", "tier": "tier2", "lat": 26.8467, "lon": 80.9462, "area": 349},
    "Kanpur":        {"state": "Uttar Pradesh", "tier": "tier2", "lat": 26.4499, "lon": 80.3319, "area": 403},
    "Nagpur":        {"state": "Maharashtra",   "tier": "tier2", "lat": 21.1458, "lon": 79.0882, "area": 227},
    "Indore":        {"state": "Madhya Pradesh","tier": "tier2", "lat": 22.7196, "lon": 75.8577, "area": 530},
    "Visakhapatnam": {"state": "Andhra Pradesh","tier": "tier2", "lat": 17.6868, "lon": 83.2185, "area": 682},
}


# ── ETL Functions ─────────────────────────────────────────────────

def _fetch_worldbank_india_urban():
    """
    Fetch India urban population total from World Bank API.
    Returns a dict of {year: total_india_urban_pop} or empty dict on failure.
    """
    url = f"{WB_BASE}/country/IND/indicator/{WB_INDICATOR}?format=json&per_page=100"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # World Bank returns [metadata_page, [records_list]]
        if len(data) < 2 or not data[1]:
            return {}
        records = {
            int(item["date"]): float(item["value"])
            for item in data[1]
            if item.get("value") is not None
        }
        return records
    except Exception as e:
        print(f"[ETL] World Bank API failed: {e}")
        return {}


def _load_csv_population():
    """Load population data from the existing curated CSV."""
    path = os.path.join(DATA_DIR, "population.csv")
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    df["year"]       = df["year"].astype(int)
    df["population"] = df["population"].astype(float)
    df["city"]       = df["city"].str.strip()
    return df


def _load_csv_infrastructure():
    """Load infrastructure data from the existing curated CSV."""
    path = os.path.join(DATA_DIR, "infrastructure.csv")
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    df["city"] = df["city"].str.strip()
    return df


def _upsert_city(db: Session, city_name: str) -> City:
    """Get or create a City record."""
    city = db.query(City).filter(City.name == city_name).first()
    if city is None:
        meta = CITY_METADATA.get(city_name, {})
        city = City(
            name      = city_name,
            state     = meta.get("state", ""),
            tier      = meta.get("tier", "tier2"),
            latitude  = meta.get("lat", 0.0),
            longitude = meta.get("lon", 0.0),
            area_km2  = meta.get("area", 0.0),
        )
        db.add(city)
        db.flush()
    return city


def _upsert_population(db: Session, city_id: int, year: int, pop: float, source: str):
    """Insert or update a population record."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    record = db.query(PopulationHistory).filter_by(city_id=city_id, year=year).first()
    if record is None:
        record = PopulationHistory(
            city_id=city_id, year=year, population=pop, source=source, fetched_at=datetime.utcnow()
        )
        db.add(record)
        return True  # new record
    else:
        if abs(record.population - pop) / max(pop, 1) > 0.01:  # >1% change
            record.population  = pop
            record.source      = source
            record.fetched_at  = datetime.utcnow()
        return False  # existing


def _upsert_infrastructure(db: Session, city_id: int, row: dict):
    """Insert or update infrastructure for a city."""
    infra = db.query(Infrastructure).filter_by(city_id=city_id).first()
    if infra is None:
        infra = Infrastructure(
            city_id   = city_id,
            schools   = int(row.get("schools", 0)),
            hospitals = int(row.get("hospitals", 0)),
            buses     = int(row.get("buses", 0)),
            roads_km  = int(row.get("roads_km", 0)),
            pop_2025  = float(row.get("population_2025", 0)),
        )
        db.add(infra)
    else:
        infra.schools   = int(row.get("schools", infra.schools))
        infra.hospitals = int(row.get("hospitals", infra.hospitals))
        infra.buses     = int(row.get("buses", infra.buses))
        infra.roads_km  = int(row.get("roads_km", infra.roads_km))
        infra.pop_2025  = float(row.get("population_2025", infra.pop_2025))
        infra.updated_at = datetime.utcnow()


# ── Main ETL Entry Point ──────────────────────────────────────────

def run_etl() -> dict:
    """
    Full ETL run: load from World Bank API + CSV, store in PostgreSQL.
    Returns a status report dict.
    """
    init_db()  # Ensure all tables exist
    db = SessionLocal()
    etl_log = ETLRun(started_at=datetime.utcnow(), status="running")
    db.add(etl_log)
    db.commit()

    cities_updated = 0
    records_added  = 0
    source_used    = []

    try:
        # ── Step 1: Try World Bank API ──
        wb_data = _fetch_worldbank_india_urban()
        if wb_data:
            source_used.append("worldbank")
            print(f"[ETL] World Bank returned {len(wb_data)} national data points.")
            # Note: World Bank gives *national* urban total, not per-city.
            # We use it as a sanity-check cross-reference, not direct city data.
        else:
            print("[ETL] World Bank API unavailable. Using CSV only.")

        # ── Step 2: Load CSV (ground truth for city-level data) ──
        pop_csv   = _load_csv_population()
        infra_csv = _load_csv_infrastructure()
        source_used.append("csv")

        # ── Step 3: Upsert cities + population ──
        for city_name in pop_csv["city"].unique():
            city_rows = pop_csv[pop_csv["city"] == city_name].sort_values("year")
            city      = _upsert_city(db, city_name)

            for _, row in city_rows.iterrows():
                added = _upsert_population(db, city.id, int(row["year"]), float(row["population"]), "csv")
                if added:
                    records_added += 1

            # If World Bank gave us national data, we could interpolate future
            # city-level estimates here using each city's historical share.
            if wb_data:
                # Calculate this city's average share of India's urban population
                india_total_2020 = wb_data.get(2020, None)
                city_2020_pop    = city_rows[city_rows["year"] == 2020]["population"]
                if india_total_2020 and not city_2020_pop.empty:
                    city_share = float(city_2020_pop.iloc[0]) / india_total_2020
                    # If WB has 2024 data newer than our CSV
                    for wb_year in sorted(wb_data.keys()):
                        if wb_year > city_rows["year"].max() and wb_year <= 2025:
                            est_pop = wb_data[wb_year] * city_share
                            added   = _upsert_population(db, city.id, wb_year, est_pop, "worldbank")
                            if added:
                                records_added += 1

            cities_updated += 1

        # ── Step 4: Upsert infrastructure ──
        for _, row in infra_csv.iterrows():
            city = db.query(City).filter(City.name == row["city"]).first()
            if city:
                _upsert_infrastructure(db, city.id, row.to_dict())

        db.commit()

        # ── Update ETL log ──
        etl_log.status         = "success"
        etl_log.finished_at    = datetime.utcnow()
        etl_log.source         = "+".join(source_used)
        etl_log.cities_updated = cities_updated
        etl_log.records_added  = records_added
        db.commit()

        return {
            "status":         "success",
            "source":         "+".join(source_used),
            "cities_updated": cities_updated,
            "records_added":  records_added,
            "worldbank_used": bool(wb_data),
            "finished_at":    etl_log.finished_at.isoformat(),
        }

    except Exception as e:
        db.rollback()
        etl_log.status        = "error"
        etl_log.finished_at   = datetime.utcnow()
        etl_log.error_message = str(e)
        db.commit()
        print(f"[ETL] Error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def get_etl_status() -> dict:
    """Return the most recent ETL run status."""
    db = SessionLocal()
    try:
        last = db.query(ETLRun).order_by(ETLRun.started_at.desc()).first()
        if last is None:
            return {"status": "never_run", "last_run": None}
        return {
            "status":         last.status,
            "source":         last.source,
            "cities_updated": last.cities_updated,
            "records_added":  last.records_added,
            "last_run":       last.finished_at.isoformat() if last.finished_at else None,
            "error":          last.error_message,
        }
    finally:
        db.close()


if __name__ == "__main__":
    print("Running ETL pipeline...")
    result = run_etl()
    print("Result:", result)
