# Revue SOLID de Follow

Revue effectuée sur `302885a`, avec `pytest` au vert (221 tests).
**Chaque bug des parties 1 et 2 a été reproduit par exécution sur le dépôt non modifié**, pas
déduit à la lecture.

> **État :** les 14 bugs des parties 1 et 2 sont **corrigés**, chacun accompagné de tests de
> régression vérifiés en échec sur le code d'avant correction. Restent ouverts les constats
> structurels des parties 3 à 5 (SOLID, duplication, qualité des tests).

Le socle est sain : modèles gelés, refus de commits qui abandonneraient un historique, messages
d'erreur qui expliquent. Ce qui suit, ce sont les endroits où le code *ne dit rien* alors qu'il
devrait crier.

| Catégorie | Nombre |
|---|---|
| Corruption / silence (critique) | 6 |
| Défauts confirmés | 8 |
| SOLID & structure | 7 |
| Duplications | 5 |
| Trous de test | 9 |

---

## Partie 1 — Six façons de perdre des données sans jamais voir d'erreur

### BUG 1 — La référence « baseline » ne bouge jamais du premier commit  ✅ corrigé

`follow/repository.py:395` — `Repository.derive`

`derive` recopie les références du parent, puis n'ajoute une baseline que *si aucune n'est déjà
présente*. Dès la deuxième dérivation, la baseline héritée (qui pointe sur le grand-parent)
satisfait la condition : la nouvelle n'est jamais posée. À la génération *n*, la baseline pointe
toujours sur la racine.

```
# v1 → v2 → v3, chaîne de dérivations ordinaire
v3.baseline pointe sur v2 ?   False   (elle pointe sur v1)
b3.diff_from_baseline()       ~ ingredients.flour: 200 g -> 240 g
                              # le vrai delta vs v2 est 220 → 240
```

**Effet :** `diff_from_baseline()`, la section « Paramètres modifiés par rapport à la référence »
de `render_fiche` et tout le raisonnement « qu'est-ce qui a varié » comparent au mauvais ancêtre.
C'est le cœur de la promesse du projet, et rien ne le signale. Le test existant s'arrête à la
première génération.

**Correctif :** `derive` n'hérite plus des références de lignage du parent (`baseline`,
`merge_source`) et pose systématiquement la baseline vers le parent immédiat — la règle que
`merge` appliquait déjà. Les autres références (`target_spec`, `prior_art`…) restent héritées.
Verrouillé par `test_baseline_follows_the_immediate_parent_across_a_chain_of_derives` et trois
tests voisins.

### BUG 2 — Une étiquette libre réutilisée bloque le commit  ✅ corrigé

`follow/repository.py:577-585` — `Repository._commit`

`Experiment.tags` se présente comme des étiquettes libres (au même titre que `metadata`), mais
chaque entrée est promue en *ref global immuable* du dépôt. Deux expériences ne peuvent donc pas
porter la même étiquette.

```
repo.new(..., tags=["important"]).commit()   → ok
repo.new(..., tags=["important"]).commit()   → FollowError: tag 'important' already
  points at exp_58b0… - tags are immutable; pass force=True
```

**Effet :** le message parle de `repo.tag(...)`, que l'utilisateur n'a jamais appelé. Deux concepts
(étiquette descriptive, ref citable) partagent un champ ; il en faut deux, ou `tags` ne doit plus
créer de refs.

**Correctif :** `_commit` ne promeut plus `Experiment.tags` en refs. Les étiquettes sont des
métadonnées descriptives réutilisables à volonté (comme `metadata`) ; un tag de dépôt se crée
uniquement via `repo.tag()`, qui conserve son immuabilité. Le test qui verrouillait l'ancien
comportement (`test_tags_passed_at_commit_time_are_applied`) a été remplacé par trois tests du
nouveau contrat.

### BUG 3 — Un nom de facteur mal orthographié produit un plan sans aucune variation  ✅ corrigé

`follow/design.py:75, 86, 117, 219` — `model_copy(update=…)`

`model_copy(update=…)` ne valide rien : ni l'existence du champ, ni son type. `Structure` a
pourtant `extra="forbid"` — contourné. Le module existe précisément pour éviter « un split
idiot », et voici ce qu'il accepte :

```
# le champ s'appelle implant_dose
sweep(ref, "implant_does", lin(2, 10, 3, unit="u"))
  → 3 variantes, toutes identiques        aucune erreur
check_identifiability(v, ["implant_does"]) → []   # « tout va bien »

full_factorial(ref, implant_dose=[2.0, 4.0])   # float au lieu de Quantity
  → accepté, committé, puis au rechargement : ValidationError
```

**Effet :** le garde-fou confirme un plan vide, et le second cas écrit dans le dépôt un JSON que
`load_structure` ne saura plus relire.

**Correctif :** les quatre constructeurs passent par un helper `_variant` qui vérifie le nom du
champ contre `model_fields` puis revalide via `model_validate` — un nom inconnu lève un
`ValueError` listant les champs disponibles, un type incorrect lève à la construction et non au
rechargement. `check_identifiability` valide aussi ses noms de facteurs, plutôt que de répondre
« rien n'est confondu » à propos d'un facteur qu'elle n'a jamais regardé. Neuf tests de
régression.

### BUG 4 — XSS depuis le titre d'une expérience, via `follow explode`  ✅ corrigé

`follow/report.py:605` (`render_page`) · `follow/cli.py:345-353`

`render_page` interpole `title`, `description`, `eyebrow`, `heading` et `subtitle` sans `_esc`.
Ce serait défendable si seuls des littéraux y passaient — mais `cmd_explode` y injecte
`experiment.title`, c'est-à-dire de la donnée du dépôt.

```
title = 'Lot <img src=x onerror=alert(1)>'
$ follow explode <id> wafers --out page.html
balise brute présente dans la page : True
```

**Effet :** `test_report.py::test_untrusted_text_is_html_escaped` valide `render_study_html` et
laisse croire que le sujet est traité ; le chemin `explode` n'est couvert par aucun test
d'échappement. Même famille : `report.py:475,504` émettent `href="{source}"` sans filtrer le
schéma — `javascript:alert(…)` passe (`_esc` échappe les guillemets, pas l'URI).

**Correctif :** `render_page` échappe désormais `title` et `description`, dont les emplacements
(`<title>`, attribut `content`) n'admettent jamais de balisage. `eyebrow`/`heading`/`subtitle`
gardent leur contrat HTML brut — les démos y composent volontairement du `<code>` — mais le
contrat est explicite dans la docstring et `cmd_explode` échappe désormais le titre
d'expérience qu'il y injecte, via le nouveau nom public `report.escape_html`. Les liens de
preuve passent par `_evidence_link`, qui refuse les schémas `javascript:`/`data:`/`vbscript:`
(reconnus même coupés par des caractères de contrôle) et affiche alors la preuve en texte
plutôt que de la masquer. Six tests de régression, dont deux bout-en-bout sur la CLI.

### BUG 5 — `follow graph` plante sur un dépôt profond, une fois sur deux  ✅ corrigé

`follow/graphing.py:20` — `_depths`

`_depths` est récursif et mémoïsé au fil de l'itération. Si le dict est parcouru des racines vers
les feuilles, la pile reste plate ; dans l'ordre inverse, elle atteint la longueur de la lignée.
Or l'ordre vient de `objects_dir.glob("*.json")` au chargement : il n'est pas garanti.

```
# exactement le même DAG, seul l'ordre du dict change
ordre racine→feuille  ok, profondeur max = 1999
ordre feuille→racine  RecursionError

# et un cycle ne remonte pas, il fausse les profondeurs :
_depths({"a": ["b"], "b": ["a"]}) → {'a': 2, 'b': 1}
```

**Effet :** un carnet de labo à quelques milliers de commits casse `follow graph` de façon
irreproductible. Dans `follow report`, le `except Exception` de `report.py:856` avale l'erreur :
le graphe disparaît de la page sans un mot. Un parcours itératif (tri topologique) règle les deux.

**Correctif :** `_depths` procède par parcours topologique (Kahn) au lieu de la récursion — la
pile ne dépend plus ni de la profondeur du lignage ni de l'ordre du dict. Vérifié identique à
l'ancien algorithme sur 200 DAG aléatoires (forks et merges compris) et tenu sur 20 000 commits
dans l'ordre défavorable. Un cycle lève désormais un `FollowError` nommant les commits impliqués,
au lieu de produire des profondeurs fausses ; et le `except Exception` de `render_study_html` a
été resserré pour laisser passer cette erreur de données tout en continuant d'absorber un simple
échec de rendu Plotly. Huit tests de régression.

### BUG 6 — `branch()` autorise ce que `commit()` refuse  ✅ corrigé

`follow/repository.py:492` — `Repository.branch`

`_commit` refuse longuement de faire avancer une branche vers un commit qui abandonnerait sa
pointe, et `tag()` exige `force=True` pour repointer. `branch()` n'a aucune de ces gardes : il
écrit le pointeur.

```
main → a1 → a2
repo.branch("main", a1.id)          # aucun avertissement
log("main") == [a1]                 a2 devient injoignable
```

**Effet :** la protection soigneusement écrite au commit se contourne par l'API publique voisine.
Trois portes vers le même invariant, deux gardées.

**Correctif :** `branch()` refuse de déplacer une branche existante vers un commit dont sa pointe
actuelle ne descend pas, avec un message qui nomme le commit menacé et rappelle comment le
préserver. Créer une branche et l'avancer en *fast-forward* restent libres — y compris à travers
le second parent d'un merge, reconnu comme de la vraie filiation. `force=True` (et
`follow branch --force`, ajouté par symétrie avec `follow tag --force`) est l'échappatoire
explicite. Cinq tests de régression, plus un bout-en-bout sur la CLI.

---

## Partie 2 — Huit comportements qui mentent un peu

### BUG 7 — `"main" in repo` est vrai alors que `repo.get("main")` plante  ✅ corrigé

`follow/repository.py:234` & `:241` — `__contains__` / `_resolve_ref`

`_resolve_ref` renvoie l'id trouvé dans `_branches` sans vérifier qu'il existe dans `_objects`.
Un `refs.json` désynchronisé (objet supprimé, écriture interrompue, copie partielle) donne :

```
"main" in repo   → True
repo.get("main") → KeyError: 'exp_196855fff4faa85a'
                   # attendu : ExperimentNotFoundError
```

**Effet :** l'exception typée du projet est court-circuitée, donc les `except FollowError` de la
CLI laissent passer une traceback nue. À corriger dans `_resolve_ref` (et valider la cohérence au
chargement).

**Correctif :** `_resolve_ref` ne renvoie un id qu'après avoir vérifié qu'il est réellement
stocké, et lève sinon un `DanglingRefError` — sous-classe d'`ExperimentNotFoundError`, pour que
les appelants existants continuent de fonctionner et que `ref in repo` réponde `False`, en accord
avec ce que `get()` fera. Le message distingue « nom inconnu » de « dépôt incohérent », deux
situations qui appellent des réparations opposées, et nomme la ref, le commit manquant et la
sortie de secours. Même traitement pour `log()` (parent absent) et pour la pointe de branche lue
par `_commit`. Six tests de régression.

### BUG 8 — Les ids ne sont pas adressés par contenu, malgré la docstring  ✅ corrigé

`follow/ids.py:13` · `follow/repository.py:574`

`content_id` promet « deux objets de même contenu ont le même id […] ce qui permet au store de
dédupliquer les expériences identiques comme git dédupliquerait ». Or le payload haché inclut
`created_at`, généré à l'instant présent.

```
deux commits au contenu strictement identique
  → même id ? False
  exp_a3e19ff93f98d630 / exp_0b038151c211a248
```

**Effet :** la déduplication annoncée n'existe pas.

**Correctif :** `created_at` est exclu du payload haché — exactement comme la comparaison de
`NothingToCommitError` le faisait déjà. Deux dépôts distincts produisent maintenant le même id
pour le même contenu, et un id déjà présent dans le store fait gagner l'objet existant (règle de
déduplication de git) plutôt que d'en réécrire le `created_at`.

> **À savoir :** `conclude()` horodate `decided_at`, qui est du contenu légitime — quand la
> décision a été prise. Une expérience conclue sans fixer ce champ garde donc un id dépendant de
> l'horloge : les démos restent non reproductibles pour cette raison, plus à cause du hachage.
 Deux sorties possibles : exclure `created_at`
du hachage (et assumer la vraie adresse par contenu), ou corriger la docstring — mais pas laisser
la promesse.

### BUG 9 — `add_step()` fabrique lui-même des collisions d'ordre  ✅ corrigé

`follow/repository.py:96`

L'ordre auto vaut `len(self.steps) + 1`, ce qui ignore les ordres déjà attribués. Le validateur
`_check_steps_are_well_formed` attrape bien le problème — mais seulement au commit, longtemps
après.

```
builder.add_step(name="A", order=2)
builder.add_step(name="B")          # order = len+1 = 2
orders = [2, 2]
builder.commit() → ValidationError  # très tard
```

**Effet :** `max(orders, default=0) + 1` supprime le piège à la source.

**Correctif :** appliqué — l'ordre auto vaut désormais `max(orders, default=0) + 1`, donc
`add_step(order=2)` suivi d'un `add_step()` nu donne 2 puis 3, sans attendre le commit.


### BUG 10 — `analyze_batch` ne voit que les champs de la première entité  ✅ corrigé

`follow/batch.py:88` — `_leaf_paths(dumps[0], …)`

La docstring promet qu'une liste hétérogène lève « un simple `KeyError` ». C'est vrai dans un sens
seulement : si l'entité 1 a *plus* de champs. Dans l'autre sens, les champs supplémentaires des
entités 2..N sont ignorés sans un mot.

```
analyze_batch([{"x": 1}, {"x": 1, "extra": 999}])
→ constant={'x': 1}, varying=[]     "extra" disparaît du plan
```

**Effet :** un facteur réel absent du rapport DOE. Il faut l'union des chemins, pas ceux du
premier élément.

**Correctif :** les chemins sont l'union de ceux de toutes les entités, dans l'ordre de première
apparition. L'hétérogénéité est signalée quelle que soit l'entité qui porte le champ en trop, par
un `BatchShapeError` qui nomme l'entité et le chemin au lieu d'un `KeyError` nu.

### BUG 11 — Deux formatages de `Quantity`, et ils divergent  ✅ corrigé

`follow/quantity.py:24` (`__str__`) · `follow/formatting.py:21` (`format_value`)

```
str(q)         → 200 g ± 5.0
format_value() → 200 g ± 5.0 (a froid)
```

**Effet :** dans une même fiche Markdown, la structure (via `format_value`) affiche la note et les
paramètres d'étape / métriques de preuve (via `{quantity}`, `rendering.py:104,137`) la perdent.
`__str__` devrait déléguer.

**Correctif :** `Quantity.__str__` délègue à `format_value`. Un seul rendu, donc plus de
divergence possible — la note apparaît partout ou nulle part.


### BUG 12 — `except FollowError` ne rattrape pas les erreurs de formulaire  ✅ corrigé

`follow/commit_form.py:22`

`FollowError` est documentée « classe de base des erreurs de Follow ». `FormValidationError` hérite
de `ValueError` seul — `issubclass(FormValidationError, FollowError)` vaut `False`. Une application
qui enveloppe `commit()` dans `except FollowError` laisse remonter le cas le plus attendu.

**Symptôme visible :** `cli.py:270` doit écrire
`except (FollowError, ValueError, KeyError, IndexError, TypeError)`. Quand un appelant doit
énumérer cinq types pour un appel, c'est la hiérarchie qui manque : `Structure.resolve` lève
`KeyError`, `merge` `ValueError`, `split_path` `ValueError`, chacun hors de l'arbre `FollowError`.

**Correctif :** toutes les erreurs vivent dans un nouveau module `follow/errors.py`, sous
`FollowError` : `StructureTypeError`, `MergeError`, `MalformedPathError`, `PathNotFoundError`,
`BatchShapeError`, `DesignError`, `FormValidationError`. Chacune conserve le builtin qu'elle
était (`ValueError`/`KeyError`), donc le code existant qui les attrape continue de fonctionner.
Le symptôme disparaît : `cli.py` écrit maintenant `except FollowError` partout au lieu d'énumérer
cinq types pour un appel. Les `ValueError` levés dans les validateurs pydantic sont laissés tels
quels — pydantic exige ce type et les enveloppe lui-même en `ValidationError`.


### BUG 13 — Les étapes sont diffées et fusionnées par index  ✅ corrigé

`follow/diffing.py:63` · `repo.diff_steps` / `take_steps`

`_walk` aligne les listes positionnellement. Insérer une étape en tête d'un protocole décale tout :
le diff annonce que chaque étape a changé, et `--take-steps "[2]"` importe l'étape voisine de la
bonne, silencieusement. `Step.order` existe pourtant et serait la clé d'alignement naturelle.

**Effet :** la résolution de conflit — l'argument de vente du `merge` — n'est fiable que si les
deux branches n'ont ni ajouté ni supprimé d'étape.

**Correctif :** les protocoles sont comparés et fusionnés indexés par `Step.order`, pas par
position. Un chemin se lit désormais `3.parameters.temperature` : le 3 est le numéro d'étape
qu'affiche la fiche. Supprimer une étape au milieu d'une branche donne
`{'2': 'removed', '3.parameters.temperature': 'changed'}`, là où la comparaison positionnelle
annonçait que « Reposer » était devenu « Cuire » et que « Cuire » avait disparu.

> **Changement d'interface :** les chemins de `follow diff --steps` et `--take-steps` changent de
> forme (`"[2]"` → `"3"`). Démos, tests, README et docs ont été migrés ; un chemin devenu invalide
> lève un `PathNotFoundError` explicite plutôt que de désigner l'étape voisine.
>
> **Limite :** `order` n'identifie une étape que tant qu'on ne renumérote pas. Une branche qui
> insère une étape *en décalant* les numéros suivants change l'identité de chaque étape, et le
> diff le reflète — aucun alignement ne peut deviner l'intention derrière une renumérotation.


### BUG 14 — Écritures non atomiques, aucun verrou  ✅ corrigé (atomicité)

`follow/repository.py:592-600` — `_persist_experiment` / `_persist_refs`

`write_text` direct sur `refs.json`. Une interruption au mauvais moment laisse un fichier tronqué —
et c'est exactement l'état qui déclenche le BUG 7. Deux processus `follow commit` concurrents
écrasent leurs refs mutuellement, sans détection.

**Correctif standard :** écrire dans un temporaire du même répertoire puis `os.replace`. Pour un
outil qui se réclame de git, l'atomicité fait partie du contrat implicite.

**Correctif :** toutes les écritures du dépôt passent par `_write_atomic` : fichier temporaire
dans le même répertoire, `fsync`, puis `os.replace` — atomique sous POSIX comme sous Windows. Une
coupure en cours d'écriture laisse l'ancien fichier intact au lieu d'un JSON tronqué, et le
temporaire est nettoyé même sur `KeyboardInterrupt`. Vérifié en coupant réellement l'écriture à
mi-parcours : avant, `refs.json` ne parsait plus du tout ; après, il est inchangé. L'encodage est
désormais explicite (`utf-8`) sur toute la chaîne de persistance — dépôt, brouillons CLI,
formulaire de commit — car `ensure_ascii=False` combiné à un `write_text` sans encodage cassait
sur un titre accentué avec une locale non-UTF-8. Trois tests de régression.

> **Limite subsistante :** l'atomicité garantit qu'aucun fichier n'est illisible ; ce n'est pas un
> verrou. Deux processus qui committent simultanément écrasent toujours leurs refs mutuelles,
> chacun écrivant une vue mémoire lue avant l'écriture de l'autre. Le résoudre demande de relire
> `refs.json` sous verrou avant d'écrire — un changement d'une autre ampleur, non entrepris ici.

---

## Partie 3 — SOLID : là où la structure force la main

Rien ici ne casse aujourd'hui. Ce sont les endroits qui rendront les corrections ci-dessus plus
coûteuses qu'elles ne devraient l'être.

| Principe | Où | Constat |
|---|---|---|
| SRP | `repository.py`, 612 lignes | `Repository` est à la fois le magasin d'objets, la table des refs, les règles métier du commit, le backend JSON, le moteur de diff/merge et l'index d'entités. Toute évolution (base SQLite, dépôt distant, cache) touche la même classe. |
| SRP | `report.py`, 877 lignes | 170 lignes de CSS, une douzaine de composants HTML, et la logique métier d'attribution d'un merge (`_merge_attribution_html`) dans un seul module. |
| OCP / DIP | `repository.py:597` | Aucune abstraction de stockage : `if self.path is not None` disséminé dans les méthodes d'écriture. Un `ObjectStore` (mémoire / fichiers) rendrait la persistance remplaçable et testable isolément. |
| DIP | `structure.py:5` | `_REGISTRY` est un singleton global alimenté par `__init_subclass__`. Non injectable, redéfinir une classe écrase l'entrée en silence, et l'état fuit entre les tests. |
| Encapsulation | `repository.py:131` | `builder.commit()` appelle `self.repo._commit(self)`, qui lit ensuite les 15 attributs du builder. Feature Envy dans les deux sens, plus une référence circulaire builder ↔ repository qui empêche de construire un builder sans dépôt. |
| ISP | `repository.py:87-102` | `add_objective`, `add_reference`, `add_step`, `add_evidence` : quatre méthodes `(**kwargs: Any)` identiques au nom du modèle près. Aucune complétion, aucun typage, et la seule validation arrive au commit. |
| Moindre surprise | `report.py:219` / `:517` | Deux conventions d'échappement opposées dans la même API publique : `fiche_card`/`trial_card` traitent tout comme du HTML, `experiment_fiche` échappe lui-même, `batch_table` fait moitié-moitié. Documenté, mais c'est exactement ainsi que naît le BUG 4. |

### Deux dépendances à démêler

- **Cycle `cli` ↔ `menu`.** `menu.py:35` importe quatre fonctions *privées* de `cli` (`_repo`,
  `_load_structure_class`, `_read_structure_payload`, `_print_form_hint`) ; `cli.cmd_menu` importe
  `menu` en différé pour casser la boucle. Ces quatre fonctions n'ont rien de spécifique à la
  CLI — elles appartiennent à un module partagé.
- **`SystemExit` levé hors de la couche CLI.** `_load_structure_class` et
  `_read_structure_payload` lèvent `SystemExit` ; `run_menu` doit donc l'attraper
  (`menu.py:377`) pour ne pas tuer la session. Une décision d'interface utilisateur prise dans une
  fonction utilitaire.

---

## Partie 4 — Cinq choses écrites plusieurs fois

Comptées, pas estimées.

| Ce qui est dupliqué | Copies | Où |
|---|---|---|
| Bloc Plotly + habillage `.graph-frame` | 6 | Les 5 démos + `report.py:839`. Identique jusqu'à `modeBarButtonsToRemove`. Devrait être `graph_section(repo, embed=…)` dans `follow.presentation.report`. |
| `main()` de démo (argparse, mkdir, write, print) | 6 | `demos/*.py` — copie mot pour mot, seul le chemin par défaut change. |
| Format de ligne de log | 3 | `rendering.render_log:160`, `cli.cmd_log:199`, `cli.cmd_trace:226`. Et `cli.py:25` importe `render_log`… sans l'utiliser. |
| Fiche d'expérience, deux implémentations | 2 | `rendering.render_fiche` (Markdown) et `report.experiment_fiche` (HTML) redisent la même structure de document — et ont déjà divergé : le diff vs baseline n'existe qu'en Markdown, l'attribution de merge qu'en HTML. |
| `_utcnow()` | 2 | `models.py:11` et `repository.py:17`, à l'identique. |

### Implémentations fragiles à surveiller

- **Chirurgie de chaîne sur du HTML** — `report.py:772` :
  `card[: -len("\n    </div>")] + lineage + "\n    </div>"`. Dépend du suffixe exact produit par
  `experiment_fiche` ; le jour où ce dernier change son indentation, la page se corrompt sans
  erreur. Un paramètre `extra_rows=` coûte trois lignes.
- **Exceptions avalées** — `report.py:856` (`except Exception`, le graphe disparaît),
  `report.py:690` et `rendering.py:89` (`except KeyError: pass`). Aucune trace, aucun
  avertissement.
- **Code mort** — `graphing.py:53` : paramètre `_d` jamais lu ; `graphing.py:100-107` : branche
  `if exp else` inatteignable (le DAG est construit à partir des mêmes objets) ; `cli.py:482` :
  `-n` par défaut à `10**9`.
- **`follow init` est décoratif** — `Repository(path)` crée les répertoires à la première
  écriture ; la commande ne fait qu'ajouter une vérification de répertoire vide que rien d'autre
  ne fait respecter.
- **Messages moitié français, moitié anglais** — `models.py` et `repository.py` en anglais,
  `commit_form.py`, `cli.py` et `design.py` en français. La même session en affiche des deux.

---

## Partie 5 — 221 tests verts, et pourtant

La suite est sérieuse — `test_misuse.py` en particulier teste de vrais scénarios d'erreur, pas des
accesseurs. Le problème est ailleurs : ce qu'elle affirme couvrir et ce qu'elle vérifie réellement
ne coïncident pas toujours.

### TEST 1 — Une assertion garantie par le typage  ✅ corrigé

`tests/test_multi_domain_coexistence.py:166`

```python
kinds = {e.kind for e in diff}
assert kinds <= {"added", "removed", "changed"}
```

`DiffEntry.kind` est un `Literal["added","removed","changed"]` : Pydantic rejette toute autre
valeur à la construction. L'assertion ne peut pas échouer, quel que soit le bug introduit dans
`_walk`.

### TEST 2 — `test_commit_computes_a_stable_content_id`  ✅ corrigé : titre ≠ contenu

`tests/test_repository.py:15`

```python
assert baseline.id.startswith("exp_")
assert baseline.parents == []
assert repo.get("main").id == baseline.id
```

Ni stabilité, ni adressage par contenu : aucune de ces trois lignes ne change si l'id devient un
UUID aléatoire. C'est précisément l'angle mort qui laisse passer le BUG 8 — un test nommé d'après
une propriété que personne ne vérifie donne l'illusion qu'elle l'est.

### TEST 3 — « HTML bien formé » = compter les `<div>`  ✅ corrigé (6 occurrences)

`test_report.py:104`, `test_demo_*.py` (×4), `test_multi_domain:187`

```python
assert html.count("<div") == html.count("</div>")
```

Un compte égal ne dit rien de l'imbrication, des attributs, ni de l'échappement — la page du BUG 4
passe ce test sans broncher. Voisins de la même famille : `assert "<style>" in html`
(`test_cli.py:501`) et `assert out.exists()` placé *après* `out.read_text()`
(`test_graphing.py:45`), qui aurait déjà levé.

### TEST 4 — Six comportements que rien ne couvre  ✅ corrigé

Une seule génération de `derive` est testée → **BUG 1**. `Repository.branch()` n'a aucun test de
repointage → **BUG 6**. Aucun test de dépôt corrompu (refs orphelines, JSON tronqué) → **BUG 7**.
Aucun test d'échappement sur `render_page` ni sur le chemin `explode` → **BUG 4**. Aucun test de
nom de facteur invalide dans `design` → **BUG 3**. `render_graph_html(embed=False)` (la branche
CDN) n'est jamais exercée.

### TEST 5 — Deux frictions structurelles  ⚠️ une corrigée, une infirmée

**Le harnais du menu est positionnel.** `tests/test_menu.py:40` remplace chaque prompt
`questionary` par une file de réponses consommée dans l'ordre d'appel. Insérer une question au
milieu d'une action décale toutes les réponses des tests suivants : ils échouent avec « action
asked for more answers than the test scripted », sans indiquer laquelle.

**Les tests de démo reconstruisent tout.** Chacun appelle `build_repository()` — jusqu'à 11
commits, avec plans factoriels et hypercubes latins — soit 5 à 8 reconstructions complètes par
fichier, là où une fixture `scope="module"` suffirait.

**Et le fond :** les tests de démo verrouillent des constantes narratives (`len(repo) == 11`,
l'ensemble exact des branches). Enrichir une démo casse un test sans qu'aucun comportement de la
bibliothèque n'ait changé.

**Correctif (le harnais) :** la file reste positionnelle — c'est la nature d'un scénario de
wizard — mais l'échec la rend lisible. Au lieu de « asked for more answers than the test
scripted », le message nomme le prompt qui a manqué et rejoue tout ce qui a été répondu avant :

```
the action asked for an answer the test did not script: confirm('Conclure maintenant ?').
Already answered, in order:
  1. text('Branche :') -> 'main'
  ...
  8. confirm('Ajouter une preuve ?') -> False
```

Une question insérée au milieu d'une action pointe désormais sur elle-même, plus sur la fin de
la file.

**Constat infirmé (le coût) :** la mesure ne soutient pas le reproche. Les 17 tests de démo
s'exécutent en 0,5 s au total, reconstructions comprises ; une fixture `scope="module"`
partagerait un `Repository` mutable entre tests pour un gain non mesurable. Rien changé, à
dessein.

**Constat infirmé (les constantes narratives) :** reprocher à `len(repo) == 11` d'être coûteux à
maintenir était théorique. Les démos ont depuis été modifiées deux fois — chemins `--take-steps`,
extraction de `graph_section()` — sans qu'une seule de ces assertions ne casse à tort. Elles sont
bon marché et attrapent les vraies régressions de démo : conservées.


---

## Partie 6 — Par où commencer

Classé par (dégât silencieux causé) ÷ (effort). Les quatre premiers se corrigent en quelques
lignes chacun et ferment les trous de test correspondants.

| # | Action | Réfs |
|---|---|---|
| ✅ 1 | Poser la baseline sur le parent réel dans `derive`, et tester trois générations. | BUG 1 |
| ✅ 2 | Valider les `update` de `design` contre `model_fields`, puis revalider le modèle. | BUG 3 |
| ✅ 3 | Échapper dans `render_page`, filtrer les schémas d'URI des preuves, ajouter le test `explode`. | BUG 4 |
| ✅ 4 | Séparer étiquettes et refs : `tags` ne crée plus de tag de dépôt. | BUG 2 |
| ✅ 5 | Rendre `_depths` itératif ; écritures atomiques via `os.replace`. | BUG 5, 14 |
| ✅ 6 | Vérifier l'existence de l'objet dans `_resolve_ref` ; aligner `branch()` sur les gardes de `commit()`. | BUG 6, 7 |
| ✅ 7 | Faire hériter toutes les erreurs de `FollowError`, puis simplifier les `except` de la CLI. | BUG 12 |
| 8 | Extraire `graph_section()` et un `demo_main()` partagé ; supprimer les 12 copies. | DRY |
| 9 | Extraire un `ObjectStore` derrière `Repository` — la condition pour que tout le reste devienne testable isolément. | SRP, DIP |
