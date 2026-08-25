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

// -- app state -----------------------------------------------------------------------------

const state = { branches: {}, tags: {}, activeRef: null };
const view = document.getElementById("view");

async function refreshSidebar() {
  const health = await get("/api/health");
  document.getElementById("repo-meta").textContent = `${health.repo} · ${health.experiments} expérience(s)`;
  state.branches = await get("/api/branches");
  state.tags = await get("/api/tags");

  const branchList = document.getElementById("branch-list");
  clear(branchList);
  for (const name of Object.keys(state.branches).sort()) {
    branchList.appendChild(el("li", {}, [
      el("button", { text: name, onclick: () => showLog(name) }),
    ]));
  }
  const tagList = document.getElementById("tag-list");
  clear(tagList);
  for (const name of Object.keys(state.tags).sort()) {
    tagList.appendChild(el("li", {}, [
      el("button", { text: name, onclick: () => showLog(name) }),
    ]));
  }
}

document.getElementById("btn-new").addEventListener("click", () => showNewExperimentForm());
document.getElementById("btn-graph").addEventListener("click", () => showGraph());
document.getElementById("btn-merge").addEventListener("click", () => showMergeForm());
document.getElementById("btn-refs").addEventListener("click", () => showRefsForm());
document.getElementById("entity-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = document.getElementById("entity-input").value.trim();
  if (id) showEntityTrace(id);
});

// -- log / detail views ----------------------------------------------------------------------

const LOG_PAGE_SIZE = 25;

async function showLog(ref, offset = 0) {
  state.activeRef = ref;
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
        onclick: () => showExperiment(exp.id),
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
          ? el("button", { class: "secondary", text: "← précédent", onclick: () => showLog(ref, Math.max(0, offset - LOG_PAGE_SIZE)) })
          : null,
        shown < page.total
          ? el("button", { class: "secondary", text: "suivant →", onclick: () => showLog(ref, offset + LOG_PAGE_SIZE) })
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

    const toolbar = el("div", { class: "toolbar" }, [
      el("button", { text: "Dériver →", onclick: () => showDeriveForm(exp) }),
      el("button", { class: "secondary", text: "← Historique", onclick: () => showLog(state.activeRef || exp.branch) }),
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

/** Build a form for one JSON-schema node. Returns {element, getValue()}. */
function buildSchemaField(node, defs, initial) {
  const resolved = resolveSchema(node, defs);
  const type = resolved.type;

  if (type === "object" && resolved.properties) {
    const rows = {};
    const wrap = el("div", {});
    for (const [key, propSchema] of Object.entries(resolved.properties)) {
      const required = (resolved.required || []).includes(key);
      const field = buildSchemaField(propSchema, defs, initial ? initial[key] : undefined);
      // Prefer the *field's own* title (set on the property in the parent schema) over the
      // title baked into whatever it $ref's to - a property typed `temperature: Quantity`
      // dereferences to Quantity's own schema, whose title is "Quantity", not "Temperature";
      // only a bare, title-less property should fall back to its key name.
      const label = propSchema && propSchema.title ? propSchema.title : key.replace(/_/g, " ");
      wrap.appendChild(el("label", { text: `${label}${required ? " *" : ""}` }));
      wrap.appendChild(field.element);
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
    const list = el("div", {});
    const items = [];

    function addRow(value) {
      const field = buildSchemaField(itemSchema, defs, value);
      const row = el("div", { class: "array-item" }, [
        el("button", { class: "remove", type: "button", text: "✕", onclick: () => { row.remove(); items.splice(items.indexOf(entry), 1); } }),
        field.element,
      ]);
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
  const structureFormContainer = el("div", { class: "card" });
  let structureField = null;

  async function loadStructureForm() {
    clear(structureFormContainer);
    if (!structureSelect.value) return;
    const schema = await get(`/api/structures/${encodeURIComponent(structureSelect.value)}/schema`);
    structureField = buildSchemaField(schema, schema.$defs || {}, undefined);
    structureFormContainer.appendChild(el("h2", { text: "Structure" }));
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
      showExperiment(result.experiment.id);
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
    structureFormContainer,
    el("h2", { text: "Avancé" }),
    objectivesField.element,
    stepsField.element,
    commitFormField.element,
    el("div", { class: "toolbar" }, [
      el("button", { type: "submit", text: "Créer et committer" }),
      el("button", { type: "button", class: "secondary", text: "Annuler", onclick: () => showLog(state.activeRef || Object.keys(state.branches)[0]) }),
    ]),
  ]);
  view.appendChild(form);
  await loadStructureForm();
}

async function showDeriveForm(parentExp) {
  clear(view);
  view.appendChild(el("h1", { text: `Dériver de ${parentExp.title}` }));
  const errorBox = el("div", {});
  view.appendChild(errorBox);

  const schema = await get(`/api/structures/${encodeURIComponent(parentExp.structure_type)}/schema`);
  const structureField = buildSchemaField(schema, schema.$defs || {}, parentExp.structure);

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
      showExperiment(result.experiment.id);
    } catch (err) {
      showError(errorBox, err);
    }
  } }, [
    el("label", { text: "Nouvelle branche (optionnel, sinon: " + parentExp.branch + ")" }), newBranchInput,
    el("label", { text: "Titre" }), titleInput,
    el("label", { text: "Intention" }), intentInput,
    el("h2", { text: "Structure (héritée du parent, modifiable)" }),
    structureField.element,
    el("h2", { text: "Preuves" }),
    evidenceField.element,
    el("h2", { text: "Conclusion" }),
    conclusionField.element,
    commitFormField.element,
    el("div", { class: "toolbar" }, [
      el("button", { type: "submit", text: "Créer et committer" }),
      el("button", { type: "button", class: "secondary", text: "Annuler", onclick: () => showExperiment(parentExp.id) }),
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
      showExperiment(result.experiment.id);
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
      el("button", { type: "button", class: "secondary", text: "Annuler", onclick: () => showLog(state.activeRef || Object.keys(state.branches)[0]) }),
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
      card.appendChild(el("div", { class: "log-entry", onclick: () => showExperiment(exp.id) }, [
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

// -- boot ------------------------------------------------------------------------------------

refreshSidebar()
  .then(() => {
    const first = Object.keys(state.branches)[0];
    if (first) showLog(first);
    else view.appendChild(el("p", { class: "muted", text: "Dépôt vide — créez une première expérience." }));
  })
  .catch((err) => showError(view, err));
