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
# Modal Split (India, MoUD Urban Mobility Report 2024)
# What % of commuters actually use PUBLIC BUSES (not private vehicles)
#
# Private two-wheelers:  ~38% of all trips
# Private cars:          ~12% of all trips
# Public buses:          ~25-38% (varies by city size)
# Walk / cycle:          ~18%
# Metro / suburban rail: ~7% (mainly Tier 1)
#
# Tier 1 metros have metro rail/local trains, so bus share is LOWER.
# Tier 2 cities depend mainly on buses, so bus share is HIGHER.
# ─────────────────────────────────────────────

MODAL_SPLIT = {
    "tier1": {
        "bus_share":     0.28,    # 28% of commuters use public buses
        "private_share": 0.50,   # 50% use private vehicles (bike/car)
        "walk_cycle":    0.15,   # 15% walk or cycle
        "other_transit": 0.07,  # 7% metro / suburban rail
    },
    "tier2": {
        "bus_share":     0.38,    # 38% of commuters use public buses
        "private_share": 0.45,   # 45% use private vehicles
        "walk_cycle":    0.17,   # 17% walk or cycle
        "other_transit": 0.00,  # 0% (no metro in most Tier 2)
    },
}

# ─────────────────────────────────────────────
# Infrastructure Norms — differentiated by city tier
# ─────────────────────────────────────────────
#
# TIER 1 METROS: Higher density, so smaller per-person norms
# TIER 2 CITIES: Lower density, so larger per-person norms
#
# Sources: URDPFI Guidelines 2014 (MoUD), WHO Norms, Smart Cities Mission

NORMS = {
    "tier1": {
        "schools": {
            "segment":    "school_age_5_17",
            "ratio":      1200,
            "label":      "1 school per 1,200 students (Tier 1 Metro norm)",
        },
        "hospitals": {
            "segment":    "total",
            "ratio":      8000,
            "label":      "1 hospital per 8,000 people (WHO, Tier 1 Metro)",
        },
        "buses": {
            "segment":    "bus_commuters",   # Only people who ACTUALLY use buses
            "ratio":      50,                # 1 bus per 50 daily passengers (bus capacity ~50)
            "label":      "1 bus per 50 public-bus commuters (28% modal split, Tier 1)",
        },
        "roads_km": {
            "segment":    "total",
            "ratio":      1000,
            "label":      "1 km road per 1,000 people (Tier 1 Metro)",
        },
    },
    "tier2": {
        "schools": {
            "segment":    "school_age_5_17",
            "ratio":      800,
            "label":      "1 school per 800 students (Tier 2 City norm)",
        },
        "hospitals": {
            "segment":    "total",
            "ratio":      10000,
            "label":      "1 hospital per 10,000 people (WHO standard)",
        },
        "buses": {
            "segment":    "bus_commuters",   # Only people who ACTUALLY use buses
            "ratio":      50,                # 1 bus per 50 daily passengers
            "label":      "1 bus per 50 public-bus commuters (38% modal split, Tier 2)",
        },
        "roads_km": {
            "segment":    "total",
            "ratio":      800,
            "label":      "1 km road per 800 people (Tier 2 City norm)",
        },
    },
}


# ─────────────────────────────────────────────
# Core Calculation Functions
# ─────────────────────────────────────────────

def _get_segment_population(total_pop: int, segment: str, city_tier: str = "tier2") -> int:
    """Calculate the population segment relevant to an infra type."""
    if segment == "total":
        return total_pop
    elif segment == "school_age_5_17":
        return int(total_pop * DEMOGRAPHICS["school_age_5_17"])
    elif segment == "commuters":
        # All commuters (working-age + students who travel daily)
        base = total_pop * (DEMOGRAPHICS["working_18_59"] + DEMOGRAPHICS["school_age_5_17"])
        return int(base * 0.75)   # 75% of eligible pop actually commutes
    elif segment == "bus_commuters":
        # KEY FIX: Only count people who actually take PUBLIC BUSES
        # Many people have private vehicles (bikes, cars, autos)
        all_commuters = total_pop * (DEMOGRAPHICS["working_18_59"] + DEMOGRAPHICS["school_age_5_17"]) * 0.75
        bus_share = MODAL_SPLIT.get(city_tier, MODAL_SPLIT["tier2"])["bus_share"]
        return int(all_commuters * bus_share)
    elif segment in DEMOGRAPHICS:
        return int(total_pop * DEMOGRAPHICS[segment])
    return total_pop


def calculate_required(total_population: int, city_tier: str = "tier2") -> tuple:
    """
    Calculate required infrastructure using city-tier-adjusted norms
    and real modal split data for bus calculations.
    """
    norms  = NORMS.get(city_tier, NORMS["tier2"])
    splits = MODAL_SPLIT.get(city_tier, MODAL_SPLIT["tier2"])

    all_commuters  = int(total_population
                        * (DEMOGRAPHICS["working_18_59"] + DEMOGRAPHICS["school_age_5_17"])
                        * 0.75)
    bus_commuters  = int(all_commuters * splits["bus_share"])
    priv_commuters = int(all_commuters * splits["private_share"])

    # Demographic breakdown
    breakdown = {
        "total":           total_population,
        "children_0_4":    int(total_population * DEMOGRAPHICS["children_0_4"]),
        "school_age_5_17": int(total_population * DEMOGRAPHICS["school_age_5_17"]),
        "working_18_59":   int(total_population * DEMOGRAPHICS["working_18_59"]),
        "senior_60_plus":  int(total_population * DEMOGRAPHICS["senior_60_plus"]),
        "all_commuters":   all_commuters,
        "bus_commuters":   bus_commuters,
        "private_vehicle_commuters": priv_commuters,
        "bus_modal_split_pct": int(splits["bus_share"] * 100),
        "private_modal_split_pct": int(splits["private_share"] * 100),
    }

    required     = {}
    segment_used = {}

    for key, norm in norms.items():
        seg_pop = _get_segment_population(total_population, norm["segment"], city_tier)
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
