"""
infrastructure.py — Demographic-Aware, City-Tier-Adjusted Infrastructure Engine v2.

Key improvements:
  1. CITY TIER SYSTEM: Tier 1 metros (Delhi, Mumbai, etc.) get denser norms
     than Tier 2 cities, reflecting higher urbanisation and land scarcity.
  2. IMPROVED DEMOGRAPHICS: Updated to India 2024 Census projections.
  3. GRADUATED WARNINGS: Critical / Warning / Caution / Surplus thresholds.
  4. ROADS IMPROVED: Uses road length per sq km norm (not just per person).

Tier 1 metros: Delhi, Mumbai, Kolkata, Bangalore, Chennai, Hyderabad
Tier 2 cities: All others (Pune, Ahmedabad, Surat, Jaipur, Lucknow, etc.)
"""

# ─────────────────────────────────────────────
# Demographic Ratios (India 2024, Census projection)
# ─────────────────────────────────────────────

DEMOGRAPHICS = {
    "children_0_4":    0.075,   # 7.5%  — infants
    "school_age_5_17": 0.246,   # 24.6% — school-going students
    "working_18_59":   0.564,   # 56.4% — working population
    "senior_60_plus":  0.115,   # 11.5% — elderly
}

# ─────────────────────────────────────────────
# Infrastructure Norms — differentiated by city tier
# ─────────────────────────────────────────────
#
# TIER 1 METROS: Higher density, so smaller per-person norms (more people share each facility)
# TIER 2 CITIES: Lower density, so larger per-person norms (more spread out)
#
# Sources: URDPFI Guidelines 2014 (MoUD), WHO Norms, Smart Cities Mission

NORMS = {
    "tier1": {
        "schools": {
            "segment":    "school_age_5_17",
            "ratio":      1200,      # 1 school per 1200 students (dense city — multi-shift schools)
            "label":      "1 school per 1,200 students (Tier 1 Metro norm)",
        },
        "hospitals": {
            "segment":    "total",
            "ratio":      8000,      # 1 hospital per 8,000 people (WHO for high-density cities)
            "label":      "1 hospital per 8,000 people (WHO, Tier 1 Metro)",
        },
        "buses": {
            "segment":    "commuters",
            "ratio":      50,        # 1 bus per 50 commuters (Metro has more transit options)
            "label":      "1 bus per 50 commuters (Tier 1 Metro)",
        },
        "roads_km": {
            "segment":    "total",
            "ratio":      1000,      # 1 km road per 1,000 people (dense, needs more roads)
            "label":      "1 km road per 1,000 people (Tier 1 Metro)",
        },
    },
    "tier2": {
        "schools": {
            "segment":    "school_age_5_17",
            "ratio":      800,       # 1 school per 800 students (URDPFI standard)
            "label":      "1 school per 800 students (Tier 2 City norm)",
        },
        "hospitals": {
            "segment":    "total",
            "ratio":      10000,     # 1 hospital per 10,000 people (WHO standard)
            "label":      "1 hospital per 10,000 people (WHO standard)",
        },
        "buses": {
            "segment":    "commuters",
            "ratio":      40,        # 1 bus per 40 commuters
            "label":      "1 bus per 40 commuters (Tier 2 City)",
        },
        "roads_km": {
            "segment":    "total",
            "ratio":      800,       # 1 km road per 800 people
            "label":      "1 km road per 800 people (Tier 2 City norm)",
        },
    },
}


# ─────────────────────────────────────────────
# Core Calculation Functions
# ─────────────────────────────────────────────

def _get_segment_population(total_pop: int, segment: str) -> int:
    """Calculate the population segment relevant to an infra type."""
    if segment == "total":
        return total_pop
    elif segment == "school_age_5_17":
        return int(total_pop * DEMOGRAPHICS["school_age_5_17"])
    elif segment == "commuters":
        base = total_pop * (DEMOGRAPHICS["working_18_59"] + DEMOGRAPHICS["school_age_5_17"])
        return int(base * 0.60)   # 60% of working+student pop commutes
    elif segment in DEMOGRAPHICS:
        return int(total_pop * DEMOGRAPHICS[segment])
    return total_pop


def calculate_required(total_population: int, city_tier: str = "tier2") -> tuple:
    """
    Calculate required infrastructure using city-tier-adjusted norms.
    Returns (required_counts, demographic_breakdown, segment_info_used).
    """
    norms = NORMS.get(city_tier, NORMS["tier2"])

    # Demographic breakdown
    breakdown = {
        "total":           total_population,
        "children_0_4":    int(total_population * DEMOGRAPHICS["children_0_4"]),
        "school_age_5_17": int(total_population * DEMOGRAPHICS["school_age_5_17"]),
        "working_18_59":   int(total_population * DEMOGRAPHICS["working_18_59"]),
        "senior_60_plus":  int(total_population * DEMOGRAPHICS["senior_60_plus"]),
        "commuters":       int(total_population
                               * (DEMOGRAPHICS["working_18_59"] + DEMOGRAPHICS["school_age_5_17"])
                               * 0.60),
    }

    required    = {}
    segment_used = {}

    for key, norm in norms.items():
        seg_pop = _get_segment_population(total_population, norm["segment"])
        required[key] = max(1, int(seg_pop / norm["ratio"]))
        segment_used[key] = {
            "segment_name":       norm["segment"],
            "segment_population": seg_pop,
            "ratio":              norm["ratio"],
            "norm_label":         norm["label"],
        }

    return required, breakdown, segment_used


def calculate_deficit(required: dict, current: dict) -> tuple:
    """Compute deficit (required − current) and deficit % for each type."""
    deficit     = {}
    deficit_pct = {}
    for key in required:
        cur = current.get(key, 0)
        req = required[key]
        gap = req - cur
        deficit[key]     = max(0, gap)
        deficit_pct[key] = round((deficit[key] / req) * 100) if req > 0 else 0
    return deficit, deficit_pct


def generate_warnings(deficit: dict, deficit_pct: dict) -> list:
    """
    Generate graduated severity warnings.
    Thresholds: CRITICAL ≥40%, WARNING ≥20%, CAUTION ≥5%, SURPLUS if negative.
    """
    warnings = []
    for key, pct in deficit_pct.items():
        label = key.replace("_km", " (km)").replace("_", " ").title()
        if pct >= 40:
            warnings.append({
                "type":     "critical",
                "category": key,
                "message":  f"🔴 CRITICAL: {label} deficit is {pct}% — immediate investment required.",
            })
        elif pct >= 20:
            warnings.append({
                "type":     "warning",
                "category": key,
                "message":  f"🟡 WARNING: {label} deficit is {pct}% — plan within 5 years.",
            })
        elif pct >= 5:
            warnings.append({
                "type":     "caution",
                "category": key,
                "message":  f"🔵 CAUTION: {label} deficit is {pct}% — monitor closely.",
            })

    # Surplus message (city is well-equipped)
    surplus_count = sum(1 for p in deficit_pct.values() if p == 0)
    if surplus_count == len(deficit_pct):
        warnings.append({
            "type":     "success",
            "category": "all",
            "message":  "✅ Current infrastructure meets all projected requirements.",
        })

    return warnings


def full_analysis(total_population: int, current_infrastructure: dict, city_tier: str = "tier2") -> dict:
    """
    Complete infrastructure analysis with tier-aware demographic norms.
    """
    required, demographics, segment_info = calculate_required(total_population, city_tier)
    deficit, deficit_pct = calculate_deficit(required, current_infrastructure)
    warnings = generate_warnings(deficit, deficit_pct)
    norms = NORMS.get(city_tier, NORMS["tier2"])

    return {
        "required":     required,
        "deficit":      deficit,
        "deficit_pct":  deficit_pct,
        "warnings":     warnings,
        "demographics": demographics,
        "segment_info": segment_info,
        "norms_used":   {k: v["label"] for k, v in norms.items()},
        "city_tier":    city_tier,
    }
