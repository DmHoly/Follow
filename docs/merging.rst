Fusionner deux lignes de travail
==================================

Une expérience peut avoir **deux parents** — c'est un commit de fusion, comme dans git. On
teste une variation sur une branche à part, puis on rapatrie dans ``main`` uniquement ce qui a
été validé. Follow ne résout jamais un conflit tout seul : on choisit explicitement, chemin par
chemin, quelle valeur garder.

.. code-block:: python

   # `essai-cuisson` a divergé de `main` puis évolué sur 3 commits (160°C, 185°C, 175°C retenu)
   for entry in repo.diff_steps("main", "essai-cuisson"):
       print(entry)
   # ~ [2].parameters.temperature: 170 C -> 175 C
   # ~ [2].parameters.duree: 35 min -> 32 min

   merged = repo.merge(
       "main", "essai-cuisson",
       title="Fusion : cuisson optimisée",
       intent="N'adopter que la température de cuisson validée sur la branche d'essai",
       take_steps=["[2]"],
   ).commit()

``take_structure``/``take_steps`` listent les chemins (au même format que
:class:`~follow.diffing.DiffEntry`, obtenus via :meth:`Repository.diff()
<follow.repository.Repository.diff>`/:meth:`Repository.diff_steps()
<follow.repository.Repository.diff_steps>`) dont la valeur doit venir du second réf plutôt que
du premier. Tout chemin non listé garde la valeur du premier réf — exactement comme un hunk de
``git merge`` qu'on ne touche pas.

Le résultat porte les deux pointes comme parents (``merged.parents`` contient les deux ids) et
deux références automatiques : ``baseline`` vers le premier parent, ``merge_source`` vers le
second.

Résolution manuelle avec :func:`~follow.merging.resolve_merge_paths`
------------------------------------------------------------------------

:meth:`Repository.merge() <follow.repository.Repository.merge>` s'appuie sur
:func:`follow.merging.resolve_merge_paths`, directement réutilisable :

.. code-block:: python

   from follow.merging import resolve_merge_paths

   merged_dump = resolve_merge_paths(ours=our_dump, theirs=their_dump, take_from_theirs=["[2]"])

Équivalent en CLI
-----------------

.. code-block:: bash

   follow diff main essai-cuisson --repo mon_labo --steps

   follow merge main essai-cuisson --repo mon_labo \
     --title "Fusion : cuisson optimisée" \
     --intent "N'adopter que la température de cuisson validée sur la branche d'essai" \
     --take-steps "[2]" \
     --out merge.json
   follow commit merge.json --repo mon_labo

Voir ``demos/fusion_selective.py`` pour un scénario complet exécutable (5 étapes, une branche à
3 commits, une fusion sélective), et ``demos/chocolate_fondant.py`` pour un cas avec plusieurs
branches et fusions séquentielles.
