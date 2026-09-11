"""A synthetic adapter that can only produce a summary.

Its whole job in the test suite is to prove that a capability an adapter never declared
is rendered as out of scope, and never as a missing or empty value.

It also accepts an ``unresolved: code / detail`` line, for the one thing only an adapter
with no ``reads`` or ``writes`` can demonstrate: that something it could not follow marks
no table, because it could never have put a table anywhere to begin with.
"""

from __future__ import annotations

from omitnix.adapters.base import Adapter, AnalysisRequest, AnalysisResult
from omitnix.model import Capability


class NoteAdapter(Adapter):
    name = "note"
    extensions = (".note",)
    capabilities = frozenset({Capability.SUMMARY})

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        lines = [line.strip() for line in request.text.splitlines() if line.strip()]
        notes = [line for line in lines if line.lower().startswith("unresolved:")]
        first_line = next((line for line in lines if line not in notes), "")

        result = AnalysisResult(values={Capability.SUMMARY: first_line})
        for note in notes:
            code, _, detail = note.partition(":")[2].partition("/")
            result.add_unresolved(code.strip() or "unresolved", detail.strip())
        return result


ADAPTER = NoteAdapter()
