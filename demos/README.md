# Démos

Scénarios complets, bout en bout, construits avec la bibliothèque Follow (pas juste des
extraits de doc) et rendus en pages HTML autonomes. Chaque script est indépendant et régénère
son propre dépôt en mémoire à chaque exécution — rien n'est persisté, rien n'est inventé : les
identifiants, diffs et fiches qui apparaissent dans le HTML sont ceux produits par une vraie
exécution de `follow`.

- `_report.py` — le thème visuel partagé (jetons de couleur, typographie, composants HTML tels
  que `.trial-card`, `.resolution-list`, `.fiche-card`) réutilisé par toutes les démos, pour
  qu'elles se lisent comme un seul produit plutôt qu'une page ad hoc à chaque fois.
- `fusion_selective.py` — une recette de gâteau à 5 étapes, une branche de test qui explore la
  cuisson (étape 3) sur 3 commits, une évolution indépendante sur `main` en parallèle, puis
  `repo.merge(...)` qui ne rapatrie que l'étape validée : la résolution de conflit chemin par
  chemin illustrée de bout en bout.
- `chocolate_fondant.py` — optimisation d'une recette de fondant au chocolat cœur coulant à
  partir de 10 recettes réelles trouvées en ligne, synthétisées en une recette de référence puis
  affinées par plusieurs expériences ciblées (voir le fichier pour le détail et les sources).

Régénérer une démo :

```bash
python -m demos.fusion_selective          # écrit demos/output/fusion_selective.html (CDN Plotly, léger)
python -m demos.fusion_selective --embed  # variante 100% hors-ligne (~4.8 Mo, plotly.js inclus)
```

Les fichiers `demos/output/*.html` sont des instantanés statiques commités pour consultation
directe (double-clic, aucune installation) ; ils utilisent le CDN Plotly et nécessitent donc une
connexion pour afficher le graphe interactif. Relancez les scripts si vous modifiez la
bibliothèque et voulez rafraîchir les instantanés.
