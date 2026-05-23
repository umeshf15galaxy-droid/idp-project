"""
data_loader.py — Loads and caches CSV data for IDP backend.
Handles population history and infrastructure baselines.
"""

import os
import pandas as pd
from functools import lru_cache

# Resolve paths relative to this file so it works from any working directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


@lru_cache(maxsize=1)
def load_population() -> pd.DataFrame:
    """Load historical population CSV. Cached after first load."""
    path = os.path.join(DATA_DIR, "population.csv")
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    df["year"] = df["year"].astype(int)
    df["population"] = df["population"].astype(float)
    df["city"] = df["city"].str.strip()
    return df


@lru_cache(maxsize=1)
def load_infrastructure() -> pd.DataFrame:
    """Load infrastructure baseline CSV. Cached after first load."""
    path = os.path.join(DATA_DIR, "infrastructure.csv")
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    df["city"] = df["city"].str.strip()
    return df


def get_city_population(city: str) -> pd.DataFrame:
    """Return sorted population history for a specific city."""
    df = load_population()
    city_df = df[df["city"].str.lower() == city.strip().lower()].copy()
    if city_df.empty:
        raise ValueError(f"City '{city}' not found in dataset. Available cities: {list_cities()}")
    return city_df.sort_values("year").reset_index(drop=True)


def get_city_infrastructure(city: str) -> dict:
    """Return current infrastructure dict for a city."""
    df = load_infrastructure()
    row = df[df["city"].str.lower() == city.strip().lower()]
    if row.empty:
        raise ValueError(f"Infrastructure data not found for city '{city}'.")
    record = row.iloc[0].to_dict()
    return record


def list_cities() -> list[str]:
    """Return all available city names."""
    df = load_population()
    return sorted(df["city"].unique().tolist())


def get_city_summary(city: str) -> dict:
    """Return combined population history + infrastructure for a city."""
    pop_df = get_city_population(city)
    infra = get_city_infrastructure(city)
    return {
        "city": city,
        "state": infra.get("state", ""),
        "area_km2": float(infra.get("area_km2", 0)),
        "historical_population": [
            {"year": int(r["year"]), "population": int(r["population"])}
            for _, r in pop_df.iterrows()
        ],
        "current_infrastructure": {
            "schools": int(infra.get("schools", 0)),
            "hospitals": int(infra.get("hospitals", 0)),
            "buses": int(infra.get("buses", 0)),
            "roads_km": int(infra.get("roads_km", 0)),
        },
        "current_population": int(infra.get("population_2025", 0)),
        "latitude": float(infra.get("latitude", 0.0)),
        "longitude": float(infra.get("longitude", 0.0)),
    }
