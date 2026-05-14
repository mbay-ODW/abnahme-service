// Three stages: paste → (maybe) inputs → result.
// State.text is preserved across stages so we can re-submit with extra fields.

const $ = (id) => document.getElementById(id);

const state = {
  text: "",
  kunde: "",
  satz: null,
  datum: "",
};

const stages = {
  paste: $("stage-paste"),
  inputs: $("stage-inputs"),
  result: $("stage-result"),
};

function show(stage) {
  for (const k of Object.keys(stages)) stages[k].classList.add("hidden");
  stages[stage].classList.remove("hidden");
}

function setLoading(on) {
  $("loading").classList.toggle("hidden", !on);
}

function showError(msg) {
  const el = $("error");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 6000);
}

function parseSatz(value) {
  if (value == null || value === "") return null;
  const cleaned = String(value).replace(/[€\s]/g, "").replace(",", ".");
  const num = parseFloat(cleaned);
  return Number.isFinite(num) ? num : null;
}

async function postProcess(payload) {
  setLoading(true);
  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    return await res.json();
  } finally {
    setLoading(false);
  }
}

function fillKundenDatalist(customers) {
  const dl = $("kunden-list");
  dl.innerHTML = "";
  for (const c of customers || []) {
    const opt = document.createElement("option");
    opt.value = c.name;
    opt.dataset.satz = c.satz;
    dl.appendChild(opt);
  }
}

function renderInputs(data) {
  const fehl = new Set(data.fehlende_eingaben || []);
  const erk = data.erkannt || {};

  // Pre-fill what we know
  $("kunde").value = erk.kunde || state.kunde || "";
  $("satz").value = erk.satz
    ? String(erk.satz).replace(".", ",")
    : (state.satz != null ? String(state.satz).replace(".", ",") : "");
  $("datum").value = erk.datum || state.datum || "";

  // Hide rows that are already known
  $("datum-row").classList.toggle("hidden", !fehl.has("datum"));

  fillKundenDatalist(data.known_customers || []);

  // Auto-fill rate when picking a known customer
  $("kunde").oninput = () => {
    const val = $("kunde").value.trim().toLowerCase();
    const dl = $("kunden-list");
    for (const opt of dl.children) {
      if (opt.value.toLowerCase() === val && opt.dataset.satz) {
        $("satz").value = String(opt.dataset.satz).replace(".", ",");
        break;
      }
    }
  };

  const hints = [];
  if (fehl.has("kunde")) hints.push("Kunde fehlt");
  if (fehl.has("satz")) hints.push("Stundensatz fehlt");
  if (fehl.has("datum")) hints.push("Datum fehlt");
  $("hint-text").textContent = hints.length
    ? "Bitte ergänzen: " + hints.join(", ")
    : "Werte prüfen und bestätigen.";

  // Focus first empty field
  for (const id of ["kunde", "satz", "datum"]) {
    if (!$(id).value) { $(id).focus(); break; }
  }
}

function renderResult(data) {
  // PDF link + preview image
  $("pdf-link").href = data.pdf_url;
  $("fname").textContent = data.pdf_filename || "";
  $("result-preview").src = data.pdf_url + ".png?_=" + Date.now();

  // Warning
  if (data.plausibilitaets_warnung) {
    $("warn").textContent = "⚠ " + data.plausibilitaets_warnung;
    $("warn").classList.remove("hidden");
  } else {
    $("warn").classList.add("hidden");
  }

  // Buchungs-Tabelle
  const b = data.buchung || {};
  const t = $("buchung");
  t.innerHTML = "";

  const addRow = (label, hours, cls = "") => {
    const tr = document.createElement("tr");
    if (cls) tr.className = cls;
    const td1 = document.createElement("td");
    td1.textContent = label;
    const td2 = document.createElement("td");
    td2.textContent = formatH(hours);
    tr.appendChild(td1); tr.appendChild(td2);
    t.appendChild(tr);
  };

  addRow("Reguläre Stunden", b.regulaere_stunden_gesamt);

  if (b.nacht_zuschlag_stunden > 0) {
    addRow("+ Nachtzuschlag 30 %", b.nacht_zuschlag_stunden);
  }
  if (b.sonntag_zuschlag_stunden > 0) {
    addRow("+ Sonntagszuschlag 50 %", b.sonntag_zuschlag_stunden);
  }
  if (b.feiertag_zuschlag_stunden > 0) {
    addRow("+ Feiertagszuschlag 100 %", b.feiertag_zuschlag_stunden);
  }
  if (
    !b.nacht_zuschlag_stunden &&
    !b.sonntag_zuschlag_stunden &&
    !b.feiertag_zuschlag_stunden
  ) {
    const tr = document.createElement("tr");
    tr.className = "detail";
    const td = document.createElement("td");
    td.colSpan = 2;
    td.textContent = "Keine Nacht-/Sonntags-/Feiertagsstunden.";
    tr.appendChild(td);
    t.appendChild(tr);
  }

  addRow("Buchung gesamt", b.buchung_gesamt, "total");
}

function formatH(h) {
  if (h == null) return "—";
  return h.toLocaleString("de-DE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }) + " h";
}

// ---------- Event handlers ----------

$("btn-process").onclick = async () => {
  const text = $("msg").value.trim();
  if (!text) {
    showError("Bitte eine Nachricht einfügen.");
    return;
  }
  state.text = text;

  try {
    const data = await postProcess({ text });
    if (data.status === "needs_input") {
      renderInputs(data);
      show("inputs");
    } else {
      renderResult(data);
      show("result");
    }
  } catch (e) {
    showError("Fehler: " + e.message);
  }
};

$("btn-submit").onclick = async () => {
  const kunde = $("kunde").value.trim();
  const satz = parseSatz($("satz").value);
  const datum = $("datum").value.trim();

  if (!kunde) { showError("Kunde fehlt."); $("kunde").focus(); return; }
  if (satz == null) { showError("Stundensatz fehlt oder ungültig."); $("satz").focus(); return; }

  state.kunde = kunde;
  state.satz = satz;
  state.datum = datum;

  try {
    const data = await postProcess({
      text: state.text,
      kunde, satz, datum: datum || null,
    });
    if (data.status === "needs_input") {
      renderInputs(data);
      show("inputs");
      showError("Noch fehlende Angaben.");
    } else {
      renderResult(data);
      show("result");
    }
  } catch (e) {
    showError("Fehler: " + e.message);
  }
};

$("btn-back").onclick = () => show("paste");

$("btn-new").onclick = () => {
  $("msg").value = "";
  state.text = state.kunde = state.datum = "";
  state.satz = null;
  show("paste");
  $("msg").focus();
};

// Submit with Cmd/Ctrl+Enter from anywhere in the textarea
$("msg").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    $("btn-process").click();
  }
});

show("paste");
