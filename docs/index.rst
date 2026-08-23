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
   * - :class:`~follow.structure.Structure`
     - La chose étudiée : sa configuration, modélisée en Pydantic avec héritage et composition libres.
     - le contenu versionné
   * - :class:`~follow.models.Experiment`
     - Un nœud immuable : intention, structure, étapes, objectifs, références, preuves, conclusion.
     - un commit
   * - :class:`~follow.repository.Repository`
     - Le graphe complet d'expériences, plus les branches/tags.
     - le dépôt
   * - Branche
     - Pointeur mutable vers la dernière expérience d'une ligne de travail.
     - une branche
   * - Tag
     - Pointeur immuable vers une expérience précise.
     - un tag
   * - :class:`~follow.models.ReferenceLink`
     - Un point de comparaison (baseline, contrôle, littérature...), pas forcément un ancêtre.
     - —
   * - :func:`~follow.diffing.diff_structures`
     - Différence générique, par introspection Pydantic, entre deux structures.
     - ``git diff``
   * - :func:`~follow.report.render_study_html`
     - Compte rendu d'étude généré automatiquement, sans IA.
     - ``git log`` / un rapport CI

.. toctree::
   :maxdepth: 2
   :caption: Guide

   quickstart
   concepts
   merging
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
