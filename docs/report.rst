Générer un compte rendu d'étude
==================================

:func:`follow.report.render_study_html` transforme un dépôt (ou le lignage d'une branche) en
une page HTML autonome, lisible comme le compte rendu d'une étude complète — sans IA, sans
moteur de template externe. Tout vient des champs déjà présents dans les expériences ; le module
(:mod:`follow.report`) est de simples f-strings Python, sans nouvelle dépendance au-delà de
Plotly (déjà utilisé par :mod:`follow.graphing`).

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

Un sommaire cliquable, le graphe de filiation, puis une fiche par expérience (intention,
objectifs, preuves, conclusion). Ce qui a changé à chaque commit est **calculé**, pas recopié à
la main :

- **un seul parent** → diff structure + protocole contre ce parent
  (:meth:`Repository.diff() <follow.repository.Repository.diff>` /
  :meth:`Repository.diff_steps() <follow.repository.Repository.diff_steps>`) ;
- **deux parents** (fusion) → chaque chemin qui diffère entre les deux parents est comparé à la
  valeur du commit de fusion pour dire explicitement de quel côté elle a été reprise, au niveau
  de chaque feuille — plus précis qu'une note écrite à la main.

Le texte issu du dépôt (titres, intentions, résumés...) est échappé avant insertion dans le HTML
(:func:`follow.report._esc`) : contrairement aux démos, où le texte est entièrement écrit par
l'auteur du script, ce renderer affiche des données saisies par n'importe qui.

Briques réutilisables
------------------------

:func:`~follow.report.render_page` assemble une page à partir de sections HTML pré-rendues ;
:func:`~follow.report.fiche_card`, :func:`~follow.report.trial_card`,
:func:`~follow.report.resolution_conflict_row` et :func:`~follow.report.resolution_plain_row`
sont les briques que :func:`~follow.report.render_study_html` utilise en interne, réutilisables
pour composer un rapport sur mesure. Voir ``demos/`` pour des exemples qui les assemblent à la
main plutôt que de laisser ``follow report`` tout dériver automatiquement, et
``demos/auto_report.py`` pour une comparaison directe des deux approches sur le même dépôt.
