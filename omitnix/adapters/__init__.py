"""Language adapters.

Dropping a module in this directory is the whole registration procedure. There is no
table of languages anywhere in the core, and nothing here imports the concrete adapters:
``omitnix.registry`` walks this package at run time and picks up every
:class:`~omitnix.adapters.base.Adapter` instance it finds.

A module whose name starts with ``_`` is skipped, so helpers can live here too.
"""
