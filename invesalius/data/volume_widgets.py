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

from vtkmodules.vtkFiltersSources import vtkPlaneSource
from vtkmodules.vtkInteractionWidgets import vtkImagePlaneWidget
from vtkmodules.vtkRenderingCore import vtkActor, vtkCellPicker, vtkPolyDataMapper
from gui.dialogs import ProgressBarHandler
import time
from wx.lib.pubsub import Publisher
AXIAL, SAGITAL, CORONAL = 0, 1, 2
PLANE_DATA = {AXIAL: ["z", (0, 0, 1)], SAGITAL: ["x", (1, 0, 0)], CORONAL: ["y", (0, 1, 0)]}


class Plane:
    """
    How to use:

    import ivVolumeWidgets as vw
    imagedata = v16.GetOutput()
    axial_plane = vw.Plane()
    axial_plane.SetRender(ren)
    axial_plane.SetInteractor(pane)
    axial_plane.SetOrientation(vw.CORONAL)
    axial_plane.SetInput(imagedata)
    axial_plane.Show()
    axial_plane.Update()
    """

    def __init__(self):
        self.orientation = AXIAL
        self.render = None
        self.iren = None
        self.index = 0
        self.source = None
        self.widget = None
        self.actor = None

    def SetOrientation(self, orientation=AXIAL):
        self.orientation = orientation

    def SetRender(self, render=None):
        self.render = render

    def SetInteractor(self, iren=None):
        self.iren = iren

    def SetSliceIndex(self, index):
        self.index = 0
        try:
            self.widget.SetSliceIndex(int(index))
        except AttributeError:
            pass
        else:
            self.Update()
            if self.widget.GetEnabled():
                print("send signal - update slice info in panel and in 2d")

    def SetInput(self, imagedata):
        axes = PLANE_DATA[self.orientation][0]  # "x", "y" or "z"
        colour = PLANE_DATA[self.orientation][1]

        # if self.orientation == SAGITAL:
        #    spacing = min(imagedata.GetSpacing())
        #    permute = vtk.vtkImagePermute()
        #    permute.SetInput(imagedata)
        #    permute.GetOutput().ReleaseDataFlagOn()
        #    permute.SetOutputSpacing(spacing, spacing, spacing)
        #    imagedata = permute.GetOutput()
        progress_dialog = ProgressBarHandler(self.iren.GetParent(), title="Loading Image Data", msg="Processing...", max_value=100)
        for i in range(101):  
            time.sleep(0.05) 
            Publisher.sendMessage("Update Progress bar", i, f"Loading slice {i}...")
            if progress_dialog.was_cancelled():
                break

        # Picker for enabling plane motion.
        # Allows selection of a cell by shooting a ray into graphics window
        picker = vtkCellPicker()
        picker.SetTolerance(0.005)
        picker.PickFromListOn()

        # 3D widget for reslicing image data.
        # This 3D widget defines a plane that can be interactively placed in an image volume.
        widget = vtkImagePlaneWidget()
        widget.SetInput(imagedata)
        widget.SetSliceIndex(self.index)
        widget.SetPicker(picker)
        widget.SetKeyPressActivationValue(axes)
        widget.SetInteractor(self.iren)
        widget.TextureVisibilityOff()
        widget.DisplayTextOff()
        widget.RestrictPlaneToVolumeOff()
        exec("widget.SetPlaneOrientationTo" + axes.upper() + "Axes()")
        widget.AddObserver("InteractionEvent", self.Update)
        self.widget = widget

        prop = widget.GetPlaneProperty()
        prop.SetColor(colour)

        # Syncronize coloured outline with texture appropriately
        source = vtkPlaneSource()
        source.SetOrigin(widget.GetOrigin())
        source.SetPoint1(widget.GetPoint1())
        source.SetPoint2(widget.GetPoint2())
        source.SetNormal(widget.GetNormal())
        self.source = source

        mapper = vtkPolyDataMapper()
        mapper.SetInput(source.GetOutput())

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetTexture(widget.GetTexture())
        actor.VisibilityOff()
        self.actor = actor

        self.render.AddActor(actor)

        

    def Update(self, x=None, y=None):
        source = self.source
        widget = self.widget

        source.SetOrigin(widget.GetOrigin())
        source.SetPoint1(widget.GetPoint1())
        source.SetPoint2(widget.GetPoint2())
        source.SetNormal(widget.GetNormal())

    def Show(self, show=1):
        actor = self.actor
        widget = self.widget

        if show:
            actor.VisibilityOn()
            widget.On()
        else:
            actor.VisibilityOff()
            widget.Off()
