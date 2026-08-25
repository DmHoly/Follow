# Follow API + GUI

Expose une `Repository` Follow existante en REST (FastAPI), avec une application web
multipage servie par le même processus pour créer/consulter/conclure des expériences sans
passer par le CLI.

## Démarrer / arrêter

```bash
pip install "follow[api]"

follow_api start --repo .follow --port 8000
#   Accueil        : http://127.0.0.1:8000/
#   Application    : http://127.0.0.1:8000/app
#   Documentation  : http://127.0.0.1:8000/docs

follow_api status
follow_api stop
```

Un seul serveur est suivi à la fois (pidfile + métadonnées sous `~/.follow/api/`) : `start`
échoue si un serveur tourne déjà, `stop`/`status` n'ont besoin d'aucun argument.

Un type de `Structure` déjà utilisé par une expérience du dépôt est importé automatiquement au
démarrage. Pour qu'un type **encore jamais committé** apparaisse dans le formulaire "nouvelle
expérience", listez son module avec `--structures` :

```bash
follow_api start --repo .follow --structures examples.recipe --structures examples.wafer_doe
```

## Pages

- `/` — page d'accueil sobre (présentation, liens vers l'app/la doc/les exemples).
- `/app` — l'application : tableau de bord, expériences **en cours** / **terminées**, historique
  par branche, fiche d'une expérience (avec diff vs référence), formulaires "nouvelle
  expérience"/"dériver" (avec conclusion, preuves, formulaire de commit du dépôt) générés
  dynamiquement à partir du JSON Schema du type de structure choisi, fusion, gestion des
  branches/tags, trace d'entité, graphe de filiation. C'est une application à page unique mais
  **multipage au sens propre** : chaque écran a sa propre URL (`/app/en-cours`,
  `/app/experience/<id>`, `/app/graphe`, ...), navigable au clavier/historique du navigateur et
  partageable en lien direct — le serveur sert la même page pour toute URL sous `/app` et le
  routeur JS (`app.js`) affiche l'écran correspondant.
- `/docs` — le site Sphinx du projet (`docs/`), servi tel quel s'il a été construit
  (`sphinx-build -b html docs docs/_build/html`, ou `follow_api start --build-docs`) ; sinon une
  page explique comment le construire.
- `/examples-gallery/<fichier>` — les rapports HTML autonomes de `demos/output/` (voir
  `demos/README.md`), listés avec description sur `/app/exemples`.

## API

Toutes les routes sont sous `/api`. Points d'entrée principaux :

- `GET /api/health` (compte les expériences en cours/terminées/branches), `/api/branches`, `/api/tags`, `/api/commit_form`
- `GET /api/structures`, `GET /api/structures/{key}/schema` (JSON Schema, pour générer un formulaire)
- `GET /api/log/{ref}?offset=&limit=` (paginé), `GET /api/experiments?status=running|completed|all&offset=&limit=`
  (toutes les expériences du dépôt, pas seulement une lignée)
- `GET /api/experiments/{ref}`, `GET /api/graph`, `GET /api/graph.html` (page Plotly autonome), `GET /api/diff?a=&b=`
- `GET /api/entities/{entity_id}`, `GET /api/examples`
- `POST /api/experiments` (créer + committer), `POST /api/experiments/{ref}/derive`, `POST /api/merge`
- `POST /api/branches`, `POST /api/tags`

Les erreurs Follow (`FollowError` et sous-classes) sont traduites en codes HTTP explicites :
404 (ref introuvable), 409 (rien à committer / conflit de fusion), 422 (formulaire ou structure
invalide), 400 (autre erreur Follow).

Hors périmètre volontairement : authentification et CORS - prévu pour un usage local/de confiance
(un `follow_api start --host 0.0.0.0` expose donc l'API sans protection, à ne faire que sur un
réseau de confiance).
