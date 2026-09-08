"""An adapter that returns a capability it never declared.

That is a defect in the adapter, not a property of the file, so the core raises instead
of quietly recording the value.
"""

from __future__ import annotations

from omitnix.adapters.base import Adapter, AnalysisRequest, AnalysisResult
from omitnix.model import Capability


class OverreachingAdapter(Adapter):
    name = "overreaching"
    extensions = (".over",)
    capabilities = frozenset({Capability.SUMMARY})

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        return AnalysisResult(
            values={Capability.SUMMARY: "declared", Capability.READS: ["orders"]}
        )


ADAPTER = OverreachingAdapter()
