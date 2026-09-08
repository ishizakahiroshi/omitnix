"""Type stubs for the fictional database client used by these fixtures."""

from typing import Any

class Connection:
    def execute(self, statement: str, parameters: tuple[Any, ...] = ...) -> list[Any]: ...

db: Connection
