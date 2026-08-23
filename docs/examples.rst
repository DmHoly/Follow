Exemples et démos
===================

Domaines (``examples/``)
---------------------------

Des ``Structure`` prêtes à l'emploi, pour voir l'héritage et la composition en pratique :

- ``examples/recipe.py`` — ``CakeRecipe`` / ``ChocolateCakeRecipe`` (recette de gâteau, variante
  par héritage).
- ``examples/mosfet.py`` — ``MOSFETStructure`` / ``FinFETStructure`` (évolution de structure de
  dispositif par héritage).
- ``examples/solar_cell.py`` — ``SolarModule`` → ``SolarCell`` → ``PNJunction`` → ``Layer``
  (composition profonde).
- ``examples/chocolate_fondant.py`` — ``MoltenChocolateCake`` (composition + séparation
  structure/protocole, utilisée par ``demos/chocolate_fondant.py``).

Scénarios complets (``demos/``)
------------------------------------

Des scripts exécutables qui construisent un dépôt réel de bout en bout et le rendent en page
HTML (voir ``demos/README.md`` dans le dépôt) :

- ``demos/fusion_selective.py`` — une recette à 5 étapes, une branche de test sur 3 commits, une
  évolution indépendante sur ``main`` en parallèle, puis une fusion qui ne rapatrie qu'une seule
  étape validée.
- ``demos/chocolate_fondant.py`` — une recette de fondant au chocolat cœur coulant synthétisée à
  partir de 10 recettes réelles, optimisée par 3 branches et 3 fusions séquentielles, avec une
  validation finale qui referme un écart de combinaison non testée.
- ``demos/auto_report.py`` — le même dépôt que ``chocolate_fondant.py``, rendu par
  :func:`~follow.report.render_study_html` sans aucune section écrite à la main.

.. code-block:: bash

   python -m demos.fusion_selective          # écrit demos/output/fusion_selective.html
   python -m demos.chocolate_fondant         # écrit demos/output/chocolate_fondant.html
   python -m demos.auto_report               # écrit demos/output/chocolate_fondant_auto_report.html

Les fichiers ``demos/output/*.html`` sont des instantanés statiques committés, consultables
directement (double-clic, aucune installation requise).
