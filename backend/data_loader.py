"""
data_loader.py — Loads city data from PostgreSQL DB with CSV fallback.

Priority:
  1. PostgreSQL database (populated by ETL pipeline)
  2. Static CSV files (always available as fallback)

This ensures the API always works even if the DB is empty or unreachable.
"""

import os
import pandas as pd
from functools import lru_cache

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(BASE_DIR, "data")


# ── CSV Loaders (Fallback) ────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_csv_population() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, "population.csv")
    df   = pd.read_csv(path)
    df.columns      = df.columns.str.strip().str.lower()
    df["year"]       = df["year"].astype(int)
    df["population"] = df["population"].astype(float)
    df["city"]       = df["city"].str.strip()
    return df


@lru_cache(maxsize=1)
def _load_csv_infrastructure() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, "infrastructure.csv")
    df   = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    df["city"] = df["city"].str.strip()
    return df


# ── DB Loaders ────────────────────────────────────────────────────

def _db_is_ready() -> bool:
    """Check if the database has been seeded with city data."""
    try:
        from database import SessionLocal, City
        db    = SessionLocal()
        count = db.query(City).count()
        db.close()
        return count > 0
    except Exception:
        return False


def _load_db_population(city: str) -> pd.DataFrame | None:
    """Load population history from PostgreSQL for a city."""
    try:
        from database import SessionLocal, City, PopulationHistory
        db      = SessionLocal()
        city_obj = db.query(City).filter(City.name.ilike(city.strip())).first()
        if city_obj is None:
            db.close()
            return None
        records = (
            db.query(PopulationHistory)
            .filter(PopulationHistory.city_id == city_obj.id)
            .order_by(PopulationHistory.year)
            .all()
        )
        db.close()
        if not records:
            return None
        return pd.DataFrame([{"year": r.year, "population": r.population} for r in records])
    except Exception:
        return None


def _load_db_infrastructure(city: str) -> dict | None:
    """Load infrastructure data from PostgreSQL for a city."""
    try:
        from database import SessionLocal, City, Infrastructure
        db       = SessionLocal()
        city_obj = db.query(City).filter(City.name.ilike(city.strip())).first()
        if city_obj is None or city_obj.infrastructure is None:
            db.close()
            return None
        infra = city_obj.infrastructure
        result = {
            "city":            city_obj.name,
            "state":           city_obj.state,
            "area_km2":        city_obj.area_km2,
            "latitude":        city_obj.latitude,
            "longitude":       city_obj.longitude,
            "schools":         infra.schools,
            "hospitals":       infra.hospitals,
            "buses":           infra.buses,
            "roads_km":        infra.roads_km,
            "population_2025": infra.pop_2025,
        }
        db.close()
        return result
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────

def list_cities() -> list[str]:
    """Return all available city names (DB preferred, CSV fallback)."""
    if _db_is_ready():
        try:
            from database import SessionLocal, City
            db     = SessionLocal()
            cities = [c.name for c in db.query(City).order_by(City.name).all()]
            db.close()
            if cities:
                return cities
        except Exception:
            pass
    df = _load_csv_population()
    return sorted(df["city"].unique().tolist())


def get_city_population(city: str) -> pd.DataFrame:
    """Return sorted population history for a city (DB preferred, CSV fallback)."""
    # Try DB first
    if _db_is_ready():
        df = _load_db_population(city)
        if df is not None:
            return df.sort_values("year").reset_index(drop=True)

    # CSV fallback
    df      = _load_csv_population()
    city_df = df[df["city"].str.lower() == city.strip().lower()].copy()
    if city_df.empty:
        raise ValueError(f"City '{city}' not found. Available: {list_cities()}")
    return city_df.sort_values("year").reset_index(drop=True)


def get_city_infrastructure(city: str) -> dict:
    """Return current infrastructure dict for a city (DB preferred, CSV fallback)."""
    # Try DB first
    if _db_is_ready():
        infra = _load_db_infrastructure(city)
        if infra is not None:
            return infra

    # CSV fallback
    df  = _load_csv_infrastructure()
    row = df[df["city"].str.lower() == city.strip().lower()]
    if row.empty:
        raise ValueError(f"Infrastructure data not found for city '{city}'.")
    return row.iloc[0].to_dict()


def get_city_summary(city: str) -> dict:
    """Return combined population history + infrastructure for a city."""
    pop_df = get_city_population(city)
    infra  = get_city_infrastructure(city)
    return {
        "city":        city,
        "state":       infra.get("state", ""),
        "area_km2":    float(infra.get("area_km2", 0)),
        "historical_population": [
            {"year": int(r["year"]), "population": int(r["population"])}
            for _, r in pop_df.iterrows()
        ],
        "current_infrastructure": {
            "schools":   int(infra.get("schools", 0)),
            "hospitals": int(infra.get("hospitals", 0)),
            "buses":     int(infra.get("buses", 0)),
            "roads_km":  int(infra.get("roads_km", 0)),
        },
        "current_population": int(infra.get("population_2025", 0)),
        "latitude":    float(infra.get("latitude", 0.0)),
        "longitude":   float(infra.get("longitude", 0.0)),
        "source":      "database" if _db_is_ready() else "csv",
    }
