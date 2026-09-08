"""PowerShell scripts, at the minimal tier.

``.ps1`` appears in 30 of the 52 repositories measured for the C6 plan, for the same
reason ``.sh`` does: it is what the small automation of a repository is written in. Same
conclusion, same three files, same refusal to claim more than a header comment.

A grammar package does exist on PyPI for PowerShell (``tree-sitter-powershell`` 0.26.4,
checked 2026-09-08) and is deliberately not used. It would become a dependency that has to
be installed before a ``.ps1`` file could be counted at all, and it would buy exactly one
column that a four-line text scan already fills.

PowerShell's comment-based help block opens with ``<#`` and its first line is usually
``.SYNOPSIS``, which is a section marker rather than a description; the shared description
filter skips markers of that shape, so the line after it is what becomes the summary.
"""

from __future__ import annotations

from ._minimal import MinimalAdapter


class PowerShellAdapter(MinimalAdapter):
    name = "powershell"
    extensions = (".ps1",)
    line_comment = ("#",)
    block_comment = (("<#", "#>"),)


ADAPTER = PowerShellAdapter()
