Suivre une même entité physique entre plusieurs expériences
================================================================

:doc:`batch` répond à *"une expérience, N variantes"*. Ceci répond à l'axe inverse : *une seule
chose physique* (un moule, un wafer, un échantillon — n'importe quoi à qui on a donné un nom),
qui réapparaît dans **plusieurs expériences séparées**, parfois bien plus tard, parfois sur une
branche sans aucun lien de filiation git avec la première.

Exemple concret : un split nomme chaque variante d'un lot avec un nom physique réel — pas un
identifiant abstrait, le nom du moule utilisé (« moule vert », « moule rouge »...). Plus tard, sur
le gâteau issu du moule vert spécifiquement, une nouvelle expérience commence (injection de
Nutella) — sans recharger de référence vers le split d'origine, juste en réutilisant le même nom.
Follow doit pouvoir dire automatiquement « ce gâteau-là a aussi été utilisé ici ».

Le champ ``entity_id``
--------------------------

Aucune référence à poser, aucun id à recopier : donnez à n'importe quelle
:class:`~follow.core.structure.Structure` (ou à une sous-structure imbriquée, par exemple une entrée
d'un ``list[...]`` de batch) un champ ``entity_id: str | None`` et attribuez-lui le nom choisi.

.. code-block:: python

   class ChocolateCake(Structure):
       name: str
       entity_id: str | None = None   # "moule-vert", "moule-rouge"...
       ...

   class CakeTrialBatch(Structure):
       batch_id: str
       trials: list[ChocolateCake]

Un split nomme chaque variante :

.. code-block:: python

   split = repo.new(
       branch="main",
       structure=CakeTrialBatch(batch_id="B1", trials=[
           baseline.model_copy(update={"trial_id": 1, "entity_id": "moule-vert"}),
           baseline.model_copy(update={"trial_id": 2, "entity_id": "moule-rouge"}),
       ]),
       title="Split moules", intent="comparer 2 moules",
   ).commit()

Plus tard, une expérience *séparée* réutilise juste le nom :

.. code-block:: python

   nutella = repo.new(
       branch="moule-vert-nutella",              # aucun lien de filiation avec `split`
       structure=baseline.model_copy(update={"entity_id": "moule-vert", "name": "+ nutella"}),
       title="Injection Nutella", intent="ameliorer le moule vert",
   ).commit()

``repo.derive(...)`` marche aussi bien : ``entity_id`` fait simplement partie de la structure
copiée, donc il survit à un ``derive()`` sans rien faire de spécial — utilisez ``derive()`` quand
la suite continue naturellement une ligne de travail (parent git + référence baseline
automatique), ou ``new()`` sur une branche fraîche quand ce n'est pas le cas ; les deux
réapparaissent dans la timeline de l'entité de la même façon.

Retrouver l'entité
----------------------

.. code-block:: python

   repo.find_entity("moule-vert")
   # [<Experiment "Split moules">, <Experiment "Injection Nutella">]  -- triées par date, les deux

:meth:`~follow.storage.repository.Repository.find_entity` parcourt le dépôt entier (toutes branches, tout
lignage confondu) et rend chaque expérience qui mentionne ``entity_id`` quelque part dans sa
structure déjà stockée — la même technique de parcours générique par forme que
:mod:`follow.paths.diffing`/:mod:`follow.doe.batch` utilisent déjà, ici pour trouver une feuille précise au
lieu d'en comparer plusieurs. C'est :func:`follow.paths.entities.find_entity_mentions` qui fait ce
parcours ; ``Repository.find_entity`` l'applique à chaque expérience stockée et trie le résultat.

En ligne de commande :

.. code-block:: console

   $ follow trace moule-vert --repo .follow
   exp_a1b2c3...  (main)                 Split moules       [concluded]  -- trials[0]
   exp_d4e5f6...  (moule-vert-nutella)   Injection Nutella  [concluded]  -- (racine)

Le chemin affiché (``trials[0]``, ou ``(racine)`` quand l'entité est la structure entière) montre
où, dans chaque expérience, le nom a été trouvé.
