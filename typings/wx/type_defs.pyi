from typing import Any

import wx

SystemFont = int
Coord = int
EventType = int
PolygonFillMode = int
PenStyle = int
PenCap = int
BrushStyle = int
WindowID = int
ArtID = str
ArtClient = str
WindowVariant = int
BitmapType = int
ClientData = Any

ColourType = (
    tuple[int, int, int]
    | tuple[int, int, int, int]
    | list[int]
    | wx.Colour
    | tuple[float, float, float, float]
    | str
)
SizeType = tuple[int, int] | list[int] | wx.Size

class wxAssertionError(AssertionError): ...
class PyAssertionError(wxAssertionError): ...
class PyNoAppError(RuntimeError): ...
