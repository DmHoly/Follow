"""A case classic git has no concept for: one experiment - one intent, one protocol, one
conclusion - whose Structure is a lot of 25 wafers split across a 5x5 semi-factorial DOE
(implant dose x anneal temperature). It's still one commit, but "one commit, 25 variants"
needs a hybrid display: the experiment-level fiche (this lot, as a whole), and the same lot
"exploded" entity by entity to see which parameters were actually varied. That's exactly what
follow.batch.analyze_batch + follow.report.batch_table give you, on top of the same Structure
composition (WaferLot.wafers: list[Wafer]) Follow already supports - nothing new in the core
engine, just a generic N-way comparison over a list field.

The 25 wafers themselves are generated, not hand-written: follow.design.full_factorial crosses
the two factors' value grids (follow.design.lin, a thin numpy.linspace wrapper) against a single
reference Wafer, so the split is defined once as "these two factors, these ranges" rather than
copy-pasted 25 times.

A second commit runs a 5-wafer confirmation lot, all at the winning combination: analyze_batch
reports it as uniform (no variation), the other half of the hybrid display.

Run: python -m demos.wafer_doe [--out demos/output/wafer_doe.html] [--embed]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from demos._report import batch_table, fiche_card, render_report
from examples.wafer_doe import Wafer, WaferLot
from follow import Quantity, Repository, analyze_batch
from follow.design import full_factorial, lin
from follow.graphing import build_graph_figure

_REFERENCE_WAFER = Wafer(
    slot=0,
    implant_dose=Quantity(value=0, unit="1e14 cm^-2"),
    anneal_temperature=Quantity(value=0, unit="C"),
    anneal_duration=Quantity(value=30, unit="min"),
)


def _factorial_lot() -> WaferLot:
    wafers = full_factorial(
        _REFERENCE_WAFER,
        id_field="slot",
        implant_dose=lin(2, 10, 5, unit="1e14 cm^-2"),
        anneal_temperature=lin(900, 1100, 5, unit="C"),
    )
    return WaferLot(lot_id="LOT-A", wafer_diameter=Quantity(value=200, unit="mm"), process="implant+anneal", wafers=wafers)


def _confirmation_lot() -> WaferLot:
    # the winning combination from LOT-A (dose=6e14, temp=1000C), re-run on 5 wafers to confirm
    # reproducibility - a uniform batch, on purpose: nothing to generate, just repeat it.
    winner = _REFERENCE_WAFER.model_copy(
        update={"implant_dose": Quantity(value=6, unit="1e14 cm^-2"), "anneal_temperature": Quantity(value=1000, unit="C")}
    )
    wafers = [winner.model_copy(update={"slot": i + 1}) for i in range(5)]
    return WaferLot(lot_id="LOT-B", wafer_diameter=Quantity(value=200, unit="mm"), process="implant+anneal", wafers=wafers)


def build_repository() -> Repository:
    repo = Repository()

    ab = repo.new(
        branch="main",
        structure=_factorial_lot(),
        title="LOT-A - split factoriel 5x5 (dose x temperature de recuit)",
        intent="Quelle combinaison dose d'implantation / temperature de recuit minimise la resistance de couche ?",
    )
    ab.add_step(order=1, name="Implantation", description="Implantation ionique, dose variable selon le plan factoriel")
    ab.add_step(order=2, name="Recuit d'activation", description="Four de recuit, temperature variable selon le plan factoriel", depends_on=[1])
    ab.add_step(order=3, name="Mesure 4 pointes", description="Resistance de couche (sheet resistance) au centre de chaque wafer", depends_on=[2])
    ab.add_objective(name="Resistance de couche", metric="rs_ohm_sq", direction="minimize", target=80.0)
    ab.add_evidence(
        id="ev-lot-a", description="Mesures 4 pointes, 25 wafers", source="file:///fab/lot-a/measurements.csv",
        metrics={"rs_ohm_sq_min": Quantity(value=76, unit="ohm/sq"), "rs_ohm_sq_median": Quantity(value=94, unit="ohm/sq")},
    )
    ab.conclude(
        status="concluded", decision="branch",
        summary=(
            "Le minimum de resistance de couche (76 ohm/sq) est obtenu au wafer #13 "
            "(dose=6e14 cm^-2, recuit=1000C) - au centre du plan, coherent avec un optimum "
            "d'activation electrique. Un lot de confirmation est necessaire avant promotion."
        ),
        objective_results=[dict(objective="Resistance de couche", status="met", observed=Quantity(value=76, unit="ohm/sq"), reasoning="Wafer #13, en dessous de la cible de 80 ohm/sq.")],
    )
    lot_a = ab.commit()

    bb = repo.derive(
        lot_a.id, title="LOT-B - confirmation a dose=6e14/1000C sur 5 wafers",
        intent="La combinaison gagnante du plan factoriel est-elle reproductible sur un lot homogene ?",
    )
    bb.structure = _confirmation_lot()
    bb.steps[0] = bb.steps[0].model_copy(update={"description": "Implantation ionique, dose fixe 6e14 cm^-2"})
    bb.steps[1] = bb.steps[1].model_copy(update={"description": "Four de recuit, 1000C fixe"})
    bb.add_evidence(
        id="ev-lot-b", description="Mesures 4 pointes, 5 wafers", source="file:///fab/lot-b/measurements.csv",
        metrics={"rs_ohm_sq_min": Quantity(value=75, unit="ohm/sq"), "rs_ohm_sq_max": Quantity(value=79, unit="ohm/sq")},
    )
    bb.conclude(
        status="concluded", decision="promote",
        summary="Reproductible : les 5 wafers du lot de confirmation restent tous dans 75-79 ohm/sq. Combinaison retenue pour la production.",
        objective_results=[dict(objective="Resistance de couche", status="met", observed=Quantity(value=77, unit="ohm/sq"), reasoning="Moyenne du lot de confirmation, sous la cible de 80 ohm/sq.")],
    )
    lot_b = bb.commit()
    repo.tag("combinaison-retenue", lot_b.id)

    return repo


def render(repo: Repository, *, embed_plotly: bool) -> str:
    lot_a = repo.log("main")[-1]
    lot_b = repo.get("combinaison-retenue")

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
      <h2 class="section-title">2 commits : split factoriel puis confirmation</h2>
      <p class="section-desc">
        Un seul plan factoriel (LOT-A, 25 wafers) suivi d'une confirmation homogene
        (LOT-B, 5 wafers) - chacun est un unique commit Follow, quel que soit le nombre
        d'entites que sa structure contient.
      </p>
    </div>
    <div class="graph-frame">
      <div class="graph-inner">
        {plot_html}
      </div>
    </div>
  </section>"""

    lot_a_structure = repo.load_structure(lot_a)
    lot_a_variation = analyze_batch(lot_a_structure.wafers, ignore=["slot"])
    lot_a_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">LOT-A - vue expérience</div>
      <h2 class="section-title">{lot_a.title}</h2>
      <p class="section-desc">
        La fiche ci-dessous est la vue "une expérience" habituelle. En dessous, la même
        expérience "explosée" par <code>analyze_batch(lot.wafers)</code> : ce qui est
        constant sur les 25 wafers, et ce qui varie réellement (les deux facteurs du plan).
      </p>
    </div>
{fiche_card(
    fiche_title=lot_a.title, exp_id=lot_a.id, branch=lot_a.branch,
    badges=[lot_a.conclusion.status, lot_a.conclusion.decision],
    intent=lot_a.intent, parents=[], conclusion=lot_a.conclusion.summary,
)}
{batch_table(lot_a_variation, entity_labels=[f"#{w.slot}" for w in lot_a_structure.wafers], title="LOT-A explosé - 25 wafers")}
  </section>"""

    lot_b_structure = repo.load_structure(lot_b)
    lot_b_variation = analyze_batch(lot_b_structure.wafers, ignore=["slot"])
    lot_b_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">LOT-B - vue expérience</div>
      <h2 class="section-title">{lot_b.title}</h2>
      <p class="section-desc">
        Le lot de confirmation n'a plus qu'une seule combinaison : <code>analyze_batch</code>
        le signale comme uniforme (<code>is_uniform</code>), l'autre moitié de l'affichage
        hybride - rien à explorer, juste confirmer.
      </p>
    </div>
{fiche_card(
    fiche_title=lot_b.title, exp_id=lot_b.id, branch=lot_b.branch,
    badges=[lot_b.conclusion.status, lot_b.conclusion.decision, "tag: combinaison-retenue"],
    intent=lot_b.intent, parents=[("parent", lot_b.branch, f"{lot_a.id[:12]} — {lot_a.title}")],
    conclusion=lot_b.conclusion.summary,
)}
{batch_table(lot_b_variation, entity_labels=[f"#{w.slot}" for w in lot_b_structure.wafers], title="LOT-B explosé - 5 wafers")}
  </section>"""

    footer = f"""<footer class="footer section">
    <div class="section-head">
      <div class="section-label">Reproduire</div>
      <h2 class="section-title">Le cas d'école : un plan factoriel n'est pas couvert par git</h2>
    </div>
    <div class="repro">
      <div class="cmt"># une expérience, 25 entités, deux facteurs qui varient</div>
      <div>from follow import analyze_batch</div>
      <div>lot = repo.load_structure(lot_a)</div>
      <div>variation = analyze_batch(lot.wafers, ignore=["slot"])</div>
      <div>variation.constant   # baseline partagée par les 25 wafers</div>
      <div>variation.varying    # les facteurs du DOE, wafer par wafer</div>
      <br />
      <div class="cmt"># reproduire ce scenario</div>
      <div class="cmd">python -m demos.wafer_doe</div>
    </div>
    <p class="credit">Généré avec <code>python -m demos.wafer_doe</code> — même moteur générique que les autres démos (recette, MOSFET, cellule solaire) : <code>follow.batch</code> n'a rien de spécifique aux wafers.</p>
  </footer>"""

    return render_report(
        title="Lot de wafers - plan factoriel",
        description=(
            "Démo Follow : un split factoriel 5x5 sur 25 wafers modélisé comme une seule "
            "expérience, avec un affichage hybride (fiche d'expérience + vue explosée par "
            "entité) via follow.batch.analyze_batch."
        ),
        eyebrow="Follow · cas d'école DOE",
        heading="Un plan factoriel sur 25 wafers, comme une seule expérience Follow",
        subtitle=(
            "Git n'a pas de notion pour « une expérience, N variantes structurelles ». Follow "
            "n'en a pas besoin : le lot est une Structure normale (une liste de wafers), et "
            "follow.batch.analyze_batch lit mécaniquement ce qui est constant et ce qui varie "
            "— le même principe s'applique à des recettes, des lentilles ou des grilles de "
            "barbecue."
        ),
        stat_chips=[
            "<b>2</b> commits",
            "<b>25</b> wafers (LOT-A)",
            "<b>2</b> facteurs de variation",
            "<b>5</b> wafers de confirmation (LOT-B)",
        ],
        sections=[graph_section, lot_a_section, lot_b_section],
        footer=footer,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demos/output/wafer_doe.html")
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
