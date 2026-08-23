Une expérience, plusieurs variantes (DOE)
============================================

Git n'a pas de notion pour ce cas : un plan d'expériences (DOE, *design of experiments*)
factoriel réparti sur, disons, 25 wafers reste **une seule expérience** — une intention, un
protocole, une conclusion — mais sa :class:`~follow.structure.Structure` contient 25 entités
(wafers, lots de pâte, formes de lentille, grilles de barbecue...) qui ont chacune reçu une
combinaison différente de paramètres.

Follow n'a rien besoin d'ajouter au moteur pour ça : une ``Structure`` a toujours pu contenir
``list[AutreStructure]`` (voir ``SolarModule.cells`` dans ``examples/solar_cell.py``).
:func:`follow.batch.analyze_batch` ajoute juste l'analyse générique qui rend cette liste utile
*en tant que* plan d'expériences : quels paramètres sont identiques sur toutes les entités (la
base commune) et lesquels varient réellement (les facteurs du plan) — lu mécaniquement plutôt
que suivi à la main.

.. code-block:: python

   from follow import analyze_batch

   lot = repo.load_structure(experiment)          # WaferLot(wafers=[Wafer(...), ...])
   variation = analyze_batch(lot.wafers, ignore=["slot"])

   variation.entity_count   # 25
   variation.constant       # {"anneal_duration": {"value": 30, "unit": "min", ...}}
   variation.varying        # [BatchFactor(path="implant_dose", values=[...]), ...]
   variation.is_uniform     # False : il y a bien des facteurs qui varient

``ignore`` exclut les champs d'identité (un numéro de slot, un nom, un id de série) qui
diffèrent par construction sur chaque entité et empêcheraient sinon un lot réellement homogène
(ex. un lot de confirmation, toutes les entités à la même combinaison retenue) de ressortir
``is_uniform``.

Affichage hybride
--------------------

:func:`follow.report.batch_table` rend un :class:`~follow.batch.BatchVariation` comme un bloc
HTML (même thème que :func:`~follow.report.experiment_fiche`) : la base commune en liste plate,
puis les facteurs variables "explosés" en un tableau (une ligne par paramètre, une colonne par
entité). Deux façons de le poser :

- ``standalone=True`` (défaut) : un ``.fiche-card`` autonome, à côté de la fiche habituelle de
  l'expérience — la fiche donne la vue "une expérience", le tableau donne la vue "many variantes".
- ``standalone=False`` : un simple fragment ``.fiche-row``, pensé pour être **intégré**
  directement dans :func:`~follow.report.experiment_fiche` via son paramètre ``split=`` — le
  split apparaît alors comme une section de plus dans la même fiche, entre les objectifs et les
  résultats (voir :doc:`report`).

.. code-block:: python

   from follow import analyze_batch, experiment_fiche
   from follow.report import batch_table

   variation = analyze_batch(lot.wafers, ignore=["slot"])
   split = batch_table(
       variation,
       entity_labels=[f"#{w.slot}" for w in lot.wafers],
       title="Split (25 wafers)",
       standalone=False,               # <- un fragment, pas une carte à part
   )
   fiche = experiment_fiche(experiment, split=split)

Voir ``demos/wafer_doe.py`` pour un scénario complet : un plan factoriel 5×5 (dose
d'implantation × température de recuit) sur 25 wafers, suivi d'un lot de confirmation de 5
wafers à la combinaison retenue — le premier ressort avec deux facteurs variables, le second
ressort ``is_uniform`` — chacun intégré dans la fiche de son expérience via ``split=``.

Équivalent en CLI
-----------------

.. code-block:: bash

   follow explode main wafers --ignore slot --repo mon_labo
   # 25 entités  ·  1 constant(s)  ·  2 variable(s)
   #
   # constants:
   #   anneal_duration: 30 min
   #
   # variables:
   #   implant_dose: [2 1e14 cm^-2, 2 1e14 cm^-2, ..., 10 1e14 cm^-2]
   #   anneal_temperature: [900 C, 950 C, ..., 1100 C]

   follow explode main wafers --ignore slot --repo mon_labo --out explode.html --open

``follow explode <ref> <chemin>`` accepte n'importe quel champ liste de la structure de
l'expérience visée ; ``--ignore`` est répétable, et ``--out`` produit la même page thémée que
``follow report``/``follow graph`` plutôt qu'un résumé texte.

Voir :doc:`design` pour générer les 25 entités elles-mêmes (factoriel complet, fractionnaire,
balayage, LHS) au lieu de les écrire à la main — c'est ce que fait ``demos/wafer_doe.py``.
