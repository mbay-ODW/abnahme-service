// Settings page – three tabs, talks to /api/{settings,skill,template}

const $ = (id) => document.getElementById(id);

function showLoading(text) {
  $("loading-text").textContent = text || "Lade…";
  $("loading").classList.remove("hidden");
}
function hideLoading() { $("loading").classList.add("hidden"); }

function toast(msg, kind = "info") {
  const t = $("toast");
  t.textContent = msg;
  t.className = `toast ${kind}`;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 4000);
}

// ---------- Tab switching ----------

for (const btn of document.querySelectorAll(".tab")) {
  btn.addEventListener("click", () => {
    for (const b of document.querySelectorAll(".tab")) b.classList.remove("active");
    btn.classList.add("active");
    for (const p of document.querySelectorAll(".tab-pane")) p.classList.add("hidden");
    $(`tab-${btn.dataset.tab}`).classList.remove("hidden");
  });
}

// ---------- General tab ----------

async function loadGeneral() {
  showLoading("Lade Einstellungen…");
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    // Der Klartext-Key wird bewusst nicht mehr ausgeliefert — das Feld bleibt leer,
    // der maskierte Wert steht im Placeholder. Leer lassen = Key unveraendert.
    $("api-key").value = "";
    $("api-key").placeholder = data.anthropic_api_key_masked || "sk-ant-…";
    $("model").value = data.anthropic_model;
    $("surcharge-night").value = data.surcharge_night_pct ?? 30;
    $("surcharge-sunday").value = data.surcharge_sunday_pct ?? 50;
    $("surcharge-holiday").value = data.surcharge_holiday_pct ?? 100;
  } finally {
    hideLoading();
  }
}

let keyVisible = false;
$("btn-toggle-key").onclick = () => {
  keyVisible = !keyVisible;
  $("api-key").type = keyVisible ? "text" : "password";
  $("btn-toggle-key").textContent = keyVisible ? "🙈" : "👁";
};

$("btn-save-general").onclick = async () => {
  showLoading("Speichere…");
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        anthropic_api_key: $("api-key").value.trim() || null,
        anthropic_model: $("model").value,
        surcharge_night_pct: parseFloat($("surcharge-night").value),
        surcharge_sunday_pct: parseFloat($("surcharge-sunday").value),
        surcharge_holiday_pct: parseFloat($("surcharge-holiday").value),
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    toast("Einstellungen gespeichert.", "success");
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
};

$("btn-test-key").onclick = async () => {
  const r = $("test-result");
  r.classList.add("hidden");
  showLoading("Teste API-Key…");
  try {
    const res = await fetch("/api/settings/test", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    r.textContent = `✓ API-Key ist gültig. Modell: ${data.model}`;
    r.className = "test-result success";
    r.classList.remove("hidden");
  } catch (e) {
    r.textContent = `✗ ${e.message}`;
    r.className = "test-result error";
    r.classList.remove("hidden");
  } finally {
    hideLoading();
  }
};

// ---------- Logo ----------

async function loadLogo() {
  const res = await fetch("/api/settings/logo/info");
  const info = await res.json();
  if (info.has_logo) {
    $("logo-preview").src = "/api/settings/logo?t=" + Date.now();
    $("logo-preview-wrap").classList.remove("hidden");
    $("logo-upload-zone").classList.add("hidden");
  } else {
    $("logo-preview-wrap").classList.add("hidden");
    $("logo-upload-zone").classList.remove("hidden");
  }
}

function setLogoStatus(msg, kind = "info") {
  const el = $("logo-status");
  el.textContent = msg;
  el.className = kind;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 4000);
}

async function uploadLogo(file) {
  const fd = new FormData();
  fd.append("file", file);
  showLoading("Logo hochladen…");
  try {
    const res = await fetch("/api/settings/logo", { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Fehler beim Hochladen");
    }
    toast("Logo gespeichert.", "success");
    await loadLogo();
  } catch (e) {
    setLogoStatus(`✗ ${e.message}`, "error");
  } finally {
    hideLoading();
  }
}

$("logo-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) uploadLogo(file);
  e.target.value = "";  // allow re-selecting the same file
});

// Whole zone is clickable (and drag & drop) — opens the file picker.
// Guard against the programmatic input.click() bubbling back here (the hidden
// input is a child of the zone), which would recurse and suppress the dialog.
const logoZone = $("logo-upload-zone");
logoZone.addEventListener("click", (e) => {
  if (e.target === $("logo-file")) return;
  $("logo-file").click();
});
logoZone.addEventListener("dragover", (e) => { e.preventDefault(); logoZone.classList.add("drag-over"); });
logoZone.addEventListener("dragleave", () => logoZone.classList.remove("drag-over"));
logoZone.addEventListener("drop", (e) => {
  e.preventDefault();
  logoZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) uploadLogo(file);
});

$("btn-delete-logo").addEventListener("click", async () => {
  if (!confirm("Logo wirklich entfernen?")) return;
  showLoading("Entferne Logo…");
  try {
    const res = await fetch("/api/settings/logo", { method: "DELETE" });
    if (!res.ok) throw new Error("Fehler beim Löschen");
    toast("Logo entfernt.", "success");
    await loadLogo();
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
});

// ---------- Signature ----------

async function loadSignature() {
  const res = await fetch("/api/settings/signature/info");
  const info = await res.json();
  if (info.has_signature) {
    $("signature-preview").src = "/api/settings/signature?t=" + Date.now();
    $("signature-preview-wrap").classList.remove("hidden");
    $("signature-upload-zone").classList.add("hidden");
  } else {
    $("signature-preview-wrap").classList.add("hidden");
    $("signature-upload-zone").classList.remove("hidden");
  }
}

function setSignatureStatus(msg, kind = "info") {
  const el = $("signature-status");
  el.textContent = msg;
  el.className = kind;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 4000);
}

async function uploadSignature(file) {
  const fd = new FormData();
  fd.append("file", file);
  showLoading("Unterschrift hochladen…");
  try {
    const res = await fetch("/api/settings/signature", { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Fehler beim Hochladen");
    }
    toast("Unterschrift gespeichert.", "success");
    await loadSignature();
  } catch (e) {
    setSignatureStatus(`✗ ${e.message}`, "error");
  } finally {
    hideLoading();
  }
}

$("signature-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) uploadSignature(file);
  e.target.value = "";  // allow re-selecting the same file
});

// Whole zone is clickable (and drag & drop) — opens the file picker.
// Guard against the programmatic input.click() bubbling back here (the hidden
// input is a child of the zone), which would recurse and suppress the dialog.
const sigZone = $("signature-upload-zone");
sigZone.addEventListener("click", (e) => {
  if (e.target === $("signature-file")) return;
  $("signature-file").click();
});
sigZone.addEventListener("dragover", (e) => { e.preventDefault(); sigZone.classList.add("drag-over"); });
sigZone.addEventListener("dragleave", () => sigZone.classList.remove("drag-over"));
sigZone.addEventListener("drop", (e) => {
  e.preventDefault();
  sigZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) uploadSignature(file);
});

$("btn-delete-signature").addEventListener("click", async () => {
  if (!confirm("Unterschrift wirklich entfernen?")) return;
  showLoading("Entferne Unterschrift…");
  try {
    const res = await fetch("/api/settings/signature", { method: "DELETE" });
    if (!res.ok) throw new Error("Fehler beim Löschen");
    toast("Unterschrift entfernt.", "success");
    await loadSignature();
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
});

// ---------- Skill tab ----------

let skillOriginal = "";
let diffVisible = false;

async function loadSkill() {
  showLoading("Lade Skill…");
  try {
    const res = await fetch("/api/skill");
    const data = await res.json();
    $("skill-editor").value = data.content || "";
    skillOriginal = data.original || "";
  } finally {
    hideLoading();
  }
}

$("btn-save-skill").onclick = async () => {
  showLoading("Speichere Skill…");
  try {
    const res = await fetch("/api/skill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: $("skill-editor").value }),
    });
    if (!res.ok) throw new Error(await res.text());
    toast("Skill gespeichert.", "success");
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
};

$("btn-reset-skill").onclick = async () => {
  if (!confirm("Skill auf Original zurücksetzen? Deine Änderungen gehen verloren.")) return;
  showLoading("Setze zurück…");
  try {
    const res = await fetch("/api/skill/reset", { method: "POST" });
    const data = await res.json();
    $("skill-editor").value = data.content;
    toast("Skill auf Original zurückgesetzt.", "success");
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
};

$("btn-toggle-diff").onclick = () => {
  diffVisible = !diffVisible;
  const pane = $("skill-diff");
  if (!diffVisible) {
    pane.classList.add("hidden");
    $("btn-toggle-diff").textContent = "Diff anzeigen";
    return;
  }
  pane.textContent = simpleDiff(skillOriginal, $("skill-editor").value);
  pane.classList.remove("hidden");
  $("btn-toggle-diff").textContent = "Diff verstecken";
};

function simpleDiff(a, b) {
  // Line-by-line diff. Good enough for a settings UI.
  const A = a.split("\n");
  const B = b.split("\n");
  const out = [];
  const max = Math.max(A.length, B.length);
  for (let i = 0; i < max; i++) {
    if (A[i] === B[i]) continue;
    if (A[i] !== undefined) out.push(`- ${A[i]}`);
    if (B[i] !== undefined) out.push(`+ ${B[i]}`);
  }
  return out.length ? out.join("\n") : "Keine Änderungen.";
};

// ---------- Template tab ----------

async function loadTemplate() {
  showLoading("Lade Vorlage…");
  try {
    const res = await fetch("/api/template");
    const data = await res.json();
    $("positions-editor").value = JSON.stringify(data.positions, null, 2);
    // Force preview reload with cache-buster
    $("template-preview").src = `/api/template/preview.png?_=${Date.now()}`;
  } finally {
    hideLoading();
  }
}

function setupUpload() {
  const zone = $("upload-zone");
  const input = $("template-file");

  $("btn-pick-file").onclick = (e) => { e.preventDefault(); input.click(); };
  input.onchange = () => { if (input.files[0]) handleUpload(input.files[0]); };

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragging");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragging");
    const f = e.dataTransfer.files[0];
    if (f) handleUpload(f);
  });
}

async function handleUpload(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    toast("Nur PDF-Dateien.", "error");
    return;
  }
  const fd = new FormData();
  fd.append("file", file);
  showLoading("Vorlage hochladen + analysieren …");
  $("upload-status").classList.add("hidden");
  try {
    const res = await fetch("/api/template/upload?analyze=true", {
      method: "POST", body: fd,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    const status = $("upload-status");
    status.classList.remove("hidden");
    if (data.analyzed) {
      status.className = "test-result success";
      status.textContent = "✓ Vorlage hochgeladen und analysiert. Prüfe die Vorschau unten.";
      await loadTemplate();
    } else {
      status.className = "test-result error";
      status.textContent = `Vorlage hochgeladen, aber Analyse fehlgeschlagen: ${data.error || "unbekannt"}. Du kannst die Positionen manuell editieren (JSON-Editor unten).`;
      await loadTemplate();
    }
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
}

$("btn-save-positions").onclick = async () => {
  let positions;
  try {
    positions = JSON.parse($("positions-editor").value);
  } catch (e) {
    toast(`JSON ungültig: ${e.message}`, "error");
    return;
  }
  showLoading("Speichere Positionen…");
  try {
    const res = await fetch("/api/template/positions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ positions }),
    });
    if (!res.ok) throw new Error(await res.text());
    toast("Positionen gespeichert.", "success");
    $("template-preview").src = `/api/template/preview.png?_=${Date.now()}`;
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
};

$("btn-reset-template").onclick = async () => {
  if (!confirm("Vorlage und Positionen auf Default zurücksetzen?")) return;
  showLoading("Setze zurück…");
  try {
    const res = await fetch("/api/template/reset", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    toast("Default wiederhergestellt.", "success");
    await loadTemplate();
  } catch (e) {
    toast(`Fehler: ${e.message}`, "error");
  } finally {
    hideLoading();
  }
};

// ---------- Init ----------

setupUpload();
loadGeneral();
loadLogo();
loadSignature();
loadSkill();
loadTemplate();

// ---------- Help tab ----------

let helpLoaded = false;
async function loadHelp() {
  if (helpLoaded) return;
  helpLoaded = true;
  try {
    const res = await fetch("/help.md", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const md = await res.text();
    $("help-content").innerHTML = renderMarkdown(md);
  } catch (e) {
    $("help-content").innerHTML =
      `<p class="error">Hilfe konnte nicht geladen werden: ${escapeHtml(e.message)}</p>`;
  }
}

// Lazy-load help when the tab is first opened
for (const btn of document.querySelectorAll(".tab")) {
  if (btn.dataset.tab === "help") {
    btn.addEventListener("click", loadHelp);
  }
}

// ---------- Tiny Markdown renderer ----------
// Covers what help.md uses: headings, bold/italic, inline code, code blocks,
// links, ordered/unordered lists, tables, blockquotes, hr. Not a general
// solution — keep help.md to these features.

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;",
    '"': "&quot;", "'": "&#39;",
  }[c]));
}

function inline(s) {
  // order matters: code first to avoid double-escaping inside it
  s = escapeHtml(s);
  // Inline code
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Bold + italic
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|\s)\*([^*\s][^*]*)\*(?=\s|[.,;:!?)]|$)/g,
    "$1<em>$2</em>");
  // Links [text](url)
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

function renderMarkdown(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  let out = "";
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code fence
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      i++;
      let code = "";
      while (i < lines.length && !lines[i].startsWith("```")) {
        code += lines[i] + "\n";
        i++;
      }
      i++; // skip closing fence
      out += `<pre class="code-block"><code${lang ? ` data-lang="${escapeHtml(lang)}"` : ""}>${escapeHtml(code)}</code></pre>`;
      continue;
    }

    // Headings
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      out += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`;
      i++;
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim()) && line.trim().length >= 3) {
      out += "<hr/>";
      i++;
      continue;
    }

    // Table — header line followed by separator
    if (line.includes("|") && i + 1 < lines.length &&
        /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const header = line.split("|").map(c => c.trim()).filter(Boolean);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(lines[i].split("|").map(c => c.trim()).filter(Boolean));
        i++;
      }
      out += "<table><thead><tr>" +
        header.map(c => `<th>${inline(c)}</th>`).join("") +
        "</tr></thead><tbody>" +
        rows.map(r => "<tr>" + r.map(c => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") +
        "</tbody></table>";
      continue;
    }

    // Lists (unordered + ordered) — items may span multiple lines if
    // continuation lines are indented (2+ spaces) and don't start a new
    // block element.
    const isUl = /^\s*[-*]\s+/.test(line);
    const isOl = /^\s*\d+\.\s+/.test(line);
    if (isUl || isOl) {
      const tag = isUl ? "ul" : "ol";
      const itemRe = isUl ? /^\s*[-*]\s+/ : /^\s*\d+\.\s+/;
      out += `<${tag}>`;
      while (i < lines.length) {
        if (!itemRe.test(lines[i])) break;
        let content = lines[i].replace(itemRe, "");
        i++;
        // Append continuation lines (indented, non-empty, no new marker)
        while (i < lines.length &&
               lines[i].trim() !== "" &&
               /^\s{2,}\S/.test(lines[i]) &&
               !/^\s*(?:[-*]|\d+\.)\s+/.test(lines[i])) {
          content += " " + lines[i].trim();
          i++;
        }
        out += `<li>${inline(content)}</li>`;
      }
      out += `</${tag}>`;
      continue;
    }

    // Blockquote
    if (line.startsWith(">")) {
      let q = "";
      while (i < lines.length && lines[i].startsWith(">")) {
        q += lines[i].slice(1).trim() + " ";
        i++;
      }
      out += `<blockquote>${inline(q.trim())}</blockquote>`;
      continue;
    }

    // Empty line — paragraph break
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph: collect consecutive non-empty, non-special lines
    let para = line;
    i++;
    while (i < lines.length && lines[i].trim() !== "" &&
           !/^(#{1,4}\s|[-*]\s|\d+\.\s|>|```|---)/.test(lines[i]) &&
           !lines[i].includes("|")) {
      para += " " + lines[i];
      i++;
    }
    out += `<p>${inline(para)}</p>`;
  }

  return out;
}
