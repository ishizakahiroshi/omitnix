"""The minimal tier: a language that is present, and nothing more.

Some extensions have to be *decided* without being *understood*. ``.sh`` appears in 37 of
the repositories measured for the C6 plan and ``.ps1`` in 30, and every extension a
repository contains must either have an adapter or be excluded by name -- otherwise it
lands in ``unknown`` and fails the run. Three files here are cheaper than an exclusion
line written into thirty configuration files, and unlike an exclusion they keep the file
*counted*.

What these adapters must not do is imply more than they looked at. They declare a summary
and nothing else, so the core renders authorization and tables as out of scope rather than
as observed-and-empty. A stylesheet must never appear in an index as a file with no
authorization check.

**No grammar is loaded.** Reading the comment block at the head of a file needs no parser,
and every grammar added here would be a dependency that has to exist on the user's machine
for a file to be counted at all -- for a column that says only what the first comment line
says. Two of these languages have no grammar package on PyPI to load even if that were
wanted (measured 2026-09-08: ``tree-sitter-vue`` does not exist there).
"""

from __future__ import annotations

from typing import ClassVar

from ..model import Capability
from ._extract import first_description_line
from .base import Adapter, AnalysisRequest, AnalysisResult

__all__ = ["MinimalAdapter", "leading_comment_block"]

#: How far into a file the header comment may start. A file whose first forty lines are
#: all code has no header comment, and scanning the rest would only find a comment that
#: describes a function.
_MAX_HEADER_LINES = 40


def leading_comment_block(
    text: str,
    line_comment: tuple[str, ...],
    block_comment: tuple[tuple[str, str], ...] = (),
) -> str:
    """The run of comments at the head of a file, as raw text.

    The block ends at the first line that is neither blank nor a comment, and at the first
    blank line after the block has started -- so a header comment is not silently joined to
    the comment above the first function.
    """
    collected: list[str] = []
    inside: tuple[str, str] | None = None

    for raw in text.splitlines()[:_MAX_HEADER_LINES]:
        line = raw.strip()

        if inside is not None:
            collected.append(line)
            if inside[1] in line:
                inside = None
            continue

        if not line:
            if collected:
                break
            continue

        # An interpreter line names a program, not the file's purpose. Promoting it to
        # the summary column would fill an index with the same three words.
        if line.startswith("#!"):
            continue

        opener = next((pair for pair in block_comment if line.startswith(pair[0])), None)
        if opener is not None:
            collected.append(line)
            if opener[1] not in line[len(opener[0]) :]:
                inside = opener
            continue

        if any(line.startswith(prefix) for prefix in line_comment):
            collected.append(line)
            continue

        break

    return "\n".join(collected)


class MinimalAdapter(Adapter):
    """Counts the file and reports the first line of its header comment.

    A subclass sets ``name``, ``extensions`` and how the language spells a comment. One
    that declares no capabilities at all reports nothing, which is the right answer for a
    file format that has no notion of a summary; the file is still discovered, still
    counted, and still passes the gate, because the gate asks only for what the adapter
    declared.
    """

    capabilities: ClassVar[frozenset[Capability]] = frozenset({Capability.SUMMARY})
    #: Prefixes that begin a comment running to the end of the line.
    line_comment: ClassVar[tuple[str, ...]] = ()
    #: (opener, closer) pairs for comments that span lines.
    block_comment: ClassVar[tuple[tuple[str, str], ...]] = ()

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        if Capability.SUMMARY not in self.capabilities:
            return AnalysisResult()
        block = leading_comment_block(request.text, self.line_comment, self.block_comment)
        return AnalysisResult(values={Capability.SUMMARY: first_description_line(block)})
