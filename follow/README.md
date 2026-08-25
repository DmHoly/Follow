# Organisation de `follow/`

Le paquet est rangé par **rôle** plutôt qu'en vrac : chaque sous-dossier regroupe les modules qui
répondent à une même question (modéliser, lire/écrire un chemin, générer un plan, persister,
afficher, piloter). L'ordre ci-dessous suit aussi l'ordre des dépendances : un dossier n'importe
que les dossiers qui le précèdent dans cette liste (jamais l'inverse) — `core` ne dépend de rien
d'autre dans `follow/`, `interfaces` peut dépendre de tout le reste.

```
follow/
├── __init__.py            API publique du paquet (tout ce qui est ré-exporté par `import follow`)
├── core/                   Modèle de domaine — la base, sans dépendance interne
│   ├── structure.py         classe Structure (à sous-classer) + registre des types
│   ├── quantity.py           Quantity (valeur + unité + incertitude)
│   ├── models.py              Experiment, Step, Evidence, Objective, Conclusion, ReferenceLink...
│   ├── ids.py                  id de contenu (hash) des expériences
│   └── errors.py                hiérarchie complète des exceptions, sous FollowError
├── paths/                  Utilitaires génériques sur une Structure déjà instanciée
│   ├── formatting.py         affichage d'une valeur/quantité pour l'humain
│   ├── merging.py              chemins pointés ("a.b[2].c") : parser/résoudre/fusionner
│   ├── diffing.py               diff structurel entre deux Structure
│   └── entities.py              retrouver un `entity_id` dans une Structure dumpée
├── doe/                    Design of experiments : générer et analyser des variantes
│   ├── design.py             générateurs de plan (sweep, factoriel complet/fractionnaire, LHS...)
│   └── batch.py                analyse d'un lot déjà construit (constant vs. variable)
├── storage/                Persistance
│   ├── backends.py           contrat ObjectStore + implémentations (MemoryStore, JsonFileStore)
│   ├── commit_form.py          questionnaire YAML exigé à la validation d'un commit
│   └── repository.py            Repository / ExperimentBuilder — commits, branches, tags, merge
├── presentation/           Mise en forme d'une sortie pour l'humain
│   ├── rendering.py           rendu texte (fiche, log)
│   ├── report.py                blocs HTML réutilisables + rapport d'étude complet
│   └── graphing.py               graphe de filiation (Plotly)
├── interfaces/             Points d'entrée utilisateur
│   ├── cli.py                 `follow` — sous-commandes scriptables (new/commit/merge/report...)
│   └── menu.py                  `follow menu` — même moteur, façade interactive (questionary)
└── api/                    Serveur web (FastAPI + GUI statique) — voir `follow/api/README.md`
```

## Pourquoi ce découpage

Avant cette réorganisation, les ~20 modules vivaient à plat dans `follow/`, sans indication de
ce qui dépendait de quoi. Le découpage ci-dessus rend explicite une hiérarchie qui existait déjà
implicitement dans le code :

- **`core`** ne connaît que lui-même : c'est le vocabulaire (`Structure`, `Quantity`, les modèles
  Pydantic, les erreurs) que tout le reste du paquet partage.
- **`paths`** et **`doe`** opèrent sur ce vocabulaire (un chemin, un plan, un diff) sans jamais
  savoir qu'un `Repository` existe.
- **`storage`** est la première couche qui persiste quelque chose ; elle s'appuie sur `core` et
  `paths` (diff, entités, chemins de merge).
- **`presentation`** transforme un `Repository` (ou une `Experiment`) en texte/HTML/graphe ; elle
  ne référence `storage.repository` que pour l'annotation de type (`TYPE_CHECKING`), jamais pour
  écrire dedans.
- **`interfaces`** est la seule couche qui a le droit de tout importer : c'est la façade
  utilisateur (CLI scriptable et menu interactif), pas une brique réutilisable par le reste du
  paquet.
- **`api/`** existait déjà comme sous-paquet séparé (serveur HTTP + GUI statique) ; il n'a pas été
  déplacé, seuls ses imports internes ont été mis à jour pour suivre le reste.

## Retrouver un symbole après la réorganisation

Les noms de fichiers n'ont pas changé (à une exception : `storage.py` → `storage/backends.py`,
pour éviter la répétition `follow.storage.storage`). Seul le chemin d'import a changé, en
préfixant le nom du dossier :

| Avant                        | Après                                  |
|-------------------------------|-----------------------------------------|
| `from follow.structure import ...` | `from follow.core.structure import ...` |
| `from follow.repository import ...` | `from follow.storage.repository import ...` |
| `from follow.design import ...`     | `from follow.doe.design import ...` |
| `from follow.report import ...`     | `from follow.presentation.report import ...` |
| `from follow.cli import ...`        | `from follow.interfaces.cli import ...` |
| ... | (même logique pour chaque module : voir le tableau ci-dessus) |

L'API publique (`from follow import Structure, Repository, Quantity, ...`) est inchangée — elle
continue d'être ré-exportée depuis `follow/__init__.py`, quel que soit le sous-dossier réel du
module.
