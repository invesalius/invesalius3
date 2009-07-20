#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------


import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
import wx
import wx.lib.pubsub as ps

import data.slice_ as sl
import constants as const
import project
import cursor_actors as ca

class Viewer(wx.Panel):
    
    def __init__(self, prnt, orientation='AXIAL'):
        wx.Panel.__init__(self, prnt, size=wx.Size(320, 300))
        
        colour = [255*c for c in const.ORIENTATION_COLOUR[orientation]]
        self.SetBackgroundColour(colour)
        
        # Interactor aditional style
        self.modes = ['DEFAULT']
        self.mouse_pressed = 0
        
        self.__init_gui()

        self.orientation = orientation
        self.slice_number = 0
        
        # VTK pipeline and actors
        self.__config_interactor()
        self.pick = vtk.vtkCellPicker()
        
        self.__bind_events()
        self.__bind_events_wx()

    def __init_gui(self):
    
        interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())

        scroll = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        self.scroll = scroll

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(interactor, 1, wx.EXPAND|wx.GROW)

        background_sizer = wx.BoxSizer(wx.HORIZONTAL)
        background_sizer.AddSizer(sizer, 1, wx.EXPAND|wx.GROW|wx.ALL, 2)
        background_sizer.Add(scroll, 0, wx.EXPAND|wx.GROW)
        self.SetSizer(background_sizer)
        background_sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.interactor = interactor

    def __config_interactor(self):
                
        ren = vtk.vtkRenderer()

        interactor = self.interactor
        interactor.GetRenderWindow().AddRenderer(ren)

        self.cam = ren.GetActiveCamera()
        self.ren = ren
        
        self.AppendMode('EDITOR')
        
    def AppendMode(self, mode):
    
        # Retrieve currently set modes
        self.modes.append(mode)
        
        # All modes and bindings
        action = {'DEFAULT': {
                             "MouseMoveEvent": self.OnCrossMove,
                             "LeftButtonPressEvent": self.OnMouseClick,
                             "LeftButtonReleaseEvent": self.OnMouseRelease
                             },
                  'EDITOR': {
                            "MouseMoveEvent": self.OnBrushMove,
                            "LeftButtonPressEvent": self.OnBrushClick,
                            "LeftButtonReleaseEvent": self.OnMouseRelease
                            }
                 }

        # Bind method according to current mode
        style = vtk.vtkInteractorStyleImage()
        self.style = style
        self.interactor.SetInteractorStyle(style)
        
        # Check all modes set by user
        for mode in self.modes:
            # Check each event available for each mode
            for event in action[mode]:
                # Bind event
                style.AddObserver(event,
                                  action[mode][event])

        # Insert cursor
        cursor = ca.CursorCircle()
        cursor.SetOrientation(self.orientation)
        coordinates = {"SAGITAL": [self.slice_number, 0, 0],
                       "CORONAL": [0, self.slice_number, 0],
                       "AXIAL": [0, 0, self.slice_number]}
        cursor.SetPosition(coordinates[self.orientation])
        self.ren.AddActor(cursor.actor)
        self.ren.Render()
        
        self.cursor = cursor

        

    def OnMouseClick(self, obj, evt_vtk):
        self.mouse_pressed = 1

    def OnMouseRelease(self, obj, evt_vtk):
        self.mouse_pressed = 0

    def OnBrushClick(self, obj, evt_vtk):
        self.mouse_pressed = 1
        coord = self.GetCoordinate()
        print "Edit pixel region based on origin:", coord

    def OnBrushMove(self, obj, evt_vtk):
        coord = self.GetCoordinateCursor()
        self.cursor.SetPosition(coord)
        self.ren.Render()
        if self.mouse_pressed:
            print "Edit pixel region based on origin:", coord
            pixels = self.cursor.GetPixels()
            for coord in pixels:
                ps.Publisher().sendMessage('Erase mask pixel', coord)
            self.interactor.Render()
                
    def OnCrossMove(self, obj, evt_vtk):
        coord = self.GetCoordinate()
        # Update position in other slices
        if self.mouse_pressed:
            ps.Publisher().sendMessage('Update cursor position in slice',
                                        coord)
            ps.Publisher().sendMessage(('Set scroll position', 'SAGITAL'),
                                        coord[0])
            ps.Publisher().sendMessage(('Set scroll position', 'CORONAL'),
                                        coord[1])
            ps.Publisher().sendMessage(('Set scroll position', 'AXIAL'),
                                        coord[2])
            
            
    def GetCoordinate(self):
    
        # Find position
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        self.pick.Pick(mouse_x, mouse_y, 0, self.ren)
        x, y, z = self.pick.GetPickPosition()
        
        # First we fix the position origin, based on vtkActor bounds
        bounds = self.actor.GetBounds()
        bound_xi, bound_xf, bound_yi, bound_yf, bound_zi, bound_zf = bounds
        x = float(x - bound_xi)
        y = float(y - bound_yi)
        z = float(z - bound_zi)
        
        # Then we fix the porpotion, based on vtkImageData spacing
        spacing_x, spacing_y, spacing_z = self.imagedata.GetSpacing()
        x = x/spacing_x
        y = y/spacing_y
        z = z/spacing_z
        
        # Based on the current orientation, we define 3D position
        coordinates = {"SAGITAL": [self.slice_number, y, z],
                       "CORONAL": [x, self.slice_number, z],
                       "AXIAL": [x, y, self.slice_number]}
        coord = [int(coord) for coord in coordinates[self.orientation]]
        
        # According to vtkImageData extent, we limit min and max value
        # If this is not done, a VTK Error occurs when mouse is pressed outside
        # vtkImageData extent
        extent = self.imagedata.GetWholeExtent()
        extent_min = extent[0], extent[2], extent[4]
        extent_max = extent[1], extent[3], extent[5]
        for index in xrange(3):
            if coord[index] > extent_max[index]:
                coord[index] = extent_max[index]
            elif coord[index] < extent_min[index]:
                coord[index] = extent_min[index]
        #print "New coordinate: ", coord
        
        return coord
     
     
    def GetCoordinateCursor(self):
    
        # Find position
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        self.pick.Pick(mouse_x, mouse_y, 0, self.ren)
        x, y, z = self.pick.GetPickPosition()
        
        # First we fix the position origin, based on vtkActor bounds
        bounds = self.actor.GetBounds()
        bound_xi, bound_xf, bound_yi, bound_yf, bound_zi, bound_zf = bounds
        x = float(x - bound_xi)
        y = float(y - bound_yi)
        z = float(z - bound_zi)

        dx = bound_xf - bound_xi;
        dy = bound_yf - bound_yi
        dz = bound_zf - bound_zi

        dimensions = self.imagedata.GetDimensions()

        try:
            x = (x * dimensions[0]) / dx
        except ZeroDivisionError:
            x = self.slice_number
        try:
            y = (y * dimensions[1]) / dy
        except ZeroDivisionError:
            y = self.slice_number
        try:
            z = (z * dimensions[2]) / dz
        except ZeroDivisionError:
            z = self.slice_number
        
        return x,y,z
            
    def __bind_events(self):
        ps.Publisher().subscribe(self.LoadImagedata, 'Load slice to viewer')
        ps.Publisher().subscribe(self.SetColour, 'Change mask colour')
        ps.Publisher().subscribe(self.UpdateRender, 'Update slice viewer')
        ps.Publisher().subscribe(self.ChangeSliceNumber, ('Set scroll position', 
                                                     self.orientation))

    def __bind_events_wx(self):
        self.scroll.Bind(wx.EVT_SCROLL, self.OnScrollBar)

    def LoadImagedata(self, pubsub_evt):
        imagedata = pubsub_evt.data
        self.SetInput(imagedata)

    def SetInput(self, imagedata):

        self.imagedata = imagedata

        ren = self.ren
        interactor = self.interactor

        # Slice pipeline, to be inserted into current viewer
        slice_ = sl.Slice()
        if slice_.imagedata is None:
            slice_.SetInput(imagedata)

        actor = vtk.vtkImageActor()
        actor.SetInput(slice_.GetOutput())
        self.actor = actor

        colour = const.ORIENTATION_COLOUR[self.orientation]

        text_property = vtk.vtkTextProperty()
        text_property.SetFontSize(16)
        text_property.SetFontFamilyToTimes()
        text_property.BoldOn()
        text_property.SetColor(colour)

        text_actor = vtk.vtkTextActor()
        text_actor.SetInput("%d" % self.slice_number)
        text_actor.GetTextProperty().ShallowCopy(text_property)
        text_actor.SetPosition(2,2)
        self.text_actor = text_actor

        ren.AddActor(actor)
        #ren.AddActor(text_actor)
        self.__update_camera()

        max_slice_number = actor.GetSliceNumberMax()
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                                     max_slice_number)
        self.SetScrollPosition(0)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        self.__update_camera()

    def __update_camera(self):
        orientation = self.orientation

        cam = self.cam
        cam.SetFocalPoint(0, 0, 0)
        cam.SetPosition(const.CAM_POSITION[self.orientation])
        cam.SetViewUp(const.CAM_VIEW_UP[self.orientation])
        cam.ComputeViewPlaneNormal()
        cam.OrthogonalizeViewUp()
        cam.ParallelProjectionOn()        

        self.__update_display_extent()
        
        self.ren.ResetCamera()
        self.ren.Render()

    def __update_display_extent(self):

        pos = self.slice_number
        e = self.imagedata.GetWholeExtent()
        
        new_extent = {"SAGITAL": (pos, pos, e[2], e[3], e[4], e[5]),
                      "CORONAL": (e[0], e[1], pos, pos, e[4], e[5]),
                      "AXIAL": (e[0], e[1], e[2], e[3], pos, pos)}
                       
        self.actor.SetDisplayExtent(new_extent[self.orientation])
        self.ren.ResetCameraClippingRange()
        self.ren.Render()

    def UpdateRender(self, evt):
        self.interactor.Render()

    def SetScrollPosition(self, position):
        self.scroll.SetThumbPosition(position)
        self.OnScrollBar()

    def OnScrollBar(self, evt=None):
        pos = self.scroll.GetThumbPosition()
        self.SetSliceNumber(pos)
        self.interactor.Render()
        if evt:
            evt.Skip()

    def SetSliceNumber(self, index):
        self.text_actor.SetInput(str(index))
        self.slice_number = index
        self.__update_display_extent()

    def ChangeSliceNumber(self, pubsub_evt):
        index = pubsub_evt.data
        self.SetSliceNumber(index)
        self.scroll.SetThumbPosition(index)
        self.interactor.Render()

    def SetColour(self, pubsub_evt):
        colour_wx = pubsub_evt.data
        colour_vtk = [colour/float(255) for colour in colour_wx]
        #self.editor.SetColour(colour_vtk)
        self.interactor.Render()

