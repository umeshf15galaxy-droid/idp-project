# Urban Infrastructure Prediction System (IDP)

**AI-powered population forecasting and infrastructure planning for Indian cities.**

## What It Does

Enter any major Indian city + target year → get:
- 🤖 AI-predicted future population (3 models compared, best selected)
- 🏗️ Required schools, hospitals, buses, roads
- ⚠️ Shortage warnings for critical deficits
- 📈 Interactive charts (population growth + infrastructure comparison)

---

## Quick Start

### 1. Start Backend (port 8000)
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
Or just double-click `start_backend.bat`

### 2. Start Frontend (port 3000)
```bash
cd frontend
python -m http.server 3000
```
Or just double-click `start_frontend.bat`

### 3. Open Browser
```
http://localhost:3000/index.html
```

API docs available at: `http://localhost:8000/docs`

---

## Project Structure

```
idp_project/
├── backend/
│   ├── main.py           # FastAPI app
│   ├── predictor.py      # AI prediction engine (3 models)
│   ├── infrastructure.py # Planning formula engine
│   ├── data_loader.py    # CSV data layer with caching
│   └── requirements.txt
├── data/
│   ├── population.csv    # Census data (1981–2021, 15 cities)
│   └── infrastructure.csv # 2021 baseline infrastructure
├── frontend/
│   ├── index.html        # Home page
│   ├── dashboard.html    # Prediction dashboard
│   ├── about.html        # Methodology
│   ├── sources.html      # Data sources
│   ├── css/style.css     # Design system
│   └── js/
│       ├── api.js        # Backend API client
│       └── charts.js     # Chart.js rendering
└── start_backend.bat
└── start_frontend.bat
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/cities` | List all available cities |
| GET | `/city/{name}` | City history + infrastructure |
| POST | `/predict` | **Full AI prediction** |

### Example prediction request:
```json
POST /predict
{
  "city": "Bangalore",
  "target_year": 2040
}
```

---

## AI Models

IDP compares 3 regression models per prediction:

1. **Linear Regression** — constant growth rate baseline
2. **Polynomial (deg 2)** — captures accelerating growth
3. **Exponential** — log-linearised compounding growth

The model with the highest **cross-validated R² score** is selected automatically.

---

## Cities Covered (V1)

Delhi · Mumbai · Bangalore · Chennai · Hyderabad · Pune · Kolkata ·
Ahmedabad · Surat · Jaipur · Lucknow · Kanpur · Nagpur · Indore · Thane

---

## Infrastructure Norms (V2 — Demographic-Aware)

| Metric | Tier 1 Metro | Tier 2 City | Applies To |
|--------|-------------|-------------|------------|
| Schools | 1 per 1,200 students | 1 per 800 students | Ages 5–17 (24.6% of pop) |
| Hospitals | 1 per 8,000 people | 1 per 10,000 people | Total population |
| Buses | 1 per 50 bus riders | 1 per 50 bus riders | Public bus commuters only (28% / 38% modal split) |
| Roads | 1 km per 1,000 people | 1 km per 800 people | Total population |

---

## Version History

| Tag | Description |
|-----|-------------|
| `v1.0-init` | Project scaffold + data CSVs |
| `v1.1-backend` | FastAPI working, /predict endpoint |
| `v1.2-frontend` | Dashboard + all 4 pages |
| `v1.3-complete` | Full end-to-end working |

---

## Roadmap

- **V2**: PostgreSQL integration, Prophet time-series, migration modelling
- **V3**: Leaflet.js map visualization, 50+ cities, user accounts
- **V4**: Vercel + Railway deployment
