"use strict";

// -- tiny API client ---------------------------------------------------------------------

async function api(path, options) {
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const detail = body && (body.detail || JSON.stringify(body.errors)) || res.statusText;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.body = body;
    throw err;
  }
  return body;
}

const get = (path) => api(path);
const post = (path, payload) => api(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

// -- DOM helpers ---------------------------------------------------------------------------

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children || []) {
    if (child) node.appendChild(child);
  }
  return node;
}

function clear(node) { node.innerHTML = ""; }

function showError(container, err) {
  container.appendChild(el("div", { class: "error-box", text: String(err.message || err) }));
}

/** A <details>/<summary> collapsible section. `open` controls whether it starts expanded. */
function collapsible(title, children, { open = false, className = "" } = {}) {
  return el("details", { class: `collapsible ${className}`.trim(), ...(open ? { open: "" } : {}) }, [
    el("summary", { text: title }),
    el("div", { class: "collapsible-body" }, children),
  ]);
}

// -- app state -----------------------------------------------------------------------------

const state = { branches: {}, tags: {}, activeRef: null, health: null };
const view = document.getElementById("view");

/** A branch or tag entry in the sidebar, with an icon distinguishing which it is and an
 * "active" state showing which one is currently open in the log view.
 */
function refBtn(name, icon) {
  return el("button", {
    "data-ref": name,
    class: name === state.activeRef ? "active" : "",
    onclick: () => navigate(`/app/historique/${encodeURIComponent(name)}`),
  }, [
    el("span", { class: "ref-icon", text: icon }),
    el("span", { class: "ref-name", text: name }),
  ]);
}

/** Re-mark whichever sidebar ref button matches state.activeRef, without refetching branches/tags. */
function highlightActiveRef() {
  document.querySelectorAll("#branch-list button, #tag-list button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.ref === state.activeRef);
  });
}

async function refreshSidebar() {
  const health = await get("/api/health");
  state.health = health;
  document.getElementById("repo-meta").textContent = `${health.repo} · ${health.experiments} expérience(s)`;
  state.branches = await get("/api/branches");
  state.tags = await get("/api/tags");

  const branchList = document.getElementById("branch-list");
  clear(branchList);
  for (const name of Object.keys(state.branches).sort()) {
    branchList.appendChild(el("li", {}, [refBtn(name, "⎇")]));
  }
  const tagList = document.getElementById("tag-list");
  clear(tagList);
  for (const name of Object.keys(state.tags).sort()) {
    tagList.appendChild(el("li", {}, [refBtn(name, "🏷")]));
  }
}

document.getElementById("btn-new").addEventListener("click", () => navigate("/app/nouvelle"));
document.getElementById("btn-merge").addEventListener("click", () => navigate("/app/fusionner"));
document.getElementById("btn-refs").addEventListener("click", () => navigate("/app/refs"));
document.getElementById("entity-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = document.getElementById("entity-input").value.trim();
  if (id) navigate(`/app/entite/${encodeURIComponent(id)}`);
});

// -- router: real, bookmarkable URLs under /app -----------------------------------------------
//
// The server (see follow/api/app.py's app_shell) serves this same page for "/app" and every
// "/app/<anything>", so a deep link, a page refresh or the browser's back/forward all land here
// with the right URL already in place; this router reads that URL and renders the matching view.

function navigate(path) {
  if (location.pathname + location.search !== path) history.pushState({}, "", path);
  router();
}
window.addEventListener("popstate", router);

function setActiveNav(routeName) {
  document.querySelectorAll("#topnav [data-route]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.route === `/app/${routeName}` || (routeName === "" && btn.dataset.route === "/app"));
  });
}

function router() {
  const path = location.pathname.replace(/^\/app\/?/, "");
  const params = new URLSearchParams(location.search);
  const segments = path.split("/").filter(Boolean).map(decodeURIComponent);
  setActiveNav(segments[0] || "");
  clear(view);

  if (segments.length === 0) return showDashboard();
  if (segments[0] === "en-cours") return showExperimentsList("running", parseInt(params.get("offset") || "0", 10));
  if (segments[0] === "terminees") return showExperimentsList("completed", parseInt(params.get("offset") || "0", 10));
  if (segments[0] === "graphe") return showGraph();
  if (segments[0] === "exemples") return showExamples();
  if (segments[0] === "historique" && segments[1]) return showLog(segments[1], parseInt(params.get("offset") || "0", 10));
  if (segments[0] === "experience" && segments[1]) return showExperiment(segments[1]);
  if (segments[0] === "nouvelle") return showNewExperimentForm();
  if (segments[0] === "deriver" && segments[1]) return showDeriveFormFor(segments[1]);
  if (segments[0] === "fusionner") return showMergeForm();
  if (segments[0] === "refs") return showRefsForm();
  if (segments[0] === "entite" && segments[1]) return showEntityTrace(segments[1]);
  view.appendChild(el("h1", { text: "Page introuvable" }));
  view.appendChild(el("p", { class: "muted", text: `Aucune route ne correspond à /app/${path}.` }));
}

document.querySelectorAll("#topnav [data-route]").forEach((btn) => {
  btn.addEventListener("click", () => navigate(btn.dataset.route));
});

// -- dashboard --------------------------------------------------------------------------------

function showDashboard() {
  view.appendChild(el("h1", { text: "Tableau de bord" }));
  const health = state.health;
  if (!health) return;

  const grid = el("div", { class: "stat-grid" }, [
    el("div", { class: "stat-tile", onclick: () => navigate("/app/en-cours") }, [
      el("span", { class: "n", text: String(health.running) }),
      el("span", { class: "label", text: "en cours" }),
    ]),
    el("div", { class: "stat-tile", onclick: () => navigate("/app/terminees") }, [
      el("span", { class: "n", text: String(health.completed) }),
      el("span", { class: "label", text: "terminées" }),
    ]),
    el("div", { class: "stat-tile", onclick: () => navigate("/app/graphe") }, [
      el("span", { class: "n", text: String(health.experiments) }),
      el("span", { class: "label", text: "expériences au total" }),
    ]),
    el("div", { class: "stat-tile", onclick: () => navigate("/app/refs") }, [
      el("span", { class: "n", text: String(health.branches) }),
      el("span", { class: "label", text: "branche(s)" }),
    ]),
  ]);
  view.appendChild(grid);

  view.appendChild(el("div", { class: "toolbar" }, [
    el("button", { text: "+ Nouvelle expérience", onclick: () => navigate("/app/nouvelle") }),
    el("button", { class: "secondary", text: "Graphe de filiation", onclick: () => navigate("/app/graphe") }),
    el("button", { class: "secondary", text: "Exemples", onclick: () => navigate("/app/exemples") }),
  ]));

  if (health.failed_structure_imports && health.failed_structure_imports.length > 0) {
    view.appendChild(el("div", { class: "error-box", text: `Modules de structure non importés : ${health.failed_structure_imports.join(", ")}` }));
  }

  const first = Object.keys(state.branches)[0];
  if (!first) {
    view.appendChild(el("p", { class: "muted", text: "Dépôt vide — créez une première expérience pour commencer." }));
  }
}

// -- log / detail views ----------------------------------------------------------------------

const LOG_PAGE_SIZE = 25;

async function showLog(ref, offset = 0) {
  state.activeRef = ref;
  highlightActiveRef();
  clear(view);
  view.appendChild(el("h1", { text: `Historique — ${ref}` }));
  const card = el("div", { class: "card" });
  view.appendChild(card);
  try {
    const page = await get(`/api/log/${encodeURIComponent(ref)}?offset=${offset}&limit=${LOG_PAGE_SIZE}`);
    if (page.total === 0) card.appendChild(el("p", { class: "muted", text: "Aucune expérience." }));
    for (const exp of page.items) {
      card.appendChild(el("div", {
        class: "log-entry",
        onclick: () => navigate(`/app/experience/${encodeURIComponent(exp.id)}`),
      }, [
        el("span", { class: "id", text: exp.id.slice(0, 10) }),
        el("span", { text: exp.title }),
        el("span", { class: "status", text: `[${exp.conclusion.status}]` }),
      ]));
    }

    const shown = page.offset + page.items.length;
    if (page.total > 0) {
      const pager = el("div", { class: "toolbar" }, [
        el("span", { class: "muted", text: `${shown} / ${page.total}` }),
        offset > 0
          ? el("button", { class: "secondary", text: "← précédent", onclick: () => navigate(`/app/historique/${encodeURIComponent(ref)}?offset=${Math.max(0, offset - LOG_PAGE_SIZE)}`) })
          : null,
        shown < page.total
          ? el("button", { class: "secondary", text: "suivant →", onclick: () => navigate(`/app/historique/${encodeURIComponent(ref)}?offset=${offset + LOG_PAGE_SIZE}`) })
          : null,
      ]);
      view.appendChild(pager);
    }
  } catch (err) {
    showError(view, err);
  }
}

async function showExperiment(id) {
  clear(view);
  try {
    const data = await get(`/api/experiments/${encodeURIComponent(id)}`);
    const exp = data.experiment;
    view.appendChild(el("h1", { text: exp.title }));

    if (data.entity_ids && data.entity_ids.length > 0) {
      view.appendChild(el("div", { class: "entity-badges" }, data.entity_ids.map((id) => el("a", {
        class: "entity-badge",
        href: `/app/entite/${encodeURIComponent(id)}`,
        onclick: (e) => { e.preventDefault(); navigate(`/app/entite/${encodeURIComponent(id)}`); },
        text: `🏷️ ${id}`,
      }))));
    }

    const toolbar = el("div", { class: "toolbar" }, [
      el("button", { text: "Dériver →", onclick: () => navigate(`/app/deriver/${encodeURIComponent(exp.id)}`) }),
      el("button", { class: "secondary", text: "← Historique", onclick: () => navigate(`/app/historique/${encodeURIComponent(state.activeRef || exp.branch)}`) }),
    ]);
    view.appendChild(toolbar);

    const baseline = (exp.references || []).find((r) => r.role === "baseline" && r.experiment_id);
    if (baseline) {
      const diffCard = el("div", { class: "card" }, [
        el("h2", { text: `Diff vs référence ${baseline.experiment_id.slice(0, 10)}` }),
      ]);
      try {
        const diff = await get(`/api/diff?a=${encodeURIComponent(baseline.experiment_id)}&b=${encodeURIComponent(exp.id)}`);
        if (diff.entries.length === 0) {
          diffCard.appendChild(el("p", { class: "muted", text: "Aucun changement." }));
        }
        for (const entry of diff.entries) {
          const cls = entry.kind === "added" ? "diff-added" : entry.kind === "removed" ? "diff-removed" : "diff-changed";
          const sign = entry.kind === "added" ? "+" : entry.kind === "removed" ? "-" : "~";
          const text = entry.kind === "changed"
            ? `${sign} ${entry.path}: ${JSON.stringify(entry.before)} → ${JSON.stringify(entry.after)}`
            : `${sign} ${entry.path}: ${JSON.stringify(entry.kind === "added" ? entry.after : entry.before)}`;
          diffCard.appendChild(el("div", { class: `diff-entry ${cls}`, text }));
        }
      } catch (err) {
        diffCard.appendChild(el("p", { class: "muted", text: "diff indisponible: " + err.message }));
      }
      view.appendChild(diffCard);
    }

    for (const field of data.batch_fields || []) {
      const panelBody = el("div", { class: "muted" }, [el("span", { class: "spinner" }), el("span", { text: "chargement…" })]);
      view.appendChild(collapsible(`Matrice de split — ${field}`, [panelBody]));
      get(`/api/experiments/${encodeURIComponent(exp.id)}/batch/${encodeURIComponent(field)}`)
        .then((result) => { clear(panelBody); panelBody.appendChild(renderDoeResultTable(result, { entityWord: "au total" })); })
        .catch((err) => { clear(panelBody); showError(panelBody, err); });
    }

    view.appendChild(el("pre", { class: "fiche", text: data.fiche_markdown }));
  } catch (err) {
    showError(view, err);
  }
}

// -- schema-driven form builder ---------------------------------------------------------------

function resolveSchema(node, defs) {
  if (node && node.$ref) {
    const key = node.$ref.replace("#/$defs/", "");
    return resolveSchema(defs[key], defs);
  }
  if (node && node.anyOf) {
    const nonNull = node.anyOf.find((n) => n.type !== "null" && !(n.$ref && defs[n.$ref.replace("#/$defs/", "")]?.type === "null"));
    return resolveSchema(nonNull || node.anyOf[0], defs);
  }
  return node || {};
}

/** Append a label + a built field to `wrap`, for one property of an object schema.
 * entity_id is a convention (see follow.entities), not a schema feature - a plain string field
 * a domain author names "entity_id" to mean "this is the physical thing's name". Highlighting it
 * here is the only way the GUI can point that out at all, since nothing about the JSON Schema
 * itself distinguishes it from any other string field.
 */
function appendLabeledField(wrap, key, propSchema, required, field, prefix = "") {
  // Prefer the *field's own* title (set on the property in the parent schema) over the title
  // baked into whatever it $ref's to - a property typed `temperature: Quantity` dereferences to
  // Quantity's own schema, whose title is "Quantity", not "Temperature"; only a bare, title-less
  // property should fall back to its key name.
  const label = propSchema && propSchema.title ? propSchema.title : key.replace(/_/g, " ");
  const isEntityId = key === "entity_id";
  const fieldWrap = isEntityId ? el("div", { class: "entity-field" }) : wrap;
  fieldWrap.appendChild(el("label", { text: `${isEntityId ? "🏷️ " : ""}${prefix}${label}${required ? " *" : ""}` }));
  fieldWrap.appendChild(field.element);
  if (isEntityId) {
    fieldWrap.appendChild(el("p", { class: "muted", text: "Identifiant physique (moule, wafer, échantillon...) - retrouvable ensuite via Entité, même sur une autre branche." }));
    wrap.appendChild(fieldWrap);
  }
}

/** Build a form for one JSON-schema node. Returns {element, getValue()}. */
function buildSchemaField(node, defs, initial) {
  const resolved = resolveSchema(node, defs);
  const type = resolved.type;

  if (type === "object" && resolved.properties) {
    // A Quantity (value/unit/uncertainty/note) is by far the most common leaf in a structure -
    // every measured or specified field is one. Rendered through the generic path below it costs
    // four full-width stacked label+input pairs; a form with a dozen such fields becomes an
    // unreadable wall. Detected structurally (by its exact property set, not by title, since a
    // title is metadata that user-defined schemas may not set) so it collapses into one compact
    // row instead: value | unit | ± uncertainty | note.
    const propNames = Object.keys(resolved.properties).sort().join(",");
    if (propNames === "note,uncertainty,unit,value") {
      const valueField = buildSchemaField(resolved.properties.value, defs, initial ? initial.value : undefined);
      valueField.element.setAttribute("placeholder", "valeur");
      const unitInput = el("input", { type: "text", placeholder: "unité" });
      if (initial && initial.unit) unitInput.value = initial.unit;
      const uncertaintyInput = el("input", { type: "number", step: "any", placeholder: "± incertitude" });
      if (initial && initial.uncertainty !== undefined && initial.uncertainty !== null) uncertaintyInput.value = initial.uncertainty;
      const noteInput = el("input", { type: "text", placeholder: "note" });
      if (initial && initial.note) noteInput.value = initial.note;

      const wrap = el("div", { class: "quantity-row" }, [
        el("div", { class: "quantity-value" }, [valueField.element]),
        el("div", { class: "quantity-unit" }, [unitInput]),
        el("div", { class: "quantity-uncertainty" }, [uncertaintyInput]),
        el("div", { class: "quantity-note" }, [noteInput]),
      ]);
      return {
        element: wrap,
        getValue() {
          const value = valueField.getValue();
          if (value === undefined || value === "") return undefined;
          const out = { value };
          if (unitInput.value.trim()) out.unit = unitInput.value.trim();
          if (uncertaintyInput.value !== "") out.uncertainty = parseFloat(uncertaintyInput.value);
          if (noteInput.value.trim()) out.note = noteInput.value.trim();
          return out;
        },
      };
    }

    const rows = {};
    const wrap = el("div", {});
    for (const [key, propSchema] of Object.entries(resolved.properties)) {
      const required = (resolved.required || []).includes(key);
      const field = buildSchemaField(propSchema, defs, initial ? initial[key] : undefined);
      appendLabeledField(wrap, key, propSchema, required, field);
      rows[key] = field;
    }
    return {
      element: wrap,
      getValue() {
        const out = {};
        for (const [key, field] of Object.entries(rows)) {
          const v = field.getValue();
          if (v !== undefined) out[key] = v;
        }
        return out;
      },
    };
  }

  if (type === "object" && !resolved.properties) {
    // a free-form mapping (dict[str, X]) - no fixed field names, but additionalProperties
    // still says what *each value* looks like, so a key/value editor can build a proper
    // field per entry instead of asking the user to hand-write JSON.
    const valueSchema = typeof resolved.additionalProperties === "object" ? resolved.additionalProperties : {};
    const list = el("div", {});
    const rows = [];

    function addRow(key, value) {
      const keyInput = el("input", { type: "text", placeholder: "clé" });
      keyInput.value = key || "";
      const field = buildSchemaField(valueSchema, defs, value);
      const row = el("div", { class: "array-item" }, [
        el("button", { class: "remove", type: "button", text: "✕", onclick: () => { row.remove(); rows.splice(rows.indexOf(entry), 1); } }),
        el("label", { text: "clé" }), keyInput,
        field.element,
      ]);
      const entry = { row, keyInput, field };
      rows.push(entry);
      list.appendChild(row);
    }

    Object.entries(initial || {}).forEach(([k, v]) => addRow(k, v));

    const wrap = el("div", {}, [
      list,
      el("button", { type: "button", class: "secondary", text: "+ ajouter une entrée", onclick: () => addRow() }),
    ]);
    return {
      element: wrap,
      getValue() {
        const out = {};
        for (const { keyInput, field } of rows) {
          const key = keyInput.value.trim();
          if (key) out[key] = field.getValue();
        }
        return out;
      },
    };
  }

  if (type === "array") {
    const itemSchema = resolved.items || {};
    const itemResolved = resolveSchema(itemSchema, defs);
    const isObjectItem = itemResolved.type === "object" && !!itemResolved.properties;
    const list = el("div", {});
    const items = [];

    function addRow(value) {
      const field = buildSchemaField(itemSchema, defs, value);
      const removeBtn = el("button", { class: "remove", type: "button", text: "✕", onclick: () => { row.remove(); items.splice(items.indexOf(entry), 1); } });
      let row;
      // A batch-generated array (a DOE split, say) can easily hold dozens of object rows - each
      // one fully expanded made that unreadable, so anything past the first few starts
      // collapsed, labelled with whatever identifying value the row already has (slot/name/
      // entity_id/id, in that order) so a summary line still means something.
      if (isObjectItem) {
        const v = value || {};
        const hint = v.slot ?? v.name ?? v.entity_id ?? v.id;
        const label = `#${items.length + 1}${hint !== undefined && hint !== null && hint !== "" ? " — " + hint : ""}`;
        const details = collapsible(label, [field.element], { open: items.length < 3 });
        row = el("div", { class: "array-item" }, [removeBtn, details]);
      } else {
        row = el("div", { class: "array-item" }, [removeBtn, field.element]);
      }
      const entry = { row, field };
      items.push(entry);
      list.appendChild(row);
    }

    (initial || []).forEach((v) => addRow(v));

    const wrap = el("div", {}, [
      list,
      el("button", { type: "button", class: "secondary", text: "+ ajouter", onclick: () => addRow(undefined) }),
    ]);
    return {
      element: wrap,
      getValue: () => items.map((e) => e.field.getValue()),
    };
  }

  if (resolved.enum) {
    const select = el("select", {});
    for (const opt of resolved.enum) {
      select.appendChild(el("option", { value: opt, text: String(opt) }));
    }
    if (initial !== undefined) select.value = initial;
    return { element: select, getValue: () => select.value };
  }

  if (type === "boolean") {
    const input = el("input", { type: "checkbox" });
    input.checked = !!initial;
    return { element: input, getValue: () => input.checked };
  }

  if (type === "integer" || type === "number") {
    const input = el("input", { type: "number", step: type === "integer" ? "1" : "any" });
    if (initial !== undefined && initial !== null) input.value = initial;
    return {
      element: input,
      getValue: () => (input.value === "" ? undefined : (type === "integer" ? parseInt(input.value, 10) : parseFloat(input.value))),
    };
  }

  // string, or unresolved/any type - fall back to a plain text input
  const input = el("input", { type: "text" });
  if (initial !== undefined && initial !== null) input.value = initial;
  return { element: input, getValue: () => (input.value === "" ? undefined : input.value) };
}

// -- evidence / conclusion editors --------------------------------------------------------------

function buildEvidenceEditor(initial) {
  const list = el("div", {});
  const items = [];

  function addRow(value) {
    value = value || {};
    const idInput = el("input", { type: "text", placeholder: "id (unique)" });
    const descInput = el("input", { type: "text", placeholder: "description" });
    const sourceInput = el("input", { type: "text", placeholder: "source (chemin/URI/DOI)" });
    const metricsInput = el("textarea", { placeholder: 'métriques (JSON), ex: {"yield": {"value": 0.9}}' });
    idInput.value = value.id || "";
    descInput.value = value.description || "";
    sourceInput.value = value.source || "";
    metricsInput.value = JSON.stringify(value.metrics || {});
    const row = el("div", { class: "array-item" }, [
      el("button", { class: "remove", type: "button", text: "✕", onclick: () => { row.remove(); items.splice(items.indexOf(entry), 1); } }),
      el("label", { text: "id" }), idInput,
      el("label", { text: "description" }), descInput,
      el("label", { text: "source" }), sourceInput,
      el("label", { text: "métriques" }), metricsInput,
    ]);
    const entry = { row, idInput, descInput, sourceInput, metricsInput };
    items.push(entry);
    list.appendChild(row);
  }

  (initial || []).forEach(addRow);

  const wrap = el("div", {}, [
    list,
    el("button", { type: "button", class: "secondary", text: "+ ajouter une preuve", onclick: () => addRow() }),
  ]);
  return {
    element: wrap,
    getValue: () => items
      .filter((e) => e.idInput.value.trim())
      .map((e) => ({
        id: e.idInput.value.trim(),
        description: e.descInput.value,
        source: e.sourceInput.value,
        metrics: e.metricsInput.value.trim() ? JSON.parse(e.metricsInput.value) : {},
      })),
  };
}

function buildConclusionEditor(objectives, initial) {
  initial = initial || {};
  const statusSelect = el("select", {}, ["draft", "running", "concluded", "abandoned"].map((s) => el("option", { value: s, text: s })));
  statusSelect.value = initial.status || "draft";
  const decisionSelect = el("select", {}, ["", "promote", "branch", "replicate", "abandon", "inconclusive"].map((s) => el("option", { value: s, text: s || "—" })));
  decisionSelect.value = initial.decision || "";
  const summaryInput = el("textarea", {});
  summaryInput.value = initial.summary || "";
  const nextStepsInput = el("textarea", {});
  nextStepsInput.value = initial.next_steps || "";

  const resultRows = [];
  const resultsList = el("div", {});

  function addResultRow(value) {
    value = value || {};
    const objectiveSelect = el("select", {}, objectives.map((o) => el("option", { value: o.name, text: o.name })));
    objectiveSelect.value = value.objective || (objectives[0] && objectives[0].name) || "";
    const statusSel = el("select", {}, ["met", "not_met", "partially_met", "inconclusive"].map((s) => el("option", { value: s, text: s })));
    statusSel.value = value.status || "inconclusive";
    const observedValue = el("input", { type: "text", placeholder: "valeur observée" });
    const observedUnit = el("input", { type: "text", placeholder: "unité" });
    if (value.observed) {
      observedValue.value = value.observed.value ?? "";
      observedUnit.value = value.observed.unit || "";
    }
    const reasoningInput = el("input", { type: "text", placeholder: "raisonnement" });
    reasoningInput.value = value.reasoning || "";
    const row = el("div", { class: "array-item" }, [
      el("button", { class: "remove", type: "button", text: "✕", onclick: () => { row.remove(); resultRows.splice(resultRows.indexOf(entry), 1); } }),
      el("label", { text: "objectif" }), objectiveSelect,
      el("label", { text: "verdict" }), statusSel,
      el("div", { class: "row" }, [
        el("div", {}, [el("label", { text: "observé (valeur)" }), observedValue]),
        el("div", {}, [el("label", { text: "unité" }), observedUnit]),
      ]),
      el("label", { text: "raisonnement" }), reasoningInput,
    ]);
    const entry = { row, objectiveSelect, statusSel, observedValue, observedUnit, reasoningInput };
    resultRows.push(entry);
    resultsList.appendChild(row);
  }

  (initial.objective_results || []).forEach(addResultRow);

  const addResultBtn = el("button", { type: "button", class: "secondary", text: "+ verdict d'objectif", onclick: () => addResultRow() });
  if (objectives.length === 0) addResultBtn.disabled = true;

  const wrap = el("div", {}, [
    el("label", { text: "Statut" }), statusSelect,
    el("label", { text: "Décision" }), decisionSelect,
    el("label", { text: "Résumé" }), summaryInput,
    el("label", { text: "Suite à donner" }), nextStepsInput,
    el("label", { text: "Verdicts par objectif" }), resultsList, addResultBtn,
  ]);

  return {
    element: wrap,
    getValue() {
      const objective_results = resultRows.map((r) => {
        const result = { objective: r.objectiveSelect.value, status: r.statusSel.value };
        if (r.observedValue.value.trim()) {
          const num = parseFloat(r.observedValue.value);
          result.observed = { value: Number.isNaN(num) ? r.observedValue.value : num, unit: r.observedUnit.value || null };
        }
        if (r.reasoningInput.value.trim()) result.reasoning = r.reasoningInput.value;
        return result;
      });
      return {
        status: statusSelect.value,
        decision: decisionSelect.value || null,
        summary: summaryInput.value || null,
        next_steps: nextStepsInput.value || null,
        objective_results,
      };
    },
  };
}

// -- repository commit form (follow.commit_form) --------------------------------------------

function buildCommitFormFields(commitForm, initial) {
  initial = initial || {};
  if (!commitForm) return { element: el("div", {}), getValue: () => ({}) };
  const fields = {};
  const wrap = el("div", { class: "card" }, [
    el("h2", { text: commitForm.title }),
    commitForm.description ? el("p", { class: "muted", text: commitForm.description }) : null,
  ]);
  for (const field of commitForm.fields) {
    let input;
    if (field.type === "choice") {
      input = el("select", {}, (field.choices || []).map((c) => el("option", { value: c, text: c })));
    } else if (field.type === "boolean") {
      input = el("input", { type: "checkbox" });
      input.checked = !!initial[field.name];
    } else if (field.type === "number") {
      input = el("input", { type: "number", step: "any" });
    } else if (field.type === "text") {
      input = el("textarea", {});
    } else {
      input = el("input", { type: "text" });
    }
    if (field.type !== "boolean" && initial[field.name] !== undefined) input.value = initial[field.name];
    wrap.appendChild(el("label", { text: `${field.label}${field.required ? " *" : ""}` }));
    wrap.appendChild(input);
    if (field.help) wrap.appendChild(el("p", { class: "muted", text: field.help }));
    fields[field.name] = { input, field };
  }
  return {
    element: wrap,
    getValue() {
      const out = {};
      for (const [name, { input, field }] of Object.entries(fields)) {
        if (field.type === "boolean") { out[name] = input.checked; continue; }
        if (field.type === "number") { if (input.value !== "") out[name] = parseFloat(input.value); continue; }
        if (input.value.trim()) out[name] = input.value;
      }
      return out;
    },
  };
}

// -- DOE / batch field editor -------------------------------------------------------------------
//
// A "batch field" is a list[Structure] field (e.g. WaferLot.wafers: list[Wafer], see
// follow.batch) - many sibling entities inside one experiment. Instead of only letting the user
// hand-add rows one at a time, this generates a whole design (sweep / full factorial / Latin
// hypercube - see follow.design) from a baseline entity plus a few factors, previews the
// resulting split matrix (which parameters stayed constant, which varied - follow.batch.analyze_batch,
// the same analysis `follow explode` runs), and flags any two factors that varied together too
// closely to tell apart (follow.design.check_identifiability) - all before anything is created.

function entityLeafFieldNames(entitySchema) {
  return Object.keys(entitySchema.properties || {});
}

function renderDoeResultTable(result, { entityWord = "générée(s)" } = {}) {
  const wrap = el("div", {});
  const { variation, identifiability = [], resolution = null, aliases = {} } = result;
  wrap.appendChild(el("p", { class: "muted", text: `${variation.entity_count} entité(s) ${entityWord}.` }));

  if (Object.keys(variation.constant).length > 0) {
    wrap.appendChild(el("p", { text: `Constant sur toutes les entités : ${Object.keys(variation.constant).join(", ")}` }));
  }

  if (variation.varying.length > 0) {
    const paths = variation.varying.map((f) => f.path);
    const table = el("table", { class: "doe-table" });
    const thead = el("tr", {}, [el("th", { text: "#" }), ...paths.map((p) => el("th", { text: p }))]);
    table.appendChild(el("thead", {}, [thead]));
    const n = variation.varying[0].values.length;
    const tbody = el("tbody", {});
    for (let i = 0; i < n; i++) {
      const cells = variation.varying.map((f) => el("td", { text: JSON.stringify(f.values[i]) }));
      tbody.appendChild(el("tr", {}, [el("td", { text: String(i + 1) }), ...cells]));
    }
    table.appendChild(tbody);
    wrap.appendChild(el("div", { class: "doe-table-wrap" }, [table]));
  }

  for (const { a, b, correlation } of identifiability) {
    wrap.appendChild(el("div", {
      class: "doe-warning",
      text: `⚠ ${a} et ${b} varient ensemble (corrélation ${correlation.toFixed(2)}) - leurs effets ne seront pas séparables statistiquement.`,
    }));
  }

  if (resolution) {
    wrap.appendChild(el("p", { class: "muted", text: `Résolution du plan fractionnaire : ${resolution === 3 ? "III" : resolution === 4 ? "IV" : resolution === 5 ? "V" : resolution}` }));
  }
  if (aliases && Object.keys(aliases).length > 0) {
    wrap.appendChild(el("pre", { class: "fiche", text: Object.entries(aliases).map(([k, v]) => `${k}  ~  ${v.join(", ")}`).join("\n") }));
  }
  return wrap;
}

function buildBatchFieldEditor(structureTypeKey, fieldName, batchInfo, initialItems) {
  const entitySchema = batchInfo.entity_schema;
  const entityDefs = entitySchema.$defs || {};
  const arrayNode = { type: "array", items: entitySchema };
  let currentField = buildSchemaField(arrayNode, entityDefs, initialItems);
  const arrayContainer = el("div", {}, [currentField.element]);

  const leafNames = entityLeafFieldNames(entitySchema);
  const planTypeSelect = el("select", {}, [
    el("option", { value: "sweep", text: "Balayage (un facteur)" }),
    el("option", { value: "full_factorial", text: "Factoriel complet (tous les facteurs croisés)" }),
    el("option", { value: "latin_hypercube", text: "Hypercube latin (échantillonnage aléatoire stratifié)" }),
  ]);
  const idFieldInput = el("input", { type: "text", placeholder: "ex: slot (optionnel, numéroté 1..N automatiquement)" });
  const referenceField = buildSchemaField(entitySchema, entityDefs, undefined);
  const factorsContainer = el("div", {});
  const resultContainer = el("div", {});
  const doeError = el("div", {});

  function factorFieldSelect() {
    return el("select", {}, leafNames.map((n) => el("option", { value: n, text: n })));
  }

  function renderFactorsForPlan() {
    clear(factorsContainer);
    if (planTypeSelect.value === "sweep") {
      const fieldSel = factorFieldSelect();
      const valuesInput = el("input", { type: "text", placeholder: "valeurs séparées par des virgules, ex: 10,20,30" });
      const unitInput = el("input", { type: "text", placeholder: "unité (optionnel)" });
      factorsContainer.appendChild(el("div", {}, [
        el("label", { text: "Facteur" }), fieldSel,
        el("label", { text: "Valeurs" }), valuesInput,
        el("label", { text: "Unité" }), unitInput,
      ]));
      factorsContainer._collect = () => ({
        type: "sweep",
        id_field: idFieldInput.value.trim() || null,
        field: fieldSel.value,
        values: valuesInput.value.split(",").map((s) => s.trim()).filter(Boolean).map((v) => parseNumberOrString(v, unitInput.value.trim())),
      });
    } else if (planTypeSelect.value === "full_factorial") {
      const rows = [];
      const list = el("div", {});
      function addRow() {
        const fieldSel = factorFieldSelect();
        const valuesInput = el("input", { type: "text", placeholder: "valeurs séparées par des virgules" });
        const unitInput = el("input", { type: "text", placeholder: "unité (optionnel)" });
        const row = el("div", { class: "array-item" }, [
          el("button", { type: "button", class: "remove", text: "✕", onclick: () => { row.remove(); rows.splice(rows.indexOf(entry), 1); } }),
          el("label", { text: "Facteur" }), fieldSel,
          el("label", { text: "Valeurs" }), valuesInput,
          el("label", { text: "Unité" }), unitInput,
        ]);
        const entry = { fieldSel, valuesInput, unitInput };
        rows.push(entry);
        list.appendChild(row);
      }
      addRow();
      addRow();
      factorsContainer.appendChild(el("div", {}, [
        list,
        el("button", { type: "button", class: "secondary", text: "+ facteur", onclick: addRow }),
      ]));
      factorsContainer._collect = () => {
        const factors = {};
        for (const r of rows) {
          const values = r.valuesInput.value.split(",").map((s) => s.trim()).filter(Boolean).map((v) => parseNumberOrString(v, r.unitInput.value.trim()));
          if (values.length) factors[r.fieldSel.value] = values;
        }
        return { type: "full_factorial", id_field: idFieldInput.value.trim() || null, factors };
      };
    } else {
      const nInput = el("input", { type: "number", value: "10" });
      const seedInput = el("input", { type: "number", placeholder: "graine aléatoire (optionnel)" });
      const rows = [];
      const list = el("div", {});
      function addRow() {
        const fieldSel = factorFieldSelect();
        const lowInput = el("input", { type: "number", step: "any", placeholder: "min" });
        const highInput = el("input", { type: "number", step: "any", placeholder: "max" });
        const unitInput = el("input", { type: "text", placeholder: "unité (optionnel)" });
        const row = el("div", { class: "array-item" }, [
          el("button", { type: "button", class: "remove", text: "✕", onclick: () => { row.remove(); rows.splice(rows.indexOf(entry), 1); } }),
          el("label", { text: "Facteur" }), fieldSel,
          el("div", { class: "row" }, [
            el("div", {}, [el("label", { text: "min" }), lowInput]),
            el("div", {}, [el("label", { text: "max" }), highInput]),
          ]),
          el("label", { text: "Unité" }), unitInput,
        ]);
        const entry = { fieldSel, lowInput, highInput, unitInput };
        rows.push(entry);
        list.appendChild(row);
      }
      addRow();
      factorsContainer.appendChild(el("div", {}, [
        el("label", { text: "Nombre d'entités (n)" }), nInput,
        el("label", { text: "Graine (optionnel)" }), seedInput,
        list,
        el("button", { type: "button", class: "secondary", text: "+ facteur", onclick: addRow }),
      ]));
      factorsContainer._collect = () => {
        const factor_ranges = {};
        for (const r of rows) {
          if (r.lowInput.value === "" || r.highInput.value === "") continue;
          const spec = [parseFloat(r.lowInput.value), parseFloat(r.highInput.value)];
          if (r.unitInput.value.trim()) spec.push(r.unitInput.value.trim());
          factor_ranges[r.fieldSel.value] = spec;
        }
        return {
          type: "latin_hypercube",
          id_field: idFieldInput.value.trim() || null,
          n: parseInt(nInput.value, 10) || null,
          seed: seedInput.value ? parseInt(seedInput.value, 10) : null,
          factor_ranges,
        };
      };
    }
  }
  planTypeSelect.addEventListener("change", renderFactorsForPlan);
  renderFactorsForPlan();

  const generateBtn = el("button", { type: "button", text: "Générer l'aperçu", onclick: async () => {
    clear(doeError);
    clear(resultContainer);
    try {
      const plan = factorsContainer._collect();
      const body = { structure_type: structureTypeKey, field: fieldName, reference: referenceField.getValue(), plan };
      const result = await post("/api/design/generate", body);
      resultContainer.appendChild(renderDoeResultTable(result));
      resultContainer.appendChild(el("button", {
        type: "button",
        text: `Utiliser ce plan (${result.variants.length} entités)`,
        onclick: () => {
          clear(arrayContainer);
          currentField = buildSchemaField(arrayNode, entityDefs, result.variants);
          arrayContainer.appendChild(currentField.element);
        },
      }));
    } catch (err) {
      showError(doeError, err);
    }
  } });

  const doePanel = collapsible("Générer un plan (DOE)", [
    el("h2", { text: "Valeurs de référence (communes à toutes les entités)" }),
    referenceField.element,
    el("h2", { text: "Plan" }),
    el("label", { text: "Type de plan" }), planTypeSelect,
    el("label", { text: "Champ identifiant (optionnel)" }), idFieldInput,
    factorsContainer,
    doeError,
    el("div", { class: "toolbar" }, [generateBtn]),
    resultContainer,
  ]);

  const wrap = el("div", {}, [arrayContainer, doePanel]);
  return { element: wrap, getValue: () => currentField.getValue() };
}

function parseNumberOrString(raw, unit) {
  const num = parseFloat(raw);
  const value = !Number.isNaN(num) && String(num) === raw.trim() ? num : raw;
  return unit ? { value, unit } : value;
}

/** Build the form for a whole Structure type: like buildSchemaField, but any top-level field
 * that holds a list of sibling entities (see follow.batch) gets the DOE-aware editor
 * (buildBatchFieldEditor) instead of the plain add/remove-rows array editor.
 */
async function buildStructureForm(structureTypeKey, initial) {
  const schema = await get(`/api/structures/${encodeURIComponent(structureTypeKey)}/schema`);
  const defs = schema.$defs || {};
  const resolved = resolveSchema(schema, defs);
  const batchFieldsList = await get(`/api/structures/${encodeURIComponent(structureTypeKey)}/batch-fields`);
  const batchFieldsMap = Object.fromEntries(batchFieldsList.map((b) => [b.field, b]));

  if (!(resolved.type === "object" && resolved.properties)) {
    return buildSchemaField(schema, defs, initial);
  }

  const rows = {};
  const wrap = el("div", {});
  for (const [key, propSchema] of Object.entries(resolved.properties)) {
    const required = (resolved.required || []).includes(key);
    const isBatch = Boolean(batchFieldsMap[key]);
    const field = isBatch
      ? buildBatchFieldEditor(structureTypeKey, key, batchFieldsMap[key], initial ? initial[key] : undefined)
      : buildSchemaField(propSchema, defs, initial ? initial[key] : undefined);
    appendLabeledField(wrap, key, propSchema, required, field, isBatch ? "📋 " : "");
    rows[key] = field;
  }
  return {
    element: wrap,
    getValue() {
      const out = {};
      for (const [key, field] of Object.entries(rows)) {
        const v = field.getValue();
        if (v !== undefined) out[key] = v;
      }
      return out;
    },
  };
}

// -- new experiment / derive forms -------------------------------------------------------------

function advancedJsonField(labelText, help) {
  const wrap = el("div", {}, [
    el("label", { text: labelText }),
    el("textarea", { placeholder: help || "[] (JSON)" }),
  ]);
  const textarea = wrap.querySelector("textarea");
  textarea.value = "[]";
  return {
    element: wrap,
    getValue() {
      const raw = textarea.value.trim();
      if (!raw) return [];
      return JSON.parse(raw);
    },
  };
}

async function showNewExperimentForm() {
  clear(view);
  view.appendChild(el("h1", { text: "Nouvelle expérience" }));
  const errorBox = el("div", {});
  view.appendChild(errorBox);

  const structures = await get("/api/structures");
  const branchSelect = el("select", {}, [
    ...Object.keys(state.branches).sort().map((b) => el("option", { value: b, text: b })),
    el("option", { value: "__new__", text: "— nouvelle branche —" }),
  ]);
  const newBranchInput = el("input", { type: "text", placeholder: "nom de la nouvelle branche" });
  newBranchInput.style.display = Object.keys(state.branches).length ? "none" : "block";
  branchSelect.addEventListener("change", () => {
    newBranchInput.style.display = branchSelect.value === "__new__" ? "block" : "none";
  });

  const structureSelect = el("select", {}, structures.map((s) => el("option", { value: s.key, text: `${s.name} (${s.key})` })));
  const titleInput = el("input", { type: "text" });
  const intentInput = el("textarea", {});
  const authorInput = el("input", { type: "text" });
  const hypothesisInput = el("textarea", {});
  const structureFormContainer = el("div", {});
  let structureField = null;

  async function loadStructureForm() {
    clear(structureFormContainer);
    if (!structureSelect.value) return;
    structureField = await buildStructureForm(structureSelect.value, undefined);
    structureFormContainer.appendChild(structureField.element);
  }
  structureSelect.addEventListener("change", loadStructureForm);

  const objectivesField = advancedJsonField("Objectifs (JSON, avancé)");
  const stepsField = advancedJsonField("Étapes (JSON, avancé)");
  const tagsInput = el("input", { type: "text", placeholder: "séparés par des virgules" });
  const commitForm = await get("/api/commit_form");
  const commitFormField = buildCommitFormFields(commitForm);

  const form = el("form", { onsubmit: async (e) => {
    e.preventDefault();
    clear(errorBox);
    const branch = branchSelect.value === "__new__" ? newBranchInput.value.trim() : branchSelect.value;
    if (!branch) {
      showError(errorBox, new Error("le nom de la branche est requis"));
      return;
    }
    try {
      const payload = {
        branch,
        structure_type: structureSelect.value,
        structure: structureField ? structureField.getValue() : {},
        title: titleInput.value,
        intent: intentInput.value,
        author: authorInput.value || null,
        hypothesis: hypothesisInput.value || null,
        objectives: objectivesField.getValue(),
        steps: stepsField.getValue(),
        tags: tagsInput.value.split(",").map((s) => s.trim()).filter(Boolean),
        form_answers: commitFormField.getValue(),
      };
      const result = await post("/api/experiments", payload);
      await refreshSidebar();
      navigate(`/app/experience/${result.experiment.id}`);
    } catch (err) {
      showError(errorBox, err);
    }
  } }, [
    el("label", { text: "Branche" }), branchSelect, newBranchInput,
    el("label", { text: "Titre" }), titleInput,
    el("label", { text: "Intention" }), intentInput,
    el("label", { text: "Auteur" }), authorInput,
    el("label", { text: "Hypothèse" }), hypothesisInput,
    el("label", { text: "Tags" }), tagsInput,
    el("h2", { text: "Type de structure" }), structureSelect,
    collapsible("Structure", [structureFormContainer], { open: true }),
    collapsible("Objectifs & étapes (avancé)", [objectivesField.element, stepsField.element]),
    commitFormField.element,
    el("div", { class: "toolbar" }, [
      el("button", { type: "submit", text: "Créer et committer" }),
      el("button", { type: "button", class: "secondary", text: "Annuler", onclick: () => navigate(state.activeRef ? `/app/historique/${encodeURIComponent(state.activeRef)}` : (Object.keys(state.branches)[0] ? `/app/historique/${encodeURIComponent(Object.keys(state.branches)[0])}` : "/app")) }),
    ]),
  ]);
  view.appendChild(form);
  await loadStructureForm();
}

async function showDeriveFormFor(id) {
  try {
    const data = await get(`/api/experiments/${encodeURIComponent(id)}`);
    return showDeriveForm(data.experiment);
  } catch (err) {
    showError(view, err);
  }
}

async function showDeriveForm(parentExp) {
  clear(view);
  view.appendChild(el("h1", { text: `Dériver de ${parentExp.title}` }));
  const errorBox = el("div", {});
  view.appendChild(errorBox);

  const structureField = await buildStructureForm(parentExp.structure_type, parentExp.structure);

  const newBranchInput = el("input", { type: "text", placeholder: parentExp.branch });
  const titleInput = el("input", { type: "text" });
  const intentInput = el("textarea", {});
  const evidenceField = buildEvidenceEditor(parentExp.evidence);
  const conclusionField = buildConclusionEditor(parentExp.objectives || [], parentExp.conclusion);
  const commitForm = await get("/api/commit_form");
  const commitFormField = buildCommitFormFields(commitForm, parentExp.form_answers);

  const form = el("form", { onsubmit: async (e) => {
    e.preventDefault();
    clear(errorBox);
    try {
      const payload = {
        title: titleInput.value,
        intent: intentInput.value,
        new_branch: newBranchInput.value.trim() || null,
        structure: structureField.getValue(),
        evidence: evidenceField.getValue(),
        conclusion: conclusionField.getValue(),
        form_answers: commitFormField.getValue(),
      };
      const result = await post(`/api/experiments/${encodeURIComponent(parentExp.id)}/derive`, payload);
      await refreshSidebar();
      navigate(`/app/experience/${result.experiment.id}`);
    } catch (err) {
      showError(errorBox, err);
    }
  } }, [
    el("label", { text: "Nouvelle branche (optionnel, sinon: " + parentExp.branch + ")" }), newBranchInput,
    el("label", { text: "Titre" }), titleInput,
    el("label", { text: "Intention" }), intentInput,
    collapsible("Structure (héritée du parent, modifiable)", [structureField.element], { open: true }),
    collapsible("Preuves", [evidenceField.element], { open: (parentExp.evidence || []).length > 0 }),
    collapsible("Conclusion", [conclusionField.element], { open: true }),
    commitFormField.element,
    el("div", { class: "toolbar" }, [
      el("button", { type: "submit", text: "Créer et committer" }),
      el("button", { type: "button", class: "secondary", text: "Annuler", onclick: () => navigate(`/app/experience/${encodeURIComponent(parentExp.id)}`) }),
    ]),
  ]);
  view.appendChild(form);
}

// -- graph / merge / refs / entity trace views ---------------------------------------------------

function showGraph() {
  clear(view);
  view.appendChild(el("h1", { text: "Graphe de filiation" }));
  const frame = el("iframe", { src: "/api/graph.html", style: "width:100%; height:75vh; border:1px solid var(--border); border-radius:10px; background:#fff;" });
  view.appendChild(frame);
}

async function showMergeForm() {
  clear(view);
  view.appendChild(el("h1", { text: "Fusionner deux expériences" }));
  const errorBox = el("div", {});
  view.appendChild(errorBox);

  const refAInput = el("input", { type: "text", placeholder: "id / branche / tag" });
  const refBInput = el("input", { type: "text", placeholder: "id / branche / tag" });
  const titleInput = el("input", { type: "text" });
  const intentInput = el("textarea", {});
  const branchInput = el("input", { type: "text", placeholder: "(par défaut: branche de A)" });
  const takeStructureInput = el("input", { type: "text", placeholder: "chemins séparés par des virgules (garder la valeur de B)" });
  const takeStepsInput = el("input", { type: "text", placeholder: "chemins d'étapes séparés par des virgules" });

  const form = el("form", { onsubmit: async (e) => {
    e.preventDefault();
    clear(errorBox);
    try {
      const payload = {
        ref_a: refAInput.value.trim(),
        ref_b: refBInput.value.trim(),
        title: titleInput.value,
        intent: intentInput.value,
        branch: branchInput.value.trim() || null,
        take_structure: takeStructureInput.value.split(",").map((s) => s.trim()).filter(Boolean),
        take_steps: takeStepsInput.value.split(",").map((s) => s.trim()).filter(Boolean),
      };
      const result = await post("/api/merge", payload);
      await refreshSidebar();
      navigate(`/app/experience/${result.experiment.id}`);
    } catch (err) {
      showError(errorBox, err);
    }
  } }, [
    el("label", { text: "Expérience A (référence conservée par défaut)" }), refAInput,
    el("label", { text: "Expérience B" }), refBInput,
    el("label", { text: "Titre" }), titleInput,
    el("label", { text: "Intention" }), intentInput,
    el("label", { text: "Branche cible" }), branchInput,
    el("label", { text: "Structure à prendre de B" }), takeStructureInput,
    el("label", { text: "Étapes à prendre de B" }), takeStepsInput,
    el("div", { class: "toolbar" }, [
      el("button", { type: "submit", text: "Fusionner et committer" }),
      el("button", { type: "button", class: "secondary", text: "Annuler", onclick: () => navigate(state.activeRef ? `/app/historique/${encodeURIComponent(state.activeRef)}` : (Object.keys(state.branches)[0] ? `/app/historique/${encodeURIComponent(Object.keys(state.branches)[0])}` : "/app")) }),
    ]),
  ]);
  view.appendChild(form);
}

function showRefsForm() {
  clear(view);
  view.appendChild(el("h1", { text: "Branches & tags" }));
  const errorBox = el("div", {});
  view.appendChild(errorBox);

  function makeForm(kind, endpoint) {
    const nameInput = el("input", { type: "text", placeholder: "nom" });
    const atInput = el("input", { type: "text", placeholder: "id / branche / tag" });
    const forceInput = el("input", { type: "checkbox" });
    const form = el("form", { class: "card", onsubmit: async (e) => {
      e.preventDefault();
      clear(errorBox);
      try {
        await post(endpoint, { name: nameInput.value.trim(), at: atInput.value.trim(), force: forceInput.checked });
        await refreshSidebar();
        showRefsForm();
      } catch (err) {
        showError(errorBox, err);
      }
    } }, [
      el("h2", { text: kind }),
      el("label", { text: "nom" }), nameInput,
      el("label", { text: "pointe vers" }), atInput,
      el("label", {}, [forceInput, document.createTextNode(" forcer (déplacer même en arrière)")]),
      el("div", { class: "toolbar" }, [el("button", { type: "submit", text: `Créer / déplacer ${kind}` })]),
    ]);
    return form;
  }

  view.appendChild(makeForm("branche", "/api/branches"));
  view.appendChild(makeForm("tag", "/api/tags"));
}

async function showEntityTrace(entityId) {
  clear(view);
  view.appendChild(el("h1", { text: `Entité — ${entityId}` }));
  try {
    const matches = await get(`/api/entities/${encodeURIComponent(entityId)}`);
    const card = el("div", { class: "card" });
    if (matches.length === 0) card.appendChild(el("p", { class: "muted", text: "Aucune expérience ne mentionne cette entité." }));
    for (const exp of matches) {
      card.appendChild(el("div", { class: "log-entry", onclick: () => navigate(`/app/experience/${encodeURIComponent(exp.id)}`) }, [
        el("span", { class: "id", text: exp.id.slice(0, 10) }),
        el("span", { text: exp.title }),
        el("span", { class: "status", text: `(${exp.branch})` }),
      ]));
    }
    view.appendChild(card);
  } catch (err) {
    showError(view, err);
  }
}

// -- en cours / terminées (all-branches, filtered by status) --------------------------------

const EXPERIMENTS_PAGE_SIZE = 25;

async function showExperimentsList(status, offset = 0) {
  const title = status === "running" ? "Expériences en cours" : "Expériences terminées";
  view.appendChild(el("h1", { text: title }));
  const card = el("div", { class: "card" });
  view.appendChild(card);
  try {
    const page = await get(`/api/experiments?status=${status}&offset=${offset}&limit=${EXPERIMENTS_PAGE_SIZE}`);
    if (page.total === 0) card.appendChild(el("p", { class: "muted", text: "Aucune expérience." }));
    for (const exp of page.items) {
      card.appendChild(el("div", {
        class: "log-entry",
        onclick: () => navigate(`/app/experience/${encodeURIComponent(exp.id)}`),
      }, [
        el("span", { class: "id", text: exp.id.slice(0, 10) }),
        el("span", { text: exp.title }),
        el("span", { class: "muted", text: exp.branch }),
        el("span", { class: "status", text: `[${exp.conclusion.status}]` }),
      ]));
    }
    const shown = page.offset + page.items.length;
    if (page.total > 0) {
      const route = status === "running" ? "en-cours" : "terminees";
      view.appendChild(el("div", { class: "toolbar" }, [
        el("span", { class: "muted", text: `${shown} / ${page.total}` }),
        offset > 0
          ? el("button", { class: "secondary", text: "← précédent", onclick: () => navigate(`/app/${route}?offset=${Math.max(0, offset - EXPERIMENTS_PAGE_SIZE)}`) })
          : null,
        shown < page.total
          ? el("button", { class: "secondary", text: "suivant →", onclick: () => navigate(`/app/${route}?offset=${offset + EXPERIMENTS_PAGE_SIZE}`) })
          : null,
      ]));
    }
  } catch (err) {
    showError(view, err);
  }
}

// -- exemples ---------------------------------------------------------------------------------

async function showExamples() {
  view.appendChild(el("h1", { text: "Exemples" }));
  view.appendChild(el("p", { class: "muted", text: "Scénarios complets, exécutés de bout en bout avec Follow et rendus en rapports HTML autonomes." }));
  try {
    const examples = await get("/api/examples");
    if (examples.length === 0) {
      view.appendChild(el("p", { class: "muted", text: "Aucun exemple disponible sur cette installation." }));
      return;
    }
    for (const ex of examples) {
      view.appendChild(el("a", { class: "card example-card", href: `/examples-gallery/${ex.file}`, target: "_blank", rel: "noopener" }, [
        el("h3", { text: ex.title }),
        el("p", { text: ex.description }),
      ]));
    }
  } catch (err) {
    showError(view, err);
  }
}

// -- boot ------------------------------------------------------------------------------------

refreshSidebar()
  .then(router)
  .catch((err) => showError(view, err));
