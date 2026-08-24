"""Reproduce the "moule vert / moule rouge" scenario: a split names each variant with a real
physical name (the mold used, not an abstract id), and a *separate* follow-up experiment - a
different branch, no parent, no reloaded reference to the split - reuses one of those names.
``repo.find_entity()`` links the two automatically, by name alone. See docs/entities.rst for the
same story narrated in prose.

Run: python -m demos.entity_tracking [--out demos/output/entity_tracking.html] [--embed]
"""

from __future__ import annotations


from demos._main import run_demo
from demos._report import batch_table, experiment_fiche, render_report
from examples.chocolate_cake import CakeTrialBatch, ChocolateCake
from follow import Quantity, Repository, analyze_batch
from follow.report import graph_section


def _baseline_recipe() -> ChocolateCake:
    return ChocolateCake(
        name="Gateau au chocolat - reference",
        dark_chocolate=Quantity(value=200, unit="g"),
        cocoa_percent=Quantity(value=64, unit="%"),
        butter=Quantity(value=150, unit="g"),
        sugar=Quantity(value=180, unit="g"),
        eggs=4,
        flour=Quantity(value=120, unit="g"),
        baking_powder=Quantity(value=5, unit="g"),
        bake_temperature=Quantity(value=190, unit="C"),
        bake_duration=Quantity(value=35, unit="min"),
    )


def build_repository() -> Repository:
    repo = Repository()

    # -- Stage 1: a split whose entities are named after something physical - the mold - rather
    # than an abstract trial number. Nothing new needed for this: entity_id is just a field on
    # ChocolateCake (see examples/chocolate_cake.py), set per trial like any other. -------------
    split = repo.new(
        branch="main",
        structure=CakeTrialBatch(
            batch_id="MOULES-1",
            trials=[
                _baseline_recipe().model_copy(update={"trial_id": 1, "entity_id": "moule-vert"}),
                _baseline_recipe().model_copy(update={"trial_id": 2, "entity_id": "moule-rouge"}),
            ],
        ),
        title="Cuisson : moule vert vs moule rouge",
        intent="Comparer deux moules physiques a recette identique, pour verifier qu'ils cuisent pareil avant de les reutiliser dans d'autres essais.",
    )
    split.add_evidence(id="ev-moules", description="Mesures + photos des deux gateaux demoules", source="file:///lab/moules/mesures.csv")
    split.conclude(
        status="concluded", decision="promote",
        summary="Les deux moules donnent un resultat equivalent (hauteur et densite comparables) : aucun biais du moule lui-meme.",
        next_steps="Les deux gateaux existent physiquement - le moule vert et le moule rouge peuvent maintenant recevoir chacun leur propre modification.",
    )
    split_commit = split.commit()

    # -- Stage 2a: a *separate* experiment on the cake that came out of the green mold - a new
    # branch, no parent, no reference back to `split_commit` reloaded. Just the same entity_id,
    # reused. -------------------------------------------------------------------------------------
    nutella = repo.new(
        branch="moule-vert-nutella",
        structure=_baseline_recipe().model_copy(update={
            "name": "Gateau (moule vert) + coeur nutella",
            "entity_id": "moule-vert",
            "topping": "coeur nutella injecte apres cuisson",
        }),
        title="Injection nutella sur le gateau du moule vert",
        intent="Ce gateau precis (moule vert) supporte-t-il une injection de nutella sans s'effondrer ?",
    )
    nutella.add_evidence(id="ev-nutella", description="Photo en coupe apres injection", source="file:///lab/moule-vert/injection.jpg")
    nutella.conclude(status="concluded", decision="promote", summary="Injection reussie, le gateau tient la structure.")
    nutella_commit = nutella.commit()

    # -- Stage 2b: same idea, the red mold's cake gets a different modification. Also a fresh
    # branch, also no reference reloaded. -----------------------------------------------------------
    glacage = repo.new(
        branch="moule-rouge-glacage",
        structure=_baseline_recipe().model_copy(update={
            "name": "Gateau (moule rouge) + glacage",
            "entity_id": "moule-rouge",
            "topping": "glacage au chocolat noir",
        }),
        title="Glacage sur le gateau du moule rouge",
        intent="Ce gateau precis (moule rouge) tient-il un glacage sans fissurer ?",
    )
    glacage.add_evidence(id="ev-glacage", description="Photo apres glacage, 2h de prise", source="file:///lab/moule-rouge/glacage.jpg")
    glacage.conclude(status="concluded", decision="promote", summary="Glacage reussi, pas de fissure.")
    glacage_commit = glacage.commit()

    # -- The point of the whole feature: find_entity() links split_commit + nutella_commit through
    # "moule-vert" alone - no parent between them, no reference, two different branches. -----------
    assert [e.id for e in repo.find_entity("moule-vert")] == [split_commit.id, nutella_commit.id]
    assert [e.id for e in repo.find_entity("moule-rouge")] == [split_commit.id, glacage_commit.id]

    return repo


def render(repo: Repository, *, embed_plotly: bool) -> str:
    split = repo.get("main")
    nutella = repo.get("moule-vert-nutella")
    glacage = repo.get("moule-rouge-glacage")

    graph_section_html = graph_section(
        repo,
        heading="3 expériences, 3 branches, aucune arête entre elles",
        description=(
            "<code>moule-vert-nutella</code> et <code>moule-rouge-glacage</code> n'ont ni parent ni référence vers <code>main</code> — le graphe git-like ne montre donc aucun lien. C'est exactement le cas que <code>find_entity</code> couvre : deux commits physiquement liés (même moule) mais sans aucune parenté à suivre."
        ),
        embed_plotly=embed_plotly,
    )

    structure = repo.load_structure(split)
    variation = analyze_batch(structure.trials, ignore=["trial_id"])
    split_table = batch_table(
        variation, entity_labels=[f"#{t.trial_id} ({t.entity_id})" for t in structure.trials],
        title="Split (2 moules)", standalone=False,
    )
    split_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Étape 1 — Nommer chaque variante physiquement</div>
      <h2 class="section-title">{split.title}</h2>
      <p class="section-desc">
        Chaque essai du split porte un <code>entity_id</code> — pas un numéro abstrait, le nom du
        moule réellement utilisé. Rien d'autre à faire : c'est un champ de plus sur la structure.
      </p>
    </div>
{experiment_fiche(split, split=split_table)}
  </section>"""

    followup_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Étape 2 — Deux expériences séparées, plus tard</div>
      <h2 class="section-title">Chaque moule reçoit sa propre modification</h2>
      <p class="section-desc">
        <code>{nutella.title}</code> (branche <code>{nutella.branch}</code>) et
        <code>{glacage.title}</code> (branche <code>{glacage.branch}</code>) : deux nouvelles
        expériences, chacune sur sa propre branche, sans parent ni référence rechargée vers
        l'expérience du split. Le seul lien posé : reprendre le même <code>entity_id</code>.
      </p>
    </div>
{experiment_fiche(nutella)}
{experiment_fiche(glacage)}
  </section>"""

    trace_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Étape 3 — Retrouver le lien automatiquement</div>
      <h2 class="section-title">follow trace moule-vert</h2>
      <p class="section-desc">
        <code>repo.find_entity("moule-vert")</code> parcourt tout le dépôt (toutes branches, tout
        lignage confondu) et retrouve les deux expériences qui mentionnent ce nom — sans qu'aucune
        des deux n'ait jamais référencé l'autre.
      </p>
    </div>
    <div class="repro">
      <div class="cmd">follow trace moule-vert --repo labo</div>
      <div>{split.id[:14]}…  ({split.branch})  {split.title}  [{split.conclusion.status}]  -- trials[0]</div>
      <div>{nutella.id[:14]}…  ({nutella.branch})  {nutella.title}  [{nutella.conclusion.status}]  -- (racine)</div>
      <br />
      <div class="cmd">follow trace moule-rouge --repo labo</div>
      <div>{split.id[:14]}…  ({split.branch})  {split.title}  [{split.conclusion.status}]  -- trials[1]</div>
      <div>{glacage.id[:14]}…  ({glacage.branch})  {glacage.title}  [{glacage.conclusion.status}]  -- (racine)</div>
    </div>
  </section>"""

    footer = """<footer class="footer section">
    <div class="section-head">
      <div class="section-label">Reproduire</div>
      <h2 class="section-title">La même idée, en résumé</h2>
    </div>
    <div class="repro">
      <div class="cmt"># le split nomme chaque variante avec un nom physique reel</div>
      <div>CakeTrialBatch(trials=[cake(entity_id="moule-vert"), cake(entity_id="moule-rouge")])</div>
      <br />
      <div class="cmt"># plus tard, une experience separee reutilise juste le nom</div>
      <div>repo.new(branch="moule-vert-nutella", structure=cake(entity_id="moule-vert"), ...)</div>
      <br />
      <div class="cmt"># retrouve automatiquement, sans reference ni parent</div>
      <div class="cmd">repo.find_entity("moule-vert")  # -&gt; les deux expériences, triées par date</div>
      <br />
      <div class="cmt"># reproduire ce scenario</div>
      <div class="cmd">python -m demos.entity_tracking</div>
    </div>
    <p class="credit">Généré avec <code>python -m demos.entity_tracking</code> — voir <code>docs/entities.rst</code> pour le même scénario narré en détail.</p>
  </footer>"""

    return render_report(
        title="Suivre une entité physique",
        description=(
            "Démo Follow : nommer chaque variante d'un split avec un nom physique réel, puis "
            "retrouver automatiquement les expériences séparées qui réutilisent ce nom - sans "
            "référence ni parenté git à poser à la main."
        ),
        eyebrow="Follow · entités physiques",
        heading="Le moule vert et le moule rouge, suivis à travers plusieurs expériences séparées",
        subtitle=(
            "Un split nomme chaque gâteau d'après le moule utilisé ; deux expériences plus "
            "tardives, chacune sur sa propre branche et sans aucun lien de filiation, "
            "réutilisent ce nom - Follow les relie automatiquement, sans bookkeeping manuel."
        ),
        stat_chips=[
            f"<b>{len(repo)}</b> commits",
            f"<b>{len(repo.branches)}</b> branches",
            "<b>0</b> lien de filiation entre elles",
            "<b>2</b> entités suivies",
        ],
        sections=[graph_section_html, split_section, followup_section, trace_section],
        footer=footer,
    )


def main() -> None:
    run_demo(
        doc=__doc__,
        default_out="demos/output/entity_tracking.html",
        build_repository=build_repository,
        render=render,
    )


if __name__ == "__main__":
    main()
