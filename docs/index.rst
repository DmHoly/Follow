Follow
======

Follow est un système de suivi façon **git, mais pour les expériences scientifiques**.

Une expérience (recette de cuisine, structure de MOSFET, empilement de cellule solaire, plan de
barbecue...) est enregistrée avec son **intention**, sa **configuration** la plus complète
possible, un **protocole** en étapes, un ou plusieurs **objectifs**, des **références** de
comparaison, des **preuves** (pointeurs vers des données externes, jamais les données
elles-mêmes) et une **conclusion**. Chaque expérience validée devient un nœud immuable dans un
graphe de filiation, avec des branches et des tags — l'équivalent des commits/branches/tags de
git, appliqué au raisonnement scientifique plutôt qu'au code.

Follow ne possède jamais les données de mesure : il référence des preuves externes et aide à
tracer le raisonnement qui en découle (objectif → preuve → conclusion).

Concepts
--------

.. list-table::
   :header-rows: 1

   * - Concept
     - Rôle
     - Équivalent git
   * - :class:`~follow.core.structure.Structure`
     - La chose étudiée : sa configuration, modélisée en Pydantic avec héritage et composition libres.
     - le contenu versionné
   * - :class:`~follow.core.models.Experiment`
     - Un nœud immuable : intention, structure, étapes, objectifs, références, preuves, conclusion.
     - un commit
   * - :class:`~follow.storage.repository.Repository`
     - Le graphe complet d'expériences, plus les branches/tags.
     - le dépôt
   * - Branche
     - Pointeur mutable vers la dernière expérience d'une ligne de travail.
     - une branche
   * - Tag
     - Pointeur immuable vers une expérience précise.
     - un tag
   * - :class:`~follow.core.models.ReferenceLink`
     - Un point de comparaison (baseline, contrôle, littérature...), pas forcément un ancêtre.
     - —
   * - :func:`~follow.paths.diffing.diff_structures`
     - Différence générique, par introspection Pydantic, entre deux structures.
     - ``git diff``
   * - :func:`~follow.presentation.report.render_study_html`
     - Compte rendu d'étude généré automatiquement, sans IA.
     - ``git log`` / un rapport CI
   * - :func:`~follow.doe.batch.analyze_batch`
     - Une expérience, N variantes structurelles (DOE) : sépare la base commune des facteurs qui varient.
     - — (pas d'équivalent git)
   * - :meth:`~follow.storage.repository.Repository.find_entity`
     - Une même entité physique (nommée via ``entity_id``), retrouvée entre plusieurs expériences séparées.
     - — (pas d'équivalent git)
   * - :func:`~follow.doe.design.full_factorial`
     - Génère les variantes d'un split (DOE) depuis une structure de référence, sans les recopier à la main.
     - — (pas d'équivalent git)
   * - :class:`~follow.storage.commit_form.CommitForm`
     - Questionnaire YAML obligatoire à chaque commit d'un dépôt donné.
     - un modèle de PR obligatoire

.. toctree::
   :maxdepth: 2
   :caption: Guide

   quickstart
   tutorial
   concepts
   merging
   batch
   entities
   design
   commit_form
   report
   cli

.. toctree::
   :maxdepth: 2
   :caption: Référence

   api
   examples

Index et tables
----------------

* :ref:`genindex`
* :ref:`modindex`
