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

// -- log / detail views ----------------------------------------------------------------------

async function showLog(ref) {
  state.activeRef = ref;
  clear(view);
  view.appendChild(el("h1", { text: `Historique — ${ref}` }));
  try {
    const commits = await get(`/api/log/${encodeURIComponent(ref)}`);
    const card = el("div", { class: "card" });
    if (commits.length === 0) card.appendChild(el("p", { class: "muted", text: "Aucune expérience." }));
    for (const exp of commits) {
      card.appendChild(el("div", {
        class: "log-entry",
        onclick: () => showExperiment(exp.id),
      }, [
        el("span", { class: "id", text: exp.id.slice(0, 10) }),
        el("span", { text: exp.title }),
        el("span", { class: "status", text: `[${exp.conclusion.status}]` }),
      ]));
    }
    view.appendChild(card);
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
      const propResolved = resolveSchema(propSchema, defs);
      wrap.appendChild(el("label", { text: `${propResolved.title || key}${required ? " *" : ""}` }));
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
    // a free-form mapping (dict[str, X]) - no fixed field names to build inputs for, so fall
    // back to raw JSON rather than guessing at keys.
    const textarea = el("textarea", {});
    textarea.value = JSON.stringify(initial !== undefined ? initial : {}, null, 2);
    return {
      element: textarea,
      getValue: () => (textarea.value.trim() ? JSON.parse(textarea.value) : {}),
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

  const form = el("form", { onsubmit: async (e) => {
    e.preventDefault();
    clear(errorBox);
    const branch = branchSelect.value === "__new__" ? newBranchInput.value.trim() : branchSelect.value;
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

  const form = el("form", { onsubmit: async (e) => {
    e.preventDefault();
    clear(errorBox);
    try {
      const payload = {
        title: titleInput.value,
        intent: intentInput.value,
        new_branch: newBranchInput.value.trim() || null,
        structure: structureField.getValue(),
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
    el("div", { class: "toolbar" }, [
      el("button", { type: "submit", text: "Créer et committer" }),
      el("button", { type: "button", class: "secondary", text: "Annuler", onclick: () => showExperiment(parentExp.id) }),
    ]),
  ]);
  view.appendChild(form);
}

// -- boot ------------------------------------------------------------------------------------

refreshSidebar()
  .then(() => {
    const first = Object.keys(state.branches)[0];
    if (first) showLog(first);
    else view.appendChild(el("p", { class: "muted", text: "Dépôt vide — créez une première expérience." }));
  })
  .catch((err) => showError(view, err));
