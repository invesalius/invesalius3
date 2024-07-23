from typing import Generic, Protocol, TypeVar

import wx
from typing_extensions import Self

from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX

T = TypeVar("T", covariant=True)

class SupportsGetItem(Protocol, Generic[T]):
    def __getitem__(self, key: int, /) -> T: ...

class CanvasObjects(Protocol):
    parent: Self | None
    def is_over(self, x: int, y: int) -> Self | None: ...
    def draw_to_canvas(self, gc: wx.GraphicsContext, canvas: CanvasRendererCTX) -> None: ...

class CanvasElement(Protocol):
    def draw_to_canvas(self, gc: wx.GraphicsContext, canvas: CanvasRendererCTX) -> None: ...
