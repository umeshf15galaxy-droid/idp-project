/**
 * api.js — Backend communication layer v2.
 * - Auto-detects local vs production environment.
 * - Keep-alive ping every 9 minutes to prevent Render free tier sleep.
 * - Proper error handling with user-friendly messages.
 */

// Local dev → localhost:8000 | Production → Render.com backend
const RENDER_BACKEND_URL = "https://idp-backend-r293.onrender.com";

const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "http://localhost:8000"
  : RENDER_BACKEND_URL;

// ── Keep-Alive: ping /health every 9 min so Render never sleeps ──
(function startKeepAlive() {
  const PING_INTERVAL_MS = 9 * 60 * 1000; // 9 minutes

  async function ping() {
    try {
      await fetch(`${API_BASE}/health`, {
        signal: AbortSignal.timeout(5000),
        cache:  "no-store",
      });
    } catch {
      // Silent — keep-alive is best-effort
    }
  }

  // First ping on page load (also wakes server early if sleeping)
  setTimeout(ping, 2000);
  // Recurring ping
  setInterval(ping, PING_INTERVAL_MS);
})();


/**
 * Fetch list of available cities.
 * @returns {Promise<{cities: string[], count: number}>}
 */
async function getCities() {
  const res = await fetch(`${API_BASE}/cities`);
  if (!res.ok) throw new Error("Failed to fetch city list. Please try again.");
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
 * @param {object|null} currentInfrastructure — optional override
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
    // Handle rate limit specifically
    if (res.status === 429) {
      throw new Error("⏳ Too many requests — please wait a moment before predicting again.");
    }
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}


/**
 * Health-check the backend (used for the online/offline indicator).
 * @returns {Promise<boolean>}
 */
async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      signal: AbortSignal.timeout(4000),
    });
    return res.ok;
  } catch {
    return false;
  }
}
