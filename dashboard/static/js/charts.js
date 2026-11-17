// Chart.js theme + helpers (error bars for 95% CIs, reference line at 1.0x).
/* global Chart */
export const C = {
  text: "#c3c9d8", muted: "#8a94ac", grid: "rgba(138,148,172,.10)", border: "#222b40",
  ok: "#34d399", bad: "#f87171", warn: "#fbbf24", rl: "#f472b6", lib: "#60a5fa", o3: "#94a3b8",
  acc: "#8b5cf6", acc2: "#22d3ee", pred: "#a78bfa", ga: "#fb923c",
};

export function theme() {
  Chart.defaults.color = C.muted;
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.borderColor = C.grid;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.tooltip.backgroundColor = "#1a2236";
  Chart.defaults.plugins.tooltip.borderColor = "#2c3753";
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.titleColor = "#e7eaf3";
  Chart.defaults.plugins.tooltip.bodyColor = "#c3c9d8";
  Chart.defaults.maintainAspectRatio = false;
  Chart.register(errorBars, refLine);
}

// datasets may carry .ci = [[lo, hi] | null, ...]; drawn as whiskers on (horizontal or vertical) bars
const errorBars = {
  id: "errorBars",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    const horiz = chart.options.indexAxis === "y";
    chart.data.datasets.forEach((ds, di) => {
      if (!ds.ci || !chart.isDatasetVisible(di)) return;
      const meta = chart.getDatasetMeta(di);
      const vs = horiz ? chart.scales.x : chart.scales.y;
      ctx.save();
      ctx.strokeStyle = "rgba(231,234,243,.75)";
      ctx.lineWidth = 1.2;
      meta.data.forEach((bar, i) => {
        const c = ds.ci[i];
        if (!c || c[0] == null) return;
        const a = vs.getPixelForValue(c[0]), b = vs.getPixelForValue(c[1]);
        const m = horiz ? bar.y : bar.x, w = 4;
        ctx.beginPath();
        if (horiz) { ctx.moveTo(a, m); ctx.lineTo(b, m); ctx.moveTo(a, m - w); ctx.lineTo(a, m + w); ctx.moveTo(b, m - w); ctx.lineTo(b, m + w); }
        else { ctx.moveTo(m, a); ctx.lineTo(m, b); ctx.moveTo(m - w, a); ctx.lineTo(m + w, a); ctx.moveTo(m - w, b); ctx.lineTo(m + w, b); }
        ctx.stroke();
      });
      ctx.restore();
    });
  },
};

// options.plugins.refLine = { value: 1, label: "-O3" }
const refLine = {
  id: "refLine",
  afterDatasetsDraw(chart, _a, opt) {
    if (!opt || opt.value == null) return;
    const horiz = chart.options.indexAxis === "y";
    const s = horiz ? chart.scales.x : chart.scales.y;
    if (!s) return;
    const p = s.getPixelForValue(opt.value);
    const { ctx, chartArea: ca } = chart;
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = opt.color || "rgba(148,163,184,.7)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (horiz) { ctx.moveTo(p, ca.top); ctx.lineTo(p, ca.bottom); } else { ctx.moveTo(ca.left, p); ctx.lineTo(ca.right, p); }
    ctx.stroke();
    if (opt.label) {
      ctx.setLineDash([]);
      ctx.fillStyle = opt.color || "rgba(148,163,184,.9)";
      ctx.font = "600 11px Inter";
      if (horiz) ctx.fillText(opt.label, p + 4, ca.top + 11); else ctx.fillText(opt.label, ca.right - ctx.measureText(opt.label).width - 2, p - 5);
    }
    ctx.restore();
  },
};

const charts = new Map();
export function chart(canvas, cfg) {
  if (typeof canvas === "string") canvas = document.getElementById(canvas);
  if (!canvas) return null;
  if (charts.has(canvas)) charts.get(canvas).destroy();
  const c = new Chart(canvas, cfg);
  charts.set(canvas, c);
  return c;
}

export const speedAxis = (title = "speedup vs -O3", extra = {}) => ({
  title: { display: !!title, text: title, color: C.muted },
  grid: { color: C.grid }, ticks: { callback: (v) => `${Number(v).toFixed(2)}×` }, ...extra,
});
