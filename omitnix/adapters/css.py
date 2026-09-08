"""Stylesheets.

The one adapter that declares *no* capability at all, on purpose. A stylesheet has no
authentication, no authorization and no tables, and it has no summary either: the comment
at the head of a CSS file is a licence banner or a section marker far more often than a
description of the file.

Declaring nothing is what keeps the index honest. Every column renders as ``n/a`` -- out
of scope -- instead of "none observed", so a stylesheet never appears in a document as a
file that was checked for an authorization call and found to have none. It is also what
keeps the new-file gate usable: the gate asks an adapter only for what it declared, so
adding a stylesheet cannot fail a commit for missing a check it could never have had.

What this adapter is for is the count. Without it every ``.css`` file in a repository is
``unknown`` and the run exits non-zero until someone writes an exclusion for it.
"""

from __future__ import annotations

from ._minimal import MinimalAdapter


class CssAdapter(MinimalAdapter):
    name = "css"
    extensions = (".css",)
    capabilities = frozenset()


ADAPTER = CssAdapter()
