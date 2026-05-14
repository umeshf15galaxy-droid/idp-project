"""
predictor.py — AI Prediction Engine for IDP.

Compares three models per city:
  1. Linear Regression      — simple, interpretable baseline
  2. Polynomial Regression  — better captures acceleration (degree=2)
  3. Exponential Regression — models compounding growth (log-linearised)

Selects the best model by cross-validated R² score.
Returns prediction + confidence band + model metadata.
"""

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import cross_val_score
from sklearn.metrics import r2_score
import warnings

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _reshape(arr):
    return np.array(arr).reshape(-1, 1)


def _train_linear(years, populations):
    model = LinearRegression()
    model.fit(_reshape(years), populations)
    return model


def _train_poly(years, populations, degree=2):
    model = make_pipeline(PolynomialFeatures(degree), LinearRegression())
    model.fit(_reshape(years), populations)
    return model


def _train_exponential(years, populations):
    """Fit a model to log(population) — i.e., exponential growth."""
    log_pop = np.log(np.array(populations, dtype=float))
    model = LinearRegression()
    model.fit(_reshape(years), log_pop)
    return model  # predict with exp(model.predict(X))


def _score_cv(model, years, populations, is_exp=False):
    """Cross-validated R² (Leave-One-Out for small datasets)."""
    X = _reshape(years)
    y = np.array(populations, dtype=float)
    if is_exp:
        y = np.log(y)
    n = len(years)
    if n < 3:
        return 0.0
    cv = min(n, 5)  # max 5-fold
    scores = cross_val_score(model, X, y, cv=cv, scoring="r2")
    return float(np.mean(scores))


def _predict_value(model, year, is_exp=False):
    X = np.array([[year]])
    val = model.predict(X)[0]
    if is_exp:
        val = np.exp(val)
    return max(float(val), 0.0)


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def predict_population(historical_years: list, historical_populations: list, target_year: int) -> dict:
    """
    Given historical data, train and compare 3 models, select the best,
    and return the predicted population for target_year.

    Returns:
        {
            "predicted_population": int,
            "model_used": str,
            "model_r2": float,
            "all_models": { "linear": {...}, "polynomial": {...}, "exponential": {...} },
            "projection_series": [{"year": int, "population": int}, ...],
            "confidence": { "low": int, "high": int }
        }
    """
    years = np.array(historical_years, dtype=float)
    pops  = np.array(historical_populations, dtype=float)

    # ── Train all three models ──
    lin_model  = _train_linear(years, pops)
    poly_model = _train_poly(years, pops, degree=2)
    exp_model  = _train_exponential(years, pops)

    # ── Score them ──
    lin_score  = _score_cv(LinearRegression(), years, pops, is_exp=False)
    poly_score = _score_cv(make_pipeline(PolynomialFeatures(2), LinearRegression()), years, pops, is_exp=False)
    exp_score  = _score_cv(LinearRegression(), years, pops, is_exp=True)

    scores = {
        "linear":      (lin_model,  lin_score,  False),
        "polynomial":  (poly_model, poly_score, False),
        "exponential": (exp_model,  exp_score,  True),
    }

    # ── Select best ──
    best_name = max(scores, key=lambda k: scores[k][1])
    best_model, best_r2, best_is_exp = scores[best_name]

    # ── Make prediction ──
    predicted = _predict_value(best_model, target_year, is_exp=best_is_exp)

    # ── Build full projection series (last known year → target) ──
    last_known = int(max(historical_years))
    series_years = list(range(last_known, target_year + 1, 1 if (target_year - last_known) <= 30 else 5))
    if series_years[-1] != target_year:
        series_years.append(target_year)

    projection = [
        {"year": y, "population": int(_predict_value(best_model, y, is_exp=best_is_exp))}
        for y in series_years
    ]

    # ── Simple confidence band: ±10% for near-term, ±20% for >15 years out ──
    years_ahead = target_year - last_known
    uncertainty = 0.10 if years_ahead <= 15 else 0.20

    # ── All model results (for transparency / UI display) ──
    all_models = {
        name: {
            "predicted_population": int(_predict_value(model, target_year, is_exp=is_exp)),
            "r2_score": round(r2, 4),
            "selected": name == best_name,
        }
        for name, (model, r2, is_exp) in scores.items()
    }

    return {
        "predicted_population": int(predicted),
        "model_used": best_name,
        "model_r2": round(best_r2, 4),
        "years_ahead": years_ahead,
        "all_models": all_models,
        "projection_series": projection,
        "confidence": {
            "low":  int(predicted * (1 - uncertainty)),
            "high": int(predicted * (1 + uncertainty)),
        },
    }
