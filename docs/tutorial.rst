Guide complet : optimiser une recette pas à pas
===================================================

Ce guide construit, étape par étape, un seul dépôt qui utilise **toutes** les fonctionnalités de
Follow : déclarer une expérience (intention, structure, référence, objectifs), démarrer un split
manuel puis plusieurs types de DOE (plan d'expériences), détecter un plan mal construit avant de
lui faire confiance, fusionner deux améliorations validées séparément, exiger un formulaire de
commit, et valider avant de conclure.

Le fil rouge est une recette de gâteau au chocolat qu'on optimise sur trois objectifs (hauteur,
densité, intensité chocolat). Chaque bloc de code ci-dessous est repris tel quel de
``demos/chocolate_cake_optimization.py`` — exécutez ``python -m demos.chocolate_cake_optimization``
pour obtenir le dépôt complet et sa page HTML (``demos/output/chocolate_cake_optimization.html``).

.. contents::
   :local:
   :depth: 1

Modéliser le domaine
------------------------

Une seule ``Structure``, avec tous les facteurs en champs **plats** (pas dans un ``dict``
imbriqué comme ``examples/recipe.py``) : c'est ce qui permet aux générateurs de
:mod:`follow.doe.design` de cibler chaque facteur directement via ``model_copy(update={...})``.

.. code-block:: python

   from follow import Quantity, Structure

   class ChocolateCake(Structure):
       name: str
       trial_id: int = 0   # identité au sein d'un lot - pas un facteur
       dark_chocolate: Quantity
       cocoa_percent: Quantity
       butter: Quantity
       sugar: Quantity
       eggs: int
       flour: Quantity
       baking_powder: Quantity
       bake_temperature: Quantity
       bake_duration: Quantity

   class CakeTrialBatch(Structure):
       """Un lot DOE : plusieurs essais de ChocolateCake, suivis comme une seule expérience."""
       batch_id: str
       trials: list[ChocolateCake]

La même classe ``ChocolateCake`` sert de recette unique (la référence, ou une recette finale
validée) **et** d'entité de lot (``CakeTrialBatch.trials``) — la structure ne change pas entre
« une expérience » et « une expérience à N variantes », voir :doc:`batch`.

Étape 0 — Déclarer l'expérience
------------------------------------

Une expérience se déclare avec :meth:`Repository.new() <follow.storage.repository.Repository.new>` :
intention, structure, éventuellement une hypothèse, puis on enrichit le brouillon
(:class:`~follow.storage.repository.ExperimentBuilder`) avant de committer.

.. code-block:: python

   from follow import Repository

   repo = Repository()

   b0 = repo.new(
       branch="main",
       structure=baseline_recipe,   # une ChocolateCake déjà valide
       title="Recette de reference",
       intent="Etablir une recette de base a optimiser (hauteur, densite, intensite chocolat).",
       hypothesis="Des ratios classiques donnent un point de depart correct mais perfectible.",
   )

**Une référence** — un point de comparaison qui n'est pas forcément un ancêtre
(:class:`~follow.core.models.ReferenceLink`, ``role`` parmi ``baseline``/``control``/``prior_art``/
``benchmark``/``target_spec``) :

.. code-block:: python

   b0.add_reference(
       role="prior_art", label="Ratios de depart (moyenne de recettes classiques)",
       external_source="https://example.com/recette-gateau-chocolat-classique",
   )

**Des objectifs** — un par direction possible, pour montrer l'éventail :

.. code-block:: python

   b0.add_objective(name="Hauteur", metric="height_cm", direction="maximize", target=5.5, tolerance=0.3,
                     rationale="Un gateau bas manque de moelleux au centre.")
   b0.add_objective(name="Densite", metric="density_g_cm3", direction="range", range=(0.55, 0.75),
                     rationale="Trop dense = pate lourde ; trop leger = sec.")
   b0.add_objective(name="Intensite chocolat", metric="score_gout", direction="maximize", target=8.0,
                     rationale="Note de degustation /10 sur l'intensite chocolat percue.")

**Un protocole** (:meth:`~follow.storage.repository.ExperimentBuilder.add_step`, ordonné, avec
dépendances), **une preuve** (:meth:`~follow.storage.repository.ExperimentBuilder.add_evidence` — un
pointeur vers des données externes, jamais les données elles-mêmes), puis **une conclusion** qui
se termine sur une prochaine étape plutôt qu'un verdict final :

.. code-block:: python

   b0.add_step(order=1, name="Faire fondre chocolat et beurre")
   # ... (voir le script pour les 4 etapes completes)

   b0.add_evidence(
       id="ev-baseline", description="Mesures + degustation, 1 gateau",
       source="file:///lab/baseline/mesures.csv",
       metrics={"height_cm": Quantity(value=4.6, unit="cm")},
   )

   b0.conclude(
       status="concluded", decision="branch",
       summary="Point de depart correct mais perfectible.",
       next_steps="Explorer plusieurs strategies de split pour ameliorer chaque axe.",
       objective_results=[dict(
           objective="Hauteur", status="not_met", observed=Quantity(value=4.6, unit="cm"),
           reasoning="Sous la cible de 5.5 cm.", evidence_ids=["ev-baseline"],
       )],
   )
   baseline = b0.commit()

``evidence_ids`` sur un :class:`~follow.core.models.ObjectiveResult` relie le verdict à **la preuve
exacte** qui le justifie — Follow n'analyse jamais rien lui-même, voir :doc:`report`.

Équivalent CLI :

.. code-block:: bash

   follow new --repo mon_labo --branch main --title "Recette de reference" \
     --intent "Etablir une recette de base a optimiser" \
     --structure-type examples.chocolate_cake.ChocolateCake --structure-file baseline.json \
     --out draft.json
   # editer draft.json a la main : references, objectives, steps, evidence, conclusion
   follow commit draft.json --repo mon_labo

Étape 1 — Un split manuel (``sweep``)
-------------------------------------------

Le cas le plus simple : **un seul facteur qui varie**, tout le reste identique. Toujours
identifiable statistiquement — rien avec quoi le confondre.

.. code-block:: python

   from follow.doe.design import lin, sweep

   t1 = repo.derive(
       baseline.id, new_branch="essai-temperature", title="Split manuel : temperature de cuisson",
       intent="Quelle temperature de cuisson maximise la hauteur sans assecher la mie ?",
   )
   t1.structure = CakeTrialBatch(
       batch_id="TEMP-1",
       trials=sweep(baseline_recipe, "bake_temperature", lin(165, 195, 5, unit="C"), id_field="trial_id"),
   )
   # ... evidence + conclusion, comme a l'etape 0
   t1.commit()

``lin(165, 195, 5, unit="C")`` (``numpy.linspace``) donne 5 valeurs de 165 à 195°C ;
``id_field="trial_id"`` numérote automatiquement les 5 essais générés. Voir :doc:`design` pour
``log`` (espacement logarithmique) et ``arange``.

Étape 2a — Le split qu'il ne faut pas faire
---------------------------------------------

L'erreur classique faite à la main : deux facteurs montés **ensemble** au lieu d'être croisés —
impossible ensuite de dire lequel explique un effet observé.
:func:`~follow.doe.design.check_identifiability` le détecte *avant* toute interprétation :

.. code-block:: python

   from follow.doe.design import check_identifiability

   naive_trials = [
       baseline_recipe.model_copy(update={
           "trial_id": i + 1,
           "sugar": Quantity(value=s, unit="g"),
           "butter": Quantity(value=b, unit="g"),
       })
       for i, (s, b) in enumerate(zip([140, 160, 180, 200, 220], [110, 125, 140, 155, 170]))
   ]
   check_identifiability(naive_trials, ["sugar", "butter"])
   # [("sugar", "butter", 0.9999...)]  <- confondus

Plutôt que de jeter le plan raté, **on le committe quand même** — abandonné, avec la raison
écrite dans la conclusion, pour que l'historique garde trace du raisonnement :

.. code-block:: python

   n1 = repo.derive(
       baseline.id, new_branch="essai-sucre-beurre-naif", title="Split naif : sucre et beurre montes ensemble",
       intent="Le sucre et le beurre, augmentes ensemble, ameliorent-ils densite et gout ?",
   )
   n1.structure = CakeTrialBatch(batch_id="SB-NAIF", trials=naive_trials)
   n1.conclude(
       status="abandoned", decision="abandon",
       summary="check_identifiability signale sucre et beurre correles a 1.000 : design rejete avant meme d'interpreter les resultats.",
       next_steps="Refaire le split en croisant sucre et beurre independamment.",
   )
   n1.commit()

Un plan raté est une donnée scientifique comme une autre : le documenter (au lieu de le
supprimer silencieusement) évite qu'on le retente sans savoir pourquoi il a été abandonné.

Étape 2b — Le corriger : plan factoriel complet
----------------------------------------------------

:func:`~follow.doe.design.full_factorial` croise **toutes** les combinaisons de **tous** les
facteurs — toujours identifiable, par construction :

.. code-block:: python

   from follow.doe.design import full_factorial

   sb_trials = full_factorial(
       baseline_recipe, id_field="trial_id",
       sugar=lin(140, 220, 4, unit="g"),
       butter=lin(110, 170, 4, unit="g"),
   )
   check_identifiability(sb_trials, ["sugar", "butter"])  # []

   f1 = repo.derive(baseline.id, new_branch="essai-sucre-beurre", title="Plan factoriel complet : sucre x beurre", intent="...")
   f1.structure = CakeTrialBatch(batch_id="SB-1", trials=sb_trials)
   # ... 16 essais (4 x 4), evidence (mesures + notebook d'analyse), conclusion decision="promote"
   f1.commit()

Étape 3 — Réduire le nombre d'essais : plan fractionnaire
----------------------------------------------------------------

16 essais pour 2 facteurs, c'est peu ; pour 4 facteurs un factoriel complet en demanderait 16
aussi (2^4) — un **plan fractionnaire** réduit ce nombre en dérivant un facteur comme le produit
d'autres, au prix d'un aliasing que :func:`~follow.doe.design.fractional_factorial` calcule
explicitement plutôt que de le laisser à découvrir après coup :

.. code-block:: python

   from follow.doe.design import fractional_factorial

   frac = fractional_factorial(
       baseline_recipe,
       factors={
           "cocoa_percent": (58, 70, "%"),
           "sugar": (150, 210, "g"),
           "butter": (120, 160, "g"),
           "bake_duration": (30, 40, "min"),
       },
       generators={"bake_duration": ["cocoa_percent", "sugar", "butter"]},  # D = ABC
       id_field="trial_id",
   )
   frac.resolution        # 4 : les effets principaux ne sont confondus qu'avec des interactions a 3 facteurs
   frac.aliases["cocoa_percent"]   # ['sugar:butter:bake_duration']
   len(frac.variants)     # 8 (2^(4-1)) au lieu de 16

   d1 = repo.derive(baseline.id, new_branch="essai-fractionnaire", title=f"Plan fractionnaire 2^(4-1) resolution {frac.resolution}", intent="...")
   d1.structure = CakeTrialBatch(batch_id="FRAC-1", trials=frac.variants)
   d1.add_evidence(
       id="ev-frac-analysis",
       description=f"Notebook d'analyse (resolution {frac.resolution} ; cacao aliase avec {frac.aliases['cocoa_percent'][0]})",
       source="notebook:///analysis/fractional_factorial.ipynb",
   )
   # ... conclusion decision="inconclusive" (screening, ne remplace pas le plan complet deja valide)
   d1.commit()

Résolution III signifierait qu'un effet principal est confondu avec une interaction à 2
facteurs (risqué) ; résolution IV (ici) ne confond les effets principaux qu'avec des
interactions à 3+ facteurs — généralement négligeables, donc le plan reste interprétable.

Étape 4 — Explorer largement : screening Latin Hypercube
------------------------------------------------------------

Pour vérifier qu'aucune zone inattendue ne bat les optima déjà trouvés, sans présupposer quels
facteurs comptent : :func:`~follow.doe.design.latin_hypercube` répartit ``n`` essais aléatoirement
mais stratifiés sur autant de facteurs qu'on veut.

.. code-block:: python

   from follow.doe.design import latin_hypercube

   lhs_trials = latin_hypercube(
       baseline_recipe, 15, seed=42, id_field="trial_id",
       cocoa_percent=(58, 75, "%"), sugar=(140, 220, "g"), butter=(110, 170, "g"),
       bake_temperature=(165, 195, "C"), bake_duration=(28, 40, "min"),
   )
   l1 = repo.derive(baseline.id, new_branch="essai-screening-lhs", title="Screening Latin Hypercube (5 facteurs, 15 essais)", intent="...")
   l1.structure = CakeTrialBatch(batch_id="LHS-1", trials=lhs_trials)
   # ... conclusion decision="inconclusive" (confirme les optima trouves ailleurs, n'en trouve pas de meilleur)
   l1.commit()

``seed=42`` rend le tirage reproductible — deux appels avec la même graine donnent le même plan.

Étape 5 — Fusionner deux améliorations validées séparément
------------------------------------------------------------------

Chaque split a validé **un** paramètre à la fois (la température, puis le couple sucre/beurre).
Pour les combiner sans repartir de zéro : deux branches candidates, une fusion explicite,
exactement la sémantique d'un ``git merge`` avec résolution manuelle chemin par chemin
(voir :doc:`merging`).

.. code-block:: python

   temp_winner = repo.derive(baseline.id, title="Retenir la temperature optimale (190C)", intent="...")
   temp_winner.structure.bake_temperature = Quantity(value=190, unit="C")
   temp_winner.conclude(decision="promote", summary="190C retenu sur main.")
   temp_winner.commit()   # continue "main" (pas de new_branch)

   sb_winner = repo.derive(baseline.id, new_branch="candidat-sucre-beurre", title="Retenir sucre/beurre optimaux", intent="...")
   sb_winner.structure.sugar = Quantity(value=180, unit="g")
   sb_winner.structure.butter = Quantity(value=140, unit="g")
   sb_winner.conclude(decision="promote", summary="Sucre=180g / beurre=140g retenus.")
   sb_candidate = sb_winner.commit()

   m1 = repo.merge(
       "main", sb_candidate.id, title="Fusion : temperature + sucre/beurre optimaux",
       intent="Combiner la temperature et le couple sucre/beurre, valides independamment.",
       take_structure=["sugar", "butter"],
   )
   m1.conclude(decision="promote", summary="Les trois parametres optimaux coexistent dans une seule recette.")
   merged = m1.commit()

``take_structure=["sugar", "butter"]`` prend ces deux champs depuis ``sb_candidate`` ; tout le
reste (dont ``bake_temperature``) garde la valeur de ``main`` — le résultat porte les deux
identifiants comme parents, comme un vrai commit de fusion.

Étape 6 — Rendre un formulaire de commit obligatoire
----------------------------------------------------------

À partir d'un certain point de l'étude, on veut tracer systématiquement qui a lancé le run et
quel type de plan a été utilisé — sans en faire un champ de la ``Structure``. Un
:class:`~follow.storage.commit_form.CommitForm` (voir :doc:`commit_form`) rend cela **obligatoire** :

.. code-block:: python

   from follow.storage.commit_form import CommitForm

   commit_form = CommitForm.model_validate({
       "title": "Formulaire de commit - Labo patisserie",
       "fields": [
           {"name": "operateur", "label": "Operateur", "type": "string", "required": True},
           {"name": "type_plan", "label": "Type de plan", "type": "choice", "required": True,
            "choices": ["sweep", "full_factorial", "fractional_factorial", "latin_hypercube", "confirmation"]},
           {"name": "facteurs_croises_verifies", "label": "Facteurs croises verifies ?", "type": "boolean", "required": True},
       ],
   })
   repo.commit_form = commit_form   # un attribut simple - a fixer des qu'un formulaire doit devenir obligatoire

À partir de là, tout commit sans ``form_answers`` valides est refusé
(:class:`~follow.storage.commit_form.FormValidationError`, qui liste tous les problèmes d'un coup).

Étape 7 — Valider avant de conclure
-----------------------------------------

Un dernier lot, **homogène** (les 4 gâteaux à la combinaison retenue), confirme la
reproductibilité avant de figer la recette :

.. code-block:: python

   v1 = repo.derive(merged.id, title="Validation finale : lot de confirmation homogene", intent="...")
   winning_recipe = repo.load_structure(merged)
   v1.structure = CakeTrialBatch(
       batch_id="VALID-1",
       trials=[winning_recipe.model_copy(update={"trial_id": i + 1}) for i in range(4)],
   )
   v1.answer_form(operateur="Alice", type_plan="confirmation", facteurs_croises_verifies=True)
   # ... evidence + conclusion decision="promote", next_steps="Publier la recette finale."
   final = v1.commit()
   repo.tag("recette-optimale", final.id)

.. code-block:: pycon

   >>> from follow import analyze_batch
   >>> variation = analyze_batch(repo.load_structure(final).trials, ignore=["trial_id"])
   >>> variation.is_uniform
   True

``is_uniform`` confirme qu'il n'y a plus rien à explorer — l'autre moitié de l'affichage
hybride décrit dans :doc:`batch`.

Étape 8 — Tout relire
--------------------------

Chaque expérience se lit avec :func:`~follow.presentation.report.experiment_fiche` (résumé → objectifs →
split le cas échéant → résultats & preuves → conclusion) :

.. code-block:: python

   from follow import experiment_fiche
   from follow.presentation.report import batch_table

   structure = repo.load_structure(final)
   variation = analyze_batch(structure.trials, ignore=["trial_id"])
   split = batch_table(variation, entity_labels=[f"#{t.trial_id}" for t in structure.trials], standalone=False)
   html = experiment_fiche(final, split=split)

Ou tout le dépôt d'un coup, sans rien écrire à la main (voir :doc:`report`) :

.. code-block:: python

   from follow import render_study_html

   open("etude.html", "w").write(render_study_html(repo, title="Optimisation gateau au chocolat"))

Équivalent en CLI, de bout en bout
----------------------------------------

.. code-block:: bash

   follow init mon_labo

   follow new --repo mon_labo --branch main --title "Recette de reference" \
     --intent "Etablir une recette de base" \
     --structure-type examples.chocolate_cake.ChocolateCake --structure-file baseline.json \
     --out draft.json
   follow commit draft.json --repo mon_labo
   # -> exp_xxxxxxxx (main)

   follow derive exp_xxxxxxxx --repo mon_labo --new-branch essai-temperature \
     --title "Split manuel : temperature" --intent "..." --out temp.json
   # editer temp.json : structure = CakeTrialBatch genere via follow.doe.design.sweep en Python,
   # puis coller le JSON resultant (model_dump) dans le champ "structure" du brouillon
   follow commit temp.json --repo mon_labo

   follow diff main essai-temperature --repo mon_labo         # ce qui varie dans la structure
   follow explode essai-temperature trials --ignore trial_id --repo mon_labo   # exploser le lot

   follow merge main candidat-sucre-beurre --repo mon_labo \
     --title "Fusion : temperature + sucre/beurre optimaux" --intent "..." \
     --take-structure "sugar" --take-structure "butter" --out merge.json
   follow commit merge.json --repo mon_labo

   follow tag recette-optimale --at exp_yyyyyyyy --repo mon_labo
   follow report --repo mon_labo --out etude.html
   follow graph --repo mon_labo --out graph.html --open

``follow new``/``derive``/``merge`` n'ont pas de générateur de DOE intégré : la structure d'un
lot (``CakeTrialBatch`` avec ses ``trials`` déjà générés par ``follow.doe.design`` en Python) se
prépare comme n'importe quel ``--structure-file``, puisque le format JSON est le même que
``ChocolateCake.model_dump(mode="json")``.

``follow menu`` (nécessite ``pip install "follow[menu]"``) offre la même chose sans mémoriser ni
les sous-commandes ni leurs options : naviguer, démarrer une expérience, la conclure, fusionner,
générer un rapport — via des invites interactives qui appellent exactement la même API.

Pour aller plus loin
-------------------------

- :doc:`concepts` — le modèle de données complet (``Experiment``, ``Structure``, branches/tags).
- :doc:`merging` — la sémantique de fusion en détail.
- :doc:`batch` et :doc:`design` — l'affichage hybride et les générateurs de plan.
- :doc:`commit_form` — le formulaire de commit obligatoire.
- :doc:`report` — la fiche ergonomique et le compte rendu automatique.
- ``demos/chocolate_cake_optimization.py`` — le script complet dont ce guide est extrait, et
  ``demos/output/chocolate_cake_optimization.html`` — son rendu.
