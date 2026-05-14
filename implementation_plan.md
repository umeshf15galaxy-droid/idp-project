# Urban Infrastructure Prediction System (IDP) — V1 Implementation Plan

## What This Project Does

A full-stack web application where a user enters a **city + target year**, and the system returns:
- Predicted future population (via Linear Regression on historical census data)
- Required infrastructure: schools, hospitals, buses, roads
- Visual charts showing growth trends and shortfall warnings
- A clean, premium dashboard UI

This is **Version 1** — no AI chatbots, no 3D maps, no login systems. Pure prediction engine + visualization. We build depth before beauty.

---

## User Review Required

> [!IMPORTANT]
> **Scope Decision**: V1 uses **bundled CSV data** for Indian cities (sourced from census/World Bank). No live database yet — PostgreSQL integration is Week 5+ per the roadmap. This keeps V1 shippable fast without DB setup friction.

> [!IMPORTANT]
> **City Coverage**: V1 will include data for ~15 major Indian cities (Delhi, Mumbai, Bangalore, Chennai, Hyderabad, Pune, Kolkata, Ahmedabad, Surat, Jaipur, Lucknow, Kanpur, Nagpur, Indore, Thane). Do you want to add/remove any?

> [!WARNING]
> **Versioning Strategy**: Every major phase will be git-tagged (`v1.0-base`, `v1.1-backend`, `v1.2-frontend`, etc.) so you can rollback cleanly. Git must be installed on your machine. If it's not, tell me and I'll use folder-based backups instead.

---

## Open Questions

> [!IMPORTANT]
> 1. **Python version**: Do you have Python 3.9+ installed? Run `python --version` to check.
> 2. **Port preference**: Backend will run on `localhost:8000`, frontend on `localhost:3000` (via a simple dev server). OK?
> 3. **Infrastructure ratios**: I'll use standard Indian urban planning ratios. Want to customize them?
>    - 1 school per 5,000 people
>    - 1 hospital per 25,000 people
>    - 1 bus per 1,200 people
>    - 1 km road per 800 people

---

## Tech Stack (V1)

| Layer | Technology | Reason |
|-------|-----------|--------|
| Frontend | HTML + CSS + Vanilla JS | Learn the fundamentals first |
| Charts | Chart.js (CDN) | Simple, powerful, no build step |
| Backend | **FastAPI** (Python) | Modern, scalable, great for AI later |
| Data | CSV files + Pandas | Real data, no DB friction yet |
| ML | scikit-learn LinearRegression | Understand before complexity |
| Dev server | Python `http.server` | No Node needed |
| Versioning | Git tags | Rollback safety |

---

## Project Folder Structure

```
idp_project/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── predictor.py         # ML prediction engine
│   ├── infrastructure.py    # Formula engine (schools/buses/etc)
│   ├── data_loader.py       # CSV → Pandas loader
│   └── requirements.txt     # Python dependencies
│
├── data/
│   ├── population.csv       # Historical city population data
│   └── infrastructure.csv   # Current infrastructure per city
│
├── frontend/
│   ├── index.html           # Home page
│   ├── dashboard.html       # Prediction dashboard
│   ├── about.html           # About page
│   ├── sources.html         # Data sources page
│   ├── css/
│   │   └── style.css        # Global styles (dark mode, premium)
│   └── js/
│       ├── app.js           # Main app logic
│       ├── charts.js        # Chart.js rendering
│       └── api.js           # Backend API calls
│
├── backups/                 # Version snapshots before risky changes
│   └── .gitkeep
│
├── .gitignore
└── README.md
```

---

## Data Flow

```
User Input (city + target_year)
        ↓
Frontend (dashboard.html + api.js)
        ↓ POST /predict
FastAPI Backend (main.py)
        ↓
data_loader.py → loads population.csv for that city
        ↓
predictor.py → trains LinearRegression → returns predicted population
        ↓
infrastructure.py → applies ratio formulas → returns needs
        ↓
JSON Response → frontend → Chart.js renders charts + cards
```

---

## API Design

### `POST /predict`
**Request:**
```json
{
  "city": "Bangalore",
  "target_year": 2035,
  "current_infrastructure": {
    "schools": 320,
    "hospitals": 85,
    "buses": 6000,
    "roads_km": 11000
  }
}
```

**Response:**
```json
{
  "city": "Bangalore",
  "target_year": 2035,
  "predicted_population": 15200000,
  "required": {
    "schools": 3040,
    "hospitals": 608,
    "buses": 12666,
    "roads_km": 19000
  },
  "deficit": {
    "schools": 2720,
    "hospitals": 523,
    "buses": 6666,
    "roads_km": 8000
  },
  "historical": [
    {"year": 2001, "population": 5701000},
    {"year": 2011, "population": 8499000},
    {"year": 2021, "population": 11556000}
  ],
  "warnings": ["Critical school deficit", "Bus shortage warning"]
}
```

### `GET /cities`
Returns list of all available cities.

### `GET /city/{city_name}`
Returns current data + historical population for a city.

---

## Frontend Pages

### 1. `index.html` — Home
- Hero section: "Predict Your City's Future"
- Quick search bar (city + year → goes to dashboard)
- Feature cards (what the tool does)
- Stats ticker (cities covered, data points, etc.)

### 2. `dashboard.html` — Prediction Dashboard
- Input panel: city dropdown + year slider + current infra fields
- Prediction cards: Population / Schools / Hospitals / Buses / Roads
- Line chart: historical + projected population
- Bar chart: required vs current infrastructure
- Warning banners for deficits > 30%

### 3. `about.html` — About
- What this project is, methodology, limitations

### 4. `sources.html` — Data Sources
- Links to census data, World Bank, methodology notes

---

## Infrastructure Formulas (V1)

```python
schools    = predicted_population // 5_000
hospitals  = predicted_population // 25_000
buses      = predicted_population // 1_200
roads_km   = predicted_population // 800
```

Deficit = required − current (negative means surplus)

---

## Versioning & Rollback Strategy

Every phase ends with a git commit + tag:

| Tag | Contents |
|-----|----------|
| `v1.0-init` | Project skeleton, data CSVs, README |
| `v1.1-backend` | FastAPI working, `/predict` returns data |
| `v1.2-frontend-base` | HTML/CSS skeleton, navigation |
| `v1.3-charts` | Chart.js integrated, charts rendering |
| `v1.4-dashboard` | Full dashboard working end-to-end |
| `v1.5-polish` | Warnings, styling polish, mobile responsive |

To rollback: `git checkout v1.1-backend` — instantly back to that state.

---

## Build Order (Exact Sequence)

1. **Init git + folder structure** → tag `v1.0-init`
2. **Create data CSVs** (real Indian census data)
3. **Build backend**: `predictor.py` → `infrastructure.py` → `main.py` (FastAPI)
4. **Test backend** with curl/browser → tag `v1.1-backend`
5. **Build CSS design system** (dark mode, colors, fonts)
6. **Build HTML pages** (index → dashboard → about → sources)
7. **Wire JS** (api.js + charts.js + app.js) → tag `v1.2-frontend`
8. **End-to-end test** full flow → tag `v1.3-complete`
9. **Polish**: warnings, mobile responsive → tag `v1.4-polish`

---

## Verification Plan

### Automated Tests
- Run `uvicorn` and hit `POST /predict` with curl for 3 cities
- Check that predicted population is > current population for future years
- Verify deficit math is correct

### Manual Verification
- Open dashboard in browser
- Enter "Delhi" + 2040 → verify charts render
- Check mobile responsiveness at 375px width
- Verify rollback works: `git stash` + `git checkout v1.1-backend`
