"""A synthetic adapter that can only produce a summary.

Its whole job in the test suite is to prove that a capability an adapter never declared
is rendered as out of scope, and never as a missing or empty value.
"""

from __future__ import annotations

from omitnix.adapters.base import Adapter, AnalysisRequest, AnalysisResult
from omitnix.model import Capability


class NoteAdapter(Adapter):
    name = "note"
    extensions = (".note",)
    capabilities = frozenset({Capability.SUMMARY})

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        first_line = next((line.strip() for line in request.text.splitlines() if line.strip()), "")
        return AnalysisResult(values={Capability.SUMMARY: first_line})


ADAPTER = NoteAdapter()
