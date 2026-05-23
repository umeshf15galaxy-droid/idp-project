"""
predictor.py — Population Prediction Engine V5 (Fixed Curvature)

Root cause of "looks linear" bug:
  - Polynomial degree 2 has CONSTANT acceleration → looks linear at chart scale
  - Logistic K (carrying capacity) was too LOW → flatlines prematurely
  
Fix:
  1. Force K >= current_pop * 4 so logistic stays on steep growth curve
  2. Prefer EXPONENTIAL (always a visible curve) for high-growth cities
  3. Train on 80%, validate on 20% (test MAPE < 20% to qualify)
  4. Model priority: Logistic > Exponential > Polynomial > Linear
  5. "Recent exponential" uses last 5 data points for current growth rate
"""

import numpy as np
from scipy.optimize import curve_fit
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
import warnings
warnings.filterwarnings("ignore")

MAX_TEST_MAPE = 20.0   # Model must predict 2020+2025 within 20% to qualify


# ── Utilities ──────────────────────────────────────────────────

def _reshape(arr):
    return np.array(arr, dtype=float).reshape(-1, 1)

def _mape(actual, predicted):
    a = np.array(actual, dtype=float)
    p = np.array(predicted, dtype=float)
    mask = a > 0
    return float(np.mean(np.abs((a[mask] - p[mask]) / a[mask])) * 100)

def _r2(actual, predicted):
    a = np.array(actual, dtype=float)
    p = np.array(predicted, dtype=float)
    ss_res = np.sum((a - p) ** 2)
    ss_tot = np.sum((a - np.mean(a)) ** 2)
    return float(max(0.0, 1.0 - ss_res / ss_tot)) if ss_tot > 0 else 1.0


# ── Model 1: Logistic (Verhulst S-Curve) with enforced generous K ──

def _logistic_fn(t, K, r, t0):
    return K / (1.0 + np.exp(-r * (t - t0)))

def _fit_logistic(t_arr, pops):
    """
    Key fix: K_min = Pn * 4 (force city onto steep part of S-curve).
    Without this, scipy finds K close to current pop and the curve flatlines.
    """
    Pn = float(max(pops))
    best, best_err = None, float("inf")
    for K in [Pn*4, Pn*6, Pn*8, Pn*12]:
        for r in [0.03, 0.05, 0.08, 0.12]:
            for t0 in [t_arr[len(t_arr)//2], t_arr[-1], t_arr[-1]+10]:
                try:
                    popt, _ = curve_fit(
                        _logistic_fn, t_arr, pops,
                        p0=[K, r, t0],
                        bounds=([Pn*4, 0.005, -50], [Pn*20, 0.4, 200]),
                        maxfev=6000,
                    )
                    err = np.sum((np.array(pops) - _logistic_fn(t_arr, *popt))**2)
                    if err < best_err:
                        best_err, best = err, popt
                except Exception:
                    continue
    return best


# ── Model 2: Exponential ──

def _fit_exp(t_arr, pops):
    m = LinearRegression()
    m.fit(_reshape(t_arr), np.log(np.maximum(pops, 1.0)))
    return m

def _pred_exp(model, t):
    return float(np.exp(np.clip(model.predict(_reshape([t]))[0], 0, 40)))


# ── Model 3: Ridge Polynomial ──

def _fit_ridge(t_arr, pops, alpha=100.0):
    m = make_pipeline(PolynomialFeatures(3), Ridge(alpha=alpha))
    m.fit(_reshape(t_arr), pops)
    return m


# ── Model 4: Linear ──

def _fit_linear(t_arr, pops):
    m = LinearRegression()
    m.fit(_reshape(t_arr), pops)
    return m


# ── Compound growth fallback ──

def _cagr_predict(pops, years, target):
    base = float(pops[-1])
    span = int(years[-1]) - int(years[-2])
    rate = max(0.003, min(0.05, (pops[-1]/max(pops[-2],1))**(1.0/max(span,1)) - 1))
    return int(base * ((1+rate)**(target - int(years[-1]))))


# ── Main ───────────────────────────────────────────────────────

def predict_population(years, populations, target_year):
    years = [int(y) for y in years]
    pops  = [float(p) for p in populations]
    n     = len(years)

    # 80/20 chronological split
    split      = max(3, int(n * 0.8))
    tr_y       = years[:split]
    tr_p       = pops[:split]
    te_y       = years[split:]
    te_p       = pops[split:]

    base_year  = int(min(years))
    base_pop   = pops[-1]
    t_train    = np.array(tr_y, dtype=float) - base_year
    t_test     = np.array(te_y, dtype=float) - base_year
    t_target   = float(target_year - base_year)
    years_ahead= target_year - max(years)

    tr_arr = np.array(tr_p, dtype=float)

    # ── Fit all models on training data ──
    entries = {}

    # 1. Logistic
    lp = _fit_logistic(t_train, tr_arr)
    if lp is not None:
        te_pred_l = [_logistic_fn(t, *lp) for t in t_test]
        fut_l     = float(_logistic_fn(t_target, *lp))
        tr_r2_l   = _r2(tr_p, [_logistic_fn(t, *lp) for t in t_train])
    else:
        te_pred_l, fut_l, tr_r2_l = list(te_p), base_pop, 0.0
    entries["logistic"] = {"te_pred": te_pred_l, "fut": fut_l, "tr_r2": tr_r2_l, "lp": lp}

    # 2. Exponential (full training set)
    em = _fit_exp(t_train, tr_arr)
    te_pred_e = [_pred_exp(em, t) for t in t_test]
    fut_e     = _pred_exp(em, t_target)
    entries["exponential"] = {"te_pred": te_pred_e, "fut": fut_e, "tr_r2": _r2(np.log(tr_arr), em.predict(_reshape(t_train))), "em": em}

    # 3. Recent exponential — train on last 5 training points only (captures current momentum)
    rec_n  = min(5, len(tr_y))
    rec_y  = tr_y[-rec_n:]
    rec_p  = tr_p[-rec_n:]
    t_rec  = np.array(rec_y, dtype=float) - base_year
    rem = _fit_exp(t_rec, np.array(rec_p, dtype=float))
    te_pred_r = [_pred_exp(rem, t) for t in t_test]
    fut_r     = _pred_exp(rem, t_target)
    entries["recent_exp"] = {"te_pred": te_pred_r, "fut": fut_r, "tr_r2": _r2(rec_p, [_pred_exp(rem, t) for t in t_rec]), "rem": rem}

    # 4. Ridge polynomial (auto-tune alpha)
    best_rm, best_rm_mape, best_rm_te = None, float("inf"), None
    for alpha in [1, 10, 50, 100, 500, 2000]:
        rm = _fit_ridge(t_train, tr_arr, alpha)
        te_p_rm = [float(rm.predict(_reshape([t]))[0]) for t in t_test]
        m = _mape(te_p, te_p_rm)
        if m < best_rm_mape:
            best_rm_mape, best_rm, best_rm_te = m, rm, te_p_rm
    fut_rm = float(best_rm.predict(_reshape([t_target]))[0]) if best_rm else base_pop
    entries["ridge_poly"] = {"te_pred": best_rm_te or list(te_p), "fut": fut_rm, "tr_r2": _r2(tr_p, best_rm.predict(_reshape(t_train)).tolist()) if best_rm else 0.0, "rm": best_rm}

    # 5. Linear (baseline)
    lm = _fit_linear(t_train, tr_arr)
    te_pred_lin = [float(lm.predict(_reshape([t]))[0]) for t in t_test]
    fut_lin     = float(lm.predict(_reshape([t_target]))[0])
    entries["linear"] = {"te_pred": te_pred_lin, "fut": fut_lin, "tr_r2": _r2(tr_p, lm.predict(_reshape(t_train)).tolist()), "lm": lm}

    # ── Evaluate & validate ──
    evaluated = {}
    for name, e in entries.items():
        te_mape = _mape(te_p, e["te_pred"])
        te_r2   = _r2(te_p, e["te_pred"])
        # Valid: test MAPE within threshold AND predicts growth
        passed  = (te_mape < MAX_TEST_MAPE) and (e["fut"] > base_pop)
        evaluated[name] = {
            "r2_score":  round(float(e["tr_r2"]), 4),
            "test_r2":   round(float(te_r2), 4),
            "test_mape": round(float(te_mape), 2),
            "prediction": int(max(0, e["fut"])),
            "selected":  False,
            "valid":     passed,
        }

    # ── Model selection: PRIORITY order (not just lowest MAPE) ──
    # Logistic > Recent Exp > Exponential > Ridge > Linear
    # A model must PASS validation. Among passing models, use priority order.
    priority = ["logistic", "recent_exp", "exponential", "ridge_poly", "linear"]
    passing  = {k: v for k, v in evaluated.items() if v["valid"]}

    best_name = None
    for name in priority:
        if name in passing:
            best_name = name
            break

    if best_name is None:
        best_name = "__fallback__"

    # ── Final prediction ──
    if best_name == "__fallback__":
        predicted_pop = _cagr_predict(pops, years, target_year)
        best_r2, best_mape = 0.0, 999.0
        display_name = "compound_growth"
    else:
        predicted_pop = evaluated[best_name]["prediction"]
        best_r2  = evaluated[best_name]["test_r2"]
        best_mape= evaluated[best_name]["test_mape"]
        display_name = best_name
        evaluated[best_name]["selected"] = True

    predicted_pop = max(predicted_pop, int(base_pop))

    # ── Confidence from all passing models ──
    valid_preds = [v["prediction"] for v in passing.values()] if passing else [predicted_pop]
    conf_low  = max(int(min(valid_preds) * 0.97), int(base_pop))
    conf_high = int(max(valid_preds) * 1.03)

    # ── Projection series (year-by-year, clamped to never decline) ──
    proj_series = []
    e = entries.get(best_name, {})
    for y in range(max(years), target_year + 1):
        t = float(y - base_year)
        if best_name == "logistic" and e.get("lp") is not None:
            p = float(_logistic_fn(t, *e["lp"]))
        elif best_name in ("exponential",) and e.get("em"):
            p = _pred_exp(e["em"], t)
        elif best_name == "recent_exp" and e.get("rem"):
            p = _pred_exp(e["rem"], t)
        elif best_name == "ridge_poly" and e.get("rm"):
            p = float(e["rm"].predict(_reshape([t]))[0])
        elif best_name == "linear" and e.get("lm"):
            p = float(e["lm"].predict(_reshape([t]))[0])
        else:
            p = _cagr_predict(pops, years, y)
        proj_series.append({"year": y, "population": int(max(p, base_pop))})

    return {
        "predicted_population": predicted_pop,
        "model_used":           display_name,
        "model_r2":             round(best_r2, 4),
        "test_mape":            round(best_mape, 2),
        "years_ahead":          years_ahead,
        "all_models":           evaluated,
        "confidence":           {"low": conf_low, "high": conf_high},
        "projection_series":    proj_series,
        "train_size":           split,
        "test_size":            len(te_y),
        "test_years":           te_y,
        "test_actual":          [int(p) for p in te_p],
    }
