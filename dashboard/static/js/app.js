// Router + global status (environment, background queue).
import { api, icon } from "./util.js";
import { theme } from "./charts.js";
import * as run from "./run.js";
import * as research from "./research.js";
import * as arch from "./arch.js";

theme();
document.querySelectorAll("[data-ico]").forEach((e) => (e.innerHTML = icon[e.dataset.ico]));

const pages = { run, research, architecture: arch };
const inited = new Set();

function route() {
  const name = (location.hash.replace("#", "").split("/")[0]) || "run";
  const key = pages[name] ? name : "run";
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${key}`));
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === key));
  if (!inited.has(key)) {
    inited.add(key);
    pages[key].init(document.getElementById(`page-${key}`));
  }
  pages[key].show?.();
  window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", route);
route();

// ---- environment pill
export async function refreshEnv() {
  const dot = document.getElementById("env-dot"), txt = document.getElementById("env-text");
  dot.className = "dot live";
  txt.textContent = "checking…";
  try {
    const e = await api("/api/env");
    const bad = e.checks.filter((c) => !c.ok);
    dot.className = `dot ${bad.length === 0 ? "ok" : bad.every((c) => /quiet|selftest/.test(c.name)) ? "warn" : "bad"}`;
    txt.textContent = bad.length === 0 ? `ready · ${e.machine_id}` : `${bad.length} check${bad.length > 1 ? "s" : ""} need attention`;
    window.dispatchEvent(new CustomEvent("env", { detail: e }));
    return e;
  } catch (err) {
    dot.className = "dot bad";
    txt.textContent = "server unreachable";
    window.dispatchEvent(new CustomEvent("env", { detail: { error: String(err) } }));
  }
}
window.ncRefreshEnv = refreshEnv;
document.getElementById("env-pill").addEventListener("click", () => { location.hash = "#run"; refreshEnv(); });
document.getElementById("queue-pill").addEventListener("click", () => { location.hash = "#run"; document.getElementById("tasks-card")?.scrollIntoView({ behavior: "smooth" }); });
refreshEnv();

// ---- background queue pill (polled)
async function pollQueue() {
  try {
    const jobs = await api("/api/jobs");
    const running = jobs.filter((j) => j.status === "running"), queued = jobs.filter((j) => j.status === "queued");
    document.getElementById("queue-dot").className = `dot ${running.length ? "live" : ""}`;
    document.getElementById("queue-text").textContent = running.length
      ? `running ${running[0].mode}${queued.length ? ` · ${queued.length} queued` : ""}` : queued.length ? `${queued.length} queued` : "idle";
    window.dispatchEvent(new CustomEvent("jobs", { detail: jobs }));
  } catch (_) { /* server down: env pill shows it */ }
}
pollQueue();
setInterval(pollQueue, 2500);
