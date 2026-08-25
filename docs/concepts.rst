Concepts
========

Structure : modéliser un domaine
---------------------------------

:class:`~follow.core.structure.Structure` est la seule classe à sous-classer pour décrire un
domaine — recette, MOSFET, cellule solaire, panneau, plan de barbecue... Follow n'introspecte
que les champs Pydantic (diff, sérialisation) : il ne connaît rien à la physique ou à la
cuisine. La généricité vient de là ; le guidage vient de l'héritage et de la composition
Pydantic classiques :

.. code-block:: python

   from follow import Quantity, Structure

   class Layer(Structure):
       material: str
       thickness: Quantity

   class MOSFETStructure(Structure):
       gate_length: Quantity
       gate_oxide: Layer

   class FinFETStructure(MOSFETStructure):
       fin_height: Quantity
       fin_width: Quantity

Un domaine complexe se construit en assemblant des ``Structure`` plus petites (composition), et
fait évoluer sa structure (ex. MOSFET planaire → FinFET) en sous-classant. Préférez
:class:`~follow.core.quantity.Quantity` pour les valeurs terminales : unité et incertitude voyagent
avec le nombre, et les diffs restent lisibles (un ``Quantity`` est traité comme une seule
feuille, pas comme plusieurs champs indépendants).

Voir ``examples/`` dans le dépôt pour des domaines complets : ``recipe.py``, ``mosfet.py``,
``solar_cell.py``, ``chocolate_fondant.py``, ``wafer_doe.py``.

Cas particulier : une expérience, N variantes (``list[SousStructure]``)
--------------------------------------------------------------------------

Rien n'empêche une ``Structure`` de contenir une liste d'entités du même genre plutôt qu'une
seule (un lot de 25 wafers en plan factoriel, une série de moules de recette, un jeu de formes
de lentille...) : c'est toujours une seule expérience — une intention, un protocole, une
conclusion — mais avec plusieurs variantes structurelles à l'intérieur. Voir :doc:`batch` pour
:func:`~follow.doe.batch.analyze_batch`, qui sépare mécaniquement la base commune des paramètres qui
varient réellement entre ces entités, et :func:`~follow.presentation.report.batch_table` pour l'afficher.

Experiment : le nœud immuable
-------------------------------

Un :class:`~follow.core.models.Experiment` est l'équivalent d'un commit git : figé une fois
committé, adressé par un identifiant dérivé de son propre contenu
(:func:`follow.core.ids.content_id`). Il porte :

- ``intent`` / ``hypothesis`` — pourquoi cette expérience,
- ``structure`` / ``structure_type`` — la configuration étudiée,
- ``steps`` (:class:`~follow.core.models.Step`) — le protocole, ordonné,
- ``objectives`` (:class:`~follow.core.models.Objective`) — ce qu'on cherche à atteindre,
- ``references`` (:class:`~follow.core.models.ReferenceLink`) — les points de comparaison,
- ``evidence`` (:class:`~follow.core.models.Evidence`) — des pointeurs vers des données externes,
  jamais les données elles-mêmes (un fichier de mesures, un notebook d'analyse...),
- ``conclusion`` (:class:`~follow.core.models.Conclusion`) — le verdict par objectif
  (:class:`~follow.core.models.ObjectiveResult`, avec ``evidence_ids`` : quelle(s) preuve(s) précise(s)
  justifient ce verdict — Follow n'analyse jamais rien lui-même, il ne fait que relier verdict et
  preuve), un ``decision`` catégoriel (promote/branch/replicate/abandon/inconclusive), et
  ``next_steps`` en texte libre pour la suite. Voir :doc:`report` pour comment tout cela se lit
  ensemble dans une fiche (:func:`~follow.presentation.report.experiment_fiche`).

On ne construit jamais un ``Experiment`` directement : on passe par un
:class:`~follow.storage.repository.ExperimentBuilder` (mutable, l'équivalent de l'arbre de travail
git), renvoyé par :meth:`Repository.new() <follow.storage.repository.Repository.new>` ou
:meth:`Repository.derive() <follow.storage.repository.Repository.derive>`, et on le fige avec
``.commit()``.

Repository : branches, tags, filiation
-----------------------------------------

:class:`~follow.storage.repository.Repository` stocke les expériences (adressées par contenu) et les
pointeurs qui naviguent dedans :

- une **branche** est un pointeur mutable vers la dernière expérience d'une ligne de travail
  (:meth:`Repository.branch() <follow.storage.repository.Repository.branch>`) — mais committer n'avance
  jamais une branche en abandonnant silencieusement son historique : si la pointe actuelle de la
  branche ne fait pas partie des parents du commit, c'est refusé (dériver d'un ancien commit sans
  ``new_branch`` explicite, ou nommer ``new_branch``/``branch`` comme une branche déjà utilisée
  ailleurs, sont tous les deux rejetés — l'équivalent du HEAD détaché de git) ; et, comme
  ``git commit`` sans rien à committer, un commit dont le contenu est identique à la pointe
  actuelle de sa branche est refusé (:class:`~follow.storage.repository.NothingToCommitError`) plutôt
  que silencieusement dupliqué ou ignoré ;
- un **tag** est un pointeur immuable vers une expérience précise
  (:meth:`Repository.tag() <follow.storage.repository.Repository.tag>`) — repointer un tag existant
  vers une autre expérience lève une erreur sauf ``force=True`` ; branches et tags partagent un
  seul espace de noms (créer l'un du nom de l'autre existant est refusé) ;
- :meth:`Repository.log() <follow.storage.repository.Repository.log>` remonte l'historique en
  premier-parent, comme ``git log`` ;
- :meth:`Repository.graph() <follow.storage.repository.Repository.graph>` donne le graphe de filiation
  complet (``{id: [parents]}``), consommé par :mod:`follow.presentation.graphing` ;
- :meth:`Repository.diff() <follow.storage.repository.Repository.diff>` /
  :meth:`Repository.diff_steps() <follow.storage.repository.Repository.diff_steps>` comparent deux
  expériences, structure ou protocole, par introspection générique
  (:func:`follow.paths.diffing.diff_structures`).

Follow ne réutilise pas git en interne : ces notions sont réimplémentées spécifiquement pour ce
domaine, avec des identifiants adressés par contenu (comme les SHA de git) mais sans dépendre
d'un vrai dépôt git.

Persistance
-----------

``Repository()`` sans argument est un dépôt en mémoire (pratique pour les tests, les scripts, un
notebook). ``Repository("./mon_labo")`` persiste en JSON simple : un fichier par expérience sous
``objects/``, plus un ``refs.json`` pour les branches et tags — lisible, diffable, versionnable
avec un vrai dépôt git si on le souhaite.
