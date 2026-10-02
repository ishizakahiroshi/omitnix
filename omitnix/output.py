"""Writing generated documents.

Every document omitnix generates is written through :func:`write_document`, so "where may
a run write" has one definition. A repository controls its own tree, so an output path
that lives inside it is validated rather than trusted.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .errors import OmitnixError


def write_document(path: Path, text: str, *, root: Path | None = None) -> None:
    """Write ``text`` to ``path``, refusing a destination that is a link or leaves ``root``.

    The text goes to a temporary file in the same directory and replaces the destination
    in one step, so a failed write leaves the previous document in place and the
    destination is never opened through a link.
    """
    directory = path.parent
    if root is not None:
        resolved_root = root.resolve()
        resolved_dir = directory.resolve()
        if resolved_dir != resolved_root and resolved_root not in resolved_dir.parents:
            raise OmitnixError(f"{path}: output directory is outside {root}")
    directory.mkdir(parents=True, exist_ok=True)
    if root is not None:
        # Checked again after mkdir: creating the directories can itself follow a link.
        resolved_dir = directory.resolve()
        if resolved_dir != resolved_root and resolved_root not in resolved_dir.parents:
            raise OmitnixError(f"{path}: output directory is outside {root}")
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise OmitnixError(f"{path}: refusing to write through a link")
    if path.exists() and not path.is_file():
        raise OmitnixError(f"{path}: output path is not a regular file")

    fd, temporary = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    try:
        # newline="\n" on purpose: these documents are meant to be committed, and the
        # platform that happened to run the tool must not show up as a whole-file diff.
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
