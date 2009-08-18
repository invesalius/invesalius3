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

import itertools

import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
import wx
import wx.lib.pubsub as ps

import data.slice_ as sl
import constants as const
import project
import cursor_actors as ca

from slice_data import SliceData

class Viewer(wx.Panel):

    def __init__(self, prnt, orientation='AXIAL'):
        wx.Panel.__init__(self, prnt, size=wx.Size(320, 300))

        colour = [255*c for c in const.ORIENTATION_COLOUR[orientation]]
        self.SetBackgroundColour(colour)

        # Interactor additional style
        self.modes = []#['DEFAULT']
        self.mouse_pressed = 0

        # All renderers and image actors in this viewer
        self.slice_data_list = []
        # The layout from slice_data, the first is number of cols, the second
        # is the number of rows
        self.layout = (1, 1)

        self.__init_gui()

        self.orientation = orientation
        self.slice_number = 0

        self._brush_cursor_op = const.DEFAULT_BRUSH_OP
        self._brush_cursor_size = const.BRUSH_SIZE
        self._brush_cursor_colour = const.BRUSH_COLOUR
        self._brush_cursor_type = const.DEFAULT_BRUSH_OP
        self.cursor = None
        # VTK pipeline and actors
        #self.__config_interactor()
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

    def append_mode(self, mode):

        #TODO: Temporary
        self.modes = []

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
                            "LeftButtonReleaseEvent": self.OnMouseRelease,
                            "EnterEvent": self.OnEnterInteractor,
                            "LeaveEvent": self.OnLeaveInteractor
                            },
                  'PAN':{
                         "MouseMoveEvent": self.OnPanMove,
                         "LeftButtonPressEvent": self.OnPanClick,
                         "LeftButtonReleaseEvent": self.OnReleaseModes
                        },
                  'SPIN':{
                         "MouseMoveEvent": self.OnSpinMove,
                         "LeftButtonPressEvent": self.OnSpinClick,
                         "LeftButtonReleaseEvent": self.OnReleaseModes
                        },
                  'ZOOM':{
                         "MouseMoveEvent": self.OnZoomMove,
                         "LeftButtonPressEvent": self.OnZoomClick,
                         "LeftButtonReleaseEvent": self.OnReleaseModes,
                         "RightButtonReleaseEvent":self.OnUnZoom
                        },
                  'ZOOMSELECT':{
                         "RightButtonReleaseEvent":self.OnUnZoom
                              }
                 }

        # Bind method according to current mode
        if(mode == 'ZOOMSELECT'):
            style = vtk.vtkInteractorStyleRubberBandZoom()
        else:
            style = vtk.vtkInteractorStyleImage()

        # Check all modes set by user
        for mode in self.modes:
            # Check each event available for each mode
            for event in action[mode]:
                # Bind event
                style.AddObserver(event,
                                  action[mode][event])
        self.style = style
        self.interactor.SetInteractorStyle(style)
    
    
    def Reposition(self):
        """
        Based on code of method Zoom in the 
        vtkInteractorStyleRubberBandZoom, the of 
        vtk 5.4.3
        """
        size = self.ren.GetSize()
        
        if (size[0] <= size[1] + 100):
            
            bound = self.actor.GetBounds()
            
            width = abs((bound[3] - bound[2]) * -1)
            height = abs((bound[1] - bound[0]) * -1)     
        
            origin = self.ren.GetOrigin()        
            cam = self.ren.GetActiveCamera()
        
            min = []
            min.append(bound[0])
            min.append(bound[2])
          
            rbcenter = []
            rbcenter.append(min[0] + 0.5 * width)
            rbcenter.append(min[1] + 0.5 * height)
            rbcenter.append(0)
            
            self.ren.SetDisplayPoint(rbcenter)
            self.ren.DisplayToView()
            self.ren.ViewToWorld()
            
            worldRBCenter = self.ren.GetWorldPoint()
            worldRBCenter = list(worldRBCenter)
            
            invw = 1.0/worldRBCenter[3]
              
            worldRBCenter[0] *= invw
            worldRBCenter[1] *= invw
            worldRBCenter[2] *= invw
            
            winCenter = []
            winCenter.append(origin[0] + 0.5 * size[0])
            winCenter.append(origin[1] + 0.5 * size[1])
            winCenter.append(0)
            
            self.ren.SetDisplayPoint(winCenter)
            self.ren.DisplayToView()
            self.ren.ViewToWorld()
                    
            worldWinCenter = list(self.ren.GetWorldPoint())
            invw = 1.0/worldWinCenter[3]
            worldWinCenter[0] *= invw
            worldWinCenter[1] *= invw
            worldWinCenter[2] *= invw
            
            translation = []
            translation.append(worldRBCenter[0] - worldWinCenter[0])
            translation.append(worldRBCenter[1] - worldWinCenter[1])
            translation.append(worldRBCenter[2] - worldWinCenter[2])
            
            if (width > height):
                cam.Zoom(size[0] / width)    
            else:
                cam.Zoom(size[1] / height)
               
        self.interactor.Render()
                    
    
    def ChangeEditorMode(self, pubsub_evt):
        self.append_mode('EDITOR')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))

    def ChangeSpinMode(self, pubsub_evt):
        self.append_mode('SPIN')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZING))
        
    def ChangeZoomMode(self, pubsub_evt):
        self.append_mode('ZOOM')
        self.mouse_pressed = 0
        ICON_IMAGE = wx.Image("../icons/tool_zoom.png",wx.BITMAP_TYPE_PNG)
        self.interactor.SetCursor(wx.CursorFromImage(ICON_IMAGE))

    def ChangePanMode(self, pubsub_evt):
        self.append_mode('PAN')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZING))

    def ChangeZoomSelectMode(self, pubsub_evt):
        self.append_mode('ZOOMSELECT')
        ICON_IMAGE = wx.Image("../icons/tool_zoom.png",wx.BITMAP_TYPE_PNG)
        self.interactor.SetCursor(wx.CursorFromImage(ICON_IMAGE))

    def OnPanMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Pan()
            evt.OnRightButtonDown()

    def OnPanClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartPan()

    def OnZoomMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Dolly()
            evt.OnRightButtonDown()

    def OnZoomClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartDolly()
    
    def OnUnZoom(self, evt, obj):
        self.ren.ResetCamera()
        self.ren.ResetCameraClippingRange()
        self.Reposition()
    
    def OnSpinMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Spin()
            evt.OnRightButtonDown()

    def OnSpinClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartSpin()

    def OnReleaseModes(self, evt, obj):
        self.mouse_pressed = 0

    def OnEnterInteractor(self, obj, evt):
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))

    def OnLeaveInteractor(self, obj, evt):
        for slice_data in self.slice_data_list:
            slice_data.cursor.Show(0)
        self.interactor.Render()

    def ChangeBrushSize(self, pubsub_evt):
        size = pubsub_evt.data
        self._brush_cursor_size = size
        for slice_data in self.slice_data_list:
            slice_data.cursor.SetSize(size)

    def ChangeBrushColour(self, pubsub_evt):
        vtk_colour = pubsub_evt.data[3]
        self._brush_cursor_colour = vtk_colour
        if (self.cursor):
            for slice_data in self.slice_data_list:
                slice_data.cursor.SetColour(vtk_colour)

    def SetBrushColour(self, pubsub_evt):
        colour_wx = pubsub_evt.data
        colour_vtk = [colour/float(255) for colour in colour_wx]
        self._brush_cursor_colour = colour_vtk
        if self.cursor:
            self.cursor.SetColour(colour_vtk)
            self.interactor.Render()

    def ChangeBrushActor(self, pubsub_evt):
        brush_type = pubsub_evt.data
        for slice_data in self.slice_data_list:
            self._brush_cursor_type = brush_type
            #self.ren.RemoveActor(self.cursor.actor)

            if brush_type == const.BRUSH_SQUARE:
                cursor = ca.CursorRectangle()
            elif brush_type == const.BRUSH_CIRCLE:
                cursor = ca.CursorCircle()
            #self.cursor = cursor

            cursor.SetOrientation(self.orientation)
            coordinates = {"SAGITAL": [slice_data.number, 0, 0],
                           "CORONAL": [0, slice_data.number, 0],
                           "AXIAL": [0, 0, slice_data.number]}
            cursor.SetPosition(coordinates[self.orientation])
            cursor.SetSpacing(self.imagedata.GetSpacing())
            cursor.SetColour(self._brush_cursor_colour)
            cursor.SetSize(self._brush_cursor_size)
            slice_data.SetCursor(cursor)
        #self.ren.AddActor(cursor.actor)
        #self.ren.Render()
        self.interactor.Render()
        #self.cursor = cursor

    def OnMouseClick(self, obj, evt_vtk):
        self.mouse_pressed = 1

    def OnMouseRelease(self, obj, evt_vtk):
        self.mouse_pressed = 0

    def OnBrushClick(self, obj, evt_vtk):
        self.mouse_pressed = 1

        mouse_x, mouse_y = self.interactor.GetEventPosition()
        render = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = self.get_slice_data(render)
        self.pick.Pick(mouse_x, mouse_y, 0, render)

        coord = self.get_coordinate_cursor()
        slice_data.cursor.SetPosition(coord)
        slice_data.cursor.SetEditionPosition(
            self.get_coordinate_cursor_edition(slice_data))
        self.__update_cursor_position(slice_data, coord)
        #render.Render()

        evt_msg = {const.BRUSH_ERASE: 'Erase mask pixel',
                   const.BRUSH_DRAW: 'Add mask pixel',
                   const.BRUSH_THRESH: 'Edit mask pixel'}
        msg = evt_msg[self._brush_cursor_op]

        pixels = itertools.ifilter(self.test_operation_position,
                                   slice_data.cursor.GetPixels())
        ps.Publisher().sendMessage(msg, pixels)

        # FIXME: This is idiot, but is the only way that brush operations are
        # working when cross is disabled
        ps.Publisher().sendMessage('Update slice viewer')
        ps.Publisher().sendMessage('Update slice viewer')

    def OnBrushMove(self, obj, evt_vtk):
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        render = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = self.get_slice_data(render)

        # TODO: Improve!
        for i in self.slice_data_list:
            i.cursor.Show(0)
        slice_data.cursor.Show()

        self.pick.Pick(mouse_x, mouse_y, 0, render)
        coord = self.get_coordinate_cursor()
        slice_data.cursor.SetPosition(coord)
        slice_data.cursor.SetEditionPosition(
            self.get_coordinate_cursor_edition(slice_data))
        self.__update_cursor_position(slice_data, coord)

        if self._brush_cursor_op == const.BRUSH_ERASE:
            evt_msg = 'Erase mask pixel'
        elif self._brush_cursor_op == const.BRUSH_DRAW:
            evt_msg = 'Add mask pixel'
        elif self._brush_cursor_op == const.BRUSH_THRESH:
            evt_msg = 'Edit mask pixel'

        if self.mouse_pressed:
            pixels = itertools.ifilter(self.test_operation_position,
                                       slice_data.cursor.GetPixels())
            ps.Publisher().sendMessage(evt_msg, pixels)
            ps.Publisher().sendMessage('Update slice viewer')
        else:
            self.interactor.Render()

    def OnCrossMove(self, obj, evt_vtk):
        coord = self.get_coordinate()
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

    def get_slice_data(self, render):
        for slice_data in self.slice_data_list:
            if slice_data.renderer is render:
                return slice_data

    def get_coordinate(self):
        # Find position
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

    def get_coordinate_cursor(self):
        # Find position
        x, y, z = self.pick.GetPickPosition()
        return x, y, z

    def get_coordinate_cursor_edition(self, slice_data):
        # Find position
        actor = slice_data.actor
        slice_number = slice_data.number
        x, y, z = self.pick.GetPickPosition()

        # First we fix the position origin, based on vtkActor bounds
        bounds = actor.GetBounds()
        bound_xi, bound_xf, bound_yi, bound_yf, bound_zi, bound_zf = bounds
        x = float(x - bound_xi)
        y = float(y - bound_yi)
        z = float(z - bound_zi)

        dx = bound_xf - bound_xi
        dy = bound_yf - bound_yi
        dz = bound_zf - bound_zi

        dimensions = self.imagedata.GetDimensions()

        try:
            x = (x * dimensions[0]) / dx
        except ZeroDivisionError:
            x = slice_number
        try:
            y = (y * dimensions[1]) / dy
        except ZeroDivisionError:
            y = slice_number
        try:
            z = (z * dimensions[2]) / dz
        except ZeroDivisionError:
            z = slice_number

        return x, y, z

    def __bind_events(self):
        ps.Publisher().subscribe(self.LoadImagedata,
                                 'Load slice to viewer')
        ps.Publisher().subscribe(self.SetBrushColour,
                                 'Change mask colour')
        ps.Publisher().subscribe(self.UpdateRender,
                                 'Update slice viewer')
        ps.Publisher().subscribe(self.ChangeSliceNumber,
                                 ('Set scroll position',
                                  self.orientation))
        ###
        ps.Publisher().subscribe(self.ChangeBrushSize,
                                 'Set edition brush size')
        ps.Publisher().subscribe(self.ChangeBrushColour,
                                 'Add mask')
        ps.Publisher().subscribe(self.ChangeBrushActor,
                                 'Set brush format')
        ps.Publisher().subscribe(self.ChangeBrushOperation,
                                 'Set edition operation')
        ps.Publisher().subscribe(self.ChangePanMode,
                                 'Set Pan Mode')
        ps.Publisher().subscribe(self.ChangeEditorMode,
                                 'Set Editor Mode')
        ps.Publisher().subscribe(self.ChangeSpinMode,
                                 'Set Spin Mode')
        ps.Publisher().subscribe(self.ChangeZoomMode,
                                 'Set Zoom Mode')
        ps.Publisher().subscribe(self.ChangeZoomSelectMode,
                                 'Set Zoom Select Mode')

    def ChangeBrushOperation(self, pubsub_evt):
        print pubsub_evt.data
        self._brush_cursor_op = pubsub_evt.data

    def __bind_events_wx(self):
        self.scroll.Bind(wx.EVT_SCROLL, self.OnScrollBar)
        self.interactor.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

    def LoadImagedata(self, pubsub_evt):
        imagedata = pubsub_evt.data
        self.SetInput(imagedata)

    def load_renderers(self, image):
        proportion_x = 1.0 / self.layout[0]
        proportion_y = 1.0 / self.layout[1]
        # The (0,0) in VTK is in bottom left. So the creation from renderers
        # must be # in inverted order, from the top left to bottom right
        for j in xrange(self.layout[1]-1, -1, -1):
            for i in xrange(self.layout[0]):
                position = ((i*proportion_x, j * proportion_y,
                             (i+1)*proportion_x, (j+1)*proportion_y))
                slice_data = self.create_slice_window(image)
                slice_data.renderer.SetViewport(position)
                slice_data.SetCursor(self.__create_cursor())
                self.slice_data_list.append(slice_data)

    def __create_cursor(self):
        cursor = ca.CursorCircle()
        cursor.SetOrientation(self.orientation)
        #self.__update_cursor_position([i for i in actor_bound[1::2]])
        cursor.SetColour(self._brush_cursor_colour)
        cursor.SetSpacing(self.imagedata.GetSpacing())
        cursor.Show(0)
        self.cursor_ = cursor
        return cursor

    def SetInput(self, imagedata):
        self.imagedata = imagedata

        #ren = self.ren
        interactor = self.interactor

        # Slice pipeline, to be inserted into current viewer
        slice_ = sl.Slice()
        if slice_.imagedata is None:
            slice_.SetInput(imagedata)

        #actor = vtk.vtkImageActor()
        #actor.SetInput(slice_.GetOutput())
        self.load_renderers(slice_.GetOutput())
        ren = self.slice_data_list[0].renderer
        actor = self.slice_data_list[0].actor
        actor_bound = actor.GetBounds()
        self.actor = actor
        self.ren = ren
        self.cam = ren.GetActiveCamera()

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

        #ren.AddActor(actor)
        #ren.AddActor(text_actor)
        for slice_data in self.slice_data_list:
            self.__update_camera(slice_data)

        number_of_slices = self.layout[0] * self.layout[1]
        max_slice_number = actor.GetSliceNumberMax() / \
                number_of_slices
        if actor.GetSliceNumberMax() % number_of_slices:
            max_slice_number += 1
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                                     max_slice_number)
        self.set_scroll_position(0)

        actor_bound = actor.GetBounds()

        # Insert cursor
        self.append_mode('EDITOR')

        self.Reposition()
        
    def __update_cursor_position(self, slice_data, position):
        x, y, z = position
        if (slice_data.cursor):
            slice_number = slice_data.number
            actor_bound = slice_data.actor.GetBounds()

            yz = [actor_bound[1] + 1 + slice_number, y, z]
            xz = [x, actor_bound[3] - 1 - slice_number, z]
            xy = [x, y, actor_bound[5] + 1 + slice_number]

            proj = project.Project()
            orig_orien = proj.original_orientation

            if (orig_orien == const.SAGITAL):
                coordinates = {"SAGITAL": xy, "CORONAL": yz, "AXIAL": xz}
            elif(orig_orien == const.CORONAL):
                coordinates = {"SAGITAL": yz, "CORONAL": xy, "AXIAL": xz}
            else:
                coordinates = {"SAGITAL": yz, "CORONAL": xz, "AXIAL": xy}

            slice_data.cursor.SetPosition(coordinates[self.orientation])

    def SetOrientation(self, orientation):
        self.orientation = orientation
        for slice_data in self.slice_data_list:
            self.__update_camera(slice_data)

    def create_slice_window(self, imagedata):
        renderer = vtk.vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(renderer)
        actor = vtk.vtkImageActor()
        actor.SetInput(imagedata)
        renderer.AddActor(actor)
        slice_data = SliceData()
        slice_data.renderer = renderer
        slice_data.actor = actor
        return slice_data

    def __update_camera(self, slice_data):
        orientation = self.orientation
        proj = project.Project()
        orig_orien = proj.original_orientation

        cam = slice_data.renderer.GetActiveCamera()
        cam.SetFocalPoint(0, 0, 0)
        cam.SetViewUp(const.SLICE_POSITION[orig_orien][0][self.orientation])
        cam.SetPosition(const.SLICE_POSITION[orig_orien][1][self.orientation])
        cam.ComputeViewPlaneNormal()
        cam.OrthogonalizeViewUp()
        cam.ParallelProjectionOn()

        self.__update_display_extent(slice_data)

        slice_data.renderer.ResetCamera()
        slice_data.renderer.Render()

    def __update_display_extent(self, slice_data):
        e = self.imagedata.GetWholeExtent()
        proj = project.Project()

        pos = slice_data.number

        x = (pos, pos, e[2], e[3], e[4], e[5])
        y = (e[0], e[1], pos, pos, e[4], e[5])
        z = (e[0], e[1], e[2], e[3], pos, pos)

        if (proj.original_orientation == const.AXIAL):
            new_extent = {"SAGITAL": x, "CORONAL": y, "AXIAL": z}
        elif(proj.original_orientation == const.SAGITAL):
            new_extent = {"SAGITAL": z,"CORONAL": x,"AXIAL": y}
        elif(proj.original_orientation == const.CORONAL):
            new_extent = {"SAGITAL": x,"CORONAL": z,"AXIAL": y}

        slice_data.actor.SetDisplayExtent(new_extent[self.orientation])
        slice_data.renderer.ResetCameraClippingRange()

    def UpdateRender(self, evt):
        self.interactor.Render()

    def set_scroll_position(self, position):
        self.scroll.SetThumbPosition(position)
        self.OnScrollBar()

    def OnScrollBar(self, evt=None):
        pos = self.scroll.GetThumbPosition()
        self.set_slice_number(pos)
        self.cursor_.Show(1)
        self.interactor.Render()
        if evt:
            evt.Skip()

    def OnKeyDown(self, evt=None):
        pos = self.scroll.GetThumbPosition()

        min = 0
        max = self.actor.GetSliceNumberMax()

        if (evt.GetKeyCode() == wx.WXK_UP and pos > min):
            pos = pos - 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()
        elif (evt.GetKeyCode() == wx.WXK_DOWN and pos < max):
            pos = pos + 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()
        self.interactor.Render()
        if evt:
            evt.Skip()

    def set_slice_number(self, index):
        self.text_actor.SetInput(str(index))
        self.slice_number = index
        for n, slice_data in enumerate(self.slice_data_list):
            ren = slice_data.renderer
            actor = slice_data.actor
            pos = self.layout[0] * self.layout[1] * index + n
            max = actor.GetSliceNumberMax()
            if pos < max:
                slice_data.number = pos
                self.__update_display_extent(slice_data)
                ren.AddActor(actor)
            else:
                ren.RemoveActor(actor)

            position = {"SAGITAL": {0: slice_data.number},
                        "CORONAL": {1: slice_data.number},
                        "AXIAL": {2: slice_data.number}}

            if 'DEFAULT' in self.modes:
                ps.Publisher().sendMessage(
                    'Update cursor single position in slice',
                    position[self.orientation])

    def ChangeSliceNumber(self, pubsub_evt):
        index = pubsub_evt.data
        self.set_slice_number(index)
        self.scroll.SetThumbPosition(index)
        self.interactor.Render()

    def test_operation_position(self, coord):
        """
        Test if coord is into the imagedata limits.
        """
        x, y, z = coord
        xi, yi, zi = 0, 0, 0
        xf, yf, zf = self.imagedata.GetDimensions()
        if xi <= x <= xf \
           and yi <= y <= yf\
           and zi <= z <= zf:
            return True
        return False
