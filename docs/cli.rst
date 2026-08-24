Référence CLI
==============

``follow`` est installée comme point d'entrée (``[project.scripts]``) dès que le paquet est
installé. ``follow --version`` affiche la version ; ``follow <sous-commande> --help`` détaille
chaque option directement depuis le terminal.

Toutes les sous-commandes acceptent ``--repo CHEMIN`` (défaut : ``.follow``).

Le principe d'authoring suit celui de git : ``new``/``derive``/``merge`` écrivent un
**brouillon JSON** (l'équivalent de l'arbre de travail), qu'on édite à la main (étapes, preuves,
conclusion une fois l'expérience réellement menée), puis ``commit`` le fige dans le dépôt.

``follow init [chemin]``
-------------------------

Crée un nouveau dépôt (répertoire ``objects/`` + ``refs.json``). Échoue si le répertoire existe
déjà et n'est pas vide.

``follow new``
----------------

Démarre un brouillon d'expérience racine (sans parent).

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``--branch``
     - Branche cible (requis).
   * - ``--title`` / ``--intent``
     - Requis.
   * - ``--structure-type``
     - Chemin pointé Python vers la classe :class:`~follow.structure.Structure`, ex. ``examples.recipe.CakeRecipe`` (requis).
   * - ``--structure-file``
     - Fichier JSON conforme à ce type (requis).
   * - ``--author`` / ``--hypothesis``
     - Optionnels.
   * - ``--out``
     - Fichier de sortie du brouillon (défaut : ``draft.json``).

``--structure-type`` importe le module à la volée pour retrouver la classe enregistrée : le
module doit donc être importable (présent dans le répertoire courant ou installé).

``follow derive <ref>``
--------------------------

Dérive un brouillon depuis une expérience existante (``ref`` : id, branche ou tag) — hérite
structure, objectifs, références et étapes du parent, ajoute automatiquement une référence
``baseline``.

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``--title`` / ``--intent``
     - Requis.
   * - ``--new-branch``
     - Créer/utiliser cette branche au lieu de continuer celle du parent.
   * - ``--structure-type`` / ``--structure-file``
     - Remplacent la structure héritée du parent (optionnels).
   * - ``--author`` / ``--hypothesis`` / ``--out``
     - Comme ``new``.

``follow merge <ref_a> <ref_b>``
-----------------------------------

Fusionne deux lignes de travail (``ref_a`` : cible, ex. ``main`` ; ``ref_b`` : la ligne à
fusionner dedans). Voir :doc:`merging` pour la sémantique complète.

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``--title`` / ``--intent``
     - Requis.
   * - ``--branch``
     - Branche du commit de fusion (défaut : celle de ``ref_a``).
   * - ``--take-structure PATH``
     - Répétable — chemin de structure à prendre de ``ref_b``.
   * - ``--take-steps PATH``
     - Répétable — chemin d'étape à prendre de ``ref_b``.
   * - ``--author`` / ``--hypothesis`` / ``--out``
     - Comme ``new``.

``follow commit <brouillon.json>``
-------------------------------------

Fige un brouillon (produit par ``new``/``derive``/``merge``, ou édité à la main) dans le dépôt.
Calcule l'id par contenu, avance la branche, applique les tags.

``follow log [ref]``
-----------------------

Historique premier-parent d'une branche/tag/expérience (défaut : ``main``). ``-n/--number``
limite le nombre de lignes.

``follow show <ref>``
------------------------

Affiche la fiche complète d'une expérience (façon ``git show``) : intention, structure (avec
écarts vs référence le cas échéant), étapes, objectifs, preuves, conclusion.

``follow diff <ref_a> <ref_b>``
-----------------------------------

Diff structurel entre deux expériences. ``--steps`` compare le protocole plutôt que la
structure.

``follow trace <entity_id>``
---------------------------------

Retrouve, tout branches et lignages confondus, chaque expérience qui mentionne la même entité
physique (voir :doc:`entities`) — un ``entity_id`` posé quelque part dans la structure, sans
référence ni parent git à poser à la main. Trié par date, avec le chemin où le nom a été trouvé
dans chaque structure.

.. code-block:: bash

   follow trace moule-vert --repo mon_labo

``follow branch [nom]`` / ``follow tag [nom]``
--------------------------------------------------

Sans argument : liste les branches/tags. Avec un nom : crée ou déplace, ``--at REF`` requis.

Branches et tags partagent un seul espace de noms : créer une branche du même nom qu'un tag
existant (ou l'inverse) est refusé plutôt que de silencieusement rendre l'un des deux
inaccessible par ce nom.

Les tags sont **immuables** : ``follow tag`` refuse de repointer un tag déjà existant vers une
autre expérience, sauf avec ``--force`` (répéter le même ``--at`` est sans effet, pas besoin de
``--force``). Les branches restent mutables par nature, aucun flag nécessaire pour les déplacer.

``follow explode <ref> <chemin>``
-------------------------------------

Éclate un champ liste de la structure d'une expérience (un lot DOE) en base constante + facteurs
variables — voir :doc:`batch`.

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``ref`` (positionnel)
     - Id, branche ou tag de l'expérience.
   * - ``chemin`` (positionnel)
     - Champ liste de la structure à éclater, ex. ``trials``.
   * - ``--ignore FIELD``
     - Répétable — champ d'identité à exclure de la comparaison (ex. un numéro d'essai).
   * - ``--out``
     - Écrire une page HTML au lieu d'afficher un résumé texte.
   * - ``--open``
     - Ouvrir le fichier HTML dans le navigateur (avec ``--out``).

.. code-block:: bash

   follow explode main trials --ignore trial_id --repo mon_labo
   follow explode main trials --ignore trial_id --repo mon_labo --out explode.html --open

``follow graph``
-------------------

Exporte le graphe de filiation complet en HTML autonome (Plotly). ``--out`` (défaut
``graph.html``), ``--open`` pour ouvrir dans le navigateur.

``follow report [ref]``
--------------------------

Génère un compte rendu d'étude complet, sans IA, dérivé du dépôt — voir :doc:`report`.

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``ref`` (positionnel, optionnel)
     - Limiter au lignage d'une branche/tag/expérience (défaut : tout le dépôt).
   * - ``--title`` / ``--description``
     - En-tête de la page.
   * - ``--out``
     - Fichier de sortie (défaut : ``report.html``).
   * - ``--no-embed``
     - Utiliser le CDN Plotly au lieu de l'inclure (fichier plus léger, nécessite une connexion).
   * - ``--open``
     - Ouvrir le fichier dans le navigateur.

``follow menu``
-------------------

Menu interactif : naviguer dans le dépôt, démarrer une expérience, en dériver une variante,
clôturer un brouillon (conclure + committer), fusionner deux branches, générer un rapport ou le
graphe — sans mémoriser les sous-commandes et leurs options. Chaque action du menu appelle
exactement la même API (:class:`~follow.repository.Repository`/
:class:`~follow.repository.ExperimentBuilder`) que les sous-commandes ci-dessus ; rien n'est
réimplémenté, seule la navigation change.

.. code-block:: bash

   follow menu --repo mon_labo

Nécessite `questionary <https://questionary.readthedocs.io/>`_, non installé par défaut :

.. code-block:: bash

   pip install "follow[menu]"

Sans ``questionary`` installé, ``follow menu`` échoue avec un message clair plutôt qu'une
trace d'erreur ; toutes les autres sous-commandes fonctionnent normalement (voir
:mod:`follow.menu`).

L'authoring de la ``Structure`` elle-même n'est volontairement pas réinventé dans le menu : comme
``follow new --structure-file``, on pointe vers un fichier JSON existant — un formulaire
générique ne peut pas construire en toute sécurité n'importe quelle forme Pydantic arbitraire. Le
menu ajoute des invites interactives pour ce qui a une forme fixe et connue (objectifs, preuves,
conclusion) et pour la navigation (choisir une expérience, une branche, les chemins à prendre
lors d'une fusion, dans une vraie liste plutôt qu'en recopiant des identifiants à la main).
