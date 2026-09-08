"""The new-file gate.

A full run answers "was everything analyzed?". The gate answers a narrower and stricter
question about the files that most need it: **a file being added right now must not
arrive without the things its own adapter is able to report.**

New code is where an inventory is weakest. It has no summary yet, its authorization call
is the one most likely to have been forgotten, and if the parser does not understand it
at all, it enters the index as a hole on the day it is written. So the gate refuses the
file rather than the report.

Two rules keep it from becoming noise:

* **What is required comes from the adapter's own capability declaration**, never from
  the file's language or extension. An adapter that cannot report an authorization call
  is not asked for one, and its files do not fail for lacking it. Without this, the day a
  stylesheet adapter is added is the day every new stylesheet fails the gate for missing
  an authorization check it could never have had.
* **Only a capability whose absence is a defect is required at all** -- the set lives in
  :data:`omitnix.model.GATE_REQUIRED_CAPABILITIES`. Reading no tables is a fact about a
  file, not an omission.

``unknown`` is the exception to the first rule and is not softened by anything: a file
nothing could classify has no capability declaration to consult, and silently admitting
it is the precise failure this tool exists to prevent.

``unresolved`` is deliberately *not* a refusal. It says the analyzer read the file and
could not follow part of it -- dynamically built SQL, an indirect call past one hop --
which is a limit of this tool, not a defect in the file. Refusing a file for it would
block work nobody can unblock by editing the file, and a gate that cannot be satisfied
is a gate that gets switched off. It is reported as a notice on every run instead, so it
stays visible without being a verdict. A file the analyzer could not read *at all* is
``unknown``, and that still refuses.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .errors import GateError
from .gitmeta import added_files_since, newly_added_files
from .globs import matches_any
from .model import (
    GATE_REQUIRED_CAPABILITIES,
    Capability,
    FieldState,
    FileRecord,
    Report,
    Status,
)
from .scan import select_files

__all__ = [
    "GateFinding",
    "GateNotice",
    "AppliedExemption",
    "GateReport",
    "NewFileSelection",
    "new_files",
    "run_gate",
]

#: How each missing check is named in the output. Short, so a failure reads as a list of
#: things to fix rather than a paragraph.
_MISSING_LABEL: dict[Capability, str] = {
    Capability.SUMMARY: "no summary",
    Capability.AUTHENTICATION: "no authentication call",
    Capability.AUTHORIZATION: "no authorization call",
}

#: Checks that only mean something once the repository has said what to look for. With
#: the list empty the tool has no definition of the call, so its absence is not evidence
#: of anything -- "not configured" is a different answer from "not called", and refusing
#: a file on the first one would make the gate unusable in every repository that has no
#: session layer at all.
_CONFIGURED_BY: dict[Capability, str] = {
    Capability.AUTHENTICATION: "authentication_functions",
    Capability.AUTHORIZATION: "authorization_functions",
}

_MISSING_DETAIL: dict[Capability, str] = {
    Capability.SUMMARY: "adapter '{adapter}' reports summaries and found none here",
    Capability.AUTHENTICATION: (
        "adapter '{adapter}' observed no call to any authentication function "
        "listed in authentication_functions"
    ),
    Capability.AUTHORIZATION: (
        "adapter '{adapter}' observed no call to any authorization function "
        "listed in authorization_functions"
    ),
}


@dataclass(frozen=True, slots=True)
class GateFinding:
    """One reason one file is refused. One finding is one printed line."""

    path: str
    item: str
    detail: str

    def line(self) -> str:
        return f"{self.path}: {self.item} ({self.detail})"


@dataclass(frozen=True, slots=True)
class GateNotice:
    """Something the gate reports without refusing the file.

    Reserved for what the analyzer could not follow. Printed on a pass as well as on a
    failure: the point is that it stays visible, not that it stops anyone.
    """

    path: str
    item: str
    detail: str

    def line(self) -> str:
        return f"{self.path}: {self.item} ({self.detail})"


@dataclass(frozen=True, slots=True)
class AppliedExemption:
    """A check that was skipped, and the configured reason it was allowed to be.

    Printed whenever it fires. An exemption that stops being visible is an exemption
    nobody re-examines.
    """

    path: str
    capability: Capability
    reason: str

    def line(self) -> str:
        return f"{self.path}: {self.capability} not required ({self.reason})"


@dataclass(frozen=True, slots=True)
class GateReport:
    checked: tuple[str, ...]
    findings: tuple[GateFinding, ...]
    exemptions: tuple[AppliedExemption, ...]
    #: Reported, never a verdict. The gate passes with notices present.
    notices: tuple[GateNotice, ...] = ()
    #: Checks that applied to at least one file but could not be made, because the
    #: repository never said what the call looks like. Stated once per run.
    unconfigured: tuple[Capability, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def failed_paths(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for finding in self.findings:
            seen.setdefault(finding.path, None)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class NewFileSelection:
    """Which newly added files the gate will look at, and what it set aside."""

    paths: tuple[str, ...]
    #: Requested paths the configuration excludes. Counted, never dropped in silence.
    excluded_by_config: int = 0
    #: Requested paths that do not exist, or lie outside the root.
    missing: tuple[str, ...] = ()


def new_files(
    config: Config, requested: list[str] | None = None, since: str | None = None
) -> NewFileSelection:
    """Narrow a candidate list down to the files git reports as newly added.

    With ``requested`` (what ``--files`` passes), the gate looks at the intersection: a
    changed-but-existing file in the same commit is not this gate's business. Without it,
    every newly added file under the root is a candidate.

    ``since`` changes what "new" is asked of. Without it the question goes to the working
    tree, which only has an answer while the file is still uncommitted -- so the gate can
    only ever run in a pre-commit hook, and a hook is enabled one machine at a time. With
    it the question is "what did this branch add since ``since``", which a server can ask
    about work anyone committed, hook or no hook. That is the difference between a gate
    whose coverage is everyone's local configuration and a gate whose coverage is stated.
    """
    added = added_files_since(config.root, since) if since else newly_added_files(config.root)
    if added is None:
        if since:
            raise GateError(
                f"the gate was asked which files were added since '{since}', and git "
                f"could not answer in {config.root}. The ref may not exist here (a "
                "shallow clone has no history to compare against; fetch it first), or "
                "the two histories may be unrelated. Refusing rather than reporting "
                "that nothing was added."
            )
        raise GateError(
            f"the gate needs git to tell which files are new, but {config.root} is not "
            "inside a git working tree"
        )

    candidates = sorted(added) if requested is None else requested
    selection = select_files(config, candidates)
    kept = tuple(rel for rel in selection if rel in added)
    return NewFileSelection(
        paths=kept,
        excluded_by_config=selection.skipped,
        missing=selection.missing,
    )


def _exemption_for(
    config: Config, path: str, capability: Capability
) -> AppliedExemption | None:
    for exemption in config.gate_exemptions:
        if capability in exemption.skip and matches_any(exemption.paths, path):
            return AppliedExemption(path=path, capability=capability, reason=exemption.reason)
    return None


def _unconfigured_checks(config: Config) -> frozenset[Capability]:
    return frozenset(
        capability
        for capability, attribute in _CONFIGURED_BY.items()
        if not getattr(config, attribute)
    )


def _check_record(
    record: FileRecord, config: Config, unconfigured: frozenset[Capability] = frozenset()
) -> tuple[list[GateFinding], list[AppliedExemption], list[GateNotice], set[Capability]]:
    if record.status is Status.UNKNOWN:
        # No adapter classified it, so there is no capability declaration to consult and
        # nothing to exempt. This is the one check no configuration can switch off.
        return (
            [
                GateFinding(
                    path=record.path,
                    item="unknown",
                    detail=record.unknown_reason or "no adapter could classify this file",
                )
            ],
            [],
            [],
            set(),
        )

    findings: list[GateFinding] = []
    exemptions: list[AppliedExemption] = []
    adapter = record.adapter or "unknown adapter"

    # Reported, not refused: what the analyzer could not follow is this tool's limit, and
    # the author of the file usually has no way to satisfy it.
    notices = [
        GateNotice(
            path=record.path,
            item=f"unresolved ({item.code})",
            detail=item.detail or "the analyzer could not follow this",
        )
        for item in record.unresolved
    ]

    skipped_unconfigured: set[Capability] = set()

    for capability in GATE_REQUIRED_CAPABILITIES:
        entry = record.fields.get(capability)
        if entry is None or entry.state is FieldState.OUT_OF_SCOPE:
            continue  # outside what this adapter can report: not a missing value
        if entry.state is FieldState.VALUE:
            continue
        if capability in unconfigured:
            # The adapter could report this, and reported nothing -- but the repository
            # never said which call counts, so nothing was looked for. Recorded so the
            # run can say the check did not happen, rather than passing in silence.
            skipped_unconfigured.add(capability)
            continue

        exemption = _exemption_for(config, record.path, capability)
        if exemption is not None:
            exemptions.append(exemption)
            continue

        findings.append(
            GateFinding(
                path=record.path,
                item=_MISSING_LABEL[capability],
                detail=_MISSING_DETAIL[capability].format(adapter=adapter),
            )
        )

    return findings, exemptions, notices, skipped_unconfigured


def run_gate(report: Report, config: Config) -> GateReport:
    """Apply the gate to a report built over newly added files only."""
    findings: list[GateFinding] = []
    exemptions: list[AppliedExemption] = []
    notices: list[GateNotice] = []
    unconfigured_seen: set[Capability] = set()
    unconfigured = _unconfigured_checks(config)

    for record in report.files:
        record_findings, record_exemptions, record_notices, record_unconfigured = _check_record(
            record, config, unconfigured
        )
        findings.extend(record_findings)
        exemptions.extend(record_exemptions)
        notices.extend(record_notices)
        unconfigured_seen |= record_unconfigured

    return GateReport(
        checked=tuple(record.path for record in report.files),
        findings=tuple(findings),
        exemptions=tuple(exemptions),
        notices=tuple(notices),
        unconfigured=tuple(sorted(unconfigured_seen, key=str)),
    )
