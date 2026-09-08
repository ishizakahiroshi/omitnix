"""Entry point for ``python -m omitnix``, equivalent to the installed ``omitnix`` script."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
