#!/usr/bin/env python
# -*- coding: utf-8 -*-
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

import numpy

import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

import wx
import wx.lib.pubsub as ps


import constants as const
import cursor_actors as ca
import data.slice_ as sl
import data.vtk_utils as vtku
import project
import slice_data as sd
import utils

from data import measures

ID_TO_TOOL_ITEM = {}
STR_WL = "WL: %d  WW: %d"

ORIENTATIONS = {
        "AXIAL": const.AXIAL,
        "CORONAL": const.CORONAL,
        "SAGITAL": const.SAGITAL,
        }

class Viewer(wx.Panel):

    def __init__(self, prnt, orientation='AXIAL'):
        wx.Panel.__init__(self, prnt, size=wx.Size(320, 300))

        #colour = [255*c for c in const.ORIENTATION_COLOUR[orientation]]
        #self.SetBackgroundColour(colour)

        # Interactor additional style
        #self.modes = []#['DEFAULT']
        self.left_pressed = 0
        self.right_pressed = 0
        self.last_position_mouse_move = ()

        # All renderers and image actors in this viewer
        self.slice_data_list = []
        # The layout from slice_data, the first is number of cols, the second
        # is the number of rows
        self.layout = (1, 1)
        self.orientation_texts = []

        self.measures = []
        self.actors_by_slice_number = {}
        self.renderers_by_slice_number = {}

        self.__init_gui()

        self.orientation = orientation
        self.slice_number = 0

        self._brush_cursor_op = const.DEFAULT_BRUSH_OP
        self._brush_cursor_size = const.BRUSH_SIZE
        self._brush_cursor_colour = const.BRUSH_COLOUR
        self._brush_cursor_type = const.DEFAULT_BRUSH_OP
        self.cursor = None
        self.wl_text = None
        self.on_wl = False
        self.on_text = False
        # VTK pipeline and actors
        self.__config_interactor()
        self.pick = vtk.vtkPropPicker()
        self.cross_actor = vtk.vtkActor()


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
        self.right_pressed = 0
        if (self.last_position_mouse_move ==\
              self.interactor.GetLastEventPosition()):
            self.PopupMenu(self.menu)
            
        evt.Skip()
           
            
    def SetPopupMenu(self, menu):
        self.menu = menu

    def SetLayout(self, layout):
        self.layout = layout
        if (layout == (1,1)) and self.on_text:
            self.ShowTextActors()
        else:
            self.HideTextActors(change_status=False)

        slice_ = sl.Slice()
        self.LoadRenderers(slice_.GetOutput())
        self.__configure_renderers()
        self.__configure_scroll()

    def HideTextActors(self, change_status=True):
        if self.wl_text:
            self.wl_text.Hide()
        [t.Hide() for t in self.orientation_texts]
        self.interactor.Render()
        if change_status:
            self.on_text = False

    def ShowTextActors(self):
        if self.on_wl and self.wl_text:
            self.wl_text.Show()
        [t.Show() for t in self.orientation_texts]
        self.Update()
        self.interactor.Render()
        self.on_text = True


    def __set_layout(self, pubsub_evt):
        layout = pubsub_evt.data
        self.SetLayout(layout)

    def __config_interactor(self):
        ren = vtk.vtkRenderer()
        style = vtk.vtkInteractorStyleImage()

        interactor = self.interactor
        interactor.SetInteractorStyle(style)
        interactor.GetRenderWindow().AddRenderer(ren)

        self.cam = ren.GetActiveCamera()
        self.ren = ren


    def SetInteractorStyle(self, state):
        self.state = state
        action = {const.SLICE_STATE_CROSS: 
                             {
                             "MouseMoveEvent": self.OnCrossMove,
                             "LeftButtonPressEvent": self.OnCrossMouseClick,
                             },
                  const.SLICE_STATE_EDITOR: 
                            {
                            "MouseMoveEvent": self.OnBrushMove,
                            "LeftButtonPressEvent": self.OnBrushClick,
                            "EnterEvent": self.OnEnterInteractor,
                            "LeaveEvent": self.OnLeaveInteractor
                            },
                  const.STATE_PAN:
                            {
                            "MouseMoveEvent": self.OnPanMove,
                            "LeftButtonPressEvent": self.OnPanClick,
                            "LeftButtonReleaseEvent": self.OnVtkRightRelease
                            },
                  const.STATE_SPIN:
                            {
                            "MouseMoveEvent": self.OnSpinMove,
                            "LeftButtonPressEvent": self.OnSpinClick,
                            "LeftButtonReleaseEvent": self.OnVtkRightRelease
                            },
                  const.STATE_ZOOM:
                            {
                            "MouseMoveEvent": self.OnZoomMoveLeft,
                            "LeftButtonPressEvent": self.OnZoomLeftClick,
                            "LeftButtonReleaseEvent": self.OnVtkRightRelease
                            },
                  const.SLICE_STATE_SCROLL:
                            {
                            "MouseMoveEvent": self.OnChangeSliceMove,
                            "LeftButtonPressEvent": self.OnChangeSliceClick,
                            },
                  const.STATE_WL:
                            {
                            "MouseMoveEvent": self.OnWindowLevelMove,
                            "LeftButtonPressEvent": self.OnWindowLevelClick,
                            },
                  const.STATE_DEFAULT:
                            {
                            },
                  const.STATE_MEASURE_DISTANCE:
                            {
                            "LeftButtonPressEvent": self.OnInsertLinearMeasurePoint
                            },
                  const.STATE_MEASURE_ANGLE:
                            {
                            "LeftButtonPressEvent": self.OnInsertAngularMeasurePoint
                            },
                 }
        if state == const.SLICE_STATE_CROSS:
            self.__set_cross_visibility(1)
            ps.Publisher().sendMessage('Activate ball reference')
        else:
            self.__set_cross_visibility(0)
            ps.Publisher().sendMessage('Deactivate ball reference')

        if state == const.STATE_WL:
            self.on_wl = True
            self.wl_text.Show()
        else:
            self.on_wl = False
            self.wl_text.Hide()


        self.__set_editor_cursor_visibility(0)

        
        # Bind method according to current mode
        if(state == const.STATE_ZOOM_SL):
            style = vtk.vtkInteractorStyleRubberBandZoom()

            style.AddObserver("RightButtonPressEvent", self.QuitRubberBandZoom)
            #style.AddObserver("RightButtonPressEvent", self.EnterRubberBandZoom)

        else:
            style = vtk.vtkInteractorStyleImage()

            # Check each event available for each state
            for event in action[state]:
                # Bind event
                style.AddObserver(event,
                                  action[state][event])

            # Common to all styles
            # Mouse Buttons' presses / releases
            style.AddObserver("LeftButtonPressEvent", self.OnLeftClick)
            style.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)
            style.AddObserver("RightButtonPressEvent", self.OnRightClick)
            style.AddObserver("RightButtonReleaseEvent", self.OnReleaseRightButton)            

            # Zoom using right button
            style.AddObserver("RightButtonPressEvent",self.OnZoomRightClick)
            style.AddObserver("MouseMoveEvent", self.OnZoomMoveRight)
            style.AddObserver("RightButtonReleaseEvent", self.OnVtkRightRelease)
            
        #Scroll change slice
        style.AddObserver("MouseWheelForwardEvent",self.OnScrollForward)
        style.AddObserver("MouseWheelBackwardEvent", self.OnScrollBackward)
            
        if ((state == const.STATE_ZOOM) or (state == const.STATE_ZOOM_SL)):
            self.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)
        else:
            self.interactor.Bind(wx.EVT_LEFT_DCLICK, None)

        self.style = style
        self.interactor.SetInteractorStyle(style)
        self.interactor.Render()
   
    def QuitRubberBandZoom(self, evt, obj):
        style =  vtk.vtkInteractorStyleImage()
        self.interactor.SetInteractorStyle(style)
        self.style = style

        style.AddObserver("LeftButtonPressEvent", self.EnterRubberBandZoom)

        # Zoom using right button
        style.AddObserver("RightButtonPressEvent", self.OnRightClick)
        style.AddObserver("RightButtonReleaseEvent", self.OnReleaseRightButton)            
        style.AddObserver("RightButtonPressEvent",self.OnZoomRightClick)
        style.AddObserver("MouseMoveEvent", self.OnZoomMoveRight)
        style.AddObserver("RightButtonReleaseEvent", self.OnReleaseRightButton)

    def EnterRubberBandZoom(self, evt, obj):
        style = vtk.vtkInteractorStyleRubberBandZoom()
        self.interactor.SetInteractorStyle(style)
        self.style = style

        style.AddObserver("RightButtonPressEvent", self.QuitRubberBandZoom)

    def OnRightClick(self, evt, obj):
        self.last_position_mouse_move = \
            self.interactor.GetLastEventPosition()
    
        self.right_pressed = 1

    def OnReleaseRightButton(self, evt, obj):
        self.right_pressed = 0
        ps.Publisher().sendMessage('Update slice viewer') 
 
    def OnLeftClick(self, evt, obj):
        self.left_pressed = 1

    def OnZoomLeftClick(self, evt, obj):
        evt.StartDolly()

    def OnReleaseLeftButton(self, evt, obj):
        self.left_pressed = 0
        ps.Publisher().sendMessage('Update slice viewer')

    def OnWindowLevelMove(self, evt, obj):
        if (self.left_pressed):
            position = self.interactor.GetLastEventPosition()
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            self.acum_achange_window += mouse_x - self.last_x
            self.acum_achange_level += mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y

            ps.Publisher().sendMessage('Bright and contrast adjustment image',
                (self.acum_achange_window, self.acum_achange_level))

            #self.SetWLText(self.acum_achange_level,
            #              self.acum_achange_window)

            const.WINDOW_LEVEL['Manual'] = (self.acum_achange_window,\
                                           self.acum_achange_level)
            ps.Publisher().sendMessage('Check window and level other')
            ps.Publisher().sendMessage('Update window level value',(self.acum_achange_window, 
                                                                self.acum_achange_level))
            #Necessary update the slice plane in the volume case exists
            ps.Publisher().sendMessage('Update slice viewer')
            ps.Publisher().sendMessage('Render volume viewer')


    def OnWindowLevelClick(self, evt, obj):
        self.last_x, self.last_y = self.interactor.GetLastEventPosition()

    def UpdateWindowLevelValue(self, pubsub_evt):
        window, level = pubsub_evt.data
        self.acum_achange_window, self.acum_achange_level = (window, level)
        self.SetWLText(window, level)


    def OnChangeSliceMove(self, evt, obj):
        if (self.left_pressed):
            min = 0
            max = self.actor.GetSliceNumberMax()
    
            if (self.left_pressed):
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
        position = list(self.interactor.GetLastEventPosition())
        self.acum_achange_slice = self.scroll.GetThumbPosition()
        self.last_position = position[1]

    def OnPanMove(self, evt, obj):
        if (self.left_pressed):
            evt.Pan()
            evt.OnRightButtonDown()

    def OnPanClick(self, evt, obj):
        evt.StartPan()

    def OnZoomMoveLeft(self, evt, obj):
        if self.left_pressed:
            evt.Dolly()
            evt.OnRightButtonDown()

    def OnVtkRightRelease(self, evt, obj):
        evt.OnRightButtonUp()


    def OnUnZoom(self, evt, obj = None):
        mouse_x, mouse_y = self.interactor.GetLastEventPosition()
        ren = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = self.get_slice_data(ren)
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        self.Reposition(slice_data)
        self.interactor.Render()

    def OnSpinMove(self, evt, obj):
        if (self.left_pressed):
            evt.Spin()
            evt.OnRightButtonDown()

    def OnSpinClick(self, evt, obj):
        evt.StartSpin()

    def OnEnterInteractor(self, evt, obj):
        #self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        pass
        
    def OnLeaveInteractor(self, evt, obj):
        for slice_data in self.slice_data_list:
            slice_data.cursor.Show(0)
        self.interactor.Render()

    def SetWLText(self, window_width, window_level):
        value = STR_WL%(window_width, window_level) 
        if (self.wl_text):
            self.wl_text.SetValue(value)
            #self.interactor.Render()

    def EnableText(self):
        if not (self.wl_text):
            proj = project.Project()            
            colour = const.ORIENTATION_COLOUR[self.orientation]

            # Window & Level text
            self.wl_text = vtku.Text()
            self.SetWLText(proj.level, proj.window)
            
                        
            # Orientation text
            if self.orientation == 'AXIAL':
                values = [_('R'), _('L'), _('A'), _('P')]
            elif self.orientation == 'SAGITAL':
                values = [_('P'), _('A'), _('T'), _('B')]
            else:
                values = [_('R'), _('L'), _('T'), _('B')]
                
            left_text = vtku.TextZero()
            left_text.ShadowOff()
            left_text.SetColour(colour)
            left_text.SetPosition(const.TEXT_POS_VCENTRE_LEFT)
            left_text.SetVerticalJustificationToCentered()
            left_text.SetValue(values[0])

            right_text = vtku.TextZero()
            right_text.ShadowOff()
            right_text.SetColour(colour)
            right_text.SetPosition(const.TEXT_POS_VCENTRE_RIGHT_ZERO)
            right_text.SetVerticalJustificationToCentered()
            right_text.SetJustificationToRight()
            right_text.SetValue(values[1])

            up_text = vtku.TextZero()
            up_text.ShadowOff()
            up_text.SetColour(colour)
            up_text.SetPosition(const.TEXT_POS_HCENTRE_UP)
            up_text.SetJustificationToCentered()
            up_text.SetValue(values[2])

            down_text = vtku.TextZero()
            down_text.ShadowOff()
            down_text.SetColour(colour)
            down_text.SetPosition(const.TEXT_POS_HCENTRE_DOWN_ZERO)
            down_text.SetJustificationToCentered()
            down_text.SetVerticalJustificationToBottom()
            down_text.SetValue(values[3])

            self.orientation_texts = [left_text, right_text, up_text,
                                      down_text]


            self.ren.AddActor(self.wl_text.actor)
            self.ren.AddActor(left_text.actor)
            self.ren.AddActor(right_text.actor)
            self.ren.AddActor(up_text.actor)
            self.ren.AddActor(down_text.actor)

    def Reposition(self, slice_data):
        """
        Based on code of method Zoom in the
        vtkInteractorStyleRubberBandZoom, the of
        vtk 5.4.3
        """
        ren = slice_data.renderer
        size = ren.GetSize()


        ren.ResetCamera()
        ren.GetActiveCamera().Zoom(1.0)
        self.interactor.Render()
        #self.interactor.GetRenderWindow().Render()

        
        #if (size[0] <= size[1] + 60):
        # Code bellow doesn't work for Promed 0013
        """
        if 0:

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
        """
                

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


    def OnBrushClick(self, evt, obj):

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

    def OnBrushMove(self, evt, obj):
       
        self.__set_editor_cursor_visibility(1)
 
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        render = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = self.get_slice_data(render)

        # TODO: Improve!
        #for i in self.slice_data_list:
            #i.cursor.Show(0)
        #slice_data.cursor.Show()

        self.pick.Pick(mouse_x, mouse_y, 0, render)
        
        if (self.pick.GetProp()):
            self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        else:
            self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
            
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
            
        if (self.left_pressed):
            pixels = itertools.ifilter(self.test_operation_position,
                                       slice_data.cursor.GetPixels())
            ps.Publisher().sendMessage(evt_msg, pixels)
            ps.Publisher().sendMessage('Update slice viewer')

        self.interactor.Render()

    def OnCrossMouseClick(self, evt, obj):
        self.ChangeCrossPosition()

    def OnCrossMove(self, evt, obj):
        # The user moved the mouse with left button pressed
        if (self.left_pressed):
            self.ChangeCrossPosition()

    def ChangeCrossPosition(self):
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        # Get in what slice data the click occurred
        renderer = self.slice_data_list[0].renderer
        # pick to get click position in the 3d world
        self.pick.Pick(mouse_x, mouse_y, self.slice_data_list[0].number, renderer)
        coord_cross = self.get_coordinate_cursor()
        coord = self.CalcultateScrollPosition(coord_cross)
        ps.Publisher().sendMessage('Update cross position',
                (self.orientation, coord_cross))
        ps.Publisher().sendMessage('Set ball reference position based on bound', coord_cross)
        ps.Publisher().sendMessage('Set camera in volume', coord_cross)
        ps.Publisher().sendMessage('Render volume viewer')
        
        print "Scroll to", coord
        self.ScrollSlice(coord)
        self.interactor.Render()

    def Navigation(self, pubsub_evt):
        # Get point from base change
        x, y, z = pubsub_evt.data
        coord_cross = x, y, z      
        coord = self.CalcultateScrollPosition(coord_cross)   
        ps.Publisher().sendMessage('Update cross position',
                (self.orientation, coord_cross))
        
        self.ScrollSlice(coord)
        self.interactor.Render()

    def ScrollSlice(self, coord):
        if self.orientation == "AXIAL":
            ps.Publisher().sendMessage(('Set scroll position', 'SAGITAL'),
                                       coord[0])
            ps.Publisher().sendMessage(('Set scroll position', 'CORONAL'),
                                       coord[1])
        elif self.orientation == "SAGITAL":
            ps.Publisher().sendMessage(('Set scroll position', 'AXIAL'),
                                       coord[2])
            ps.Publisher().sendMessage(('Set scroll position', 'CORONAL'),
                                       coord[1])
        elif self.orientation == "CORONAL":
            ps.Publisher().sendMessage(('Set scroll position', 'AXIAL'),
                                       coord[2])
            ps.Publisher().sendMessage(('Set scroll position', 'SAGITAL'),
                                       coord[0])

    def OnZoomMoveRight(self, evt, obj):
        if (self.right_pressed):
            evt.Dolly()
            evt.OnRightButtonDown()

    def OnZoomRightClick(self, evt, obj):
        evt.StartDolly()

    def get_slice_data(self, render):
        for slice_data in self.slice_data_list:
            if slice_data.renderer is render:
                return slice_data

    def CalcultateScrollPosition(self, coord):
        # Based in the given coord (x, y, z), returns a list with the scroll positions for each
        # orientation, being the first position the sagital, second the coronal
        # and the last, axial.
        x, y, z = coord

        proj = project.Project()
        orig_orien = proj.original_orientation

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

        x, y, z = self._assert_coord_into_image([x, y, z])

        # Based on the current orientation, we define 3D position
        # Sagita, coronal, axial
        coordinates = {const.AXIAL: [x, y, z],
                const.SAGITAL: [z, x, y],
                const.CORONAL: [x, z, y]}

        coord = [int(i) for i in coordinates[orig_orien]]

        # According to vtkImageData extent, we limit min and max value
        # If this is not done, a VTK Error occurs when mouse is pressed outside
        # vtkImageData extent
        return coord

    def get_coordinate_cursor(self):
        # Find position
        x, y, z = self.pick.GetPickPosition()
        bounds = self.actor.GetBounds()
        if bounds[0] == bounds[1]:
            x = bounds[0]
        elif bounds[2] == bounds[3]:
            y = bounds[2]
        elif bounds[4] == bounds[5]:
            z = bounds[4]
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
        ps.Publisher().subscribe(self.Navigation,
                                 'Co-registered Points')
        ###
        ps.Publisher().subscribe(self.ChangeBrushSize,
                                 'Set edition brush size')
        ps.Publisher().subscribe(self.ChangeBrushColour,
                                 'Add mask')
        ps.Publisher().subscribe(self.ChangeBrushActor,
                                 'Set brush format')
        ps.Publisher().subscribe(self.ChangeBrushOperation,
                                 'Set edition operation')

        ps.Publisher().subscribe(self.UpdateWindowLevelValue,\
                                 'Update window level value')

        #ps.Publisher().subscribe(self.__set_cross_visibility,\
        #                         'Set cross visibility')
        ###
        ps.Publisher().subscribe(self.__set_layout,
                                'Set slice viewer layout')

        ps.Publisher().subscribe(self.OnSetInteractorStyle,
                                'Set slice interaction style')
        ps.Publisher().subscribe(self.OnCloseProject, 'Close project data')

        #####
        ps.Publisher().subscribe(self.OnShowText,
                                 'Show text actors on viewers')
        ps.Publisher().subscribe(self.OnHideText,
                                 'Hide text actors on viewers')
        ps.Publisher().subscribe(self.OnExportPicture,'Export picture to file')
        ps.Publisher().subscribe(self.SetDefaultCursor, 'Set interactor default cursor')
    
        ps.Publisher().subscribe(self.AddActors, ('Add actors', ORIENTATIONS[self.orientation]))
        ps.Publisher().subscribe(self.RemoveActors, ('Remove actors', ORIENTATIONS[self.orientation]))

    def SetDefaultCursor(self, pusub_evt):
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
    
    def OnExportPicture(self, pubsub_evt):
        ps.Publisher().sendMessage('Begin busy cursor')
        view_prop_list = []
        for slice_data in self.slice_data_list:
            view_prop_list.append(slice_data.box_actor) 
            self.ren.RemoveViewProp(slice_data.box_actor)

        id, filename, filetype = pubsub_evt.data
        dict = {"AXIAL": const.AXIAL,
                "CORONAL": const.CORONAL,
                "SAGITAL": const.SAGITAL}

        if id == dict[self.orientation]:
            if filetype == const.FILETYPE_POV:
                renwin = self.interactor.GetRenderWindow()
                image = vtk.vtkWindowToImageFilter()
                image.SetInput(renwin)
                writer = vtk.vtkPOVExporter()
                writer.SetFilePrefix(filename.split(".")[0])
                writer.SetRenderWindow(renwin)
                writer.Write()
            else:
                #Use tiling to generate a large rendering.
                image = vtk.vtkRenderLargeImage()
                image.SetInput(self.ren)
                image.SetMagnification(2)

                image = image.GetOutput()


                # write image file
                if (filetype == const.FILETYPE_BMP):
                    writer = vtk.vtkBMPWriter()
                elif (filetype == const.FILETYPE_JPG):
                    writer =  vtk.vtkJPEGWriter()
                elif (filetype == const.FILETYPE_PNG):
                    writer = vtk.vtkPNGWriter()
                elif (filetype == const.FILETYPE_PS):
                    writer = vtk.vtkPostScriptWriter()
                elif (filetype == const.FILETYPE_TIF):
                    writer = vtk.vtkTIFFWriter()
                    filename = "%s.tif"%filename.strip(".tif")
                
                writer.SetInput(image)
                writer.SetFileName(filename)
                writer.Write()

            for actor in view_prop_list:
                self.ren.AddViewProp(actor)

        ps.Publisher().sendMessage('End busy cursor')

    def OnShowText(self, pubsub_evt):
        self.ShowTextActors()

    def OnHideText(self, pubsub_evt):
        self.HideTextActors()


    def OnCloseProject(self, pubsub_evt):
        self.CloseProject()

    def CloseProject(self):
        for slice_data in self.slice_data_list:
            del slice_data
            
        self.modes = []#['DEFAULT']
        self.slice_data_list = []
        self.layout = (1, 1)
        self.orientation_texts = []
        self.slice_number = 0
        self.cursor = None
        self.wl_text = None
        self.pick = vtk.vtkPropPicker()


    def OnSetInteractorStyle(self, pubsub_evt):
        state = pubsub_evt.data
        self.SetInteractorStyle(state)
        
        if (state != const.SLICE_STATE_EDITOR):
            ps.Publisher().sendMessage('Set interactor default cursor')

        
        
    def ChangeBrushOperation(self, pubsub_evt):
        self._brush_cursor_op = pubsub_evt.data

    def __bind_events_wx(self):
        self.scroll.Bind(wx.EVT_SCROLL, self.OnScrollBar)
        self.scroll.Bind(wx.EVT_SCROLL_THUMBTRACK, self.OnScrollBarRelease)
        #self.scroll.Bind(wx.EVT_SCROLL_ENDSCROLL, self.OnScrollBarRelease)
        self.interactor.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.interactor.Bind(wx.EVT_RIGHT_UP, self.OnContextMenu)
        self.interactor.Bind(wx.EVT_SIZE, self.OnSize)

    def LoadImagedata(self, pubsub_evt):
        imagedata, mask_dict = pubsub_evt.data
        self.SetInput(imagedata, mask_dict)
        

    def LoadRenderers(self, imagedata):
        number_renderers = self.layout[0] * self.layout[1]
        diff = number_renderers - len(self.slice_data_list)
        if diff > 0:
            for i in xrange(diff):
                slice_data = self.create_slice_window(imagedata)
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
        w, h = self.interactor.GetRenderWindow().GetSize()
        w *= proportion_x
        h *= proportion_y
        n = 0
        for j in xrange(self.layout[1]-1, -1, -1):
            for i in xrange(self.layout[0]):
                slice_xi = i*proportion_x
                slice_xf = (i+1)*proportion_x
                slice_yi = j*proportion_y
                slice_yf = (j+1)*proportion_y

                position = (slice_xi, slice_yi, slice_xf, slice_yf)
                slice_data = self.slice_data_list[n]
                slice_data.renderer.SetViewport(position)
                # Text actor position
                x, y = const.TEXT_POS_LEFT_DOWN
                slice_data.text.SetPosition((x+slice_xi,y+slice_yi))
                slice_data.SetCursor(self.__create_cursor())
                slice_data.SetSize((w, h))
                self.__update_camera(slice_data)

                style = 0
                if j == 0:
                    style = style | sd.BORDER_DOWN
                if j == self.layout[1] - 1:
                    style = style | sd.BORDER_UP

                if i == 0:
                    style = style | sd.BORDER_LEFT
                if i == self.layout[0] - 1:
                    style = style | sd.BORDER_RIGHT

                slice_data.SetBorderStyle(style)
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

    def SetInput(self, imagedata, mask_dict):
        pass
        #self.imagedata = imagedata

        ##ren = self.ren
        #interactor = self.interactor

        ## Slice pipeline, to be inserted into current viewer
        #slice_ = sl.Slice()
        #if slice_.imagedata is None:
            #slice_.SetInput(imagedata, mask_dict)
            
        actor = vtk.vtkImageActor()
        ##actor.SetInput(slice_.GetOutput())
        #self.LoadRenderers(slice_.GetOutput())
        #self.__configure_renderers()
        #ren = self.slice_data_list[0].renderer
        #actor = self.slice_data_list[0].actor
        #actor_bound = actor.GetBounds()
        self.actor = actor
        self.ren.AddActor(self.actor)
        #self.cam = ren.GetActiveCamera()

        #for slice_data in self.slice_data_list:
            #self.__update_camera(slice_data)
            #self.Reposition(slice_data)

        #number_of_slices = self.layout[0] * self.layout[1]
        #max_slice_number = actor.GetSliceNumberMax() + 1/ \
                #number_of_slices

        #if actor.GetSliceNumberMax() % number_of_slices:
            #max_slice_number += 1
        max_slice_number = sl.Slice().GetNumberOfSlices(self.orientation)
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                                     max_slice_number)
        #self.set_scroll_position(0)

        #actor_bound = actor.GetBounds()

        #self.EnableText()
        ## Insert cursor
        #self.SetInteractorStyle(const.STATE_DEFAULT)

        #self.__build_cross_lines()

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
        cross_actor.VisibilityOff()
        # Only the slices are pickable
        cross_actor.PickableOff()
        self.cross_actor = cross_actor

        renderer.AddActor(cross_actor)

    def __update_cross_position(self, pubsub_evt):
        x, y, z = pubsub_evt.data[1]
        orientation = pubsub_evt.data[0]
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
        extent = slice_data.actor.GetDisplayExtent()
        cam = slice_data.renderer.GetActiveCamera()

        vCamera = numpy.array(cam.GetPosition()) - numpy.array(cam.GetFocalPoint())
        n_vCamera = vCamera / numpy.linalg.norm(vCamera)

        pos = [j + 0.01 * i for i,j in zip(n_vCamera, (x, y, z))]

        #yz = [x + abs(x * 0.001), y, z]
        #xz = [x, y - abs(y * 0.001), z]
        #xy = [x, y, z + abs(z * 0.001)]

        proj = project.Project()
        orig_orien = proj.original_orientation
        #pos = [x, y, z]

        #if (orig_orien == const.SAGITAL):
        #    coordinates = {"SAGITAL": xy, "CORONAL": yz, "AXIAL": xz}
        #elif(orig_orien == const.CORONAL):
        #    #coordinates = {"SAGITAL": yz, "CORONAL": xy, "AXIAL": xz}
        #    if orientation == "AXIAL":
        #        pos[2] += abs(pos[2] * 0.001)
        #    elif orientation == "SAGITAL":
        #        pos[0] += abs(pos[0] * 0.001)
        #    elif orientation == "CORONAL":
        #        pos[1] -= abs(pos[1] * 0.001)
        #else:
        #    #coordinates = {"SAGITAL": yz, "CORONAL": xz, "AXIAL": xy}
        #    print "AXIAL"
        #    if orientation == "AXIAL":
        #        pos[2] += abs(pos[2] * 0.001)
        #    elif orientation == "SAGITAL":
        #        pos[0] += abs(pos[0] * 0.001)
        #    elif orientation == "CORONAL":
        #        pos[1] -= abs(pos[1] * 0.001)


        #pos = [x, y, z]
        #if orientation == "AXIAL":
        #    pos[2] += abs(pos[2] * 0.001)
        #elif orientation == "SAGITAL":
        #    pos[0] += abs(pos[0] * 0.001)
        #elif orientation == "CORONAL":
        #    pos[1] -= abs(pos[1] * 0.001)
        #print ">POS", pos
        #print
        self.cross.SetFocalPoint(pos)

        #print
        #print slice_number
        #print x, y, z
        #print "Focal", self.cross.GetFocalPoint()
        #print "bounds", self.cross.GetModelBounds()
        #print "actor bounds", slice_data.actor.GetBounds()
        #print

    def __set_cross_visibility(self, visibility):
        self.cross_actor.SetVisibility(visibility)

    def __set_editor_cursor_visibility(self, visibility):
        for slice_data in self.slice_data_list:
            slice_data.cursor.actor.SetVisibility(visibility)

    def __update_cursor_position(self, slice_data, position):
        x, y, z = position
        if (slice_data.cursor):
            slice_number = slice_data.number
            actor_bound = slice_data.actor.GetBounds()

            yz = [x + abs(x * 0.001), y, z]
            xz = [x, y - abs(y * 0.001), z]
            xy = [x, y, z + abs(z * 0.001)]

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
        slice_data = sd.SliceData()
        slice_data.SetOrientation(self.orientation)
        slice_data.renderer = renderer
        slice_data.actor = actor
        slice_data.SetBorderStyle(sd.BORDER_UP | sd.BORDER_DOWN)
        renderer.AddActor(actor)
        renderer.AddActor(slice_data.text.actor)
        renderer.AddViewProp(slice_data.box_actor)
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
        #slice_data.renderer.Render()

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
        max_slice_number = actor.GetSliceNumberMax()/ \
                number_of_slices
        if actor.GetSliceNumberMax()% number_of_slices:
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
        slice_ = sl.Slice()
        image = slice_.GetSlices(self.orientation, pos)
        self.actor.SetInput(image)
        self.ren.ResetCamera()
        self.interactor.Render()
        print "slice", pos
        #self.set_slice_number(pos)
        ##self.UpdateSlice3D(pos)
        #self.pos = pos
        #self.interactor.Render()
        #if evt:
            #evt.Skip()
            
    def OnScrollBarRelease(self, evt):
        #self.UpdateSlice3D(self.pos)
        evt.Skip()

    def OnKeyDown(self, evt=None, obj=None):
        pos = self.scroll.GetThumbPosition()

        min = 0
        max = self.actor.GetSliceNumberMax()

        if (evt.GetKeyCode() == wx.WXK_UP and pos > min):
            self.OnScrollForward()
            self.OnScrollBar()
            
        elif (evt.GetKeyCode() == wx.WXK_DOWN and pos < max):
            self.OnScrollBackward()
            self.OnScrollBar()
        
        self.UpdateSlice3D(pos)
        self.interactor.Render()

        if evt:
            evt.Skip()

    def OnScrollForward(self, evt=None, obj=None):
        pos = self.scroll.GetThumbPosition()
        min = 0
        
        if(pos > min):
            pos = pos - 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()

    
    
    def OnScrollBackward(self, evt=None, obj=None):
        pos = self.scroll.GetThumbPosition()
        max = self.actor.GetSliceNumberMax()
        
        if(pos < max):
            pos = pos + 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()

            

    def OnSize(self, evt):
        w, h = evt.GetSize() 
        w = float(w) / self.layout[0]
        h = float(h) / self.layout[1]
        for slice_data in self.slice_data_list:
            slice_data.SetSize((w, h))
        evt.Skip()

    def set_slice_number(self, index):
        self.slice_number = index
        # for m in self.actors_by_slice_number.values():
            # for actor in m:
                # actor.SetVisibility(0) 
        # Removing actor from the previous renderers/slice.
        for n in self.renderers_by_slice_number:
            renderer = self.renderers_by_slice_number[n]
            for actor in self.actors_by_slice_number.get(n, []):
                renderer.RemoveActor(actor)

        self.renderers_by_slice_number = {}

        for n, slice_data in enumerate(self.slice_data_list):
            ren = slice_data.renderer
            actor = slice_data.actor
            pos = self.layout[0] * self.layout[1] * index + n
            max = actor.GetSliceNumberMax() + 1
            if pos < max:
                self.renderers_by_slice_number[pos] = ren
                for m_actor in self.actors_by_slice_number.get(pos, []):
                    ren.AddActor(m_actor)
                slice_data.SetNumber(pos)
                # for actor in self.actors_by_slice_number.get(pos, []):
                    # actor.SetVisibility(1)
                self.__update_display_extent(slice_data)
                slice_data.Show()
            else:
                slice_data.Hide()

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

    def _assert_coord_into_image(self, coord):
        extent = self.imagedata.GetWholeExtent()
        extent_min = extent[0], extent[2], extent[4]
        extent_max = extent[1], extent[3], extent[5]
        for index in xrange(3):
            if coord[index] > extent_max[index]:
                coord[index] = extent_max[index]
            elif coord[index] < extent_min[index]:
                coord[index] = extent_min[index]
        return coord

    def OnInsertLinearMeasurePoint(self, obj, evt):
        x,y = self.interactor.GetEventPosition()
        render = self.interactor.FindPokedRenderer(x, y)
        slice_data = self.get_slice_data(render)
        slice_number = slice_data.number
        self.pick.Pick(x, y, 0, render)
        x, y, z = self.pick.GetPickPosition()
        if self.pick.GetViewProp(): 
            self.render_to_add = slice_data.renderer
            ps.Publisher().sendMessage("Add measurement point",
                    ((x, y,z), const.LINEAR, ORIENTATIONS[self.orientation],
                        slice_number))
            self.interactor.Render()

    def OnInsertAngularMeasurePoint(self, obj, evt):
        x,y = self.interactor.GetEventPosition()
        render = self.interactor.FindPokedRenderer(x, y)
        slice_data = self.get_slice_data(render)
        slice_number = slice_data.number
        self.pick.Pick(x, y, 0, render)
        x, y, z = self.pick.GetPickPosition()
        if self.pick.GetViewProp(): 
            self.render_to_add = slice_data.renderer
            ps.Publisher().sendMessage("Add measurement point",
                    ((x, y,z), const.ANGULAR, ORIENTATIONS[self.orientation],
                        slice_number))
            self.interactor.Render()

    def AddActors(self, pubsub_evt):
        "Inserting actors"
        actors, n = pubsub_evt.data
        try:
            renderer = self.renderers_by_slice_number[n]
            for actor in actors:
                renderer.AddActor(actor)
        except KeyError:
            pass
        try:
            self.actors_by_slice_number[n].extend(actors)
        except KeyError:
            self.actors_by_slice_number[n] = list(actors)

    def RemoveActors(self, pubsub_evt):
        "Remove a list of actors"
        actors, n = pubsub_evt.data
        try:
            renderer = self.renderers_by_slice_number[n]
        except KeyError:
            for actor in actors:
                self.actors_by_slice_number[n].remove(actor)
        else:
            for actor in actors:
                # Remove the actor from the renderer
                renderer.RemoveActor(actor)
                # and remove the actor from the actor's list
                self.actors_by_slice_number[n].remove(actor)
