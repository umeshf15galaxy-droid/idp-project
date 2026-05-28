"""
main.py — FastAPI Application Entry Point for IDP.

Security hardening v2:
  - Rate limiting via slowapi (10 req/min on predict, 60/min on reads)
  - CORS restricted to known origins only
  - Input validation tightened
  - /health endpoint for uptime monitors
"""

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from data_loader import list_cities, get_city_summary, get_city_population, get_city_infrastructure
from predictor import predict_population
from infrastructure import full_analysis

# ─────────────────────────────────────────────
# Rate limiter setup
# ─────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/hour"])

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

app = FastAPI(
    title="Urban Infrastructure Prediction System",
    description="AI-powered population forecasting and infrastructure planning for Indian cities.",
    version="2.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─────────────────────────────────────────────
# CORS — only allow known trusted origins
# ─────────────────────────────────────────────

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    # Vercel production domains (adjust if your Vercel URL is different)
    "https://idp-project.vercel.app",
    "https://idp-project-git-main.vercel.app",
    # Allow any *.vercel.app subdomain (covers preview deployments)
    "https://*.vercel.app",
]

# In development or if ALLOW_ALL_ORIGINS env var is set, allow all
if os.getenv("ALLOW_ALL_ORIGINS", "false").lower() == "true":
    ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",  # covers all Vercel preview URLs
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class CurrentInfrastructure(BaseModel):
    schools:   Optional[int] = Field(None, ge=0, le=1_000_000)
    hospitals: Optional[int] = Field(None, ge=0, le=100_000)
    buses:     Optional[int] = Field(None, ge=0, le=500_000)
    roads_km:  Optional[int] = Field(None, ge=0, le=1_000_000)


class PredictRequest(BaseModel):
    city:        str = Field(..., min_length=2, max_length=64, example="Bangalore")
    target_year: int = Field(..., ge=2026, le=2060, example=2040)
    current_infrastructure: Optional[CurrentInfrastructure] = None


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "project": "Urban Infrastructure Prediction System",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    """Uptime monitor endpoint — keeps Render free tier from sleeping."""
    return {"status": "ok"}


@app.get("/cities", tags=["Data"])
@limiter.limit("60/minute")
def get_cities(request: Request):
    """Return all cities available in the dataset."""
    cities = list_cities()
    return {"cities": cities, "count": len(cities)}


@app.get("/city/{city_name}", tags=["Data"])
@limiter.limit("30/minute")
def get_city(city_name: str, request: Request):
    """Return historical population + current infrastructure for a city."""
    if len(city_name) > 64:
        raise HTTPException(status_code=400, detail="City name too long.")
    try:
        summary = get_city_summary(city_name)
        return summary
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/predict", tags=["Prediction"])
@limiter.limit("10/minute")
def predict(req: PredictRequest, request: Request):
    """
    Core prediction endpoint — rate limited to 10 requests/minute per IP.
    Uses multi-model AI selection with 80/20 train/test validation.
    """
    try:
        # ── Validate city name is safe ──
        safe_city = req.city.strip()
        if not safe_city.replace(" ", "").replace("-", "").isalpha():
            raise HTTPException(status_code=400, detail="Invalid city name.")

        # ── Load historical data ──
        pop_df = get_city_population(safe_city)
        infra  = get_city_infrastructure(safe_city)

        historical_years = pop_df["year"].tolist()
        historical_pops  = pop_df["population"].tolist()

        # ── Merge current infra: CSV defaults overridden by user input ──
        current_infra = {
            "schools":   int(infra.get("schools",   0)),
            "hospitals": int(infra.get("hospitals", 0)),
            "buses":     int(infra.get("buses",     0)),
            "roads_km":  int(infra.get("roads_km",  0)),
        }
        if req.current_infrastructure:
            override = req.current_infrastructure.model_dump(exclude_none=True)
            current_infra.update(override)

        # ── Run AI prediction ──
        prediction = predict_population(historical_years, historical_pops, req.target_year)

        # ── Run infrastructure analysis ──
        infra_analysis = full_analysis(
            prediction["predicted_population"],
            current_infra,
            city_tier=_get_city_tier(safe_city),
        )

        # ── Build historical series for charts ──
        historical_series = [
            {"year": int(y), "population": int(p)}
            for y, p in zip(historical_years, historical_pops)
        ]

        # ── Derived metrics ──
        base_pop    = float(historical_pops[-1])
        pred_pop    = float(prediction["predicted_population"])
        years_ahead = prediction["years_ahead"]
        area_km2    = float(infra.get("area_km2", 0)) or 1.0

        cagr = round(((pred_pop / base_pop) ** (1 / max(years_ahead, 1)) - 1) * 100, 2) if base_pop > 0 else 0.0
        density_predicted = round(pred_pop / area_km2)
        density_current   = round(base_pop / area_km2)

        # ── Forecast reliability warning ──
        forecast_warnings = []
        if years_ahead > 20:
            forecast_warnings.append({
                "type": "info",
                "message": f"⚠️ Forecasting {years_ahead} years ahead — uncertainty increases significantly beyond 20 years.",
            })
        if prediction.get("model_used") == "compound_growth":
            forecast_warnings.append({
                "type": "warning",
                "message": "⚠️ All ML models failed validation — using historical growth rate as fallback.",
            })

        return {
            "city":        req.city,
            "state":       infra.get("state", ""),
            "area_km2":    float(infra.get("area_km2", 0)),
            "latitude":    float(infra.get("latitude", 0.0)),
            "longitude":   float(infra.get("longitude", 0.0)),
            "target_year": req.target_year,

            # AI prediction
            "predicted_population": prediction["predicted_population"],
            "base_population":      int(base_pop),
            "model_used":           prediction["model_used"],
            "model_r2":             prediction["model_r2"],
            "test_mape":            prediction.get("test_mape", None),
            "years_ahead":          years_ahead,
            "all_models":           prediction["all_models"],
            "confidence":           prediction["confidence"],
            "train_size":           prediction.get("train_size"),
            "test_size":            prediction.get("test_size"),

            # Derived metrics
            "cagr":              cagr,
            "density_current":   density_current,
            "density_predicted": density_predicted,

            # Infrastructure
            "current_infrastructure":  current_infra,
            "required_infrastructure": infra_analysis["required"],
            "deficit":                 infra_analysis["deficit"],
            "deficit_pct":             infra_analysis["deficit_pct"],
            "warnings":                infra_analysis["warnings"] + forecast_warnings,
            "norms_used":              infra_analysis["norms_used"],
            "demographics":            infra_analysis["demographics"],
            "segment_info":            infra_analysis["segment_info"],
            "city_tier":               infra_analysis["city_tier"],

            # Chart data
            "historical_series":  historical_series,
            "projection_series":  prediction["projection_series"],
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

# Cities classified as Tier 1 metros — higher infrastructure density norms
_TIER1 = {"delhi", "mumbai", "kolkata", "bangalore", "chennai", "hyderabad"}

def _get_city_tier(city: str) -> str:
    return "tier1" if city.lower() in _TIER1 else "tier2"
