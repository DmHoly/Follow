Générer un compte rendu d'étude
==================================

:func:`follow.presentation.report.render_study_html` transforme un dépôt (ou le lignage d'une branche) en
une page HTML autonome, lisible comme le compte rendu d'une étude complète — sans IA, sans
moteur de template externe. Tout vient des champs déjà présents dans les expériences ; le module
(:mod:`follow.presentation.report`) est de simples f-strings Python, sans nouvelle dépendance au-delà de
Plotly (déjà utilisé par :mod:`follow.presentation.graphing`).

.. code-block:: python

   from follow import render_study_html

   html = render_study_html(repo, title="Étude gâteau au yaourt")
   open("etude.html", "w").write(html)

   # limiter au lignage d'une branche/tag/expérience
   html = render_study_html(repo, ref="essai-cuisson")

En CLI :

.. code-block:: bash

   follow report --repo mon_labo --title "Étude gâteau au yaourt" --out etude.html
   follow report essai-cuisson --repo mon_labo --out etude-branche.html

Ce que contient la page
-------------------------

Un sommaire cliquable, le graphe de filiation, puis une fiche par expérience — chacune rendue
par :func:`~follow.presentation.report.experiment_fiche`, dans un seul ordre de lecture : **résumé**
(intention + hypothèse) → **objectifs de l'étude** → **résultats & preuves** (chaque verdict relié
à l'``Evidence`` exacte qui le justifie) → **conclusion** (décision, résumé, et la suite). Ce qui
a changé à chaque commit est **calculé**, pas recopié à la main :

- **un seul parent** → diff structure + protocole contre ce parent
  (:meth:`Repository.diff() <follow.storage.repository.Repository.diff>` /
  :meth:`Repository.diff_steps() <follow.storage.repository.Repository.diff_steps>`) ;
- **deux parents** (fusion) → chaque chemin qui diffère entre les deux parents est comparé à la
  valeur du commit de fusion pour dire explicitement de quel côté elle a été reprise, au niveau
  de chaque feuille — plus précis qu'une note écrite à la main.

Le texte issu du dépôt (titres, intentions, résumés...) est échappé avant insertion dans le HTML
(:func:`follow.presentation.report._esc`) : contrairement aux démos, où le texte est entièrement écrit par
l'auteur du script, ce renderer affiche des données saisies par n'importe qui.

Résultats reliés à leurs preuves
------------------------------------

Follow n'analyse jamais rien lui-même : l'analyse (statistique, notebook, graphique) est
déléguée à autre chose. Ce que :func:`~follow.presentation.report.results_table` fait, c'est rendre explicite
**quelle preuve** justifie **quel verdict**, via
:attr:`ObjectiveResult.evidence_ids <follow.core.models.ObjectiveResult.evidence_ids>` :

.. code-block:: python

   builder.add_evidence(id="ev-raw", description="Mesures brutes", source="file:///data.csv")
   builder.add_evidence(id="ev-analysis", description="Notebook d'analyse (ANOVA)", source="notebook:///analysis.ipynb")
   builder.conclude(
       objective_results=[dict(
           objective="Résistance de couche", status="met", observed=Quantity(value=76, unit="ohm/sq"),
           evidence_ids=["ev-raw", "ev-analysis"],   # <- la preuve qui atteste ce verdict
       )],
       next_steps="Lancer un lot de confirmation avant promotion.",
   )

La preuve citée devient un lien cliquable dans la fiche (``ev-analysis`` peut très bien pointer
vers une feuille Jupyter qui a fait l'analyse statistique). Une ``Evidence`` jamais citée par
aucun résultat n'est pas perdue pour autant : elle apparaît dans un bloc « Autres preuves »
séparé plutôt que de disparaître silencieusement. ``Conclusion.next_steps`` (texte libre) capture
la décision d'après, distincte de ``decision`` (la catégorie promote/branch/replicate/abandon).

Briques réutilisables
------------------------

:func:`~follow.presentation.report.render_page` assemble une page à partir de sections HTML pré-rendues.
:func:`~follow.presentation.report.experiment_fiche` est la brique de haut niveau (elle échappe elle-même le
texte de l'``Experiment`` qu'on lui passe) ; ses composants plus bas niveau —
:func:`~follow.presentation.report.objectives_table`, :func:`~follow.presentation.report.results_table`,
:func:`~follow.presentation.report.fiche_card` (où l'appelant échappe lui-même chaque argument),
:func:`~follow.presentation.report.trial_card`, :func:`~follow.presentation.report.resolution_conflict_row` et
:func:`~follow.presentation.report.resolution_plain_row` — sont individuellement réutilisables pour composer
un rapport sur mesure. Voir :doc:`batch` pour intégrer un split DOE directement dans la fiche via
``experiment_fiche(..., split=batch_table(variation, standalone=False))``, ``demos/`` pour des
exemples qui assemblent ces briques à la main plutôt que de laisser ``follow report`` tout dériver
automatiquement, et ``demos/auto_report.py`` pour une comparaison directe des deux approches sur
le même dépôt.
