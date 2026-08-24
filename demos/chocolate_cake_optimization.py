"""The complete guide, as a runnable script: how to declare an experiment (intent, structure,
references, objectives), start a DOE or a manual split, catch a flawed split before trusting it,
read a fractional factorial's alias structure, merge validated findings back together, require a
commit form, and render the result - all in one continuous optimization of a chocolate cake
recipe. See docs/tutorial.rst for the same story narrated step by step; this script is what that
guide's code actually runs.

Repository shape (10 commits across 7 branches):

  main:                        baseline -> +temperature(190C) -> +sugar/butter(merge) -> validation (tag: recette-optimale)
  essai-temperature:           manual split (sweep), 1 factor, 5 trials
  essai-sucre-beurre-naif:     the mistake - two factors varied together, abandoned
  essai-sucre-beurre:          the fix - full factorial, 2 factors, 16 trials
  essai-fractionnaire:         fractional factorial, 4 factors in 8 runs (resolution IV)
  essai-screening-lhs:         Latin Hypercube screening, 5 factors, 15 runs
  candidat-sucre-beurre:       single-recipe candidate merged into main

Run: python -m demos.chocolate_cake_optimization [--out demos/output/chocolate_cake_optimization.html] [--embed]
"""

from __future__ import annotations


from demos._main import run_demo
from demos._report import batch_table, experiment_fiche, render_report
from examples.chocolate_cake import CakeTrialBatch, ChocolateCake
from follow import Quantity, Repository, analyze_batch
from follow.report import graph_section
from follow.commit_form import CommitForm
from follow.design import check_identifiability, fractional_factorial, full_factorial, latin_hypercube, lin, sweep

COMMIT_FORM = CommitForm.model_validate(
    {
        "title": "Formulaire de commit - Labo pâtisserie",
        "fields": [
            {"name": "operateur", "label": "Opérateur", "type": "string", "required": True},
            {
                "name": "type_plan", "label": "Type de plan", "type": "choice", "required": True,
                "choices": ["sweep", "full_factorial", "fractional_factorial", "latin_hypercube", "confirmation"],
            },
            {"name": "facteurs_croises_verifies", "label": "Facteurs croisés vérifiés (non confondus) ?", "type": "boolean", "required": True},
        ],
    }
)


def _baseline_recipe() -> ChocolateCake:
    return ChocolateCake(
        name="Gâteau au chocolat - référence",
        dark_chocolate=Quantity(value=200, unit="g"),
        cocoa_percent=Quantity(value=64, unit="%"),
        butter=Quantity(value=150, unit="g"),
        sugar=Quantity(value=180, unit="g"),
        eggs=4,
        flour=Quantity(value=120, unit="g"),
        baking_powder=Quantity(value=5, unit="g"),
        bake_temperature=Quantity(value=180, unit="C"),
        bake_duration=Quantity(value=35, unit="min"),
    )


def _baseline_steps() -> list[dict]:
    return [
        dict(order=1, name="Faire fondre chocolat et beurre", description="Bain-marie ou micro-ondes par tranches de 30s"),
        dict(order=2, name="Fouetter oeufs et sucre", description="Jusqu'au ruban"),
        dict(order=3, name="Assembler la pate", description="Incorporer le chocolat fondu, puis farine + levure tamisees", depends_on=[1, 2]),
        dict(order=4, name="Cuire au four", description="Four a chaleur statique, prechauffe", depends_on=[3]),
    ]


def build_repository() -> Repository:
    repo = Repository()

    # -- Stage 0: declare the experiment - intent, structure, hypothesis, an external reference,
    # multiple objectives (one per direction: maximize/range/maximize), steps, evidence, and a
    # conclusion that ends in next_steps instead of a final verdict. -----------------------------
    b0 = repo.new(
        branch="main",
        structure=_baseline_recipe(),
        title="Recette de reference",
        intent="Etablir une recette de base a optimiser (hauteur, densite, intensite chocolat).",
        hypothesis="Des ratios classiques (beurre ~0.75x chocolat, sucre ~0.9x chocolat) donnent un point de depart correct mais perfectible sur les trois objectifs.",
    )
    b0.add_reference(role="prior_art", label="Ratios de depart (moyenne de recettes classiques)", external_source="https://example.com/recette-gateau-chocolat-classique")
    b0.add_objective(name="Hauteur", metric="height_cm", direction="maximize", target=5.5, tolerance=0.3, rationale="Un gateau bas manque de moelleux au centre.")
    b0.add_objective(name="Densite", metric="density_g_cm3", direction="range", range=(0.55, 0.75), rationale="Trop dense = pate lourde ; trop leger = sec.")
    b0.add_objective(name="Intensite chocolat", metric="score_gout", direction="maximize", target=8.0, rationale="Note de degustation /10 sur l'intensite chocolat percue.")
    for s in _baseline_steps():
        b0.add_step(**s)
    b0.add_evidence(
        id="ev-baseline", description="Mesures + degustation, 1 gateau", source="file:///lab/baseline/mesures.csv",
        metrics={"height_cm": Quantity(value=4.6, unit="cm"), "density_g_cm3": Quantity(value=0.81, unit="g/cm3"), "score_gout": Quantity(value=6.5, unit="/10")},
    )
    b0.conclude(
        status="concluded", decision="branch",
        summary="Point de depart correct mais perfectible : gateau un peu bas, dense, et pas assez intense en chocolat.",
        next_steps="Explorer plusieurs strategies de split (manuel, factoriel, fractionnaire, screening) pour ameliorer chaque axe.",
        objective_results=[
            dict(objective="Hauteur", status="not_met", observed=Quantity(value=4.6, unit="cm"), reasoning="Sous la cible de 5.5 cm.", evidence_ids=["ev-baseline"]),
            dict(objective="Densite", status="not_met", observed=Quantity(value=0.81, unit="g/cm3"), reasoning="Au-dessus de la plage cible 0.55-0.75.", evidence_ids=["ev-baseline"]),
            dict(objective="Intensite chocolat", status="not_met", observed=Quantity(value=6.5, unit="/10"), reasoning="Sous la cible de 8/10.", evidence_ids=["ev-baseline"]),
        ],
    )
    baseline = b0.commit()

    # -- Stage 1: a manual split - one factor, sweep() - always identifiable, nothing to confound
    # the one thing that varies with. --------------------------------------------------------------
    t1 = repo.derive(
        baseline.id, new_branch="essai-temperature", title="Split manuel : temperature de cuisson",
        intent="Quelle temperature de cuisson maximise la hauteur sans assecher la mie ?",
    )
    t1.structure = CakeTrialBatch(
        batch_id="TEMP-1",
        trials=sweep(_baseline_recipe(), "bake_temperature", lin(165, 195, 5, unit="C"), id_field="trial_id"),
    )
    t1.steps[3] = t1.steps[3].model_copy(update={"description": "Temperature variable selon le split, duree fixe (35 min)"})
    t1.add_evidence(id="ev-temp-raw", description="Mesures brutes, 5 gateaux", source="file:///lab/temp-sweep/mesures.csv")
    t1.add_evidence(id="ev-temp-analysis", description="Notebook d'analyse (hauteur vs temperature)", source="notebook:///analysis/temp_sweep.ipynb")
    t1.conclude(
        status="concluded", decision="promote",
        summary="Hauteur maximale a 190C (5.4 cm) ; au-dela la mie s'asseche (note gout en baisse). 190C retenu.",
        next_steps="Figer 190C sur main, puis chercher a ameliorer densite et intensite via un autre split.",
        objective_results=[dict(objective="Hauteur", status="met", observed=Quantity(value=5.4, unit="cm"), reasoning="Essai a 190C, dans la plage cible.", evidence_ids=["ev-temp-raw", "ev-temp-analysis"])],
    )
    t1.commit()

    # -- Stage 2a: the mistake - two factors moved together instead of crossed. Caught by
    # check_identifiability BEFORE trusting any result, and the branch is committed anyway -
    # abandoned, not deleted, so the reasoning ("we tried this, here's why it's flawed") stays in
    # the repository's history rather than silently vanishing. --------------------------------------
    naive_trials = [
        _baseline_recipe().model_copy(update={"trial_id": i + 1, "sugar": Quantity(value=s, unit="g"), "butter": Quantity(value=b, unit="g")})
        for i, (s, b) in enumerate(zip([140, 160, 180, 200, 220], [110, 125, 140, 155, 170], strict=True))
    ]
    confounded = check_identifiability(naive_trials, ["sugar", "butter"])
    assert confounded and confounded[0][2] > 0.99, "the naive split is supposed to be a cautionary example of confounding"

    n1 = repo.derive(
        baseline.id, new_branch="essai-sucre-beurre-naif", title="Split naif : sucre et beurre montes ensemble",
        intent="Le sucre et le beurre, augmentes ensemble, ameliorent-ils densite et gout ?",
    )
    n1.structure = CakeTrialBatch(batch_id="SB-NAIF", trials=naive_trials)
    n1.steps[3] = n1.steps[3].model_copy(update={"description": "190C / 35 min, fixe (retenu a l'essai precedent)"})
    n1.conclude(
        status="abandoned", decision="abandon",
        summary=(
            f"check_identifiability signale sucre et beurre correles a {confounded[0][2]:.3f} sur ce plan : "
            "ils montent ensemble, impossible de separer statistiquement leurs effets sur la densite. "
            "Design rejete avant meme d'interpreter les resultats."
        ),
        next_steps="Refaire le split en croisant sucre et beurre independamment (plan factoriel complet).",
    )
    n1.commit()

    # -- Stage 2b: the fix - full_factorial(), always identifiable by construction. ------------------
    f1 = repo.derive(
        baseline.id, new_branch="essai-sucre-beurre", title="Plan factoriel complet : sucre x beurre",
        intent="Quelle combinaison sucre/beurre optimise densite et intensite, sans les confondre ?",
    )
    sb_trials = full_factorial(
        _baseline_recipe(), id_field="trial_id",
        sugar=lin(140, 220, 4, unit="g"),
        butter=lin(110, 170, 4, unit="g"),
    )
    assert check_identifiability(sb_trials, ["sugar", "butter"]) == []
    f1.structure = CakeTrialBatch(batch_id="SB-1", trials=sb_trials)
    f1.steps[3] = f1.steps[3].model_copy(update={"description": "190C / 35 min, fixe"})
    f1.add_evidence(id="ev-sb-raw", description="Mesures brutes, 16 gateaux", source="file:///lab/sucre-beurre/mesures.csv")
    f1.add_evidence(id="ev-sb-analysis", description="Notebook d'analyse (ANOVA densite/gout, sucre x beurre)", source="notebook:///analysis/sugar_butter_factorial.ipynb")
    f1.conclude(
        status="concluded", decision="promote",
        summary="Optimum a sucre=180g / beurre=140g : densite 0.68 g/cm3 (dans la plage cible), gout 8.2/10. Les deux facteurs sont significatifs et non confondus (ANOVA jointe).",
        next_steps="Retenir sucre=180g / beurre=140g comme candidat a fusionner avec la temperature validee.",
        objective_results=[
            dict(objective="Densite", status="met", observed=Quantity(value=0.68, unit="g/cm3"), reasoning="Dans la plage cible 0.55-0.75.", evidence_ids=["ev-sb-raw", "ev-sb-analysis"]),
            dict(objective="Intensite chocolat", status="met", observed=Quantity(value=8.2, unit="/10"), reasoning="Au-dessus de la cible de 8/10.", evidence_ids=["ev-sb-raw", "ev-sb-analysis"]),
        ],
    )
    f1.commit()

    # -- Stage 3: a fractional factorial - 4 factors in 8 runs instead of 16, with the resulting
    # alias structure computed and cited explicitly rather than discovered later. -------------------
    frac = fractional_factorial(
        _baseline_recipe(),
        factors={
            "cocoa_percent": (58, 70, "%"),
            "sugar": (150, 210, "g"),
            "butter": (120, 160, "g"),
            "bake_duration": (30, 40, "min"),
        },
        generators={"bake_duration": ["cocoa_percent", "sugar", "butter"]},  # D = ABC -> resolution IV
        id_field="trial_id",
    )
    assert frac.resolution == 4

    d1 = repo.derive(
        baseline.id, new_branch="essai-fractionnaire", title=f"Plan fractionnaire 2^(4-1) resolution {frac.resolution}",
        intent="Screener 4 facteurs (cacao, sucre, beurre, duree de cuisson) en 8 essais plutot que 16.",
    )
    d1.structure = CakeTrialBatch(batch_id="FRAC-1", trials=frac.variants)
    d1.steps[3] = d1.steps[3].model_copy(update={"description": "190C fixe, duree selon le plan"})
    d1.add_evidence(
        id="ev-frac-analysis",
        description=f"Notebook d'analyse (resolution {frac.resolution} ; cacao aliase avec {frac.aliases['cocoa_percent'][0]})",
        source="notebook:///analysis/fractional_factorial.ipynb",
    )
    d1.conclude(
        status="concluded", decision="inconclusive",
        summary=(
            f"Resolution {frac.resolution} : les effets principaux ne sont confondus qu'avec des interactions a 3 facteurs "
            "(negligees par hypothese), mais aucune combinaison ne depasse nettement l'optimum deja trouve par le plan complet sucre/beurre. "
            "Screening utile pour confirmer qu'aucun autre facteur ne domine, sans remettre en cause la strategie retenue."
        ),
        next_steps="Ne pas re-ouvrir cacao/duree pour cette iteration ; les garder aux valeurs de reference.",
    )
    d1.commit()

    # -- Stage 4: Latin Hypercube - broad screening over 5 factors before committing to a design. ---
    lhs_trials = latin_hypercube(
        _baseline_recipe(), 15, seed=42, id_field="trial_id",
        cocoa_percent=(58, 75, "%"), sugar=(140, 220, "g"), butter=(110, 170, "g"),
        bake_temperature=(165, 195, "C"), bake_duration=(28, 40, "min"),
    )
    l1 = repo.derive(
        baseline.id, new_branch="essai-screening-lhs", title="Screening Latin Hypercube (5 facteurs, 15 essais)",
        intent="Explorer largement 5 facteurs a la fois, pour verifier qu'aucune zone inattendue ne bat les optima trouves separement.",
    )
    l1.structure = CakeTrialBatch(batch_id="LHS-1", trials=lhs_trials)
    l1.steps[3] = l1.steps[3].model_copy(update={"description": "Temperature et duree variables selon le plan LHS"})
    l1.add_evidence(id="ev-lhs-analysis", description="Notebook d'analyse (regression sur l'echantillon LHS)", source="notebook:///analysis/lhs_screening.ipynb")
    l1.conclude(
        status="concluded", decision="inconclusive",
        summary="Aucune region du plan LHS ne surpasse la combinaison deja retenue (190C / sucre=180g / beurre=140g) - confirme, ne remplace pas.",
        next_steps="Passer a la fusion des ameliorations validees (temperature + sucre/beurre).",
    )
    l1.commit()

    # -- Stage 5: merge two validated, single-recipe branches back into main with take_structure -
    # exactly the git-merge semantics, applied to structured data instead of text. -------------------
    temp_winner = repo.derive(baseline.id, title="Retenir la temperature optimale (190C)", intent="Figer la temperature validee par essai-temperature avant de fusionner d'autres ameliorations.")
    temp_winner.structure.bake_temperature = Quantity(value=190, unit="C")
    temp_winner.conclude(status="concluded", decision="promote", summary="190C retenu sur main.", next_steps="Fusionner avec la combinaison sucre/beurre validee separement.")
    temp_winner.commit()  # advances "main"

    sb_winner = repo.derive(baseline.id, new_branch="candidat-sucre-beurre", title="Retenir sucre/beurre optimaux", intent="Figer sucre=180g / beurre=140g, valides par le plan factoriel complet.")
    sb_winner.structure.sugar = Quantity(value=180, unit="g")
    sb_winner.structure.butter = Quantity(value=140, unit="g")
    sb_winner.conclude(status="concluded", decision="promote", summary="Sucre=180g / beurre=140g retenus.")
    sb_candidate = sb_winner.commit()

    m1 = repo.merge(
        "main", sb_candidate.id, title="Fusion : temperature + sucre/beurre optimaux",
        intent="Combiner la temperature (190C) et le couple sucre/beurre (180g/140g), valides independamment.",
        take_structure=["sugar", "butter"],
    )
    m1.conclude(status="concluded", decision="promote", summary="Les trois parametres optimaux coexistent dans une seule recette.", next_steps="Valider la reproductibilite avant de publier la recette finale.")
    merged = m1.commit()

    # -- Stage 6 + 7: from here on, a commit form is required (repo.commit_form is just a plain
    # attribute - set it whenever a study decides metadata should stop being optional) - and a
    # final, uniform confirmation batch validates reproducibility before tagging. --------------------
    repo.commit_form = COMMIT_FORM

    v1 = repo.derive(merged.id, title="Validation finale : lot de confirmation homogene", intent="La recette finale (190C / sucre=180g / beurre=140g) est-elle reproductible sur plusieurs gateaux identiques ?")
    winning_recipe = repo.load_structure(merged)
    v1.structure = CakeTrialBatch(batch_id="VALID-1", trials=[winning_recipe.model_copy(update={"trial_id": i + 1}) for i in range(4)])
    v1.answer_form(operateur="Alice", type_plan="confirmation", facteurs_croises_verifies=True)
    v1.add_evidence(id="ev-valid-raw", description="Mesures brutes, 4 gateaux identiques", source="file:///lab/validation/mesures.csv")
    v1.add_evidence(id="ev-valid-analysis", description="Notebook d'analyse (ecart-type inter-gateaux)", source="notebook:///analysis/validation.ipynb")
    v1.conclude(
        status="concluded", decision="promote",
        summary="Reproductible : hauteur 5.3-5.5 cm, densite 0.66-0.70 g/cm3, gout 8.0-8.3/10 sur les 4 gateaux. Recette finale retenue.",
        next_steps="Publier la recette finale ; documenter les 3 splits qui ont mene a chaque parametre.",
        objective_results=[
            dict(objective="Hauteur", status="met", observed=Quantity(value=5.4, unit="cm"), evidence_ids=["ev-valid-raw", "ev-valid-analysis"]),
            dict(objective="Densite", status="met", observed=Quantity(value=0.68, unit="g/cm3"), evidence_ids=["ev-valid-raw", "ev-valid-analysis"]),
            dict(objective="Intensite chocolat", status="met", observed=Quantity(value=8.15, unit="/10"), evidence_ids=["ev-valid-raw", "ev-valid-analysis"]),
        ],
    )
    final = v1.commit()
    repo.tag("recette-optimale", final.id)

    return repo


def _batch_section(repo: Repository, exp, *, label: str, desc: str) -> str:
    """One fiche for a batch-typed experiment (CakeTrialBatch), with its split embedded via
    batch_table(..., standalone=False) - the same pattern demos/wafer_doe.py uses.
    """
    structure = repo.load_structure(exp)
    variation = analyze_batch(structure.trials, ignore=["trial_id"])
    split = batch_table(
        variation, entity_labels=[f"#{t.trial_id}" for t in structure.trials],
        title=f"Split ({len(structure.trials)} essais)", standalone=False,
    )
    return f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">{label}</div>
      <h2 class="section-title">{exp.title}</h2>
      <p class="section-desc">{desc}</p>
    </div>
{experiment_fiche(exp, split=split)}
  </section>"""


def render(repo: Repository, *, embed_plotly: bool) -> str:
    baseline = repo.log("essai-temperature")[-1]
    temp_batch = repo.get("essai-temperature")
    naive_batch = repo.get("essai-sucre-beurre-naif")
    sb_batch = repo.get("essai-sucre-beurre")
    frac_batch = repo.get("essai-fractionnaire")
    lhs_batch = repo.get("essai-screening-lhs")
    temp_winner = [e for e in repo if e.title == "Retenir la temperature optimale (190C)"][0]
    sb_candidate = repo.get("candidat-sucre-beurre")
    merged = [e for e in repo if e.title == "Fusion : temperature + sucre/beurre optimaux"][0]
    final = repo.get("recette-optimale")

    graph_section_html = graph_section(
        repo,
        heading="10 commits, 4 strategies de split, 1 fusion, 1 validation",
        description=(
            "Un seul dépôt : un split manuel (<code>essai-temperature</code>), un split raté puis corrigé (<code>essai-sucre-beurre-naif</code> → <code>essai-sucre-beurre</code>), un plan fractionnaire (<code>essai-fractionnaire</code>) et un screening LHS (<code>essai-screening-lhs</code>) — puis une fusion qui combine les deux améliorations validées, et une validation finale."
        ),
        embed_plotly=embed_plotly,
    )

    baseline_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Étape 0 — Déclarer l'expérience</div>
      <h2 class="section-title">{baseline.title}</h2>
      <p class="section-desc">
        Intention, structure de référence, une référence externe ("prior_art"), trois objectifs
        (un par direction : maximiser, viser une plage, maximiser), un protocole en étapes, une
        preuve, et une conclusion qui se termine par une prochaine étape plutôt qu'un verdict
        final.
      </p>
    </div>
{experiment_fiche(baseline)}
  </section>"""

    temp_section = _batch_section(
        repo, temp_batch, label="Étape 1 — Split manuel (sweep)",
        desc="Un seul facteur qui varie (température de cuisson), généré par follow.design.sweep - toujours identifiable, rien avec quoi le confondre.",
    )

    naive_section = _batch_section(
        repo, naive_batch, label="Étape 2a — Le split idiot (à ne pas faire)",
        desc="Sucre et beurre montés ensemble au lieu d'être croisés : follow.design.check_identifiability les signale corrélés à plus de 0.99 avant même d'interpréter un résultat. La branche est committée quand même, abandonnée avec la raison écrite noir sur blanc plutôt que supprimée.",
    )

    sb_section = _batch_section(
        repo, sb_batch, label="Étape 2b — La correction (plan factoriel complet)",
        desc="Les deux mêmes facteurs, cette fois croisés par follow.design.full_factorial : check_identifiability ne signale plus rien, chaque effet est estimable indépendamment.",
    )

    frac_section = _batch_section(
        repo, frac_batch, label="Étape 3 — Plan fractionnaire (2^(4-1))",
        desc="4 facteurs en 8 essais au lieu de 16 : follow.design.fractional_factorial calcule la structure d'aliasing (résolution IV — les effets principaux ne sont confondus qu'avec des interactions à 3 facteurs), citée explicitement dans la preuve plutôt que découverte après coup.",
    )

    lhs_section = _batch_section(
        repo, lhs_batch, label="Étape 4 — Screening (Latin Hypercube)",
        desc="15 essais répartis aléatoirement mais stratifiés sur 5 facteurs à la fois, via follow.design.latin_hypercube - pour vérifier qu'aucune zone inattendue ne bat les optima déjà trouvés séparément.",
    )

    merge_section = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Étape 5 — Fusionner (follow merge)</div>
      <h2 class="section-title">Combiner deux améliorations validées séparément</h2>
      <p class="section-desc">
        <code>{temp_winner.title}</code> continue <code>main</code> avec la température retenue ;
        <code>{sb_candidate.title}</code> fige sucre/beurre sur une branche à part. La fusion
        prend explicitement <code>sugar</code> et <code>butter</code> depuis la seconde branche,
        tout le reste (dont la température) reste celui de <code>main</code> — exactement la
        sémantique d'un <code>git merge</code> avec résolution manuelle, chemin par chemin.
      </p>
    </div>
{experiment_fiche(temp_winner)}
{experiment_fiche(sb_candidate, parents=[("baseline", sb_candidate.branch, "recette de référence")])}
{experiment_fiche(
    merged,
    parents=[("baseline", "main", f"{temp_winner.id[:12]} — {temp_winner.title}"),
             ("merge_source", sb_candidate.branch, f"{sb_candidate.id[:12]} — {sb_candidate.title}")],
    parents_label="Filiation (fusion)",
)}
  </section>"""

    validation_section = _batch_section(
        repo, final, label="Étape 6+7 — Formulaire de commit + validation finale",
        desc=(
            "À partir d'ici, repo.commit_form exige operateur/type de plan/facteurs croisés vérifiés "
            "avant tout commit (voir docs/tutorial.rst). Le lot de confirmation - 4 gâteaux identiques - "
            "ressort uniforme (is_uniform) : rien à explorer, juste à confirmer avant de taguer "
            "\"recette-optimale\"."
        ),
    )

    footer = """<footer class="footer section">
    <div class="section-head">
      <div class="section-label">Reproduire</div>
      <h2 class="section-title">La recette finale, en résumé</h2>
    </div>
    <div class="repro">
      <div class="cmt"># recette finale (main, tag recette-optimale)</div>
      <div>200g chocolat noir 64% &middot; 150g beurre &middot; 180g sucre</div>
      <div>4 oeufs &middot; 120g farine &middot; 5g levure</div>
      <div>190&deg;C, 35 min</div>
      <br />
      <div class="cmt"># chaque parametre vient d'un split different</div>
      <div>temperature: essai-temperature (sweep, 5 essais)</div>
      <div>sucre / beurre: essai-sucre-beurre (full_factorial, 16 essais)</div>
      <div>confirme par: essai-fractionnaire + essai-screening-lhs (aucun n'a fait mieux)</div>
      <br />
      <div class="cmt"># reproduire ce scenario</div>
      <div class="cmd">python -m demos.chocolate_cake_optimization</div>
    </div>
    <p class="credit">Généré avec <code>python -m demos.chocolate_cake_optimization</code> — voir <code>docs/tutorial.rst</code> pour le même scénario narré étape par étape.</p>
  </footer>"""

    return render_report(
        title="Optimisation d'un gâteau au chocolat",
        description=(
            "Démo Follow : le guide complet en un seul dépôt - déclarer une expérience, choisir "
            "une stratégie de split (manuel, factoriel, fractionnaire, screening), détecter un "
            "plan mal construit, fusionner des améliorations validées séparément, exiger un "
            "formulaire de commit, et valider avant de conclure."
        ),
        eyebrow="Follow · guide complet",
        heading="Optimiser un gâteau au chocolat avec chaque fonctionnalité de Follow",
        subtitle=(
            "Une recette de référence, quatre stratégies de split différentes (dont une "
            "délibérément ratée puis corrigée), une fusion qui combine deux améliorations "
            "validées séparément, un formulaire de commit obligatoire, et une validation finale "
            "— le même dépôt que docs/tutorial.rst construit pas à pas."
        ),
        stat_chips=[
            f"<b>{len(repo)}</b> commits",
            f"<b>{len(repo.branches)}</b> branches",
            "<b>4</b> stratégies de split",
            "<b>1</b> fusion",
        ],
        sections=[graph_section_html, baseline_section, temp_section, naive_section, sb_section, frac_section, lhs_section, merge_section, validation_section],
        footer=footer,
    )


def main() -> None:
    run_demo(
        doc=__doc__,
        default_out="demos/output/chocolate_cake_optimization.html",
        build_repository=build_repository,
        render=render,
    )


if __name__ == "__main__":
    main()
