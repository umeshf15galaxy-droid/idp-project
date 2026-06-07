"""
main.py — FastAPI Application Entry Point for IDP v3.0.

New in v3.0:
  - PostgreSQL database integration
  - ETL pipeline endpoints (GET /etl/status, POST /etl/run)
  - ML model training endpoints (GET /models/status, POST /models/train)
  - /predict now uses pre-trained cached models (fast) with live fallback
  - APScheduler runs ETL + training weekly automatically

Endpoints:
  GET  /              → health check
  GET  /health        → uptime monitor ping
  GET  /cities        → list all cities
  GET  /city/{name}   → city history + current infrastructure
  POST /predict       → AI prediction (cached if available)
  GET  /etl/status    → last ETL run info
  POST /etl/run       → manually trigger ETL pipeline
  GET  /models/status → training cache info
  POST /models/train  → manually trigger model retraining
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from data_loader import list_cities, get_city_summary, get_city_population, get_city_infrastructure
from predictor import predict_population
from infrastructure import full_analysis
from etl import run_etl, get_etl_status
from trainer import train_all_cities, get_cached_prediction, get_training_status
from database import init_db


# ── Rate limiter ──────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/hour"])


# ── Startup / Shutdown ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup: initialise DB, seed from CSV/API, pre-train models."""
    print("[Startup] Initialising database...")
    init_db()

    print("[Startup] Running ETL seed...")
    etl_result = run_etl()
    print(f"[Startup] ETL done: {etl_result['status']}")

    print("[Startup] Pre-training ML models...")
    train_result = train_all_cities()
    print(f"[Startup] Training done: {train_result.get('cities_trained', 0)} cities")

    # ── Weekly scheduler ──
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(run_etl,          "cron", day_of_week="sun", hour=2, minute=0)
        scheduler.add_job(train_all_cities, "cron", day_of_week="sun", hour=2, minute=30)
        scheduler.start()
        print("[Startup] Scheduler started — ETL + training every Sunday 2:00 / 2:30 UTC")
    except Exception as e:
        print(f"[Startup] Scheduler warning: {e}")

    yield  # ← app runs here


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Urban Infrastructure Prediction System",
    description="AI-powered population forecasting and infrastructure planning for Indian cities.",
    version="3.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)


# ── Request / Response Models ─────────────────────────────────────

class CurrentInfrastructure(BaseModel):
    schools:   Optional[int] = Field(None, ge=0, le=1_000_000)
    hospitals: Optional[int] = Field(None, ge=0, le=100_000)
    buses:     Optional[int] = Field(None, ge=0, le=500_000)
    roads_km:  Optional[int] = Field(None, ge=0, le=1_000_000)


class PredictRequest(BaseModel):
    city:        str = Field(..., min_length=2, max_length=64, example="Bangalore")
    target_year: int = Field(..., ge=2026, le=2060, example=2040)
    current_infrastructure: Optional[CurrentInfrastructure] = None


# ── Routes ────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "status":  "online",
        "project": "Urban Infrastructure Prediction System",
        "version": "3.0.0",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    """Uptime monitor endpoint — prevents Render free tier from sleeping."""
    return {"status": "ok"}


@app.get("/cities", tags=["Data"])
@limiter.limit("60/minute")
def get_cities(request: Request):
    cities = list_cities()
    return {"cities": cities, "count": len(cities)}


@app.get("/city/{city_name}", tags=["Data"])
@limiter.limit("30/minute")
def get_city(city_name: str, request: Request):
    if len(city_name) > 64:
        raise HTTPException(status_code=400, detail="City name too long.")
    try:
        return get_city_summary(city_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/predict", tags=["Prediction"])
@limiter.limit("10/minute")
def predict(req: PredictRequest, request: Request):
    """
    AI prediction endpoint. Tries cached pre-trained model first (fast <100ms),
    falls back to live training if no cache exists.
    """
    try:
        safe_city = req.city.strip()

        # ── 1. Try cached prediction (pickle from trainer) ──
        cached = get_cached_prediction(safe_city, req.target_year)
        if cached is not None:
            prediction   = cached
            cache_source = "cached"
        else:
            # ── 2. Live prediction fallback ──
            pop_df = get_city_population(safe_city)
            prediction = predict_population(
                pop_df["year"].tolist(),
                pop_df["population"].tolist(),
                req.target_year,
            )
            cache_source = "live"

        # ── Infrastructure ──
        infra = get_city_infrastructure(safe_city)
        current_infra = {
            "schools":   int(infra.get("schools",   0)),
            "hospitals": int(infra.get("hospitals", 0)),
            "buses":     int(infra.get("buses",     0)),
            "roads_km":  int(infra.get("roads_km",  0)),
        }
        if req.current_infrastructure:
            override = req.current_infrastructure.model_dump(exclude_none=True)
            current_infra.update(override)

        infra_analysis = full_analysis(
            prediction["predicted_population"],
            current_infra,
            city_tier=_get_city_tier(safe_city),
        )

        # ── Historical series ──
        pop_df = get_city_population(safe_city)
        historical_series = [
            {"year": int(y), "population": int(p)}
            for y, p in zip(pop_df["year"].tolist(), pop_df["population"].tolist())
        ]

        # ── Derived metrics ──
        base_pop    = float(pop_df["population"].iloc[-1])
        pred_pop    = float(prediction["predicted_population"])
        years_ahead = prediction["years_ahead"]
        area_km2    = float(infra.get("area_km2", 0)) or 1.0

        cagr              = round(((pred_pop / base_pop) ** (1 / max(years_ahead, 1)) - 1) * 100, 2) if base_pop > 0 else 0.0
        density_current   = round(base_pop / area_km2)
        density_predicted = round(pred_pop / area_km2)

        # ── Forecast warnings ──
        forecast_warnings = []
        if years_ahead > 20:
            forecast_warnings.append({
                "type":    "info",
                "message": f"⚠️ Forecasting {years_ahead} years ahead — uncertainty increases beyond 20 years.",
            })
        if prediction.get("model_used") == "compound_growth":
            forecast_warnings.append({
                "type":    "warning",
                "message": "⚠️ All ML models failed validation — using historical CAGR as fallback.",
            })

        return {
            "city":        req.city,
            "state":       infra.get("state", ""),
            "area_km2":    float(infra.get("area_km2", 0)),
            "latitude":    float(infra.get("latitude", 0.0)),
            "longitude":   float(infra.get("longitude", 0.0)),
            "target_year": req.target_year,
            "data_source": cache_source,  # "cached" | "live"

            "predicted_population": prediction["predicted_population"],
            "base_population":      int(base_pop),
            "model_used":           prediction["model_used"],
            "model_r2":             prediction["model_r2"],
            "test_mape":            prediction.get("test_mape"),
            "years_ahead":          years_ahead,
            "all_models":           prediction["all_models"],
            "confidence":           prediction["confidence"],
            "train_size":           prediction.get("train_size"),
            "test_size":            prediction.get("test_size"),

            "cagr":              cagr,
            "density_current":   density_current,
            "density_predicted": density_predicted,

            "current_infrastructure":  current_infra,
            "required_infrastructure": infra_analysis["required"],
            "deficit":                 infra_analysis["deficit"],
            "deficit_pct":             infra_analysis["deficit_pct"],
            "warnings":                infra_analysis["warnings"] + forecast_warnings,
            "norms_used":              infra_analysis["norms_used"],
            "demographics":            infra_analysis["demographics"],
            "segment_info":            infra_analysis["segment_info"],
            "city_tier":               infra_analysis["city_tier"],

            "historical_series":  historical_series,
            "projection_series":  prediction["projection_series"],
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")


# ── ETL Endpoints ─────────────────────────────────────────────────

@app.get("/etl/status", tags=["ETL"])
def etl_status(request: Request):
    """Return the status and timestamp of the last ETL run."""
    return get_etl_status()


@app.post("/etl/run", tags=["ETL"])
@limiter.limit("3/hour")
def etl_run(request: Request, background_tasks: BackgroundTasks):
    """
    Manually trigger the ETL pipeline.
    Runs in the background so the HTTP response returns immediately.
    Rate limited to 3 calls/hour to prevent abuse.
    """
    background_tasks.add_task(run_etl)
    return {"status": "started", "message": "ETL pipeline triggered in background."}


# ── Model Training Endpoints ──────────────────────────────────────

@app.get("/models/status", tags=["ML"])
def models_status(request: Request):
    """Return training metadata — when trained, accuracy stats."""
    return get_training_status()


@app.post("/models/train", tags=["ML"])
@limiter.limit("2/hour")
def models_train(request: Request, background_tasks: BackgroundTasks):
    """
    Manually trigger model retraining for all cities.
    Runs in the background.
    Rate limited to 2 calls/hour.
    """
    background_tasks.add_task(train_all_cities)
    return {"status": "started", "message": "Model training triggered in background."}


# ── Helpers ───────────────────────────────────────────────────────

_TIER1 = {"delhi", "mumbai", "kolkata", "bangalore", "chennai", "hyderabad"}

def _get_city_tier(city: str) -> str:
    return "tier1" if city.lower() in _TIER1 else "tier2"
