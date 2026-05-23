"""
infrastructure.py — Demographic-Aware Infrastructure Formula Engine.

Key fix: Schools are calculated from STUDENT-AGE population, not total.
Each infrastructure type uses the correct demographic segment.

Demographic breakdown (India 2024, World Bank / Census):
  - Children 0-4:    ~7.5%
  - School-age 5-17: ~24.6%  (the STUDENT population)
  - Working-age 18-59: ~56.4%
  - Senior 60+:      ~11.5%

Infrastructure norms (URDPFI / WHO / MOUD):
  - Schools:   1 per 800 students   (school-age pop / 800)
  - Hospitals: 1 per 10,000 people  (WHO norm: 3.5 beds/1000, ~35 beds/hospital)
  - Buses:     1 per 1,200 commuters (working + student pop × 60% commute rate)
  - Roads:     1 km per 800 people  (total pop / 800)
"""

# ─────────────────────────────────────────────
# Demographic Ratios (India 2024)
# ─────────────────────────────────────────────

DEMOGRAPHICS = {
    "children_0_4":   0.075,   # 7.5%  — infants, not in school
    "school_age_5_17": 0.246,  # 24.6% — primary + secondary students
    "working_18_59":  0.564,   # 56.4% — working population
    "senior_60_plus": 0.115,   # 11.5% — elderly population
}

# ─────────────────────────────────────────────
# Infrastructure Norms
# ─────────────────────────────────────────────

NORMS = {
    "schools": {
        "segment": "school_age_5_17",   # Schools serve students, NOT total population
        "ratio": 800,                    # 1 school per 800 students (URDPFI norm)
        "label": "1 school per 800 students",
    },
    "hospitals": {
        "segment": "total",              # Hospitals serve everyone
        "ratio": 10000,                  # WHO: 1 hospital per 10,000 people
        "label": "1 hospital per 10,000 people (WHO)",
    },
    "buses": {
        "segment": "commuters",          # Commuters = (working + student) × 60%
        "ratio": 40,                     # 1 bus per 40 daily commuters
        "label": "1 bus per 40 commuters",
    },
    "roads_km": {
        "segment": "total",              # Roads serve everyone
        "ratio": 800,                    # 1 km road per 800 people
        "label": "1 km road per 800 people",
    },
}


def _get_segment_population(total_pop, segment):
    """Calculate the population segment relevant to an infra type."""
    if segment == "total":
        return total_pop
    elif segment == "school_age_5_17":
        return int(total_pop * DEMOGRAPHICS["school_age_5_17"])
    elif segment == "commuters":
        # Commuters = (working-age + school-age) × 60% commute-rate
        base = total_pop * (DEMOGRAPHICS["working_18_59"] + DEMOGRAPHICS["school_age_5_17"])
        return int(base * 0.60)
    elif segment in DEMOGRAPHICS:
        return int(total_pop * DEMOGRAPHICS[segment])
    else:
        return total_pop


def calculate_required(total_population):
    """
    Calculate required infrastructure based on demographic segments.
    Returns dict of required counts + demographic breakdown.
    """
    breakdown = {
        "total": total_population,
        "children_0_4":    int(total_population * DEMOGRAPHICS["children_0_4"]),
        "school_age_5_17": int(total_population * DEMOGRAPHICS["school_age_5_17"]),
        "working_18_59":   int(total_population * DEMOGRAPHICS["working_18_59"]),
        "senior_60_plus":  int(total_population * DEMOGRAPHICS["senior_60_plus"]),
        "commuters":       int(total_population * (DEMOGRAPHICS["working_18_59"] + DEMOGRAPHICS["school_age_5_17"]) * 0.60),
    }

    required = {}
    segment_used = {}
    for key, norm in NORMS.items():
        seg_pop = _get_segment_population(total_population, norm["segment"])
        required[key] = max(1, int(seg_pop / norm["ratio"]))
        segment_used[key] = {
            "segment_name": norm["segment"],
            "segment_population": seg_pop,
            "ratio": norm["ratio"],
            "norm_label": norm["label"],
        }

    return required, breakdown, segment_used


def calculate_deficit(required, current):
    """Compute deficit (required - current) for each infra type."""
    deficit = {}
    deficit_pct = {}
    for key in required:
        cur = current.get(key, 0)
        req = required[key]
        deficit[key] = max(0, req - cur)
        deficit_pct[key] = round((deficit[key] / req) * 100) if req > 0 else 0
    return deficit, deficit_pct


def generate_warnings(deficit, deficit_pct):
    """Auto-generate severity warnings based on deficit percentage."""
    warnings = []
    for key, pct in deficit_pct.items():
        label = key.replace("_", " ").title()
        if pct >= 30:
            warnings.append({
                "type": "critical",
                "category": key,
                "message": f"🔴 CRITICAL: {label} deficit is {pct}% — immediate action required.",
            })
        elif pct >= 10:
            warnings.append({
                "type": "warning",
                "category": key,
                "message": f"🟡 WARNING: {label} deficit is {pct}% — planning needed within 5 years.",
            })
    return warnings


def full_analysis(total_population, current_infrastructure):
    """
    Complete infrastructure analysis with demographic awareness.
    Returns required, deficit, warnings, demographic breakdown, and norms.
    """
    required, demographics, segment_info = calculate_required(total_population)
    deficit, deficit_pct = calculate_deficit(required, current_infrastructure)
    warnings = generate_warnings(deficit, deficit_pct)

    return {
        "required":        required,
        "deficit":         deficit,
        "deficit_pct":     deficit_pct,
        "warnings":        warnings,
        "demographics":    demographics,
        "segment_info":    segment_info,
        "norms_used": {k: v["label"] for k, v in NORMS.items()},
    }
