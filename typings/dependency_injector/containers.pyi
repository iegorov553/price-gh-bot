from __future__ import annotations

from typing import Any


class DeclarativeContainer:
    """Minimal stub of dependency_injector.containers.DeclarativeContainer."""

    wiring_config: Any
    config: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
