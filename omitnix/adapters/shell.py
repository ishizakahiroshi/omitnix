"""Shell scripts, at the minimal tier.

``.sh`` turned up in 37 of the 52 repositories measured for the C6 plan -- the widest
distribution of any source extension, wider than any language this tool analyzes in full.
That is the whole argument for the minimal tier: without an adapter, almost every
repository would need an exclusion written for shell scripts before its first run could
finish, and an excluded file is one that stops being counted.

A script's header comment is read as its summary. Nothing else is claimed. A shell script
that runs ``psql`` is touching tables, and this adapter does not pretend to see it; that
shows in the index as ``n/a``, not as an empty table column.
"""

from __future__ import annotations

from ._minimal import MinimalAdapter


class ShellAdapter(MinimalAdapter):
    name = "shell"
    extensions = (".sh",)
    line_comment = ("#",)


ADAPTER = ShellAdapter()
