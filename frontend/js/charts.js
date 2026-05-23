/**
 * charts.js — Chart.js rendering layer for IDP Dashboard.
 * All chart instances live here so they can be updated without re-creating.
 */

// ── Chart defaults ──
Chart.defaults.color = "#475569";
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;

const CHART_COLORS = {
  purple: "#7c3aed",
  blue:   "#3b82f6",
  cyan:   "#06b6d4",
  success:"#10b981",
  warning:"#f59e0b",
  danger: "#ef4444",
};

function gradientFill(ctx, color1, color2) {
  const grad = ctx.createLinearGradient(0, 0, 0, 300);
  grad.addColorStop(0, color1);
  grad.addColorStop(1, color2);
  return grad;
}

// ── Track instances so we can destroy/recreate ──
let populationChart = null;
let infraChart      = null;
let modelChart      = null;

/**
 * Render population growth chart:
 * Historical (solid) + Projected (dashed) + Confidence band.
 */
function renderPopulationChart(canvasId, historicalSeries, projectionSeries, confidence, targetYear) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  if (populationChart) { populationChart.destroy(); populationChart = null; }

  const histLabels = historicalSeries.map(d => d.year);
  const histData   = historicalSeries.map(d => d.population);
  const projLabels = projectionSeries.map(d => d.year);
  const projData   = projectionSeries.map(d => d.population);
  const confHigh   = projectionSeries.map(d => Math.round(d.population * (confidence.high / projectionSeries[projectionSeries.length - 1].population)));
  const confLow    = projectionSeries.map(d => Math.round(d.population * (confidence.low  / projectionSeries[projectionSeries.length - 1].population)));

  const allLabels = [...new Set([...histLabels, ...projLabels])].sort((a, b) => a - b);

  const gradient = ctx.getContext("2d").createLinearGradient(0, 0, 0, 400);
  gradient.addColorStop(0, "rgba(124,58,237,0.25)");
  gradient.addColorStop(1, "rgba(124,58,237,0)");

  const gradProj = ctx.getContext("2d").createLinearGradient(0, 0, 0, 400);
  gradProj.addColorStop(0, "rgba(59,130,246,0.2)");
  gradProj.addColorStop(1, "rgba(59,130,246,0)");

  populationChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: allLabels,
      datasets: [
        {
          label: "Historical Population",
          data: allLabels.map(y => {
            const point = historicalSeries.find(d => d.year === y);
            return point ? point.population : null;
          }),
          borderColor: CHART_COLORS.purple,
          backgroundColor: gradient,
          pointBackgroundColor: CHART_COLORS.purple,
          pointRadius: 6,
          pointHoverRadius: 8,
          fill: true,
          tension: 0.4,
          borderWidth: 2.5,
          spanGaps: false,
        },
        {
          label: "AI Projection",
          data: allLabels.map(y => {
            const point = projectionSeries.find(d => d.year === y);
            return point ? point.population : null;
          }),
          borderColor: CHART_COLORS.blue,
          backgroundColor: gradProj,
          pointBackgroundColor: CHART_COLORS.blue,
          pointRadius: 4,
          pointHoverRadius: 6,
          fill: true,
          tension: 0.4,
          borderWidth: 2.5,
          borderDash: [8, 4],
          spanGaps: false,
        },
        {
          label: "Confidence Band High",
          data: allLabels.map(y => {
            const idx = projLabels.indexOf(y);
            return idx >= 0 ? confHigh[idx] : null;
          }),
          borderColor: "rgba(59,130,246,0.2)",
          backgroundColor: "rgba(59,130,246,0.06)",
          fill: "+1",
          pointRadius: 0,
          borderWidth: 1,
          borderDash: [4, 4],
          tension: 0.4,
          spanGaps: false,
        },
        {
          label: "Confidence Band Low",
          data: allLabels.map(y => {
            const idx = projLabels.indexOf(y);
            return idx >= 0 ? confLow[idx] : null;
          }),
          borderColor: "rgba(59,130,246,0.2)",
          backgroundColor: "rgba(59,130,246,0.06)",
          fill: false,
          pointRadius: 0,
          borderWidth: 1,
          borderDash: [4, 4],
          tension: 0.4,
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: {
            filter: item => !item.text.includes("Confidence Band"),
            usePointStyle: true,
            pointStyle: "circle",
          },
        },
        tooltip: {
          backgroundColor: "rgba(255,255,255,0.98)",
          titleColor: "#0f172a",
          bodyColor: "#475569",
          borderColor: "#e2e8f0",
          borderWidth: 1,
          padding: 12,
          boxShadow: "0 4px 20px rgba(0,0,0,0.1)",
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#f1f5f9" },
          ticks: { color: "#64748b" },
        },
        y: {
          grid: { color: "#f1f5f9" },
          ticks: {
            color: "#64748b",
            callback: v => formatNumberShort(v),
          },
        },
      },
    },
  });
}

/**
 * Render horizontal bar chart: Required vs Current infrastructure.
 */
function renderInfraChart(canvasId, required, current, deficit) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  if (infraChart) { infraChart.destroy(); infraChart = null; }

  const labels = ["Schools", "Hospitals", "Buses", "Roads (km)"];
  const keys   = ["schools", "hospitals", "buses", "roads_km"];

  const reqVals = keys.map(k => required[k]);
  const curVals = keys.map(k => current[k]);

  infraChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Required",
          data: reqVals,
          backgroundColor: "rgba(124,58,237,0.7)",
          borderColor: CHART_COLORS.purple,
          borderWidth: 1.5,
          borderRadius: 6,
          borderSkipped: false,
        },
        {
          label: "Current",
          data: curVals,
          backgroundColor: "rgba(59,130,246,0.6)",
          borderColor: CHART_COLORS.blue,
          borderWidth: 1.5,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { usePointStyle: true, pointStyle: "circle" } },
        tooltip: {
          backgroundColor: "rgba(255,255,255,0.98)",
          titleColor: "#0f172a",
          bodyColor: "#475569",
          borderColor: "#e2e8f0",
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${formatNumber(ctx.parsed.x)}`,
            afterLabel: (ctx) => {
              const key = keys[ctx.dataIndex];
              const def = deficit[key];
              if (ctx.datasetIndex === 1 && def > 0) {
                return `  Deficit: ${formatNumber(def)}`;
              }
              return "";
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#f1f5f9" },
          ticks: { color: "#64748b", callback: v => formatNumberShort(v) },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#475569" },
        },
      },
    },
  });
}

/**
 * Render doughnut chart comparing model R² scores.
 */
function renderModelChart(canvasId, allModels) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  if (modelChart) { modelChart.destroy(); modelChart = null; }

  const labels = Object.keys(allModels).map(k => k.charAt(0).toUpperCase() + k.slice(1));
  const scores = Object.values(allModels).map(m => Math.max(0, m.r2_score));
  const colors = [CHART_COLORS.purple, CHART_COLORS.blue, CHART_COLORS.cyan];
  const selected = Object.values(allModels).findIndex(m => m.selected);

  modelChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: scores,
        backgroundColor: colors.map((c, i) => i === selected ? c : c + "66"),
        borderColor:     colors.map((c, i) => i === selected ? c : "transparent"),
        borderWidth: 2,
        hoverBorderWidth: 3,
        offset: scores.map((_, i) => i === selected ? 12 : 0),
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "70%",
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, padding: 16 } },
        tooltip: {
          callbacks: {
            label: ctx => ` R² Score: ${ctx.parsed.toFixed(4)}`,
          },
        },
      },
    },
  });
}

// ── Number formatting helpers ──
function formatNumber(n) {
  if (n == null || isNaN(n)) return "—";
  return new Intl.NumberFormat("en-IN").format(Math.round(n));
}

function formatNumberShort(n) {
  if (n >= 1e7) return (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return (n / 1e5).toFixed(1) + "L";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n;
}
