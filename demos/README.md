# Démos

Scénarios complets, bout en bout, construits avec la bibliothèque Follow (pas juste des
extraits de doc) et rendus en pages HTML autonomes. Chaque script est indépendant et régénère
son propre dépôt en mémoire à chaque exécution — rien n'est persisté, rien n'est inventé : les
identifiants, diffs et fiches qui apparaissent dans le HTML sont ceux produits par une vraie
exécution de `follow`.

Ces scripts assemblent leurs sections **à la main** (narration, cartes d'essai choisies,
libellés) pour montrer ce qui est possible avec un peu de mise en récit. Pour un rapport généré
**automatiquement**, sans rien écrire, voir `follow report` (section dédiée dans le README
principal) et `follow.render_study_html` — qui utilisent le même thème visuel.

- `_report.py` — ré-export de `follow.report` (le thème visuel et les briques HTML vivent
  désormais dans la bibliothèque elle-même, voir plus haut) pour que ces démos et `follow
  report` se lisent comme un seul produit plutôt que des pages ad hoc.
- `fusion_selective.py` — une recette de gâteau à 5 étapes, une branche de test qui explore la
  cuisson (étape 3) sur 3 commits, une évolution indépendante sur `main` en parallèle, puis
  `repo.merge(...)` qui ne rapatrie que l'étape validée : la résolution de conflit chemin par
  chemin illustrée de bout en bout.
- `chocolate_fondant.py` — optimisation d'une recette de fondant au chocolat cœur coulant à
  partir de 10 recettes réelles trouvées en ligne, synthétisées en une recette de référence puis
  affinées par plusieurs expériences ciblées (voir le fichier pour le détail et les sources).
- `auto_report.py` — le même dépôt que `chocolate_fondant.py`, rendu par `render_study_html`
  sans aucune section écrite à la main : comparez `chocolate_fondant.html` et
  `chocolate_fondant_auto_report.html` dans `output/` pour voir la différence entre un rapport
  automatique et une démo narrée.
- `wafer_doe.py` — un plan factoriel 5×5 (dose d'implantation × température de recuit) sur 25
  wafers, modélisé comme une seule expérience Follow, suivi d'un lot de confirmation homogène :
  l'affichage hybride (fiche + vue explosée par entité, `follow.batch.analyze_batch` +
  `follow.report.batch_table`) et `follow.design.full_factorial` pour générer le split.
- `chocolate_cake_optimization.py` — le guide complet en un seul dépôt exécutable : déclarer une
  expérience (intention, structure, référence, objectifs), un split manuel (`sweep`), un split
  raté puis corrigé (`check_identifiability`, `full_factorial`), un plan fractionnaire
  (`fractional_factorial` + structure d'aliasing), un screening (`latin_hypercube`), une fusion
  de deux améliorations validées séparément (`repo.merge`), un formulaire de commit obligatoire
  (`follow.commit_form`), et une validation finale. Voir `docs/tutorial.rst` pour le même
  scénario narré étape par étape.

Régénérer une démo :

```bash
python -m demos.fusion_selective          # écrit demos/output/fusion_selective.html (CDN Plotly, léger)
python -m demos.fusion_selective --embed  # variante 100% hors-ligne (~4.8 Mo, plotly.js inclus)
```

Les fichiers `demos/output/*.html` sont des instantanés statiques commités pour consultation
directe (double-clic, aucune installation) ; ils utilisent le CDN Plotly et nécessitent donc une
connexion pour afficher le graphe interactif. Relancez les scripts si vous modifiez la
bibliothèque et voulez rafraîchir les instantanés.
