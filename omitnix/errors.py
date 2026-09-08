"""Error types shared by the core.

The distinction that matters: a file the tool cannot analyze is *data* (it becomes an
``unknown`` record and fails the run), while a malformed adapter or a malformed
configuration is a *defect* and raises.
"""

from __future__ import annotations


class OmitnixError(Exception):
    """Base class for every error raised by omitnix."""


class ConfigError(OmitnixError):
    """The configuration file is missing, unreadable, or declares something unknown."""


class AdapterContractError(OmitnixError):
    """An adapter violates the contract in ``omitnix.adapters.base``.

    Raised for defects such as declaring no extension, or returning a value for a
    capability it never declared. This is never used for "this file could not be
    analyzed" -- that is an ``unknown`` record, not an exception.
    """


class GateError(OmitnixError):
    """The new-file gate cannot run, so it must not report a pass.

    Raised when newness cannot be established at all -- there is no git working tree to
    ask. Reporting "no new files" in that situation would be a gate that passes because
    it looked nowhere.
    """


class CompletenessError(OmitnixError):
    """The counting invariant broke.

    ``discovered == analyzed + unresolved + unknown`` is the whole point of this tool.
    If it ever fails to hold, the run is a defect and must not produce output.
    """
