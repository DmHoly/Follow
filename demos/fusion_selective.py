"""Reproduce the "selective merge" scenario and render it as a themed HTML report.

A 5-step reference recipe on `main`; a `essai-cuisson` branch that varies step 3 (baking
temperature) over 3 commits; a small independent change on `main` meanwhile (step 1); then a
merge that adopts only the validated step 3 change, resolved path by path. See README.md for
the full narrative and `follow merge --take-steps` docs in the top-level README.

Run: python -m demos.fusion_selective [--out demos/output/fusion_selective.html] [--embed]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from demos._report import fiche_card, render_report, resolution_conflict_row, resolution_plain_row, trial_card
from examples.recipe import BakeStep, CakeRecipe
from follow import Quantity, Repository
from follow.graphing import build_graph_figure


def _recipe() -> CakeRecipe:
    return CakeRecipe(
        name="Gateau au yaourt",
        ingredients={
            "farine": Quantity(value=200, unit="g"),
            "sucre": Quantity(value=150, unit="g"),
            "yaourt": Quantity(value=1, unit="pot"),
        },
        bake=BakeStep(temperature=Quantity(value=170, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def _five_steps(bake_temp: float, bake_duration: float) -> list[dict]:
    return [
        dict(order=1, name="Melanger le sec", description="Farine, sucre, levure"),
        dict(order=2, name="Melanger le liquide", description="Oeufs, yaourt, huile"),
        dict(
            order=3,
            name="Cuire",
            description="Four prechauffe",
            parameters={
                "temperature": Quantity(value=bake_temp, unit="C"),
                "duree": Quantity(value=bake_duration, unit="min"),
            },
        ),
        dict(order=4, name="Refroidir", description="Sur une grille"),
        dict(order=5, name="Demouler", description="Demouler et glacer"),
    ]


def build_repository() -> Repository:
    repo = Repository()

    v1b = repo.new(
        branch="main",
        structure=_recipe(),
        title="Recette de reference",
        intent="Etablir une recette de reference pour le gateau au yaourt",
    )
    for s in _five_steps(170, 35):
        v1b.add_step(**s)
    v1b.add_objective(name="Levee", metric="hauteur_cm", direction="maximize", target=4.5, tolerance=0.5)
    v1b.conclude(status="concluded", decision="promote", summary="Recette de base validee, sert de reference.")
    v1 = v1b.commit()

    a1b = repo.derive(
        v1.id,
        new_branch="essai-cuisson",
        title="Essai a 160C",
        intent="La levee est-elle amelioree par une cuisson plus douce et plus longue ?",
    )
    a1b.steps[2] = a1b.steps[2].model_copy(
        update={"parameters": {"temperature": Quantity(value=160, unit="C"), "duree": Quantity(value=42, unit="min")}}
    )
    a1b.add_evidence(
        id="ev-160",
        description="Photo + sonde de coeur de gateau",
        source="file:///labo/essai-160/photo.jpg",
        metrics={"hauteur_cm": Quantity(value=4.1, unit="cm")},
    )
    a1b.conclude(status="concluded", decision="branch", summary="Centre encore humide, texture trop dense.")
    a1 = a1b.commit()

    a2b = repo.derive(a1.id, title="Essai a 185C", intent="Une cuisson plus vive corrige-t-elle la densite du centre ?")
    a2b.steps[2] = a2b.steps[2].model_copy(
        update={"parameters": {"temperature": Quantity(value=185, unit="C"), "duree": Quantity(value=28, unit="min")}}
    )
    a2b.add_evidence(
        id="ev-185",
        description="Photo + sonde de coeur de gateau",
        source="file:///labo/essai-185/photo.jpg",
        metrics={"hauteur_cm": Quantity(value=4.6, unit="cm")},
    )
    a2b.conclude(status="concluded", decision="branch", summary="Bonne levee mais bords secs et craquelage.")
    a2 = a2b.commit()

    a3b = repo.derive(
        a2.id, title="Essai a 175C", intent="Un compromis entre les deux essais precedents corrige-t-il les deux defauts ?"
    )
    a3b.steps[2] = a3b.steps[2].model_copy(
        update={"parameters": {"temperature": Quantity(value=175, unit="C"), "duree": Quantity(value=32, unit="min")}}
    )
    a3b.add_evidence(
        id="ev-175",
        description="Photo + sonde de coeur de gateau",
        source="file:///labo/essai-175/photo.jpg",
        metrics={"hauteur_cm": Quantity(value=4.8, unit="cm")},
    )
    a3b.conclude(status="concluded", decision="promote", summary="Meilleure levee, bords dores, centre moelleux.")
    a3 = a3b.commit()

    v2b = repo.derive(v1.id, title="Melange plus long", intent="Un melange plus long homogeneise-t-il mieux la pate ?")
    v2b.steps[0] = v2b.steps[0].model_copy(update={"description": "Farine, sucre, levure - fouetter 4 min (au lieu de 2)"})
    v2b.add_evidence(
        id="ev-melange",
        description="Notes de texture de pate",
        source="file:///labo/melange-long/notes.txt",
        metrics={"hauteur_cm": Quantity(value=4.6, unit="cm")},
    )
    v2b.conclude(status="concluded", decision="promote", summary="Pate plus homogene, sans impact sur la cuisson.")
    v2b.commit()

    merge_b = repo.merge(
        "main",
        a3.id,
        title="Fusion : temperature de cuisson optimisee",
        intent=(
            "Combiner le melange ameliore (main) et la temperature de cuisson validee sur la "
            "branche d'essai, sans reprendre le reste de l'exploration."
        ),
        take_steps=["[2]"],
    )
    merge_b.conclude(
        status="concluded",
        decision="promote",
        summary=(
            "Recette consolidee : melange 4 min + cuisson 175C/32min. Les essais a 160C et 185C "
            "restent tracables sur la branche essai-cuisson pour reference future."
        ),
    )
    merge_b.commit()

    return repo


def render(repo: Repository, *, embed_plotly: bool) -> str:
    history = repo.log("essai-cuisson")  # a3, a2, a1, v1 (newest first)
    a3, a2, a1, v1 = history[0], history[1], history[2], history[3]
    v2 = [e for e in repo if e.branch == "main" and e.title == "Melange plus long"][0]
    merged = repo.get("main")

    fig = build_graph_figure(repo)
    plot_html = fig.to_html(
        include_plotlyjs=True if embed_plotly else "cdn",
        full_html=False,
        div_id="follow-graph",
        config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["toImage"]},
    )

    graph_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Graphe de filiation</div>
      <h2 class="section-title">follow graph — rendu Plotly, sans Graphviz</h2>
      <p class="section-desc">
        Disposition en couches calculee par Follow lui-meme (une rangee par generation). Le
        commit de fusion est le seul noeud a deux aretes entrantes : il descend a la fois de la
        pointe de <code>main</code> et de la pointe de <code>essai-cuisson</code>.
      </p>
    </div>
    <div class="graph-frame">
      <div class="graph-inner">
        {plot_html}
      </div>
      <div class="graph-legend">
        <span class="legend-item good"><span class="legend-dot"></span>concluded &middot; promote</span>
        <span class="legend-item explore"><span class="legend-dot"></span>concluded &middot; branch (exploration)</span>
        <span class="legend-item bad"><span class="legend-dot"></span>abandoned</span>
        <span class="legend-item neutral"><span class="legend-dot"></span>draft / running</span>
      </div>
    </div>
  </section>"""

    trials_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Branche essai-cuisson</div>
      <h2 class="section-title">Trois commits pour faire varier une seule etape</h2>
      <p class="section-desc">
        Chaque commit derive du precedent et ne change que les parametres de l'etape 3
        (temperature / duree de cuisson). Objectif herite de la reference : une hauteur &ge; 4,5&nbsp;cm.
      </p>
    </div>
    <div class="trial-grid">
{trial_card(order_label="Essai 1", exp_id=a1.id, headline="160°C", headline_unit="/ 42 min",
            meta=a1.conclusion.summary, metric_label="hauteur_cm",
            metric_value=str(a1.evidence[0].metrics["hauteur_cm"]), verdict="branch", verdict_label="Rejete — on continue")}
{trial_card(order_label="Essai 2", exp_id=a2.id, headline="185°C", headline_unit="/ 28 min",
            meta=a2.conclusion.summary, metric_label="hauteur_cm",
            metric_value=str(a2.evidence[0].metrics["hauteur_cm"]), verdict="branch", verdict_label="Rejete — on continue")}
{trial_card(order_label="Essai 3", exp_id=a3.id, headline="175°C", headline_unit="/ 32 min",
            meta=a3.conclusion.summary, metric_label="hauteur_cm",
            metric_value=str(a3.evidence[0].metrics["hauteur_cm"]), verdict="promote", verdict_label="Retenu pour la fusion")}
    </div>
  </section>"""

    resolution_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Resolution de la fusion</div>
      <h2 class="section-title">follow merge main essai-cuisson --take-steps "[2]"</h2>
      <p class="section-desc">
        Pendant que la branche explorait la cuisson, <code>main</code> a evolue de son cote (un
        melange plus long, etape 1). Les deux lignes divergent donc sur deux etapes — Follow ne
        choisit rien automatiquement : chaque etape en conflit est resolue explicitement.
      </p>
    </div>
    <div class="resolution-list">
{resolution_conflict_row(
    step_index=0, step_name="Etape 1 — Melanger le sec",
    left_src="main", left_val="« …fouetter 4 min (au lieu de 2) »", left_note=f"Changement independant, commit {v2.id[:12]} sur main",
    right_src="essai-cuisson", right_val="« …fouetter 2 min »", right_note="Jamais retouche sur cette branche",
    winner="left", flag_text='chemin non liste dans --take-steps &rarr; valeur de ref_a (main) conservee par defaut',
)}
{resolution_plain_row(1, "Etape 2 — Melanger le liquide")}
{resolution_conflict_row(
    step_index=2, step_name="Etape 3 — Cuire",
    left_src="main", left_val="170°C / 35 min", left_note="Valeur de reference, jamais retestee sur main",
    right_src="essai-cuisson", right_val="175°C / 32 min", right_note="Valide apres 3 essais (voir ci-dessus)",
    winner="right", flag_text='--take-steps "[2]" &rarr; valeur de ref_b (essai-cuisson) explicitement demandee', arrow="&rarr;",
)}
{resolution_plain_row(3, "Etape 4 — Refroidir")}
{resolution_plain_row(4, "Etape 5 — Demouler")}
    </div>
  </section>"""

    fiche_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Fiche de l'experience</div>
      <h2 class="section-title">Le commit de fusion, sur main</h2>
    </div>
{fiche_card(
    fiche_title=merged.title, exp_id=merged.id, branch=merged.branch,
    badges=[merged.conclusion.status, merged.conclusion.decision],
    intent=merged.intent,
    parents=[
        ("baseline", "main", f"{v2.id[:12]} — {v2.title}"),
        ("merge_source", "essai-cuisson", f"{a3.id[:12]} — {a3.title}"),
    ],
    conclusion=merged.conclusion.summary,
)}
  </section>"""

    footer = f"""<footer class="footer section">
    <div class="section-head">
      <div class="section-label">Reproduire</div>
      <h2 class="section-title">Les memes commandes, en CLI</h2>
    </div>
    <div class="repro">
      <div class="cmt"># apres les 3 commits sur la branche essai-cuisson…</div>
      <div class="cmd">follow diff main essai-cuisson --repo labo --steps</div>
      <div>~ [2].parameters.temperature: 170 C -&gt; 175 C</div>
      <div>~ [2].parameters.duree: 35 min -&gt; 32 min</div>
      <br />
      <div class="cmd">follow merge main essai-cuisson --repo labo \\</div>
      <div>&nbsp;&nbsp;--title "Fusion : temperature de cuisson optimisee" \\</div>
      <div>&nbsp;&nbsp;--intent "Adopter la cuisson validee sans reprendre le reste" \\</div>
      <div>&nbsp;&nbsp;--take-steps "[2]" --out merge.json</div>
      <br />
      <div class="cmd">follow commit merge.json --repo labo</div>
      <div>{merged.id[:14]}…  (main)  {merged.title}</div>
    </div>
    <p class="credit">Genere avec <code>python -m demos.fusion_selective</code> — toutes les valeurs ci-dessus viennent d'une execution reelle du scenario (voir demos/fusion_selective.py).</p>
  </footer>"""

    return render_report(
        title="Fusion sélective",
        description=(
            "Démo Follow : une branche d'essai à 3 commits, fusionnée dans main en ne reprenant "
            "qu'une seule étape sur cinq, avec résolution de conflit explicite."
        ),
        eyebrow="Follow · dépôt d'expériences",
        heading="Fusionner une branche d'essai sans reprendre toute l'exploration",
        subtitle=(
            "Un scénario réel exécuté avec la bibliothèque : une recette de référence à 5 étapes "
            "sur <code>main</code>, une branche <code>essai-cuisson</code> pour faire varier "
            "l'étape 3 (température de cuisson) sur trois commits, puis une fusion qui ne "
            "rapatrie que cette étape — chaque autre différence est résolue manuellement, "
            "chemin par chemin."
        ),
        stat_chips=[
            "<b>6</b> commits",
            "<b>2</b> branches",
            "<b>1</b> fusion (2 parents)",
            "<b>1</b> chemin repris de la branche",
        ],
        sections=[graph_section, trials_section, resolution_section, fiche_section],
        footer=footer,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demos/output/fusion_selective.html")
    parser.add_argument("--embed", action="store_true", help="embed plotly.js (~4.8MB, fully offline) instead of using the CDN")
    args = parser.parse_args()

    repo = build_repository()
    html = render(repo, embed_plotly=args.embed)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
