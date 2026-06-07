const STORAGE_KEY = "microalgae_backend_url";

const state = {
  backend: localStorage.getItem(STORAGE_KEY) || "",
  manualLock: false,
};

const el = (id) => document.getElementById(id);

const commandText = {
  TREAT: "Treat water",
  FLUSH: "Flush intake",
  HOLD: "Hold",
  LOCKOUT: "Safety lockout",
};

const growthText = {
  SEALED_GROW: "Closed algae growth",
  LOW_LIGHT_SUPPORT: "Low-light support",
  MAINTENANCE: "Maintenance required",
  IDLE: "Idle",
};

const alertText = {
  NONE: "None",
  SENSOR_CHECK: "Check sensors",
  MANUAL_LOCKOUT: "Manual lockout",
  PH_ABNORMAL: "Unsafe pH",
  CLEAN_INTAKE: "Clean intake",
  LOW_DO: "Low oxygen",
  HARVEST_BIOFILM: "Service algae cartridge",
};

const reportReasonText = {
  first_report: "First report",
  scheduled_60s: "Scheduled 60-second update",
  web_demo: "Simulation button on dashboard",
  do_changed: "DO changed significantly",
  ph_changed: "pH changed significantly",
  turbidity_changed: "Turbidity changed significantly",
  sunlight_changed: "Light changed significantly",
  temperature_changed: "Temperature changed significantly",
  film_changed: "Film density changed significantly",
  alert_do_critical: "Critical low oxygen",
  alert_do_low: "Low oxygen",
  alert_ph_out_of_range: "Unsafe pH range",
  alert_turbidity_high: "High turbidity",
  alert_film_dense: "Dense algae cartridge",
};

function setConnection(text, kind = "default") {
  const pill = el("connection-pill");
  pill.textContent = text;
  pill.className = "pill";
  if (kind === "live") pill.classList.add("live");
  if (kind === "error") pill.classList.add("error");
}

function baseUrl(path) {
  if (!state.backend) return null;
  return `${state.backend.replace(/\/$/, "")}${path}`;
}

function metric(label, value) {
  return `
    <div class="metric">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `;
}

function stateItem(label, value) {
  return `
    <div class="state-item">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `;
}

function renderEmpty(message) {
  el("module-list").innerHTML = `<div class="empty-state">${message}</div>`;
}

function renderModules(modules = []) {
  if (!modules.length) {
    renderEmpty("No module data available yet.");
    return;
  }

  const ordered = [...modules].sort((a, b) => Number(b.sequence || 0) - Number(a.sequence || 0));
  el("module-list").innerHTML = ordered.map((module) => `
    <article class="module-card">
      <div class="module-head">
        <div>
          <div class="module-title">${module.module_id}</div>
          <div class="module-subtitle">${module.array_id} - ${module.time}</div>
        </div>
        <span class="command-badge ${module.command}">${commandText[module.command] || module.command}</span>
      </div>

      <div class="metric-grid">
        ${metric("DO", `${Number(module.dissolved_o2 || 0).toFixed(1)} mg/L`)}
        ${metric("pH", `${Number(module.ph || 0).toFixed(1)}`)}
        ${metric("Turbidity", `${Math.round(module.turbidity || 0)} NTU`)}
        ${metric("Sunlight", `${Math.round(module.sunlight || 0)} %`)}
        ${metric("Temperature", `${Number(module.temperature_c || 0).toFixed(1)} C`)}
        ${metric("Film density", `${Math.round(module.film_density || 0)} %`)}
      </div>

      <div class="reason-box">${module.reason || "No AI reason provided yet."}</div>

      <div class="state-grid">
        ${stateItem("Flow mode", module.flow_level || "-")}
        ${stateItem("Growth mode", growthText[module.growth_mode] || module.growth_mode || "-")}
        ${stateItem("Alert", alertText[module.alert] || module.alert || "None")}
        ${stateItem("Water score", module.quality_score ?? "-")}
        ${stateItem("Report reason", reportReasonText[module.report_reason] || module.report_reason || "-")}
      </div>
    </article>
  `).join("");
}

function renderSummary(data) {
  const modules = data.modules || [];
  const avg = modules.length
    ? (modules.reduce((sum, item) => sum + Number(item.dissolved_o2 || 0), 0) / modules.length).toFixed(1)
    : "--";
  const active = modules.filter((item) => item.command === "TREAT" || item.command === "FLUSH").length;
  const alerts = modules.filter((item) => item.alert && item.alert !== "NONE").length;

  el("module-count").textContent = String(modules.length);
  el("avg-do").textContent = avg;
  el("active-count").textContent = String(active);
  el("alert-count").textContent = String(alerts);
}

async function fetchJson(path, options) {
  const url = baseUrl(path);
  if (!url) throw new Error("No backend URL configured");
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function poll() {
  if (!state.backend) {
    renderEmpty("Save a backend URL to load module data.");
    setConnection("Disconnected");
    return;
  }

  try {
    const data = await fetchJson("/data");
    state.manualLock = Boolean(data.manual_lockout);
    renderSummary(data);
    renderModules(data.modules || []);
    setConnection("Connected", "live");
  } catch (error) {
    renderEmpty(`Could not reach backend: ${error.message}`);
    setConnection("Backend error", "error");
  }
}

async function simulate(scenario) {
  try {
    await fetchJson("/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario }),
    });
    poll();
  } catch (error) {
    setConnection("Simulation failed", "error");
  }
}

async function toggleLock() {
  try {
    await fetchJson("/manual_lock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locked: !state.manualLock }),
    });
    poll();
  } catch (error) {
    setConnection("Lock failed", "error");
  }
}

function init() {
  el("backend-url").value = state.backend;
  el("backend-status").textContent = state.backend
    ? `Saved backend: ${state.backend}`
    : "No backend saved yet.";

  el("backend-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const value = el("backend-url").value.trim().replace(/\/$/, "");
    state.backend = value;
    if (value) {
      localStorage.setItem(STORAGE_KEY, value);
      el("backend-status").textContent = `Saved backend: ${value}`;
    } else {
      localStorage.removeItem(STORAGE_KEY);
      el("backend-status").textContent = "Backend URL cleared.";
    }
    poll();
  });

  document.querySelectorAll("[data-sim]").forEach((button) => {
    button.addEventListener("click", () => simulate(button.dataset.sim));
  });

  el("manual-lock").addEventListener("click", toggleLock);

  poll();
  window.setInterval(poll, 10000);
}

init();
