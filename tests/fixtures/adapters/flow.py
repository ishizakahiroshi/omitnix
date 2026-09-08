"""A synthetic adapter used by the tests.

It parses a made-up ``.flow`` format so the core can be exercised end to end without a
real language parser, and without copying anything out of a real codebase::

    summary: List orders for the signed-in customer
    authn: require_session
    authz: apply_visibility_filter
    reads: orders, customers
    writes:
    unresolved: dynamic_sql / table name built at run time

Two directives exist only to reach failure paths: ``unparsable:`` makes the adapter
report the file as unknown, and ``raise:`` makes it blow up.
"""

from __future__ import annotations

from omitnix.adapters.base import Adapter, AnalysisRequest, AnalysisResult
from omitnix.model import Capability


def _parse(text: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if not stripped or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        directives.setdefault(key.strip().lower(), []).append(value.strip())
    return directives


def _items(directives: dict[str, list[str]], key: str) -> list[str]:
    values: list[str] = []
    for line in directives.get(key, []):
        values.extend(part.strip() for part in line.split(",") if part.strip())
    return values


def _configured(names: list[str], configured: tuple[str, ...]) -> list[str]:
    """Only report a name the repository actually calls authentication/authorization."""
    if not configured:
        return names
    return [name for name in names if name in configured]


class FlowAdapter(Adapter):
    name = "flow"
    extensions = (".flow",)
    capabilities = frozenset(
        {
            Capability.SUMMARY,
            Capability.AUTHENTICATION,
            Capability.AUTHORIZATION,
            Capability.READS,
            Capability.WRITES,
        }
    )

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        directives = _parse(request.text)
        if "unparsable" in directives:
            return AnalysisResult.unknown("the file declares itself unparsable")
        if "raise" in directives:
            raise ValueError("synthetic adapter failure")

        result = AnalysisResult()
        result.values[Capability.SUMMARY] = " ".join(directives.get("summary", []))
        result.values[Capability.READS] = _items(directives, "reads")
        result.values[Capability.WRITES] = _items(directives, "writes")
        result.values[Capability.AUTHENTICATION] = _configured(
            _items(directives, "authn"), request.authentication_functions
        )
        result.values[Capability.AUTHORIZATION] = _configured(
            _items(directives, "authz"), request.authorization_functions
        )
        for detail in directives.get("unresolved", []):
            code, _, rest = detail.partition("/")
            result.add_unresolved(code.strip() or "unresolved", rest.strip())
        return result


ADAPTER = FlowAdapter()
