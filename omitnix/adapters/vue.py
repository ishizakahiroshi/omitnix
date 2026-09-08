"""Vue single-file components, at the minimal tier.

A ``.vue`` file is three languages in one envelope -- a template, a script and a style
block -- and reading it properly means reaching into each of them. That is worth doing
only once there is enough of it to be worth doing: the C6 measurement found 113 files
across 4 repositories, against 21,382 ``.ts`` files across 15.

There is also nothing to reach for it with. **``tree-sitter-vue`` is not published on
PyPI** (checked 2026-09-08: pip reports no matching distribution at any version), and
bringing in a parser from outside the tree-sitter family for one file type is the trade
this project already refused once.

So the component is counted and its leading comment is read. Its script block is not
analyzed, and the index says so with ``n/a`` in every other column rather than with a
blank that would read as "this component calls nothing".
"""

from __future__ import annotations

from ._minimal import MinimalAdapter


class VueAdapter(MinimalAdapter):
    name = "vue"
    extensions = (".vue",)
    #: A single-file component opens with markup, so its header comment is an HTML one.
    block_comment = (("<!--", "-->"), ("/*", "*/"))
    line_comment = ("//",)


ADAPTER = VueAdapter()
