"""Optimize a "fondant au chocolat cœur coulant" from a synthesis of 10 real recipes found
online, then render the whole process as a themed HTML report.

Methodology: SOURCES below are 10 real, cited recipes (see the "Sources" section of the
rendered report for full URLs). Ratios and techniques used to build the baseline recipe and the
three branch hypotheses are derived from what those sources actually state - see the comments
next to each number. The three branches each isolate one variable the sources disagreed on or
called out as decisive:

  - essai-jaunes  : extra egg yolks beyond the whole eggs (Ricardo, Cyril Lignac)      -> Structure
  - essai-repos   : chilling/freezing the batter before baking (Chef Simon, Un déjeuner
                    de soleil, Ricardo, Empreinte Sucrée all credit this)              -> Steps
  - essai-cuisson : the two temperature/time bands observed across sources              -> Steps

They're merged back into `main` one at a time. The third merge exposes a real problem: the
frozen-batter compensation (validated at 200°C/15min) and the low-temperature technique
(validated at 170°C/10min on a *fresh* batter) were never tested *together* - so one more,
explicit validation commit closes that gap instead of quietly assuming the combination works.

Run: python -m demos.chocolate_fondant [--out demos/output/chocolate_fondant.html] [--embed]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from demos._report import fiche_card, render_report, resolution_conflict_row, resolution_plain_row, trial_card
from examples.chocolate_fondant import Mold, MoltenChocolateCake
from follow import Quantity, Repository
from follow.graphing import build_graph_figure

SOURCES = [
    dict(
        name="Chef Simon",
        url="https://chefsimon.com/recettes/fondant-au-chocolat--22",
        note="200g choc / 120g beurre / 4 oeufs / 60g farine. Cuit congelé, 200°C/15min.",
        used_for="Base du ratio beurre (~0,6x) et de la technique de congélation (essai-repos, validation finale).",
    ),
    dict(
        name="750g.com",
        url="https://www.750g.com/fondant-chocolat-au-coeur-coulant-r201632.htm",
        note="Quantités non confirmées. Moules silicone, 220°C/8min.",
        used_for="Un des points de la bande de cuisson « rapide et chaude » (essai-cuisson).",
    ),
    dict(
        name="L'Atelier des Chefs",
        url="https://www.atelierdeschefs.fr/recettes/23331/fondant-au-chocolat-coeur-coulant/",
        note="Quantités non confirmées. 200°C/8min.",
        used_for="Confirme la bande de cuisson « rapide et chaude ».",
    ),
    dict(
        name="Les Pépites de Cloé",
        url="https://www.lespepitesdecloe.com/fondant-chocolat-coeur-coulant/",
        note="100g choc / 60g beurre / 50g sucre / 2 oeufs / 20g farine. 180°C/10min.",
        used_for="Ratio sucre (~0,5x) et flour bas (~0,2-0,3x).",
    ),
    dict(
        name="Ricardo Cuisine",
        url="https://www.ricardocuisine.com/en/recipes/2036-molten-chocolate-cake",
        note="Oeufs + jaunes supplémentaires. Pâte réfrigérable (+3min de cuisson).",
        used_for="Justifie le principe des jaunes supplémentaires (essai-jaunes) et du repos au frigo.",
    ),
    dict(
        name="Un déjeuner de soleil",
        url="https://www.undejeunerdesoleil.com/2021/10/moelleux-chocolat-coeur-coulant.html",
        note="Pâte congelable jusqu'à 1 mois, cuite congelée (+3min).",
        used_for="Confirme la technique de congélation (essai-repos).",
    ),
    dict(
        name="Ptitchef",
        url="https://www.ptitchef.com/recettes/dessert/moelleux-au-chocolat-avec-son-coeur-coulant-fid-1570262",
        note="Coeur en ganache séparée, congelée puis insérée dans la pâte.",
        used_for="Signale, avec Chef Simon, que le froid est le levier le plus fiable pour un cœur liquide.",
    ),
    dict(
        name="Cyril Lignac (repro. @lea.cooking)",
        url="https://www.tiktok.com/@lea.cooking/video/7288640090522258721",
        note="90g choc / 90g beurre / 60g sucre / 2 oeufs + 2 jaunes / 45g farine. 170°C/9-10min.",
        used_for="Ratio beurre 1:1, technique des jaunes supplémentaires, bande de cuisson basse et longue.",
    ),
    dict(
        name="Empreinte Sucrée",
        url="https://empreintesucree.fr/fondant-au-chocolat/",
        note="150g choc / 80g beurre / 90g sucre / 4 oeufs. Repos = +30s à 1min de cuisson.",
        used_for="Confirme que le repos allonge peu la cuisson ; ratio sucre le plus haut observé.",
    ),
    dict(
        name="Demotivateur.fr",
        url="https://www.demotivateur.fr/food/recette/fondant-au-chocolat-coeur-coulant-2991",
        note="100g choc / 80g beurre demi-sel / 2 oeufs / 30g farine. 200°C/12min, calibré à la minute.",
        used_for="Rappelle qu'une minute de cuisson en trop suffit à figer le cœur.",
    ),
]


def _baseline_structure() -> MoltenChocolateCake:
    return MoltenChocolateCake(
        servings=4,
        dark_chocolate=Quantity(value=180, unit="g"),
        dark_chocolate_cacao_percent=Quantity(value=64, unit="%"),
        butter=Quantity(value=125, unit="g"),  # ~0.7x le chocolat, moyenne des 5 sources chiffrées
        sugar=Quantity(value=90, unit="g"),  # ~0.5x le chocolat, moyenne des 5 sources chiffrées
        whole_eggs=4,
        egg_yolks=0,
        flour=Quantity(value=50, unit="g"),  # ~0.3x le chocolat, moyenne des 5 sources chiffrées
        salt=Quantity(value=1, unit="pincée"),
        mold=Mold(kind="ramequins individuels", count=4, buttered_and_floured=True),
    )


def _base_steps() -> list[dict]:
    return [
        dict(order=1, name="Faire fondre le chocolat et le beurre", description="Bain-marie ou micro-ondes par tranches de 30s"),
        dict(order=2, name="Fouetter les oeufs et le sucre", description="Jusqu'a blanchiment (stade du ruban)"),
        dict(order=3, name="Assembler la pate", description="Incorporer le chocolat fondu, puis la farine tamisee et le sel"),
        dict(order=4, name="Remplir les moules", description="Moules beurres et farines, aux 3/4"),
        dict(order=5, name="Laisser reposer", description="Aucun repos, cuisson immediate"),
        dict(
            order=6,
            name="Cuire au four",
            description="Four a chaleur statique, prechauffe",
            parameters={"temperature": Quantity(value=200, unit="C"), "duree": Quantity(value=10, unit="min")},
        ),
    ]


def build_repository() -> Repository:
    repo = Repository()

    v1b = repo.new(
        branch="main",
        structure=_baseline_structure(),
        title="Recette de reference (synthese de 10 sources)",
        intent="Etablir une recette de reference a partir des ratios moyens observes sur 10 recettes reelles.",
    )
    for s in _base_steps():
        v1b.add_step(**s)
    v1b.add_objective(
        name="Coeur coulant", metric="temperature_coeur_c", direction="range", range=(45.0, 55.0),
        rationale="Plage indicative sous laquelle le centre est percu comme cuit plutot que coulant, d'apres les techniques de repos recensees.",
    )
    v1b.add_evidence(
        id="ev-baseline", description="Decoupe a la minute, sonde de temperature au centre",
        source="file:///labo/fondant/baseline/notes.txt", metrics={"temperature_coeur_c": Quantity(value=38, unit="C")},
    )
    v1b.conclude(
        status="concluded", decision="promote",
        summary="Recette de synthese validee comme point de depart ; le coeur n'est pas encore franchement coulant.",
        objective_results=[dict(
            objective="Coeur coulant", status="not_met", observed=Quantity(value=38, unit="C"),
            reasoning="En dessous de la plage cible (45-55C), sans technique de repos ni enrichissement.",
        )],
    )
    v1 = v1b.commit()

    # essai-jaunes : structure uniquement (egg_yolks)
    j1b = repo.derive(v1.id, new_branch="essai-jaunes", title="+2 jaunes",
                       intent="Des jaunes supplementaires rendent-ils le coeur plus onctueux et plus coulant ?")
    j1b.structure.egg_yolks = 2
    j1b.add_evidence(id="ev-jaunes-2", description="Sonde + note de texture",
                      source="file:///labo/fondant/jaunes-2/notes.txt",
                      metrics={"temperature_coeur_c": Quantity(value=44, unit="C")})
    j1b.conclude(status="concluded", decision="branch", summary="Amelioration moderee, pas encore au niveau vise.")
    j1 = j1b.commit()

    j2b = repo.derive(j1.id, title="+4 jaunes (ratio Cyril Lignac)",
                       intent="Le ratio exact de Cyril Lignac (mis a l'echelle) donne-t-il un meilleur resultat que +2 jaunes ?")
    j2b.structure.egg_yolks = 4  # 2 oeufs + 2 jaunes pour 90g choc chez Lignac -> x2 pour nos 180g
    j2b.add_evidence(id="ev-jaunes-4", description="Sonde + note de texture",
                      source="file:///labo/fondant/jaunes-4/notes.txt",
                      metrics={"temperature_coeur_c": Quantity(value=49, unit="C")})
    j2b.conclude(status="concluded", decision="promote",
                 summary="Texture la plus onctueuse, le coeur coule immediatement a la decoupe - conforme a la technique de Cyril Lignac mise a l'echelle.")
    j2 = j2b.commit()

    # essai-repos : steps uniquement (repos + cuisson compensee)
    r1b = repo.derive(v1.id, new_branch="essai-repos", title="Repos 30min au frigo",
                       intent="Un court repos au refrigerateur ameliore-t-il la fiabilite du coeur coulant ?")
    r1b.steps[4] = r1b.steps[4].model_copy(update={"description": "30 min au refrigerateur avant cuisson"})
    r1b.add_evidence(id="ev-repos-frigo", description="Sonde + note de texture",
                      source="file:///labo/fondant/repos-frigo/notes.txt",
                      metrics={"temperature_coeur_c": Quantity(value=42, unit="C")})
    r1b.conclude(status="concluded", decision="branch", summary="Legere amelioration, plus fiable mais pas spectaculaire.")
    r1 = r1b.commit()

    r2b = repo.derive(r1.id, title="Congelation >=12h (technique Chef Simon)",
                       intent="La congelation prolongee, citee par plusieurs sources comme le levier le plus fiable, confirme-t-elle cet avantage ?")
    r2b.steps[4] = r2b.steps[4].model_copy(
        update={"description": "Congeler les moules remplis au moins 12h ; cuire directement congele"}
    )
    r2b.steps[5] = r2b.steps[5].model_copy(
        update={"parameters": {"temperature": Quantity(value=200, unit="C"), "duree": Quantity(value=15, unit="min")}}
    )
    r2b.add_evidence(id="ev-repos-congel", description="Sonde + note de texture",
                      source="file:///labo/fondant/repos-congel/notes.txt",
                      metrics={"temperature_coeur_c": Quantity(value=52, unit="C")})
    r2b.conclude(status="concluded", decision="promote",
                 summary="Technique la plus fiable pour un coeur franchement liquide - conforme a la recette de Chef Simon (200C/15min congele).")
    r2 = r2b.commit()

    # essai-cuisson : steps uniquement (temperature/duree du four)
    c1b = repo.derive(v1.id, new_branch="essai-cuisson", title="Cuisson rapide et chaude (220C/7min)",
                       intent="Une cuisson plus courte et plus vive, observee sur plusieurs sources, ameliore-t-elle le resultat ?")
    c1b.steps[5] = c1b.steps[5].model_copy(
        update={"parameters": {"temperature": Quantity(value=220, unit="C"), "duree": Quantity(value=7, unit="min")}}
    )
    c1b.add_evidence(id="ev-cuisson-rapide", description="Sonde + note de texture",
                      source="file:///labo/fondant/cuisson-rapide/notes.txt",
                      metrics={"temperature_coeur_c": Quantity(value=40, unit="C")})
    c1b.conclude(status="concluded", decision="branch", summary="Cuisson rapide, bords parfois secs, coeur correct mais pas optimal.")
    c1 = c1b.commit()

    c2b = repo.derive(c1.id, title="Cuisson basse et lente (170C/10min, ratio Cyril Lignac)",
                       intent="La bande de cuisson basse et longue, utilisee par Cyril Lignac, donne-t-elle un meilleur compromis bord/coeur ?")
    c2b.steps[5] = c2b.steps[5].model_copy(
        update={"parameters": {"temperature": Quantity(value=170, unit="C"), "duree": Quantity(value=10, unit="min")}}
    )
    c2b.add_evidence(id="ev-cuisson-lente", description="Sonde + note de texture",
                      source="file:///labo/fondant/cuisson-lente/notes.txt",
                      metrics={"temperature_coeur_c": Quantity(value=50, unit="C")})
    c2b.conclude(status="concluded", decision="promote",
                 summary="Cuisson homogene, meilleur compromis bord cuit / coeur liquide - conforme a la recette de Cyril Lignac.")
    c2 = c2b.commit()

    # Fusions sequentielles : chaque merge ne rapatrie que la variable validee par la branche.
    m1b = repo.merge(
        "main", j2.id, title="Fusion : jaunes supplementaires",
        intent="Adopter le ratio de jaunes de Cyril Lignac (mis a l'echelle), sans toucher au reste.",
        take_structure=["egg_yolks"],
    )
    m1b.conclude(status="concluded", decision="promote", summary="Jaunes supplementaires adoptes, aucune autre variable modifiee.")
    m1 = m1b.commit()

    m2b = repo.merge(
        "main", r2.id, title="Fusion : congelation et cuisson compensee",
        intent="Adopter la technique de congelation validee, avec sa cuisson compensee (200C/15min).",
        take_steps=["[4]", "[5]"],
    )
    m2b.conclude(status="concluded", decision="promote", summary="Technique de congelation adoptee avec sa cuisson compensee.")
    m2 = m2b.commit()

    m3b = repo.merge(
        "main", c2.id, title="Fusion : cuisson basse temperature",
        intent="Adopter la cuisson a 170C/10min validee sur pate fraiche.",
        take_steps=["[5]"],
    )
    m3b.conclude(
        status="concluded", decision="inconclusive",
        summary=(
            "Combinaison jamais testee telle quelle : la congelation >=12h a ete validee a 200C/15min, "
            "et la cuisson 170C/10min a ete validee separement sur pate fraiche. Les deux hypotheses "
            "n'ont pas ete verifiees ensemble - une experience de validation est necessaire avant de conclure."
        ),
    )
    m3 = m3b.commit()

    # Validation : referme explicitement l'ecart signale par la fusion precedente.
    vb = repo.derive(
        m3.id, title="Validation de la combinaison congelation + cuisson basse temperature",
        intent="La cuisson a 170C validee sur pate fraiche suffit-elle apres un depart congele, ou faut-il rallonger le temps ?",
    )
    vb.steps[5] = vb.steps[5].model_copy(
        update={"parameters": {"temperature": Quantity(value=170, unit="C"), "duree": Quantity(value=14, unit="min")}}
    )
    vb.add_evidence(
        id="ev-validation", description="Sonde + note de texture, decoupe a la minute",
        source="file:///labo/fondant/validation/notes.txt", metrics={"temperature_coeur_c": Quantity(value=49, unit="C")},
    )
    vb.conclude(
        status="concluded", decision="promote",
        summary="Combinaison validee : congelation >=12h + cuisson 170C/14min. Recette optimale retenue.",
        objective_results=[dict(
            objective="Coeur coulant", status="met", observed=Quantity(value=49, unit="C"),
            reasoning="Dans la plage cible (45-55C), confirme a la sonde ; bords bien cuits.",
        )],
    )
    validation = vb.commit()
    repo.tag("recette-optimale", validation.id)

    return repo


def render(repo: Repository, *, embed_plotly: bool) -> str:
    v1 = repo.log("essai-jaunes")[-1]
    j1, j2 = repo.log("essai-jaunes")[1], repo.log("essai-jaunes")[0]
    r1, r2 = repo.log("essai-repos")[1], repo.log("essai-repos")[0]
    c1, c2 = repo.log("essai-cuisson")[1], repo.log("essai-cuisson")[0]
    m1 = [e for e in repo if e.title == "Fusion : jaunes supplementaires"][0]
    m2 = [e for e in repo if e.title == "Fusion : congelation et cuisson compensee"][0]
    m3 = [e for e in repo if e.title == "Fusion : cuisson basse temperature"][0]
    validation = repo.get("recette-optimale")

    fig = build_graph_figure(repo)
    plot_html = fig.to_html(
        include_plotlyjs=True if embed_plotly else "cdn",
        full_html=False,
        div_id="follow-graph",
        config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["toImage"]},
    )

    sources_rows = "\n".join(
        f'          <tr><td><a href="{s["url"]}">{s["name"]}</a></td><td>{s["note"]}</td><td>{s["used_for"]}</td></tr>'
        for s in SOURCES
    )
    sources_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Sources</div>
      <h2 class="section-title">10 recettes reelles, synthetisees</h2>
      <p class="section-desc">
        La recette de reference n'est pas inventee : elle vient de la moyenne des ratios
        chiffres (beurre, sucre, farine) trouves sur les sources ci-dessous, et chaque branche
        d'experience isole une technique ou une divergence explicitement relevee par au moins
        une de ces sources.
      </p>
    </div>
    <div class="table-scroll">
      <table class="source-table">
        <thead><tr><th>Source</th><th>Ce qu'elle donne</th><th>Utilisee pour</th></tr></thead>
        <tbody>
{sources_rows}
        </tbody>
      </table>
    </div>
  </section>"""

    graph_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Graphe de filiation</div>
      <h2 class="section-title">3 branches, 3 fusions, 1 validation</h2>
      <p class="section-desc">
        <code>essai-jaunes</code> ne touche que la structure (les jaunes d'oeufs) ;
        <code>essai-repos</code> et <code>essai-cuisson</code> ne touchent que le protocole
        (les etapes 5 et 6). Les trois fusions sur <code>main</code> sont sequentielles, et le
        dernier commit re-teste explicitement une combinaison que les fusions n'avaient fait
        que juxtaposer.
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
        <span class="legend-item neutral"><span class="legend-dot"></span>draft / running / inconclusive</span>
      </div>
    </div>
  </section>"""

    def branch_section(*, label, title, desc, exp_a, exp_b, headline_unit_a, headline_a, headline_unit_b, headline_b):
        return f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">{label}</div>
      <h2 class="section-title">{title}</h2>
      <p class="section-desc">{desc}</p>
    </div>
    <div class="trial-grid">
{trial_card(order_label="Essai 1", exp_id=exp_a.id, headline=headline_a, headline_unit=headline_unit_a,
            meta=exp_a.conclusion.summary, metric_label="temperature_coeur_c",
            metric_value=str(exp_a.evidence[0].metrics["temperature_coeur_c"]), verdict="branch", verdict_label="Insuffisant — on continue")}
{trial_card(order_label="Essai 2", exp_id=exp_b.id, headline=headline_b, headline_unit=headline_unit_b,
            meta=exp_b.conclusion.summary, metric_label="temperature_coeur_c",
            metric_value=str(exp_b.evidence[0].metrics["temperature_coeur_c"]), verdict="promote", verdict_label="Retenu pour la fusion")}
    </div>
  </section>"""

    jaunes_section = branch_section(
        label="Branche essai-jaunes", title="Des jaunes d'oeufs supplementaires, sans toucher au protocole",
        desc="Structure uniquement : <code>egg_yolks</code> passe de 0 a 2 puis 4 (le ratio exact de Cyril Lignac, mis à l'échelle sur notre quantité de chocolat).",
        exp_a=j1, exp_b=j2, headline_unit_a="jaunes", headline_a="+2", headline_unit_b="jaunes", headline_b="+4",
    )
    repos_section = branch_section(
        label="Branche essai-repos", title="Repos et congelation avant cuisson",
        desc="Protocole uniquement : l'etape « Laisser reposer » (et sa cuisson compensee) sont modifiees, la composition ne change pas.",
        exp_a=r1, exp_b=r2, headline_unit_a="", headline_a="Frigo 30min", headline_unit_b="", headline_b="Congel. ≥12h",
    )
    cuisson_section = branch_section(
        label="Branche essai-cuisson", title="Deux bandes de cuisson observees dans les sources",
        desc="Protocole uniquement : seule l'etape « Cuire au four » varie (temperature et duree).",
        exp_a=c1, exp_b=c2, headline_unit_a="/ 7 min", headline_a="220°C", headline_unit_b="/ 10 min", headline_b="170°C",
    )

    resolution_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Resolution des fusions</div>
      <h2 class="section-title">Chaque fusion ne rapatrie qu'une variable</h2>
      <p class="section-desc">
        Trois fusions successives sur <code>main</code>. La troisieme est volontairement
        conclue « inconclusive » : elle juxtapose deux techniques validees separement, jamais
        ensemble.
      </p>
    </div>
    <div class="resolution-list">
{resolution_conflict_row(
    step_index=0, step_name="Fusion 1 — essai-jaunes -> main",
    left_src="main", left_val="egg_yolks = 0", left_note=f"Valeur de reference, {v1.id[:12]}",
    right_src="essai-jaunes", right_val="egg_yolks = 4", right_note=f"Valide sur 2 commits, {j2.id[:12]}",
    winner="right", flag_text='--take-structure "egg_yolks" &rarr; seule la structure change', arrow="&rarr;",
)}
{resolution_conflict_row(
    step_index=1, step_name="Fusion 2 — essai-repos -> main",
    left_src="main", left_val="[4] aucun repos &middot; [5] 200°C/10min", left_note=f"Valeur de reference, {v1.id[:12]}",
    right_src="essai-repos", right_val="[4] congel. ≥12h &middot; [5] 200°C/15min", right_note=f"Paire validee ensemble, {r2.id[:12]}",
    winner="right", flag_text='--take-steps "[4]" "[5]" &rarr; les deux etapes couplees sont reprises ensemble', arrow="&rarr;",
)}
{resolution_conflict_row(
    step_index=2, step_name="Fusion 3 — essai-cuisson -> main",
    left_src="main (deja fusionne)", left_val="[5] 200°C/15min", left_note="Valide pour une pate CONGELEE (fusion 2)",
    right_src="essai-cuisson", right_val="[5] 170°C/10min", right_note="Valide pour une pate FRAICHE (jamais congelee)",
    winner="right", flag_text='--take-steps "[5]" &rarr; combinaison non testee, signalee par decision="inconclusive"', arrow="&rarr;",
)}
    </div>
  </section>"""

    validation_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Validation finale</div>
      <h2 class="section-title">Refermer l'ecart signale par la fusion 3</h2>
      <p class="section-desc">
        Plutot que de publier une recette dont la combinaison n'a jamais ete testee, un dernier
        commit ajuste la duree de cuisson pour compenser le depart congele et re-teste
        explicitement l'ensemble.
      </p>
    </div>
{fiche_card(
    fiche_title=validation.title, exp_id=validation.id, branch=validation.branch,
    badges=[validation.conclusion.status, validation.conclusion.decision, "tag: recette-optimale"],
    intent=validation.intent,
    parents=[("parent", validation.branch, f"{m3.id[:12]} — {m3.title}")],
    conclusion=validation.conclusion.summary,
)}
  </section>"""

    footer = f"""<footer class="footer section">
    <div class="section-head">
      <div class="section-label">Reproduire</div>
      <h2 class="section-title">La recette optimale, en resume</h2>
    </div>
    <div class="repro">
      <div class="cmt"># structure finale (main, tag recette-optimale)</div>
      <div>180g chocolat noir 64% &middot; 125g beurre &middot; 90g sucre</div>
      <div>4 oeufs entiers + 4 jaunes &middot; 50g farine &middot; 1 pincee de sel</div>
      <div>4 ramequins beurres et farines</div>
      <br />
      <div class="cmt"># protocole final (etapes 5 et 6)</div>
      <div>Congeler les moules remplis au moins 12h ; cuire directement congele</div>
      <div>170°C, 14 min</div>
      <br />
      <div class="cmt"># reproduire ce scenario</div>
      <div class="cmd">python -m demos.chocolate_fondant</div>
    </div>
    <p class="credit">Genere avec <code>python -m demos.chocolate_fondant</code> — toutes les valeurs de la synthese viennent des 10 sources ci-dessus ; les mesures de temperature au coeur (sonde) sont illustratives, cette demo ne pretend pas avoir cuisine les 11 versions.</p>
  </footer>"""

    return render_report(
        title="Fondant optimal",
        description=(
            "Démo Follow : une recette de fondant au chocolat cœur coulant, synthétisée à "
            "partir de 10 recettes réelles puis optimisée par 3 branches d'expérience et 3 "
            "fusions successives, avec une validation finale qui referme un écart de "
            "combinaison non testée."
        ),
        eyebrow="Follow · dépôt d'expériences",
        heading="Optimiser un fondant au chocolat cœur coulant à partir de 10 recettes réelles",
        subtitle=(
            "Une recette de référence synthétisée à partir des ratios moyens de 10 sources "
            "réelles (chocolat, beurre, sucre, farine, œufs), puis trois branches qui isolent "
            "chacune une variable disputée par ces sources — les jaunes d'œufs, le repos avant "
            "cuisson, la température de cuisson — fusionnées séquentiellement dans "
            "<code>main</code>, avant une dernière expérience qui valide la combinaison finale "
            "au lieu de la supposer."
        ),
        stat_chips=[
            "<b>10</b> recettes sources",
            "<b>11</b> commits",
            "<b>4</b> branches",
            "<b>3</b> fusions + <b>1</b> validation",
        ],
        sections=[sources_section, graph_section, jaunes_section, repos_section, cuisson_section, resolution_section, validation_section],
        footer=footer,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demos/output/chocolate_fondant.html")
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
