"""omitnix: a static code inventory whose product is completeness, not coverage of rows.

The core never knows about a specific language. Everything language-shaped lives in an
adapter under ``omitnix/adapters/`` and is found by the discovery mechanism in
``omitnix.registry``.
"""

__version__ = "0.1.3"

__all__ = ["__version__"]
