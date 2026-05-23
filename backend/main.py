"""
main.py — FastAPI Application Entry Point for IDP.

Endpoints:
  GET  /              → health check
  GET  /cities        → list all cities
  GET  /city/{name}   → city history + current infrastructure
  POST /predict       → full AI prediction + infrastructure analysis
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from data_loader import list_cities, get_city_summary, get_city_population, get_city_infrastructure
from predictor import predict_population
from infrastructure import full_analysis

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

app = FastAPI(
    title="Urban Infrastructure Prediction System",
    description="AI-powered population forecasting and infrastructure planning for Indian cities.",
    version="1.0.0",
)

# Allow frontend (localhost:3000) to call backend (localhost:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class CurrentInfrastructure(BaseModel):
    schools:   Optional[int] = None
    hospitals: Optional[int] = None
    buses:     Optional[int] = None
    roads_km:  Optional[int] = None


class PredictRequest(BaseModel):
    city:        str = Field(..., example="Bangalore")
    target_year: int = Field(..., ge=2025, le=2060, example=2040)
    current_infrastructure: Optional[CurrentInfrastructure] = None  # override CSV defaults


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "project": "Urban Infrastructure Prediction System",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/cities", tags=["Data"])
def get_cities():
    """Return all cities available in the dataset."""
    cities = list_cities()
    return {"cities": cities, "count": len(cities)}


@app.get("/city/{city_name}", tags=["Data"])
def get_city(city_name: str):
    """Return historical population + current infrastructure for a city."""
    try:
        summary = get_city_summary(city_name)
        return summary
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/predict", tags=["Prediction"])
def predict(req: PredictRequest):
    """
    Core prediction endpoint.
    Uses multi-model AI selection (Linear / Polynomial / Exponential).
    Returns predicted population + required infrastructure + deficit analysis.
    """
    try:
        # ── Load historical data ──
        pop_df = get_city_population(req.city)
        infra  = get_city_infrastructure(req.city)

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
        infra_analysis = full_analysis(prediction["predicted_population"], current_infra)

        # ── Build historical series for charts (all data points) ──
        historical_series = [
            {"year": int(y), "population": int(p)}
            for y, p in zip(historical_years, historical_pops)
        ]

        # ── Derived metrics ──
        base_pop      = float(historical_pops[-1])
        pred_pop      = float(prediction["predicted_population"])
        years_ahead   = prediction["years_ahead"]
        area_km2      = float(infra.get("area_km2", 0)) or 1.0

        # CAGR: compound annual growth rate from last known year to target year
        cagr = round(((pred_pop / base_pop) ** (1 / max(years_ahead, 1)) - 1) * 100, 2) if base_pop > 0 else 0.0

        # Population density (predicted)
        density_predicted = round(pred_pop / area_km2)
        density_current   = round(base_pop / area_km2)

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
            "years_ahead":          years_ahead,
            "all_models":           prediction["all_models"],
            "confidence":           prediction["confidence"],

            # Derived metrics
            "cagr":              cagr,
            "density_current":   density_current,
            "density_predicted": density_predicted,

            # Infrastructure
            "current_infrastructure":  current_infra,
            "required_infrastructure": infra_analysis["required"],
            "deficit":                 infra_analysis["deficit"],
            "deficit_pct":             infra_analysis["deficit_pct"],
            "warnings":                infra_analysis["warnings"],
            "norms_used":              infra_analysis["norms_used"],
            "demographics":            infra_analysis["demographics"],
            "segment_info":            infra_analysis["segment_info"],

            # Chart data
            "historical_series":   historical_series,
            "projection_series":   prediction["projection_series"],
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")
