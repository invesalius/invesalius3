import wx

SystemFont = int
Coord = int
EventType = int
PolygonFillMode = int
PenStyle = int
PenCap = int
BrushStyle = int

ColourType = (
    tuple[int, int, int]
    | tuple[int, int, int, int]
    | list[int]
    | wx.Colour
    | tuple[float, float, float, float]
    | str
)

class wxAssertionError(AssertionError): ...
class PyAssertionError(wxAssertionError): ...
class PyNoAppError(RuntimeError): ...
