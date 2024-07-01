from typing import Protocol

class SupportsGetItem[T](Protocol):
    def __getitem__(self, key: int, /) -> T: ...
