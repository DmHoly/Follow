Générer un split (DOE) sans réécrire la structure de référence
==================================================================

Une fois une :class:`~follow.core.structure.Structure` de référence définie, il est inutile de
recopier ses champs à la main pour chaque variante d'un plan d'expériences (DOE). Le module
:mod:`follow.doe.design` prend une instance de référence déjà valide et un spec par facteur, et
renvoie la liste de variantes prête à passer dans un champ liste de ``Structure`` (voir
:doc:`batch` pour l'exploiter ensuite avec :func:`~follow.doe.batch.analyze_batch`).

Générateurs de valeurs
-------------------------

:func:`~follow.doe.design.lin` (``numpy.linspace``), :func:`~follow.doe.design.log`
(``numpy.geomspace``, pour un facteur dont l'effet est multiplicatif plutôt qu'additif) et
:func:`~follow.doe.design.arange` produisent une liste de valeurs — ou de
:class:`~follow.core.quantity.Quantity` directement si ``unit=`` est passé, puisque la plupart des
facteurs réels sont des quantités, pas des flottants nus.

.. code-block:: python

   from follow.doe.design import lin, log

   lin(2, 10, 5, unit="1e14 cm^-2")        # 5 valeurs, 2 à 10 uniformément espacées
   log(1, 1000, 4, unit="Hz")              # 1, 10, 100, 1000 Hz - espacement logarithmique

Trois façons de construire un plan
--------------------------------------

- :func:`~follow.doe.design.sweep` — **un seul facteur qui varie**, tout le reste identique à la
  référence. Toujours statistiquement identifiable : il n'y a rien avec quoi confondre l'unique
  chose qui change.
- :func:`~follow.doe.design.full_factorial` — **toutes les combinaisons de tous les facteurs**
  (produit cartésien). Toujours identifiable aussi, par construction — chaque effet principal et
  chaque interaction peut être estimé indépendamment des autres.
- :func:`~follow.doe.design.latin_hypercube` — **balayage aléatoire stratifié** (LHS) : ``n``
  combinaisons, chaque facteur couvert uniformément sur sa plage même si les combinaisons
  elles-mêmes sont randomisées. Utile pour un screening quand un factoriel complet demanderait
  trop de runs, ou pour explorer sans présupposer quels facteurs comptent.

.. code-block:: python

   from follow.doe.design import full_factorial, lin
   from examples.wafer_doe import Wafer

   reference = Wafer(slot=0, implant_dose=..., anneal_temperature=..., anneal_duration=...)

   wafers = full_factorial(
       reference,
       id_field="slot",
       implant_dose=lin(2, 10, 5, unit="1e14 cm^-2"),
       anneal_temperature=lin(900, 1100, 5, unit="C"),
   )
   # 25 Wafer, slot numéroté automatiquement 1..25 - rien recopié à la main

``id_field`` numérote automatiquement les variantes (1, 2, 3...) sur le champ nommé, quand la
``Structure`` en a un dédié à l'identité de l'entité (un numéro de slot, par exemple).

Plan fractionnaire et structure d'aliasing
----------------------------------------------

Un factoriel complet grandit vite (2 niveaux, k facteurs = 2^k runs). Un **plan fractionnaire**
réduit ce nombre en dérivant certains facteurs comme le produit d'autres — au prix d'un
aliasing : certains effets deviennent statistiquement indiscernables d'autres.
:func:`~follow.doe.design.fractional_factorial` construit le plan *et* calcule explicitement cette
structure d'aliasing, plutôt que de la découvrir après coup sur des résultats inexplicables.

.. code-block:: python

   from follow.doe.design import fractional_factorial

   result = fractional_factorial(
       reference,
       factors={
           "implant_dose": (2, 10, "1e14 cm^-2"),
           "anneal_temperature": (900, 1100, "C"),
           "anneal_duration": (20, 40, "min"),
       },
       generators={"anneal_duration": ["implant_dose", "anneal_temperature"]},  # D = A*B
       id_field="slot",
   )
   result.resolution   # 3 : un effet principal est aliasé avec une interaction à 2 facteurs
   result.aliases       # {"implant_dose": ["anneal_duration:anneal_temperature"], ...}

Les facteurs absents de ``generators`` sont les facteurs de base (factoriel complet à 2 niveaux
sur eux) ; chaque facteur listé dans ``generators`` prend son signe du produit des facteurs de
base nommés. :func:`~follow.doe.design.alias_structure` calcule la même chose de façon autonome, sans
générer de variantes — pratique pour évaluer un plan candidat avant de s'engager dessus.

Ne pas faire de split idiot : :func:`~follow.doe.design.check_identifiability`
-------------------------------------------------------------------------------

L'erreur classique — faite à la main, pas via un plan fractionnaire réfléchi — est un balayage
« diagonal » où deux facteurs montent ensemble, pas de façon croisée : impossible ensuite de dire
si un effet observé vient de l'un ou de l'autre.
:func:`~follow.doe.design.check_identifiability` vérifie, après coup, la corrélation entre chaque
paire de facteurs sur le plan effectivement construit (par les fonctions ci-dessus ou à la main)
et signale toute paire trop corrélée :

.. code-block:: python

   from follow.doe.design import check_identifiability

   good = full_factorial(reference, implant_dose=lin(2, 10, 5, unit="..."), anneal_temperature=lin(900, 1100, 5, unit="C"))
   check_identifiability(good, ["implant_dose", "anneal_temperature"])
   # [] - rien à signaler, le plan est croisé

   bad = [reference.model_copy(update={...}) for dose, temp in zip([2, 4, 6, 8, 10], [900, 950, 1000, 1050, 1100])]
   check_identifiability(bad, ["implant_dose", "anneal_temperature"])
   # [("implant_dose", "anneal_temperature", 0.9999...)] - les deux montent ensemble, confondus

C'est un contrôle générique sur les colonnes du plan (rien à voir avec les résultats mesurés) :
il s'applique aussi bien à un plan construit à la main qu'à un plan issu de
:func:`~follow.doe.design.sweep`/:func:`~follow.doe.design.full_factorial`/
:func:`~follow.doe.design.latin_hypercube`. Pour un plan fractionnaire, préférez
:func:`~follow.doe.design.alias_structure`, qui donne la structure complète (y compris les
interactions), pas seulement les corrélations de facteurs principaux.

Voir ``demos/wafer_doe.py`` pour un scénario complet exécutable : un split factoriel 5×5 généré
par :func:`~follow.doe.design.full_factorial`, suivi d'un lot de confirmation homogène.
