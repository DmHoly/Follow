Référence de l'API
====================

follow.core
-----------

Modèle de domaine : la classe de base ``Structure``, les types métier (``Experiment``, ``Step``...),
``Quantity``, la génération d'ids et la hiérarchie d'erreurs.

follow.core.structure
~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.core.structure
   :members:

follow.core.quantity
~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.core.quantity
   :members:

follow.core.models
~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.core.models
   :members:

follow.core.ids
~~~~~~~~~~~~~~~~

.. automodule:: follow.core.ids
   :members:

follow.core.errors
~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.core.errors
   :members:

follow.paths
------------

Utilitaires génériques opérant sur une ``Structure`` déjà instanciée : chemins pointés, diff,
formatage d'affichage, entités nommées.

follow.paths.formatting
~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.paths.formatting
   :members:

follow.paths.merging
~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.paths.merging
   :members:

follow.paths.diffing
~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.paths.diffing
   :members:

follow.paths.entities
~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.paths.entities
   :members:

follow.doe
----------

Génération de plans d'expériences (DOE) et analyse des variantes d'un lot.

follow.doe.design
~~~~~~~~~~~~~~~~~~

.. automodule:: follow.doe.design
   :members:

follow.doe.batch
~~~~~~~~~~~~~~~~~

.. automodule:: follow.doe.batch
   :members:

follow.storage
---------------

Persistance : dépôt (``Repository``), backends de stockage et formulaire de commit.

follow.storage.repository
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.storage.repository
   :members:

follow.storage.backends
~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.storage.backends
   :members:

follow.storage.commit_form
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.storage.commit_form
   :members:

follow.presentation
--------------------

Génération de sortie destinée à un humain : rendu texte, rapports HTML, graphe de filiation.

follow.presentation.rendering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.presentation.rendering
   :members:

follow.presentation.report
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.presentation.report
   :members:

follow.presentation.graphing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.presentation.graphing
   :members:

follow.interfaces
------------------

Points d'entrée utilisateur : la CLI scriptable et le menu interactif.

follow.interfaces.cli
~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.interfaces.cli
   :members:

follow.interfaces.menu
~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: follow.interfaces.menu
   :members:
