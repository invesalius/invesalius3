from typing import Generic, Protocol, TypeVar

T = TypeVar("T", covariant=True)

class SupportsGetItem(Protocol, Generic[T]):
    def __getitem__(self, key: int, /) -> T: ...
