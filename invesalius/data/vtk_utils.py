# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------
import os
import sys
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Sequence, SupportsInt, Tuple, Union

import wx
from vtkmodules.vtkCommonCore import (
    VTK_CHAR,
    VTK_DOUBLE,
    VTK_FLOAT,
    VTK_INT,
    VTK_SHORT,
    VTK_UNSIGNED_CHAR,
    VTK_UNSIGNED_INT,
    VTK_UNSIGNED_SHORT,
)
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkImagingCore import vtkExtractVOI
from vtkmodules.vtkIOGeometry import vtkOBJReader, vtkSTLReader
from vtkmodules.vtkIOPLY import vtkPLYReader
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
from vtkmodules.vtkRenderingCore import (
    vtkActor2D,
    vtkCoordinate,
    vtkTextActor,
    vtkTextMapper,
    vtkTextProperty,
)

import invesalius.constants as const
import invesalius.utils as utils
from invesalius import inv_paths
from invesalius.enhanced_logging import get_logger
from invesalius.error_handling import (
    ErrorCategory,
    ErrorSeverity,
    VTKError,
    handle_errors,
)
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

# Initialize logger
logger = get_logger("data.vtk_utils")

if TYPE_CHECKING:
    import numpy as np
    from vtkmodules.vtkCommonExecutionModel import vtkAlgorithm

    from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX


@handle_errors(
    error_message="Error getting VTK array type",
    category=ErrorCategory.VTK,
    severity=ErrorSeverity.ERROR,
    reraise=False,
)
def get_vtk_array_type(numpy_dtype):
    """
    Convert numpy data type to VTK array type.

    Args:
        numpy_dtype: Numpy data type

    Returns:
        int: VTK array type constant
    """
    import numpy as np

    # Map numpy types to VTK types
    type_map = {
        np.float32: VTK_FLOAT,
        np.float64: VTK_DOUBLE,
        np.int8: VTK_CHAR,
        np.uint8: VTK_UNSIGNED_CHAR,
        np.int16: VTK_SHORT,
        np.uint16: VTK_UNSIGNED_SHORT,
        np.int32: VTK_INT,
        np.uint32: VTK_UNSIGNED_INT,
    }

    logger.debug(f"Converting numpy dtype {numpy_dtype} to VTK array type")
    # Get the corresponding VTK type or default to VTK_FLOAT
    vtk_type = type_map.get(numpy_dtype.type, VTK_FLOAT)
    logger.debug(f"Converted to VTK type {vtk_type}")
    return vtk_type


class ProgressDialog:
    def __init__(self, parent: Optional[wx.Window], maximum: int, abort: bool = False):
        self.title = "InVesalius 3"
        self.msg = _("Loading DICOM files")
        self.maximum = maximum
        self.current = 0
        self.style = wx.PD_APP_MODAL
        if abort:
            self.style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT

        logger.debug(f"Creating ProgressDialog with maximum={maximum}, abort={abort}")
        self.dlg = wx.ProgressDialog(
            self.title, self.msg, maximum=self.maximum, parent=parent, style=self.style
        )

        self.dlg.Bind(wx.EVT_BUTTON, self.Cancel)
        self.dlg.SetSize(wx.Size(250, 150))

    def Cancel(self, evt: wx.CommandEvent) -> None:
        logger.info("ProgressDialog cancel button pressed")
        Publisher.sendMessage("Cancel DICOM load")

    def Update(self, value: SupportsInt, message: str) -> Union[Tuple[bool, bool], bool]:
        if int(value) != self.maximum:
            try:
                logger.debug(f"Updating progress dialog: value={value}, message={message}")
                return self.dlg.Update(int(value), message)
            # TODO:
            # Exception in the Wtindows XP 64 Bits with wxPython 2.8.10
            except wx.PyAssertionError:
                logger.warning("PyAssertionError in progress dialog update")
                return True
        else:
            return False

    def Close(self) -> None:
        logger.debug("Closing progress dialog")
        self.dlg.Destroy()


if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
        logger.warning("win32api module not found on Windows, using regular paths")
else:
    _has_win32api = False

# If you are frightened by the code bellow, or think it must have been result of
# an identation error, lookup at:
# Closures in Python (pt)
# http://devlog.waltercruz.com/closures
# http://montegasppa.blogspot.com/2007/01/tampinhas.html
# Closures not only in Python (en)
# http://en.wikipedia.org/wiki/Closure_%28computer_science%29
# http://www.ibm.com/developerworks/library/l-prog2.html
# http://jjinux.blogspot.com/2006/10/python-modifying-counter-in-closure.html


@handle_errors(
    error_message="Error creating progress handler",
    category=ErrorCategory.GUI,
    severity=ErrorSeverity.ERROR,
    reraise=False,
)
def ShowProgress(
    number_of_filters: int = 1, dialog_type: str = "GaugeProgress"
) -> Callable[[Union[float, int, "vtkAlgorithm"], str], float]:
    """
    To use this closure, do something like this:
        UpdateProgress = ShowProgress(NUM_FILTERS)
        UpdateProgress(vtkObject)
    """
    logger.debug(f"Creating progress handler with {number_of_filters} filters, type={dialog_type}")
    progress: List[float] = [0]
    last_obj_progress: List[float] = [0]
    if dialog_type == "ProgressDialog":
        try:
            dlg = ProgressDialog(wx.GetApp().GetTopWindow(), 100)
        except (wx.PyNoAppError, AttributeError) as e:
            logger.error(f"Error creating progress dialog: {e}")
            return lambda obj, label: 0

    # when the pipeline is larger than 1, we have to consider this object
    # percentage
    number_of_filters = max(number_of_filters, 1)
    ratio = 100.0 / number_of_filters

    def UpdateProgress(obj: Union[float, int, "vtkAlgorithm"], label: str = "") -> float:
        """
        Show progress on GUI according to pipeline execution.
        """
        # object progress is cummulative and is between 0.0 - 1.0
        # is necessary verify in case is sending the progress
        # represented by number in case multiprocess, not vtk object
        if isinstance(obj, float) or isinstance(obj, int):
            obj_progress = obj
        else:
            obj_progress = obj.GetProgress()

        # as it is cummulative, we need to compute the diference, to be
        # appended on the interface
        if obj_progress < last_obj_progress[0]:  # current obj != previous obj
            difference = obj_progress  # 0
        else:  # current obj == previous obj
            difference = obj_progress - last_obj_progress[0]

        last_obj_progress[0] = obj_progress

        # final progress status value
        progress[0] = progress[0] + ratio * difference
        # Tell GUI to update progress status value
        if dialog_type == "GaugeProgress":
            logger.debug(f"Updating gauge progress: value={progress[0]}, label={label}")
            Publisher.sendMessage("Update status in GUI", value=progress[0], label=label)
        else:
            if progress[0] >= 99.999:
                progress[0] = 100

            if not (dlg.Update(progress[0], label)):
                logger.info("Progress dialog canceled by user")
                dlg.Close()

        return progress[0]

    return UpdateProgress


class Text:
    def __init__(self):
        self.layer: int = 99
        self.children = []
        property = vtkTextProperty()
        property.SetFontSize(const.TEXT_SIZE)
        property.SetFontFamilyToArial()
        property.BoldOff()
        property.ItalicOff()
        property.ShadowOn()
        property.SetJustificationToLeft()
        property.SetVerticalJustificationToTop()
        property.SetColor(const.TEXT_COLOUR)
        self.property = property

        mapper = vtkTextMapper()
        mapper.SetTextProperty(property)
        self.mapper = mapper

        actor = vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        actor.PickableOff()
        self.actor = actor

        self.SetPosition(const.TEXT_POS_LEFT_UP)

    def SetColour(self, colour: Sequence[float]) -> None:
        self.property.SetColor(colour)

    def ShadowOff(self) -> None:
        self.property.ShadowOff()

    def BoldOn(self) -> None:
        self.property.BoldOn()

    def SetSize(self, size: int) -> None:
        self.property.SetFontSize(size)

    def SetValue(self, value: Union[int, float, str]) -> None:
        if isinstance(value, int) or isinstance(value, float):
            value = str(value)
            if sys.platform == "win32":
                value += ""  # Otherwise 0 is not shown under win32
        # With some encoding in some dicom fields (like name) raises a
        # UnicodeEncodeError because they have non-ascii characters. To avoid
        # that we encode in utf-8.
        if sys.platform == "win32":
            self.mapper.SetInput(value.encode("utf-8", errors="replace"))
        else:
            try:
                self.mapper.SetInput(value.encode("latin-1"))
            except UnicodeEncodeError:
                self.mapper.SetInput(value.encode("utf-8", errors="replace"))

    def GetValue(self) -> str:
        return self.mapper.GetInput()

    def SetCoilDistanceValue(self, value: Union[int, float, str]) -> None:
        # TODO: Not being used anymore. Can be deleted.
        if isinstance(value, int) or isinstance(value, float):
            value = "Dist: " + str(f"{value:06.2f}") + " mm"
            if sys.platform == "win32":
                value += ""  # Otherwise 0 is not shown under win32
                # With some encoding in some dicom fields (like name) raises a
                # UnicodeEncodeError because they have non-ascii characters. To avoid
                # that we encode in utf-8.

        if sys.platform == "win32":
            self.mapper.SetInput(value.encode("utf-8"))
        else:
            try:
                self.mapper.SetInput(value.encode("latin-1"))
            except UnicodeEncodeError:
                self.mapper.SetInput(value.encode("utf-8"))

    def SetPosition(self, position: Tuple[float, float]) -> None:
        self.actor.GetPositionCoordinate().SetValue(position[0], position[1])

    def GetPosition(self) -> Tuple[float, float, float]:
        return self.actor.GetPositionCoordinate().GetValue()

    def SetJustificationToRight(self) -> None:
        self.property.SetJustificationToRight()

    def SetJustificationToCentered(self) -> None:
        self.property.SetJustificationToCentered()

    def SetVerticalJustificationToBottom(self) -> None:
        self.property.SetVerticalJustificationToBottom()

    def SetVerticalJustificationToCentered(self) -> None:
        self.property.SetVerticalJustificationToCentered()

    def Show(self, value: bool = True) -> None:
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()

    def Hide(self) -> None:
        self.actor.VisibilityOff()


class TextZero:
    def __init__(self):
        self.layer = 99
        self.children = []
        property = vtkTextProperty()
        property.SetFontSize(const.TEXT_SIZE_LARGE)
        property.SetFontFamilyToArial()
        property.BoldOn()
        property.ItalicOff()
        # property.ShadowOn()
        property.SetJustificationToLeft()
        property.SetVerticalJustificationToTop()
        property.SetColor(const.TEXT_COLOUR)
        self.property = property

        actor = vtkTextActor()
        actor.GetTextProperty().ShallowCopy(property)
        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        actor.PickableOff()
        self.actor = actor

        self.text = ""
        self.position = (0, 0)
        self.symbolic_syze = wx.FONTSIZE_MEDIUM
        self.bottom_pos = False
        self.right_pos = False

    def SetColour(self, colour: Sequence[float]) -> None:
        self.property.SetColor(colour)

    def ShadowOff(self) -> None:
        self.property.ShadowOff()

    def SetSize(self, size: int) -> None:
        self.property.SetFontSize(size)
        self.actor.GetTextProperty().ShallowCopy(self.property)

    def SetSymbolicSize(self, size: int) -> None:
        self.symbolic_syze = size

    def SetValue(self, value: Union[int, float, str]) -> None:
        if isinstance(value, int) or isinstance(value, float):
            value = str(value)
            if sys.platform == "win32":
                value += ""  # Otherwise 0 is not shown under win32
        # With some encoding in some dicom fields (like name) raises a
        # UnicodeEncodeError because they have non-ascii characters. To avoid
        # that we encode in utf-8.
        try:
            self.actor.SetInput(value.encode("cp1252"))
        except UnicodeEncodeError:
            self.actor.SetInput(value.encode("utf-8", "surrogatepass"))

        self.text = value

    def SetPosition(self, position: Tuple[float, float]) -> None:
        self.position = position
        self.actor.GetPositionCoordinate().SetValue(position[0], position[1])

    def GetPosition(self) -> Tuple[float, float, float]:
        return self.actor.GetPositionCoordinate().GetValue()

    def SetJustificationToRight(self) -> None:
        self.property.SetJustificationToRight()

    def SetJustificationToCentered(self) -> None:
        self.property.SetJustificationToCentered()

    def SetVerticalJustificationToBottom(self) -> None:
        self.property.SetVerticalJustificationToBottom()

    def SetVerticalJustificationToCentered(self) -> None:
        self.property.SetVerticalJustificationToCentered()

    def Show(self, value: bool = True) -> None:
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()

    def Hide(self) -> None:
        self.actor.VisibilityOff()

    def draw_to_canvas(self, gc: wx.GraphicsContext, canvas: "CanvasRendererCTX") -> None:
        coord = vtkCoordinate()
        coord.SetCoordinateSystemToNormalizedDisplay()
        coord.SetValue(*self.position)
        x, y = coord.GetComputedDisplayValue(canvas.evt_renderer)
        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font.SetSymbolicSize(self.symbolic_syze)
        font.Scale(canvas.viewer.GetContentScaleFactor())
        if self.bottom_pos or self.right_pos:
            w, h = canvas.calc_text_size(self.text, font)
            if self.right_pos:
                x -= w
            if self.bottom_pos:
                y += h
        canvas.draw_text(self.text, (x, y), font=font)


def numpy_to_vtkMatrix4x4(affine: "np.ndarray") -> vtkMatrix4x4:
    """
    Convert a numpy 4x4 array to a vtk 4x4 matrix
    """
    import numpy as np

    matrix = vtkMatrix4x4()
    for row in range(4):
        for col in range(4):
            matrix.SetElement(row, col, affine[row, col])
    return matrix


@handle_errors(
    error_message="Error extracting image from VTK reader",
    category=ErrorCategory.VTK,
    severity=ErrorSeverity.ERROR,
    reraise=False,
)
def get_image_from_reader(reader, slice_interval=0):
    """
    Extract the vtkImageData from a VTK reader, optionally skipping slices.

    Args:
        reader: A VTK reader object (like vtkGDCMImageReader) with loaded data
        slice_interval: Interval to skip slices (0 means no skipping)

    Returns:
        vtkImageData: The image data extracted from the reader
    """
    logger.debug(f"Extracting image from reader with slice interval: {slice_interval}")

    image_data = reader.GetOutput()

    # If slice_interval is 0, return the original image
    if slice_interval == 0:
        logger.debug("No slice interval specified, returning original image")
        return image_data

    # Otherwise, extract slices with the specified interval
    logger.debug(f"Extracting slices with interval: {slice_interval}")
    extent = image_data.GetExtent()

    # Create a VOI (Volume Of Interest) extractor to select specific slices
    voi = vtkExtractVOI()
    voi.SetInputData(image_data)

    # Set the same X and Y extents
    voi.SetVOI(
        extent[0],
        extent[1],  # X min, max
        extent[2],
        extent[3],  # Y min, max
        extent[4],
        extent[5],  # Z min, max
    )

    # Set the sample rate to skip slices according to the interval
    voi.SetSampleRate(1, 1, slice_interval + 1)
    voi.Update()

    logger.debug("Slice extraction completed")
    return voi.GetOutput()


@handle_errors(
    error_message="Error creating polydata from file",
    category=ErrorCategory.IO,
    severity=ErrorSeverity.ERROR,
    reraise=False,
)
def CreateObjectPolyData(filename: str) -> Any:
    """
    Reads file (STL, PLY, OBJ or VTP) and returns a vtkPolyData containing the 3D model.
    """
    logger.debug(f"Creating polydata from file: {filename}")

    filename = utils.decode(filename, const.FS_ENCODE)
    if filename:
        if filename.lower().endswith(".stl"):
            reader = vtkSTLReader()
        elif filename.lower().endswith(".ply"):
            reader = vtkPLYReader()
        elif filename.lower().endswith(".obj"):
            reader = vtkOBJReader()
        elif filename.lower().endswith(".vtp"):
            reader = vtkXMLPolyDataReader()
        else:
            wx.MessageBox(_("File format not reconized by InVesalius"), _("Import surface error"))
            return
    else:
        filename = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")
        reader = vtkSTLReader()

    if _has_win32api:
        obj_name = win32api.GetShortPathName(filename).encode(const.FS_ENCODE)
    else:
        obj_name = filename.encode(const.FS_ENCODE)

    reader.SetFileName(obj_name)
    reader.Update()
    obj_polydata = reader.GetOutput()

    if obj_polydata.GetNumberOfPoints() == 0:
        wx.MessageBox(
            _("InVesalius was not able to import this surface"), _("Import surface error")
        )
        obj_polydata = None

    return obj_polydata
