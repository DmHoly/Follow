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

Voir `examples/` pour trois domaines complets : `recipe.py` (recette de gâteau, avec variante
par héritage), `mosfet.py` (MOSFET → FinFET), `solar_cell.py` (composition profonde
module → cellule → jonction PN → couche).

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

`repo.log("main")`, `repo.branch(...)`, `repo.tag(...)` et `render_dot(repo)` (export Graphviz du
graphe de filiation complet) complètent l'API — voir les docstrings de `follow/repository.py` et
`follow/rendering.py`.

## Développer

```bash
uv pip install -e ".[dev]"
pytest
```
