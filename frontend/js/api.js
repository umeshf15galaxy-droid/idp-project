/**
 * api.js — Backend communication layer.
 * All fetch calls to FastAPI live here. Frontend never touches the URL directly.
 */

// Local dev → localhost:8000 | Production → Render.com backend
const RENDER_BACKEND_URL = "https://idp-backend-r293.onrender.com";

const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "http://localhost:8000"
  : RENDER_BACKEND_URL;

/**
 * Fetch list of available cities.
 * @returns {Promise<{cities: string[], count: number}>}
 */
async function getCities() {
  const res = await fetch(`${API_BASE}/cities`);
  if (!res.ok) throw new Error("Failed to fetch cities");
  return res.json();
}

/**
 * Fetch historical + infrastructure data for one city.
 * @param {string} cityName
 * @returns {Promise<object>}
 */
async function getCityData(cityName) {
  const res = await fetch(`${API_BASE}/city/${encodeURIComponent(cityName)}`);
  if (!res.ok) throw new Error(`City data not found: ${cityName}`);
  return res.json();
}

/**
 * Run the full AI prediction pipeline.
 * @param {string} city
 * @param {number} targetYear
 * @param {object|null} currentInfrastructure  — optional override
 * @returns {Promise<object>}
 */
async function runPrediction(city, targetYear, currentInfrastructure = null) {
  const body = { city, target_year: targetYear };
  if (currentInfrastructure) body.current_infrastructure = currentInfrastructure;

  const res = await fetch(`${API_BASE}/predict`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

/**
 * Health-check the backend.
 * @returns {Promise<boolean>}
 */
async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/`, { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}
