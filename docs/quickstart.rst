Démarrage rapide
=================

Installation
------------

.. code-block:: bash

   # depuis PyPI, une fois publié (pas encore le cas)
   pip install follow

   # depuis ce dépôt Git, dès maintenant
   pip install git+https://github.com/DmHoly/Follow.git

   # en local, pour développer (avec les tests et la doc)
   git clone https://github.com/DmHoly/Follow.git && cd Follow
   pip install -e ".[dev,docs]"

Python 3.11 ou plus est requis. Quatre dépendances : `pydantic <https://docs.pydantic.dev/>`_
(les modèles), `plotly <https://plotly.com/python/>`_ (le graphe de filiation), `numpy
<https://numpy.org/>`_ (générateurs de plan d'expériences, :mod:`follow.doe.design`) et `pyyaml
<https://pyyaml.org/>`_ (formulaires de commit, :mod:`follow.storage.commit_form`) — pas de Graphviz,
pas de base de données, pas de moteur de template.

.. code-block:: pycon

   >>> import follow
   >>> follow.__version__
   '0.1.0'

Premier dépôt
-------------

On modélise d'abord le domaine étudié en sous-classant :class:`~follow.core.structure.Structure` :

.. code-block:: python

   from follow import Quantity, Structure

   class CakeRecipe(Structure):
       ingredients: dict[str, Quantity]

Puis on ouvre un dépôt et on commite une première expérience (l'équivalent d'un premier commit
git) :

.. code-block:: python

   from follow import Repository

   repo = Repository()  # ou Repository("./mon_labo") pour persister sur disque

   baseline = (
       repo.new(
           branch="main",
           structure=CakeRecipe(ingredients={"farine": Quantity(value=200, unit="g")}),
           title="Référence",
           intent="Établir une base de comparaison",
       )
       .conclude(status="concluded", decision="promote", summary="Recette de départ.")
       .commit()
   )

On dérive une variante (comme ``git checkout -b`` + copie de la config) et on la commite à son
tour :

.. code-block:: python

   variant = repo.derive(
       baseline.id, title="Plus de farine", intent="Plus de farine améliore-t-elle la levée ?"
   )
   variant.structure.ingredients["farine"] = Quantity(value=240, unit="g")
   variant.conclude(summary="Légère amélioration.", decision="promote")
   committed = variant.commit()

``repo.derive`` ajoute automatiquement une référence de type ``baseline`` vers le parent, donc
on peut immédiatement voir ce qui a changé :

.. code-block:: pycon

   >>> for entry in repo.diff(baseline.id, committed.id):
   ...     print(entry)
   ~ ingredients.farine: 200 g -> 240 g

Enfin, on génère un compte rendu complet, sans rien écrire à la main :

.. code-block:: python

   from follow import render_study_html

   html = render_study_html(repo, title="Étude gâteau")
   open("etude.html", "w").write(html)

Équivalent en ligne de commande
--------------------------------

.. code-block:: bash

   follow init mon_labo
   follow new --repo mon_labo --branch main --title Référence --intent "Établir une base" \
     --structure-type mon_module.CakeRecipe --structure-file cake.json --out draft.json
   follow commit draft.json --repo mon_labo
   follow log main --repo mon_labo
   follow report --repo mon_labo --out etude.html

Voir :doc:`cli` pour la référence complète des sous-commandes, :doc:`concepts` pour le modèle de
données en détail, et :doc:`tutorial` pour un guide complet — déclarer une expérience, choisir
une stratégie de split (manuel, factoriel, fractionnaire, screening), fusionner des améliorations
validées séparément, exiger un formulaire de commit — sur une recette optimisée de bout en bout.
