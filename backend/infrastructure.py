"""
infrastructure.py — Formula Engine for IDP.

Converts a predicted population into required infrastructure
using Indian Urban Planning norms, then calculates deficits vs
current stock.
"""

# ─────────────────────────────────────────────────────────────────
# Planning Norms (can be overridden per-request in future versions)
# ─────────────────────────────────────────────────────────────────
NORMS = {
    "schools":    5_000,   # 1 school per N people
    "hospitals":  25_000,  # 1 hospital per N people
    "buses":      1_200,   # 1 bus per N people
    "roads_km":   800,     # 1 km road per N people
}

# Severity thresholds for warnings
CRITICAL_DEFICIT_PCT = 0.30   # > 30% shortfall → critical
WARNING_DEFICIT_PCT  = 0.10   # 10–30% shortfall → warning


def compute_required(population: int) -> dict:
    """Return required infrastructure counts for a given population."""
    return {
        key: max(1, int(population // norm))
        for key, norm in NORMS.items()
    }


def compute_deficit(required: dict, current: dict) -> dict:
    """
    Deficit = required − current.
    Positive → shortfall (need more).
    Negative → surplus (have extra).
    """
    return {
        key: required[key] - int(current.get(key, 0))
        for key in required
    }


def compute_deficit_pct(required: dict, current: dict) -> dict:
    """Percentage deficit relative to what is required."""
    result = {}
    for key in required:
        req = required[key]
        cur = int(current.get(key, 0))
        if req == 0:
            result[key] = 0.0
        else:
            result[key] = round((req - cur) / req * 100, 1)
    return result


def generate_warnings(deficit_pct: dict) -> list[dict]:
    """
    Produce human-readable warnings for each infrastructure type
    that breaches the warning or critical threshold.
    """
    labels = {
        "schools":   "Schools",
        "hospitals": "Hospitals",
        "buses":     "Buses",
        "roads_km":  "Roads",
    }
    warnings = []
    for key, pct in deficit_pct.items():
        if pct <= 0:
            continue  # surplus, no warning
        label = labels.get(key, key.title())
        if pct >= CRITICAL_DEFICIT_PCT * 100:
            warnings.append({
                "type": "critical",
                "metric": key,
                "message": f"🔴 CRITICAL: {label} deficit is {pct:.0f}% — immediate action required.",
            })
        elif pct >= WARNING_DEFICIT_PCT * 100:
            warnings.append({
                "type": "warning",
                "metric": key,
                "message": f"🟡 WARNING: {label} shortage of {pct:.0f}% projected.",
            })
    return warnings


def full_analysis(predicted_population: int, current_infrastructure: dict) -> dict:
    """
    One-shot function: given predicted pop + current infra,
    return required, deficit, deficit_pct, and warnings.
    """
    required    = compute_required(predicted_population)
    deficit     = compute_deficit(required, current_infrastructure)
    deficit_pct = compute_deficit_pct(required, current_infrastructure)
    warnings    = generate_warnings(deficit_pct)

    return {
        "required":    required,
        "deficit":     deficit,
        "deficit_pct": deficit_pct,
        "warnings":    warnings,
        "norms_used":  NORMS,
    }
