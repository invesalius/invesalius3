#!/usr/bin/env python3
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
import logging
import os
import sys
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Sequence, SupportsInt, Tuple, Union

import wx
from vtkmodules.vtkCommonMath import vtkMatrix4x4
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
from invesalius.error_handling import ErrorCategory, ErrorSeverity, handle_errors
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

if TYPE_CHECKING:
    import numpy as np
    from vtkmodules.vtkCommonExecutionModel import vtkAlgorithm

    from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX

# Initialize logger
logger = logging.getLogger("invesalius.data.vtk_utils")

class ProgressDialog:
    def __init__(self, parent: Optional[wx.Window], maximum: int, abort: bool = False):
        self.title = "InVesalius 3"
        self.msg = _("Loading DICOM files")
        self.maximum = maximum
        self.current = 0
        self.style = wx.PD_APP_MODAL
        if abort:
            self.style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT

        self.dlg = wx.ProgressDialog(
            self.title, self.msg, maximum=self.maximum, parent=parent, style=self.style
        )

        self.dlg.Bind(wx.EVT_BUTTON, self.Cancel)
        self.dlg.SetSize(wx.Size(250, 150))

    def Cancel(self, evt: wx.CommandEvent) -> None:
        Publisher.sendMessage("Cancel DICOM load")

    def Update(self, value: SupportsInt, message: str) -> Union[Tuple[bool, bool], bool]:
        if int(value) != self.maximum:
            try:
                return self.dlg.Update(int(value), message)
            # TODO:
            # Exception in the Wtindows XP 64 Bits with wxPython 2.8.10
            except wx.PyAssertionError:
                return True
        else:
            return False

    def Close(self) -> None:
        self.dlg.Destroy()


if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
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


def ShowProgress(
    number_of_filters: int = 1, dialog_type: str = "GaugeProgress"
) -> Callable[[Union[float, int, "vtkAlgorithm"], str], float]:
    """
    To use this closure, do something like this:
        UpdateProgress = ShowProgress(NUM_FILTERS)
        UpdateProgress(vtkObject)
    """
    progress: List[float] = [0]
    last_obj_progress: List[float] = [0]
    if dialog_type == "ProgressDialog":
        try:
            dlg = ProgressDialog(wx.GetApp().GetTopWindow(), 100)
        except (wx.PyNoAppError, AttributeError):
            return lambda obj, label: 0

    # when the pipeline is larger than 1, we have to consider this object
    # percentage
    number_of_filters = max(number_of_filters, 1)
    ratio = 100.0 / number_of_filters

    def UpdateProgress(obj: Union[float, int, "vtkAlgorithm"], label: str = "") -> float:
        """
        Show progress on GUI according to pipeline execution.
        """
        try:
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
                Publisher.sendMessage("Update status in GUI", value=progress[0], label=label)
            else:
                if progress[0] >= 99.999:
                    progress[0] = 100

                if not (dlg.Update(progress[0], label)):
                    dlg.Close()

            return progress[0]
        except Exception as e:
            logger.error(f"Error updating progress: {e}")
            return 0

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

    @handle_errors(
        error_message="Error setting text value",
        category=ErrorCategory.EXTERNAL_LIBRARY,
        severity=ErrorSeverity.WARNING,
    )
    def SetValue(self, value: Union[int, float, str]) -> None:
        try:
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
        except Exception as e:
            logger.error(f"Failed to set text value: {e}")
            raise

    def GetValue(self) -> str:
        return self.mapper.GetInput()

    @handle_errors(
        error_message="Error setting coil distance value",
        category=ErrorCategory.EXTERNAL_LIBRARY,
        severity=ErrorSeverity.WARNING,
    )
    def SetCoilDistanceValue(self, value: Union[int, float, str]) -> None:
        # TODO: Not being used anymore. Can be deleted.
        try:
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
        except Exception as e:
            logger.error(f"Failed to set coil distance value: {e}")
            raise

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
        self.layer: int = 99
        # property = vtkTextProperty()
        # property.SetFontSize(const.TEXT_SIZE)
        # property.SetFontFamilyToArial()
        # property.BoldOff()
        # property.ItalicOff()
        # property.ShadowOn()
        # property.SetJustificationToLeft()
        # property.SetVerticalJustificationToTop()
        # property.SetColor(const.TEXT_COLOUR)
        # self.property = property

        # mapper = vtkTextMapper()
        # mapper.SetTextProperty(property)
        # self.mapper = mapper

        # actor = vtkActor2D()
        # actor.SetMapper(mapper)
        # actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        # actor.PickableOff()
        # self.actor = actor

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

        self.text_size = const.TEXT_SIZE
        self.text_colour = const.TEXT_COLOUR
        self.visibility = False
        self.value = ""
        self.position = const.TEXT_POS_LEFT_UP
        # self.SetPosition(const.TEXT_POS_LEFT_UP)

    def SetColour(self, colour: Sequence[float]) -> None:
        self.text_colour = colour

    def ShadowOff(self) -> None:
        pass  # self.property.ShadowOff()

    def SetSize(self, size: int) -> None:
        self.text_size = size
        self.property.SetFontSize(size)

    def SetSymbolicSize(self, size: int) -> None:
        self.text_size = const.SYMBOLIC_SIZES[size]
        self.property.SetFontSize(const.SYMBOLIC_SIZES[size])

    @handle_errors(
        error_message="Error setting text value",
        category=ErrorCategory.EXTERNAL_LIBRARY,
        severity=ErrorSeverity.WARNING,
    )
    def SetValue(self, value: Union[int, float, str]) -> None:
        try:
            if isinstance(value, int) or isinstance(value, float):
                value = str(value)
                if sys.platform == "win32":
                    value += ""  # Otherwise 0 is not shown under win32
            # With some encoding in some dicom fields (like name) raises a
            # UnicodeEncodeError because they have non-ascii characters. To avoid
            # that we encode in utf-8.
            self.value = value
            
            # Update the mapper with the value
            try:
                if sys.platform == "win32":
                    self.mapper.SetInput(value.encode("latin-1"))
                else:
                    self.mapper.SetInput(value.encode("utf-8"))
            except UnicodeEncodeError:
                self.mapper.SetInput(value.encode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to set text value: {e}")
            raise

    def SetPosition(self, position: Tuple[float, float]) -> None:
        self.position = position
        self.actor.GetPositionCoordinate().SetValue(position[0], position[1])

    def GetPosition(self) -> Tuple[float, float, float]:
        return self.position

    def SetJustificationToRight(self) -> None:
        self.property.SetJustificationToRight()

    def SetJustificationToCentered(self) -> None:
        self.property.SetJustificationToCentered()

    def SetVerticalJustificationToBottom(self) -> None:
        self.property.SetVerticalJustificationToBottom()

    def SetVerticalJustificationToCentered(self) -> None:
        self.property.SetVerticalJustificationToCentered()

    def Show(self, value: bool = True) -> None:
        self.visibility = value
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()

    def Hide(self) -> None:
        self.visibility = False
        self.actor.VisibilityOff()

    def draw_to_canvas(self, gc: wx.GraphicsContext, canvas: "CanvasRendererCTX") -> None:
        if not self.visibility:
            return

        size = canvas.GetSize()
        text_width, text_height = gc.GetFullTextExtent(self.value)[0:2]

        if hasattr(self, "GetPosition"):
            x, y, z = self.GetPosition()
            x, y = size[0] * x, size[1] * y
        else:
            x, y = size[0] * self.position[0], size[1] * self.position[1]

        gc.SetTextForeground(self.text_colour)
        gc.SetFont(
            wx.Font(self.text_size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        )

        gc.DrawText(self.value, x, y)

@handle_errors(
    error_message="Error converting numpy array to vtkMatrix4x4",
    category=ErrorCategory.EXTERNAL_LIBRARY,
    severity=ErrorSeverity.ERROR,
)
def numpy_to_vtkMatrix4x4(affine: "np.ndarray") -> vtkMatrix4x4:
    """
    Convert a numpy 4x4 array to a vtk 4x4 matrix
    """
    try:
        matrix = vtkMatrix4x4()
        for i in range(4):
            for j in range(4):
                matrix.SetElement(i, j, affine[i, j])
        logger.debug("Successfully converted numpy array to vtkMatrix4x4")
        return matrix
    except Exception as e:
        logger.error(f"Failed to convert numpy array to vtkMatrix4x4: {e}")
        raise

@handle_errors(
    error_message="Error creating VTK object from file",
    category=ErrorCategory.EXTERNAL_LIBRARY,
    severity=ErrorSeverity.ERROR,
)
def CreateObjectPolyData(filename: str) -> Any:
    """
    Creates a vtkPolyData object from the given filename.
    """
    try:
        if filename.lower().endswith('.stl'):
            reader = vtkSTLReader()
            logger.info(f"Loading STL file: {filename}")
        elif filename.lower().endswith('.ply'):
            reader = vtkPLYReader()
            logger.info(f"Loading PLY file: {filename}")
        elif filename.lower().endswith('.obj'):
            reader = vtkOBJReader()
            logger.info(f"Loading OBJ file: {filename}")
        elif filename.lower().endswith('.vtp'):
            reader = vtkXMLPolyDataReader()
            logger.info(f"Loading VTP file: {filename}")
        else:
            logger.error(f"Unsupported file format: {filename}")
            raise ValueError("Unsupported file format")
            
        reader.SetFileName(filename)
        reader.Update()
        
        logger.debug(f"Successfully loaded polydata from {filename}")
        return reader.GetOutput()
    except Exception as e:
        logger.error(f"Failed to create object polydata from file {filename}: {e}")
        raise
