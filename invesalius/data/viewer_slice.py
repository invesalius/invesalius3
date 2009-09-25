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


import constants as const
import cursor_actors as ca
import data.slice_ as sl
import data.vtk_utils as vtku
import project
from slice_data import SliceData

ID_TO_TOOL_ITEM = {}

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
        self.text = None
        # VTK pipeline and actors
        #self.__config_interactor()
        self.pick = vtk.vtkPropPicker()

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


    def OnContextMenu(self, evt):
        self.PopupMenu(self.menu)

    def SetPopupMenu(self, menu):
        self.menu = menu

    def SetLayout(self, layout):
        self.layout = layout
        slice_ = sl.Slice()
        self.LoadRenderers(slice_.GetOutput())
        self.__configure_renderers()
        self.__configure_scroll()

    def __set_layout(self, pubsub_evt):
        layout = pubsub_evt.data
        self.SetLayout(layout)

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
        action = {'CROSS': {
                             "MouseMoveEvent": self.OnCrossMove,
                             "LeftButtonPressEvent": self.OnCrossMouseClick,
                             "LeftButtonReleaseEvent": self.OnCrossMouseRelease
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
                        },
                  'CHANGESLICE':{
                                "MouseMoveEvent": self.OnChangeSliceMove,
                                "LeftButtonPressEvent": self.OnChangeSliceClick,
                                "LeftButtonReleaseEvent": self.OnReleaseModes
                         },
                  'WINDOWLEVEL':{
                                "MouseMoveEvent": self.OnWindowLevelMove,
                                "LeftButtonPressEvent": self.OnWindowLevelClick,
                                "LeftButtonReleaseEvent": self.OnReleaseModes
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
        
        if ((mode == "ZOOM") or (mode == "ZOOMSELECT")):
            self.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)
        else:
            self.interactor.Bind(wx.EVT_LEFT_DCLICK, None)
            
        self.style = style
        self.interactor.SetInteractorStyle(style)

    def __set_mode_editor(self, pubsub_evt):
        self.append_mode('EDITOR')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))

    def __set_mode_spin(self, pubsub_evt):
        self.append_mode('SPIN')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZING))

    def __set_mode_zoom(self, pubsub_evt):
        print "Zoom"
        self.append_mode('ZOOM')
        self.mouse_pressed = 0
        ICON_IMAGE = wx.Image("../icons/tool_zoom.png",wx.BITMAP_TYPE_PNG)
        self.interactor.SetCursor(wx.CursorFromImage(ICON_IMAGE))

    def __set_mode_pan(self, pubsub_evt):
        self.append_mode('PAN')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZING))

    def __set_mode_zoom_select(self, pubsub_evt):
        self.append_mode('ZOOMSELECT')
        ICON_IMAGE = wx.Image("../icons/tool_zoom.png",wx.BITMAP_TYPE_PNG)
        self.interactor.SetCursor(wx.CursorFromImage(ICON_IMAGE))

    def __set_mode_window_level(self, pubsub_evt):
        self.append_mode('WINDOWLEVEL')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZING))
        self.interactor.Render()

    def __set_mode_slice_scroll(self, pubsub_evt):
        self.append_mode('CHANGESLICE')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZENS))

    def __set_mode_cross(self, pubsub_evt):
        self.append_mode('CROSS')
        self.mouse_pressed = 0
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_NONE))

    def OnWindowLevelMove(self, evt, obj):
        if self.mouse_pressed:
            position = self.interactor.GetLastEventPosition()
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            self.acum_achange_window += mouse_x - self.last_x
            self.acum_achange_level += mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y

            ps.Publisher().sendMessage('Bright and contrast adjustment image',
                (self.acum_achange_window, self.acum_achange_level))

            ps.Publisher().sendMessage('Update window and level text',\
                                       "WL: %d  WW: %d"%(self.acum_achange_level,\
                                                         self.acum_achange_window))

            const.WINDOW_LEVEL['Other'] = (self.acum_achange_window,\
                                           self.acum_achange_level)
            ps.Publisher().sendMessage('Check window and level other')
            
            #Necessary update the slice plane in the volume case exists
            ps.Publisher().sendMessage('Render volume viewer')
            
        self.interactor.Render()


    def OnWindowLevelClick(self, evt, obj):
        self.last_x, self.last_y = self.interactor.GetLastEventPosition()
        self.mouse_pressed = 1

    def UpdateWindowLevelValue(self, pubsub_evt):
        window, level = pubsub_evt.data
        self.acum_achange_window, self.acum_achange_level = (window, level)


    def OnChangeSliceMove(self, evt, obj):

        min = 0
        max = self.actor.GetSliceNumberMax()

        if (self.mouse_pressed):
            position = self.interactor.GetLastEventPosition()
            scroll_position = self.scroll.GetThumbPosition()

            if (position[1] > self.last_position) and\
                            (self.acum_achange_slice > min):
                self.acum_achange_slice -= 1
            elif(position[1] < self.last_position) and\
                            (self.acum_achange_slice < max):
                 self.acum_achange_slice += 1
            self.last_position = position[1]

            self.scroll.SetThumbPosition(self.acum_achange_slice)
            self.OnScrollBar()


    def OnChangeSliceClick(self, evt, obj):
        self.mouse_pressed = 1
        position = list(self.interactor.GetLastEventPosition())
        self.acum_achange_slice = self.scroll.GetThumbPosition()
        self.last_position = position[1]

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

    def OnUnZoom(self, evt, obj = None):
        mouse_x, mouse_y = self.interactor.GetLastEventPosition()
        ren = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = self.get_slice_data(ren)
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        self.Reposition(slice_data)
        self.interactor.Render()

    def OnSpinMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Spin()
            evt.OnRightButtonDown()

    def OnSpinClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartSpin()

    def OnReleaseModes(self, evt, obj):
        self.mouse_pressed = 0
        ps.Publisher().sendMessage('Update slice viewer')

    def OnEnterInteractor(self, obj, evt):
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))

    def OnLeaveInteractor(self, obj, evt):
        for slice_data in self.slice_data_list:
            slice_data.cursor.Show(0)
        self.interactor.Render()

    def UpdateText(self, pubsub_evt):
        if (self.text):
            self.text.SetValue(pubsub_evt.data)
            self.interactor.Render()

    def EnableText(self):
        if not (self.text):
            text = self.text = vtku.Text()
            self.ren.AddActor(text.actor)
            proj = project.Project()

        ps.Publisher().sendMessage('Update window and level text',\
                                       "WL: %d  WW: %d"%(proj.level, proj.window))


    def Reposition(self, slice_data):
        """
        Based on code of method Zoom in the
        vtkInteractorStyleRubberBandZoom, the of
        vtk 5.4.3
        """
        ren = slice_data.renderer
        size = ren.GetSize()

        if (size[0] <= size[1] + 60):

            bound = slice_data.actor.GetBounds()

            width = abs((bound[3] - bound[2]) * -1)
            height = abs((bound[1] - bound[0]) * -1)

            origin = ren.GetOrigin()
            cam = ren.GetActiveCamera()

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

            ren.SetDisplayPoint(winCenter)
            ren.DisplayToView()
            ren.ViewToWorld()

            worldWinCenter = list(ren.GetWorldPoint())
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
        self.interactor.Render()

    def OnCrossMove(self, obj, evt_vtk):
        # Update position in other slices
        if self.mouse_pressed:
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            renderer = self.slice_data_list[0].renderer
            self.pick.Pick(mouse_x, mouse_y, 0, renderer)
            coord_cross = self.get_coordinate_cursor()
            coord = self.get_coordinate()
            ps.Publisher().sendMessage('Update cross position', coord_cross)
            ps.Publisher().sendMessage(('Set scroll position', 'SAGITAL'),
                                       coord[0])
            ps.Publisher().sendMessage(('Set scroll position', 'CORONAL'),
                                       coord[1])
            ps.Publisher().sendMessage(('Set scroll position', 'AXIAL'),
                                       coord[2])

    def OnCrossMouseClick(self, obj, evt_vtk):
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        renderer = self.slice_data_list[0].renderer
        self.pick.Pick(mouse_x, mouse_y, 0, renderer)
        coord_cross = self.get_coordinate_cursor()
        coord = self.get_coordinate()
        ps.Publisher().sendMessage('Update cross position', coord_cross)
        ps.Publisher().sendMessage(('Set scroll position', 'SAGITAL'),
                                   coord[0])
        ps.Publisher().sendMessage(('Set scroll position', 'CORONAL'),
                                   coord[1])
        ps.Publisher().sendMessage(('Set scroll position', 'AXIAL'),
                                   coord[2])
        self.mouse_pressed = 1

    def OnCrossMouseRelease(self, obj, evt_vtk):
        self.mouse_pressed = 0

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
        ps.Publisher().subscribe(self.__update_cross_position,
                                'Update cross position')
        ###
        ps.Publisher().subscribe(self.ChangeBrushSize,
                                 'Set edition brush size')
        ps.Publisher().subscribe(self.ChangeBrushColour,
                                 'Add mask')
        ps.Publisher().subscribe(self.ChangeBrushActor,
                                 'Set brush format')
        ps.Publisher().subscribe(self.ChangeBrushOperation,
                                 'Set edition operation')

        ###
        ps.Publisher().subscribe(self.__set_mode_pan,
                                 ('Set interaction mode',
                                  const.MODE_MOVE))
        ps.Publisher().subscribe(self.__set_mode_editor,
                                 ('Set interaction mode',
                                  const.MODE_SLICE_EDITOR))
        ps.Publisher().subscribe(self.__set_mode_spin,
                                 ('Set interaction mode',
                                  const.MODE_ROTATE))
        ps.Publisher().subscribe(self.__set_mode_zoom,
                                 ('Set interaction mode',
                                  const.MODE_ZOOM))
        ps.Publisher().subscribe(self.__set_mode_zoom_select,
                                 ('Set interaction mode',
                                  const.MODE_ZOOM_SELECTION))
        ps.Publisher().subscribe(self.__set_mode_slice_scroll,
                                 ('Set interaction mode',
                                  const.MODE_SLICE_SCROLL))
        ps.Publisher().subscribe(self.__set_mode_window_level,
                                 ('Set interaction mode',
                                  const.MODE_WW_WL))
        ps.Publisher().subscribe(self.__set_mode_cross,
                                 ('Set interaction mode',
                                  const.MODE_SLICE_CROSS))
        ####
        ps.Publisher().subscribe(self.UpdateText,\
                                 'Update window and level text')
        ps.Publisher().subscribe(self.UpdateWindowLevelValue,\
                                 'Update window level value')

        ###
        ps.Publisher().subscribe(self.__set_layout,
                                'Set slice viewer layout')

    def ChangeBrushOperation(self, pubsub_evt):
        print pubsub_evt.data
        self._brush_cursor_op = pubsub_evt.data

    def __bind_events_wx(self):
        self.scroll.Bind(wx.EVT_SCROLL, self.OnScrollBar)
        self.scroll.Bind(wx.EVT_SCROLL_THUMBTRACK, self.OnScrollBarRelease)
        #self.scroll.Bind(wx.EVT_SCROLL_ENDSCROLL, self.OnScrollBarRelease)
        self.interactor.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.interactor.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

    def LoadImagedata(self, pubsub_evt):
        imagedata = pubsub_evt.data
        self.SetInput(imagedata)

    def LoadRenderers(self, image):
        number_renderers = self.layout[0] * self.layout[1]
        diff = number_renderers - len(self.slice_data_list)
        if diff > 0:
            for i in xrange(diff):
                slice_data = self.create_slice_window(image)
                self.slice_data_list.append(slice_data)
        elif diff < 0:
            to_remove = self.slice_data_list[number_renderers::]
            for slice_data in to_remove:
                self.interactor.GetRenderWindow().RemoveRenderer(slice_data.renderer)
            self.slice_data_list = self.slice_data_list[:number_renderers]

    def __configure_renderers(self):
        proportion_x = 1.0 / self.layout[0]
        proportion_y = 1.0 / self.layout[1]
        # The (0,0) in VTK is in bottom left. So the creation from renderers
        # must be # in inverted order, from the top left to bottom right
        n = 0
        for j in xrange(self.layout[1]-1, -1, -1):
            for i in xrange(self.layout[0]):
                position = ((i*proportion_x, j * proportion_y,
                             (i+1)*proportion_x, (j+1)*proportion_y))
                slice_data = self.slice_data_list[n]
                slice_data.renderer.SetViewport(position)
                slice_data.SetCursor(self.__create_cursor())
                self.__update_camera(slice_data)
                n += 1

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
        self.LoadRenderers(slice_.GetOutput())
        self.__configure_renderers()
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
        text_actor.SetPosition(1,1)
        self.text_actor = text_actor

        #ren.AddActor(actor)
        #ren.AddActor(text_actor)
        for slice_data in self.slice_data_list:
            self.__update_camera(slice_data)
            self.Reposition(slice_data)

        number_of_slices = self.layout[0] * self.layout[1]
        max_slice_number = actor.GetSliceNumberMax() / \
                number_of_slices
        if actor.GetSliceNumberMax() % number_of_slices:
            max_slice_number += 1
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                                     max_slice_number)
        self.set_scroll_position(0)

        actor_bound = actor.GetBounds()

        self.EnableText()
        # Insert cursor
        self.append_mode('EDITOR')

        self.__build_cross_lines()

    def __build_cross_lines(self):
        actor = self.slice_data_list[0].actor
        renderer = self.slice_data_list[0].renderer
        xi, xf, yi, yf, zi, zf = actor.GetBounds()

        #vline = vtk.vtkLineSource()
        #vline.SetPoint1(xi, yi, zi)
        #vline.SetPoint2(xi, yf, zi)
        #self.vline = vline

        #hline = vtk.vtkLineSource()
        #hline.SetPoint1(xi, yi, zi)
        #hline.SetPoint2(xf, yi, zi)
        #self.hline = hline

        #cross = vtk.vtkAppendPolyData()
        #cross.AddInput(vline.GetOutput())
        #cross.AddInput(hline.GetOutput())
        cross = vtk.vtkCursor3D()
        cross.AllOff()
        cross.AxesOn()
        #cross.WrapOn()
        #cross.OutlineOff()
        #cross.ZShadowsOff()
        #cross.YShadowsOff()
        #cross.XShadowsOff()
        cross.SetModelBounds(self.imagedata.GetBounds())
        self.cross = cross

        cross_mapper = vtk.vtkPolyDataMapper()
        cross_mapper.SetInput(cross.GetOutput())

        property = vtk.vtkProperty()
        property.SetColor(1, 0, 0)

        cross_actor = vtk.vtkActor()
        cross_actor.SetMapper(cross_mapper)
        cross_actor.SetProperty(property)
        # Only the slices are pickable
        cross_actor.PickableOff()
        self.cross_actor = cross_actor

        renderer.AddActor(cross_actor)

    def __update_cross_position(self, pubsub_evt):
        x, y, z = pubsub_evt.data
        #xi, yi, zi = self.vline.GetPoint1()
        #xf, yf, zf = self.vline.GetPoint2()
        #self.vline.SetPoint1(x, yi, z)
        #self.vline.SetPoint2(x, yf, z)
        #self.vline.Update()

        #xi, yi, zi = self.hline.GetPoint1()
        #xf, yf, zf = self.hline.GetPoint2()
        #self.hline.SetPoint1(xi, y, z)
        #self.hline.SetPoint2(xf, y, z)
        #self.hline.Update()
        slice_data = self.slice_data_list[0]
        slice_number = slice_data.number
        actor_bound = slice_data.actor.GetBounds()

        print
        print self.orientation
        print x, y, z
        print actor_bound
        print

        xy = [x, y, actor_bound[0]]
        yz = [actor_bound[2], y, z]
        xz = [x, actor_bound[4], z]

        proj = project.Project()
        orig_orien = proj.original_orientation

        if (orig_orien == const.SAGITAL):
            coordinates = {"SAGITAL": xy, "CORONAL": yz, "AXIAL": xz}
        elif(orig_orien == const.CORONAL):
            coordinates = {"SAGITAL": yz, "CORONAL": xy, "AXIAL": xz}
        else:
            coordinates = {"SAGITAL": yz, "CORONAL": xz, "AXIAL": xy}

        self.cross.SetFocalPoint(x, y, z)

        #print
        #print slice_number
        #print x, y, z
        #print "Focal", self.cross.GetFocalPoint()
        #print "bounds", self.cross.GetModelBounds()
        #print "actor bounds", slice_data.actor.GetBounds()
        #print

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

            slice_data.cursor.SetPosition((x, y, z))

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

    def __configure_scroll(self):
        actor = self.slice_data_list[0].actor
        number_of_slices = self.layout[0] * self.layout[1]
        max_slice_number = actor.GetSliceNumberMax() / \
                number_of_slices
        if actor.GetSliceNumberMax() % number_of_slices:
            max_slice_number += 1
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                                     max_slice_number)
        self.set_scroll_position(0)

    def set_scroll_position(self, position):
        self.scroll.SetThumbPosition(position)
        self.OnScrollBar()
    
    def UpdateSlice3D(self, pos):
        original_orientation = project.Project().original_orientation
        pos = self.scroll.GetThumbPosition()
        if (self.orientation == "CORONAL") and \
            (original_orientation == const.AXIAL):
            pos = abs(self.scroll.GetRange() - pos)
        elif(self.orientation == "AXIAL") and \
            (original_orientation == const.CORONAL):
                pos = abs(self.scroll.GetRange() - pos)
        elif(self.orientation == "AXIAL") and \
            (original_orientation == const.SAGITAL):            
                pos = abs(self.scroll.GetRange() - pos)
        ps.Publisher().sendMessage('Change slice from slice plane',\
                                   (self.orientation, pos))
                
    def OnScrollBar(self, evt=None):
        pos = self.scroll.GetThumbPosition()
        self.set_slice_number(pos)
        #self.UpdateSlice3D(pos)
        self.pos = pos
        self.cursor_.Show(1)
        self.interactor.Render()
        if evt:
            evt.Skip()
            
    def OnScrollBarRelease(self, evt):
        print "OnScrollBarRelease"
        self.UpdateSlice3D(self.pos)
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
        self.UpdateSlice3D(pos)
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

            #if 'DEFAULT' in self.modes:
            #    ps.Publisher().sendMessage(
            #        'Update cursor single position in slice',
            #        position[self.orientation])

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
