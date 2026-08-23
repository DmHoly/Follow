Formulaire de commit obligatoire
====================================

Une ``Structure`` capture la configuration étudiée, mais pas certaines métadonnées qu'on veut
systématiquement tracer — qui a lancé le run, sur quel équipement, si un plan croisé a bien été
vérifié pour l'aliasing (voir :doc:`design`)... :mod:`follow.commit_form` définit ce
questionnaire une fois, en YAML, et le rend **obligatoire** à chaque commit d'un dépôt donné —
plutôt que de compter sur un message de commit bien rédigé.

Le même fichier YAML est pensé pour piloter, plus tard, un vrai formulaire d'interface (label,
type, choix, obligatoire ou non pour chaque champ) — pas seulement pour valider du texte.

Définir un formulaire
-------------------------

.. code-block:: yaml

   # commit_form.yml
   title: Formulaire de commit - Fab wafers
   fields:
     - name: operator
       label: Opérateur
       type: string
       required: true
     - name: design_type
       label: Type de plan d'expérience
       type: choice
       choices: [full_factorial, fractional_factorial, sweep, latin_hypercube, autre]
       required: true
     - name: checked_confounding
       label: Facteurs croisés vérifiés ?
       type: boolean
       required: true
     - name: notes
       label: Notes libres
       type: text
       required: false

Types disponibles : ``string``, ``text`` (même validation que ``string``, distingue juste un
champ multi-lignes pour une future UI), ``number``, ``boolean``, ``choice`` (avec ``choices``).

L'attacher à un dépôt
-------------------------

.. code-block:: python

   from follow import Repository
   from follow.commit_form import load_commit_form

   repo = Repository("mon_labo", commit_form="commit_form.yml")

Pour un dépôt persistant, déposer simplement ``commit_form.yml`` **dans le dossier du dépôt**
suffit — ``Repository`` le détecte automatiquement à l'ouverture, sans argument :

.. code-block:: python

   repo = Repository("mon_labo")   # charge mon_labo/commit_form.yml s'il existe

Un dépôt sans formulaire configuré n'exige rien : ``form_answers`` reste optionnel et n'est
jamais validé.

Répondre et committer
-------------------------

.. code-block:: python

   builder = repo.new(branch="main", structure=lot, title="LOT-A", intent="...")
   builder.answer_form(operator="Alice", design_type="full_factorial", checked_confounding=True)
   builder.commit()   # lève FormValidationError si une réponse obligatoire manque ou est invalide

:meth:`~follow.repository.ExperimentBuilder.answer_form` peut être appelé plusieurs fois (les
réponses se fusionnent) ; la validation n'a lieu qu'au commit, et
:class:`~follow.commit_form.FormValidationError` liste **tous** les problèmes trouvés en une
seule fois (champs manquants, type incorrect, choix invalide, champ inconnu du formulaire) —
pensé pour une UI qui affiche tout d'un coup plutôt qu'un aller-retour par erreur.

Les réponses validées sont stockées sur l'expérience committée
(``experiment.form_answers``), persistées comme le reste.

Équivalent en CLI
-----------------

``follow new``/``derive``/``merge`` affichent les champs requis dès l'écriture du brouillon si
le dépôt a un formulaire configuré :

.. code-block:: bash

   follow new --repo mon_labo --branch main --title "LOT-A" --intent "..." \
     --structure-type examples.wafer_doe.WaferLot --structure-file lot.json --out draft.json
   # Ce dépôt exige un formulaire de commit ('Formulaire de commit - Fab wafers') :
   #   - operator (string, requis): Opérateur
   #   - design_type (choice, requis): Type de plan d'expérience
   #   - checked_confounding (boolean, requis): Facteurs croisés vérifiés ?
   #   - notes (text, optionnel): Notes libres

Éditez ensuite la clé ``form_answers`` de ``draft.json`` à la main avant ``follow commit`` — les
réponses invalides ou manquantes refusent le commit avec le même message clair qu'en Python.

Voir ``examples/wafer_doe_commit_form.yml`` pour un template complet.
