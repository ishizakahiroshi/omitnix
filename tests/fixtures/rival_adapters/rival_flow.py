"""A second adapter claiming ``.flow``.

Used to check that an ambiguous extension is an error the repository has to settle,
rather than something resolved silently by import order.
"""

from __future__ import annotations

from omitnix.adapters.base import Adapter, AnalysisRequest, AnalysisResult
from omitnix.model import Capability


class RivalFlowAdapter(Adapter):
    name = "rival_flow"
    extensions = (".flow",)
    capabilities = frozenset({Capability.SUMMARY})

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        return AnalysisResult(values={Capability.SUMMARY: "rival"})


ADAPTER = RivalFlowAdapter()
