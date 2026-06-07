"""
trainer.py — Pre-trains ML models for all cities and caches them.

What it does:
  1. Loads population history for every city from the database (or CSV fallback).
  2. For each city, runs the full 5-model evaluation pipeline from predictor.py.
  3. Saves the winning model as a .pkl (pickle) file in backend/models/.
  4. Saves the training metadata (R2, MAPE, model used, trained_at) to the
     predictions_cache table in PostgreSQL.

Why pre-train?
  - Current system re-trains models on EVERY /predict API call (~2-3 seconds).
  - Pre-training brings response time down to <100ms (just loads the pickle).
  - Models are re-trained automatically by the weekly ETL scheduler.

Usage:
  python trainer.py            → train all cities for years 2030, 2040, 2050, 2060
  from trainer import train_all_cities → call programmatically
"""

import os
import pickle
import numpy as np
from datetime import datetime
from sqlalchemy.orm import Session

from database import SessionLocal, init_db, City, PopulationHistory, PredictionCache
from predictor import predict_population

# ── Config ────────────────────────────────────────────────────────

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Years to pre-train predictions for
TARGET_YEARS = [2030, 2035, 2040, 2045, 2050, 2055, 2060]


# ── Helpers ───────────────────────────────────────────────────────

def _get_city_population_from_db(db: Session, city_id: int):
    """Load sorted (year, population) pairs from the database."""
    records = (
        db.query(PopulationHistory)
        .filter(PopulationHistory.city_id == city_id)
        .order_by(PopulationHistory.year)
        .all()
    )
    years = [r.year for r in records]
    pops  = [r.population for r in records]
    return years, pops


def _save_model_pickle(city_name: str, target_year: int, prediction_result: dict) -> str:
    """
    Pickle the prediction result dict (includes model params and projection series).
    Returns the file path.
    """
    safe_name = city_name.lower().replace(" ", "_")
    filename  = f"{safe_name}_{target_year}.pkl"
    filepath  = os.path.join(MODELS_DIR, filename)
    with open(filepath, "wb") as f:
        pickle.dump(prediction_result, f)
    return filepath


def _load_model_pickle(city_name: str, target_year: int) -> dict | None:
    """Load a cached prediction from pickle. Returns None if not found."""
    safe_name = city_name.lower().replace(" ", "_")
    filepath  = os.path.join(MODELS_DIR, f"{safe_name}_{target_year}.pkl")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _upsert_prediction_cache(db: Session, city_id: int, target_year: int,
                              result: dict, pickle_path: str):
    """Insert or update a prediction cache record."""
    record = (
        db.query(PredictionCache)
        .filter_by(city_id=city_id, target_year=target_year)
        .first()
    )
    if record is None:
        record = PredictionCache(city_id=city_id, target_year=target_year)
        db.add(record)

    record.predicted_population = float(result["predicted_population"])
    record.model_used           = result["model_used"]
    record.model_r2             = float(result["model_r2"])
    record.test_mape            = float(result.get("test_mape", 0))
    record.confidence_low       = float(result["confidence"]["low"])
    record.confidence_high      = float(result["confidence"]["high"])
    record.trained_at           = datetime.utcnow()
    record.pickle_path          = pickle_path


# ── Main Training Function ────────────────────────────────────────

def train_city(city_name: str, city_id: int, db: Session, target_years=TARGET_YEARS) -> dict:
    """Train and cache models for a single city across all target years."""
    years, pops = _get_city_population_from_db(db, city_id)

    if len(years) < 4:
        return {"city": city_name, "status": "skipped", "reason": "insufficient data"}

    results = {}
    for target_year in target_years:
        try:
            result = predict_population(years, pops, target_year)

            # Save pickle
            pkl_path = _save_model_pickle(city_name, target_year, result)

            # Cache in DB
            _upsert_prediction_cache(db, city_id, target_year, result, pkl_path)

            results[target_year] = {
                "model": result["model_used"],
                "r2":    result["model_r2"],
                "mape":  result.get("test_mape"),
                "pred":  result["predicted_population"],
            }
            print(f"  ✓ {city_name} {target_year}: {result['model_used']} | "
                  f"R²={result['model_r2']:.3f} | MAPE={result.get('test_mape', 'N/A')}%")

        except Exception as e:
            results[target_year] = {"error": str(e)}
            print(f"  ✗ {city_name} {target_year}: ERROR — {e}")

    return {"city": city_name, "status": "trained", "years": results}


def train_all_cities(target_years=TARGET_YEARS) -> dict:
    """
    Train models for ALL cities in the database.
    Called on startup and by the weekly scheduler.
    """
    init_db()
    db = SessionLocal()

    try:
        cities = db.query(City).all()
        if not cities:
            return {"status": "error", "error": "No cities found in database. Run ETL first."}

        print(f"[Trainer] Training {len(cities)} cities × {len(target_years)} target years...")
        start    = datetime.utcnow()
        reports  = []

        for city in cities:
            print(f"\n[Trainer] → {city.name}")
            report = train_city(city.name, city.id, db, target_years)
            reports.append(report)

        db.commit()
        elapsed = (datetime.utcnow() - start).total_seconds()
        trained = sum(1 for r in reports if r["status"] == "trained")

        print(f"\n[Trainer] Done. {trained}/{len(cities)} cities trained in {elapsed:.1f}s")
        return {
            "status":        "success",
            "cities_trained": trained,
            "elapsed_sec":   round(elapsed, 1),
            "trained_at":    datetime.utcnow().isoformat(),
            "reports":       reports,
        }

    except Exception as e:
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def get_cached_prediction(city_name: str, target_year: int) -> dict | None:
    """
    Try to load a pre-trained prediction from pickle cache.
    Returns None if not cached (caller should fall back to live prediction).
    """
    return _load_model_pickle(city_name, target_year)


def get_training_status() -> dict:
    """Return summary of the last training run from the database."""
    db = SessionLocal()
    try:
        total_cities     = db.query(City).count()
        cached_entries   = db.query(PredictionCache).count()
        latest_train     = (
            db.query(PredictionCache)
            .order_by(PredictionCache.trained_at.desc())
            .first()
        )
        return {
            "total_cities":    total_cities,
            "cached_entries":  cached_entries,
            "last_trained_at": latest_train.trained_at.isoformat() if latest_train else None,
            "pickle_dir":      MODELS_DIR,
            "target_years":    TARGET_YEARS,
        }
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting full training run...")
    result = train_all_cities()
    print("\nSummary:", result["status"],
          f"| {result.get('cities_trained')} cities | {result.get('elapsed_sec')}s")
