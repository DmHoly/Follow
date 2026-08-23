# Follow

Follow est un système de suivi façon **git, mais pour les expériences scientifiques**.

Une expérience (recette de cuisine, structure de MOSFET, empilement de cellule solaire, plan de
barbecue...) est enregistrée avec son **intention**, sa **configuration** la plus complète
possible, un **protocole** en étapes, un ou plusieurs **objectifs**, des **références** de
comparaison, des **preuves** (pointeurs vers des données externes, jamais les données
elles-mêmes) et une **conclusion**. Chaque expérience validée devient un nœud immuable dans un
graphe de filiation, avec des branches et des tags — l'équivalent des commits/branches/tags de
git, appliqué au raisonnement scientifique plutôt qu'au code.

Follow ne possède jamais les données de mesure : il référence des preuves externes et aide à
vérifier/tracer le raisonnement qui en découle (objectif → preuve → conclusion). C'est aussi le
point d'ancrage prévu pour une couche d'inférence causale/corrélative (ex. DoWhy) dans une
itération future — non incluse dans ce périmètre v1 "cœur".

Documentation complète (guide, référence de l'API, CLI) : voir `docs/` (`make html` avec Sphinx,
détails plus bas) ou `demos/` pour des scénarios complets exécutables.

## Installation

```bash
# depuis PyPI, une fois publié (pas encore le cas)
pip install follow

# depuis ce dépôt Git, dès maintenant
pip install git+https://github.com/DmHoly/Follow.git

# en local, pour développer (avec les tests et la doc)
git clone https://github.com/DmHoly/Follow.git && cd Follow
pip install -e ".[dev,docs]"
```

Python ≥ 3.11 requis. Deux dépendances : `pydantic` (les modèles) et `plotly` (le graphe de
filiation) — pas de Graphviz, pas de base de données, pas de moteur de template.

```python
>>> import follow
>>> follow.__version__
'0.1.0'
```

## Démarrage rapide

```python
from follow import Quantity, Repository, Structure

class CakeRecipe(Structure):
    ingredients: dict[str, Quantity]

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

variant = repo.derive(baseline.id, title="Plus de farine", intent="Plus de farine améliore-t-elle la levée ?")
variant.structure.ingredients["farine"] = Quantity(value=240, unit="g")
variant.conclude(summary="Légère amélioration.", decision="promote")
committed = variant.commit()

for entry in repo.diff(baseline.id, committed.id):
    print(entry)   # ~ ingredients.farine: 200 g -> 240 g
```

Équivalent en ligne de commande :

```bash
follow init mon_labo
follow new --repo mon_labo --branch main --title Référence --intent "Établir une base" \
  --structure-type mon_module.CakeRecipe --structure-file cake.json --out draft.json
follow commit draft.json --repo mon_labo
follow log main --repo mon_labo
follow report --repo mon_labo --out etude.html   # la fiche complète, générée automatiquement
```

La suite de ce README détaille chaque concept ; `docs/quickstart.rst` reprend cet exemple pas à
pas avec plus de contexte.

## Concepts

| Concept | Rôle | Équivalent git |
|---|---|---|
| `Structure` | La chose étudiée : sa configuration/géométrie/recette, modélisée en Pydantic avec héritage et composition libres. | le contenu versionné |
| `Experiment` | Un nœud immuable : intention, structure, étapes, objectifs, références, preuves, conclusion. | un commit |
| `Repository` | Le graphe complet d'expériences + les branches/tags. | le dépôt |
| `Branch` | Pointeur mutable vers la dernière expérience d'une ligne de travail. | une branche |
| `Tag` | Pointeur immuable vers une expérience précise (ex. "championne-v3"). | un tag |
| `ReferenceLink` | Un point de comparaison (baseline, contrôle, littérature...), pas forcément un ancêtre. | — |
| `StructureDiff` | Différence générique, calculée par introspection Pydantic, entre deux structures. | `git diff` |
| `fiche` (Markdown) | Rendu humain d'une expérience : intention, structure, écarts vs référence, objectifs, preuves, conclusion. | `git show` |

Follow ne réutilise pas git en interne : les notions de version/branche/parenté sont
réimplémentées spécifiquement pour ce domaine (voir `follow/repository.py`), avec des
identifiants adressés par contenu (comme les SHA de git) mais sans dépendre d'un vrai dépôt git.

## Modéliser un domaine (générique + guidé)

`Structure` est la seule classe à hériter pour décrire un domaine — recette, MOSFET, cellule
solaire, panneau, plan de barbecue... La généricité de Follow vient du fait qu'il n'introspecte
que les champs Pydantic (diff, sérialisation), sans connaître la physique/le domaine. Le guidage
vient de l'héritage/la composition : un domaine complexe se construit en assemblant des
`Structure` plus petites, et fait évoluer sa structure (ex. MOSFET planaire → FinFET) en
sous-classant.

```python
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
```

Voir `examples/` pour les domaines complets : `recipe.py` (recette de gâteau, avec variante par
héritage), `mosfet.py` (MOSFET → FinFET), `solar_cell.py` (composition profonde
module → cellule → jonction PN → couche), `chocolate_fondant.py` (optimisation d'une recette de
fondant au chocolat cœur coulant à partir de recettes réelles).

Voir `demos/` pour des scénarios complets, bout en bout, rendus en pages HTML autonomes.

## Workflow

```python
from examples.recipe import BakeStep, CakeRecipe
from follow import Quantity, Repository, render_fiche

repo = Repository("./mon_labo")  # ou Repository() pour un dépôt en mémoire

baseline = (
    repo.new(
        branch="main",
        structure=CakeRecipe(
            name="Gâteau vanille",
            ingredients={"farine": Quantity(value=200, unit="g")},
            bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
        ),
        title="Référence",
        intent="Établir une base de comparaison",
    )
    .add_objective(name="hauteur", metric="height_cm", direction="maximize", target=5.0, tolerance=0.5)
    .commit()
)

# Dériver une variante : copie la config du parent + ajoute automatiquement
# une référence "baseline" vers lui.
variant = repo.derive(baseline.id, title="Plus de farine", intent="Plus de farine améliore-t-elle la levée ?")
variant.structure.ingredients["farine"] = Quantity(value=240, unit="g")
variant.add_evidence(id="ev1", description="Photo du four", source="file:///data/photo.jpg",
                      metrics={"height_cm": Quantity(value=5.4, unit="cm")})
variant.conclude(summary="Légère amélioration de la levée.", decision="promote")
committed = variant.commit()

print(render_fiche(committed, repo))       # la "fiche" façon git show
print(repo.diff(baseline.id, committed.id))  # uniquement les paramètres qui ont varié
```

`repo.log("main")`, `repo.branch(...)`, `repo.tag(...)` et `render_graph_html(repo, "graph.html")`
(graphe de filiation interactif, voir plus bas) complètent l'API — voir les docstrings de
`follow/repository.py` et `follow/rendering.py`.

## CLI façon git

Après `uv pip install -e .`, la commande `follow` est disponible. Le principe suit celui de git :
un brouillon JSON joue le rôle de l'arbre de travail (on l'édite à la main — ajout d'étapes, de
preuves, écriture de la conclusion une fois l'expérience réellement menée), puis `follow commit`
le fige dans le dépôt.

```bash
follow init mon_labo

follow new --repo mon_labo \
  --branch main --title Baseline --intent "Établir une référence" \
  --structure-type examples.recipe.CakeRecipe --structure-file cake.json \
  --out draft.json
# éditer draft.json à la main si besoin (étapes, objectifs, preuves...)
follow commit draft.json --repo mon_labo
# -> exp_xxxxxxxx  (main)  Baseline

follow derive exp_xxxxxxxx --repo mon_labo \
  --title "Plus de farine" --intent "Plus de farine améliore-t-elle la levée ?" \
  --out variant.json
# variant.json hérite la structure + une référence "baseline" automatique vers le parent
# -> éditer variant.json : changer la farine, ajouter evidence + conclusion
follow commit variant.json --repo mon_labo

follow log main --repo mon_labo          # historique de la branche
follow show exp_yyyyyyyy --repo mon_labo # la fiche complète (façon `git show`)
follow diff exp_xxxxxxxx exp_yyyyyyyy --repo mon_labo          # ce qui a varié dans la structure
follow diff exp_xxxxxxxx exp_yyyyyyyy --repo mon_labo --steps  # ce qui a varié dans le protocole
follow branch --repo mon_labo            # lister les branches
follow branch essai --at exp_yyyyyyyy --repo mon_labo  # créer/déplacer une branche
follow tag championne --at exp_yyyyyyyy --repo mon_labo
follow graph --repo mon_labo --out graph.html --open
```

`--structure-type` attend un chemin pointé Python (`module.Classe`) : la CLI importe ce module à
la volée pour retrouver la classe `Structure` enregistrée, donc vos domaines (`examples/recipe.py`
et consorts) doivent être importables (présents dans le répertoire courant ou installés).

`follow --help` / `follow <sous-commande> --help` détaille chaque option.

## Fusionner deux lignes de travail (`follow merge`)

Une expérience peut avoir **deux parents** — c'est un commit de fusion, comme dans git. Vous
testez une variation sur une branche à part, puis vous rapatriez dans `main` uniquement ce qui a
été validé : Follow ne résout jamais un conflit tout seul, vous choisissez explicitement, chemin
par chemin, quelle valeur garder.

```bash
# `essai-cuisson` a divergé de `main` puis évolué sur 3 commits (160°C, 185°C, 175°C retenu)
follow diff main essai-cuisson --repo mon_labo --steps
# ~ [2].parameters.temperature: 170 C -> 175 C
# ~ [2].parameters.duree: 35 min -> 32 min

follow merge main essai-cuisson --repo mon_labo \
  --title "Fusion : cuisson optimisée" \
  --intent "N'adopter que la température de cuisson validée sur la branche d'essai" \
  --take-steps "[2]" \
  --out merge.json
# merge.json : parents = [tip(main), tip(essai-cuisson)], step [2] vient de la branche,
# toutes les autres étapes (y compris les changements propres à main) restent inchangées
follow commit merge.json --repo mon_labo
```

`--take-structure PATH` fait la même chose pour la `Structure` (les chemins viennent de
`follow diff`, sans `--steps`) ; `--take-steps PATH` cible le protocole (chemins de
`follow diff --steps`, ex. `[2]` pour toute l'étape, `[2].parameters.temperature` pour un seul
champ). Tout chemin non listé garde la valeur du premier réf (`ref_a`, la cible de la fusion) —
exactement comme un hunk de `git merge` qu'on ne touche pas. Voir `Repository.merge` et
`resolve_merge_paths` (`follow/merging.py`) côté Python.

## Une expérience, N variantes (`follow explode`)

Cas hors de portée de git : un plan d'expériences (DOE) factoriel réparti sur 25 wafers (ou 25
moules de recette, 25 formes de lentille...) reste **une seule expérience** — une intention, un
protocole, une conclusion — mais sa `Structure` contient une liste de 25 entités qui ont chacune
reçu une combinaison différente de paramètres. `follow.batch.analyze_batch` sépare
mécaniquement ce qui est constant sur toutes les entités de ce qui varie réellement (les
facteurs du plan) ; `follow.report.batch_table` l'affiche comme un bloc « explosé » à poser à
côté de la fiche habituelle de l'expérience — un affichage hybride, par expérience et par
entité.

```bash
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
```

`--ignore` exclut les champs d'identité (un numéro de slot, un id de série) qui diffèrent par
construction sur chaque entité et empêcheraient sinon un lot réellement homogène (ex. un lot de
confirmation) de ressortir comme uniforme. Voir `demos/wafer_doe.py` (plan factoriel 5×5 sur 25
wafers, puis lot de confirmation) et `docs/batch.rst` côté Python.

## Générer une fiche/compte rendu d'étude (`follow report`)

`follow report` transforme un dépôt (ou le lignage d'une branche) en une page HTML autonome,
lisible comme le compte rendu d'une étude complète — sans IA, sans moteur de template externe :
tout vient des champs déjà présents dans les expériences (`follow/report.py`, pure f-strings
Python, zéro nouvelle dépendance au-delà de Plotly déjà utilisé par `follow graph`).

```bash
follow report --repo mon_labo --title "Étude gâteau au yaourt" --out etude.html
follow report essai-cuisson --repo mon_labo --out etude-branche.html  # limiter à une branche
```

La page contient : un sommaire cliquable, le graphe de filiation, puis une fiche par expérience
(intention, objectifs, preuves, conclusion). Pour chaque commit, ce qui a changé est calculé —
pas recopié à la main :

- **un seul parent** → diff structure + protocole contre ce parent (`repo.diff`/`diff_steps`) ;
- **deux parents** (fusion) → chaque chemin qui diffère entre les deux parents est comparé à la
  valeur du commit de fusion pour dire explicitement de quel côté elle a été reprise
  (« valeur conservée du premier parent » / « valeur reprise du second parent »), au niveau de
  chaque feuille — plus précis qu'une note écrite à la main.

Le texte issu du dépôt (titres, intentions, résumés...) est échappé avant insertion dans le
HTML. `render_study_html(repo, ...)` est l'équivalent Python direct ; les briques visuelles
(`fiche_card`, `trial_card`, `resolution_conflict_row`...) sont réutilisables pour composer un
rapport sur mesure — voir `demos/` pour des exemples qui les assemblent à la main plutôt que de
laisser `follow report` tout dériver automatiquement.

## Graphe de filiation

`follow graph` (ou `render_graph_html`/`build_graph_figure` en Python) exporte le graphe complet
en un unique fichier HTML autonome via **Plotly** — pas de Graphviz, pas de binaire système à
installer. La mise en page est une simple disposition en couches (une rangée par génération,
un nœud positionné par la moyenne des positions de ses parents) : suffisante pour lire la
filiation et les embranchements sans dépendre d'un moteur de layout externe. Les nœuds sont
colorés par statut de conclusion (`draft`/`running`/`concluded`/`abandoned`) et chaque pointe de
branche est étiquetée.

## Développer

```bash
uv pip install -e ".[dev]"
pytest
```

## Documentation (Sphinx)

Guide complet, référence de l'API (autodoc à partir des docstrings) et référence CLI dans
`docs/` :

```bash
pip install -e ".[docs]"
sphinx-build -b html docs docs/_build/html   # ou : cd docs && make html
```

Ouvrir `docs/_build/html/index.html`. Le contenu source (`docs/*.rst`) est versionné ; le rendu
HTML (`docs/_build/`) ne l'est pas — il se régénère à la demande.

## Publier une nouvelle version

Le numéro de version vit à un seul endroit : `__version__` dans `follow/__init__.py`
(`pyproject.toml` le lit dynamiquement via `[tool.hatch.version]`). Pour publier :

```bash
# 1. mettre à jour follow/__init__.py : __version__ = "x.y.z"
python -m build            # construit dist/*.whl et dist/*.tar.gz (pip install build)
python -m twine upload dist/*   # vers PyPI, si/quand le paquet y est publié
```

Ce dépôt n'est pas encore publié sur PyPI — `pip install git+https://github.com/DmHoly/Follow.git`
reste la façon d'installer une version précise sans attendre une publication.
