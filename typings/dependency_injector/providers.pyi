from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class Provider(Generic[T]):
    """Base provider interface."""

    def __call__(self, *args: Any, **kwargs: Any) -> T: ...


class Configuration:
    """Configuration provider stub."""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def from_dict(self, data: dict[str, Any]) -> None: ...

    def __getattr__(self, name: str) -> Any: ...
    def __setattr__(self, name: str, value: Any) -> None: ...


class Singleton(Provider[T]):
    """Singleton provider stub."""

    def __init__(
        self,
        factory: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> None: ...
