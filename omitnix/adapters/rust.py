"""Rust, at the minimal tier.

Rust is here to be counted, not understood. The C6 plan measured every ``.rs`` file under
the author's repositories -- 254 files across 6 repositories -- and found no database
crate declared in any of their ``Cargo.toml`` files. An adapter that extracted table names
from Rust would have nothing to extract from and no way to be shown wrong, which is the
worst state for a feature this tool's premise depends on.

So it declares a summary and stops there. **The moment a repository appears whose Rust
talks to a database, this moves to the full tier** -- and by then there is something real
to test it against.
"""

from __future__ import annotations

from ._minimal import MinimalAdapter


class RustAdapter(MinimalAdapter):
    name = "rust"
    extensions = (".rs",)
    #: ``//!`` is an inner doc comment and is usually the one that describes a module.
    line_comment = ("//!", "///", "//")
    block_comment = (("/*", "*/"),)


ADAPTER = RustAdapter()
