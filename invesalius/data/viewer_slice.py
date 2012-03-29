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
from wx.lib.pubsub import pub as Publisher

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
        
        self.spined_image = False #Use to control to spin
        self.paned_image = False
        
        self.last_position_mouse_move = ()
        self.state = const.STATE_DEFAULT

        # All renderers and image actors in this viewer
        self.slice_data_list = []
        self.slice_data = None
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
        self.cross_actor = vtk.vtkActor()

        self.__bind_events()
        self.__bind_events_wx()

        self._warped = False
        self._flush_buffer = False

    def __init_gui(self):
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())

        scroll = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        self.scroll = scroll
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.interactor, 1, wx.EXPAND|wx.GROW)

        background_sizer = wx.BoxSizer(wx.HORIZONTAL)
        background_sizer.AddSizer(sizer, 1, wx.EXPAND|wx.GROW|wx.ALL, 2)
        background_sizer.Add(scroll, 0, wx.EXPAND|wx.GROW)
        self.SetSizer(background_sizer)
        background_sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.pick = vtk.vtkWorldPointPicker()
        self.interactor.SetPicker(self.pick)

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
        style = vtk.vtkInteractorStyleImage()

        interactor = self.interactor
        interactor.SetInteractorStyle(style)

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
                            "LeftButtonReleaseEvent": self.OnBrushRelease,
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
            Publisher.sendMessage('Activate ball reference')
        else:
            self.__set_cross_visibility(0)
            Publisher.sendMessage('Deactivate ball reference')

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
            self.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnSpinPan)

        # Measures are using vtkPropPicker because they need to get which actor
        # was picked.
        if state in (const.STATE_MEASURE_DISTANCE, const.STATE_MEASURE_ANGLE):
            self.pick = vtk.vtkPropPicker()
            self.interactor.SetPicker(self.pick)
        else:
            self.pick = vtk.vtkWorldPointPicker()
            self.interactor.SetPicker(self.pick)

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
        Publisher.sendMessage('Update slice viewer') 
 
    def OnLeftClick(self, evt, obj):
        self.left_pressed = 1

    def OnZoomLeftClick(self, evt, obj):
        evt.StartDolly()

    def OnReleaseLeftButton(self, evt, obj):
        self.left_pressed = 0
        Publisher.sendMessage('Update slice viewer')

    def OnWindowLevelMove(self, evt, obj):
        if (self.left_pressed):
            position = self.interactor.GetLastEventPosition()
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            self.acum_achange_window += mouse_x - self.last_x
            self.acum_achange_level += mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y

            Publisher.sendMessage('Bright and contrast adjustment image',
                (self.acum_achange_window, self.acum_achange_level))

            #self.SetWLText(self.acum_achange_level,
            #              self.acum_achange_window)

            const.WINDOW_LEVEL['Manual'] = (self.acum_achange_window,\
                                           self.acum_achange_level)
            Publisher.sendMessage('Check window and level other')
            Publisher.sendMessage('Update window level value',(self.acum_achange_window, 
                                                                self.acum_achange_level))
            #Necessary update the slice plane in the volume case exists
            Publisher.sendMessage('Update slice viewer')
            Publisher.sendMessage('Render volume viewer')

    def OnWindowLevelClick(self, evt, obj):
        self.last_x, self.last_y = self.interactor.GetLastEventPosition()

    def UpdateWindowLevelValue(self, pubsub_evt):
        window, level = pubsub_evt.data
        self.acum_achange_window, self.acum_achange_level = (window, level)
        self.SetWLText(window, level)
        Publisher.sendMessage('Update all slice')


    def OnChangeSliceMove(self, evt, obj):
        if (self.left_pressed):
            min = 0
            max = self.slice_.GetMaxSliceNumber(self.orientation)
    
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
        mouse_x, mouse_y = self.interactor.GetLastEventPosition()
        ren = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        cam = ren.GetActiveCamera()

        if (self.left_pressed):
            evt.Pan()
            evt.OnRightButtonDown()
            self.paned_image = True

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
        #self.Reposition(slice_data)
        self.interactor.Render()

    def OnUnSpinPan(self, evt):        
        orientation = self.orientation
        proj = project.Project()
        orig_orien = 1
        mouse_x, mouse_y = self.interactor.GetLastEventPosition()
        ren = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
         
        if((self.state == const.STATE_SPIN) and (self.spined_image)):
            self.cam.SetViewUp(const.SLICE_POSITION[orig_orien][0][self.orientation])

            if self.orientation == 'AXIAL':
                values = [_("A"), _("R"), _("P"), _("L")]
            elif self.orientation == 'SAGITAL':
                values = [_("T"), _("R"), _("B"), _("L")]
            else:
                values = [_("T"), _("P"), _("B"), _("A")]

            self.RenderTextDirection(values)
            self.interactor.Render()
            self.spined_image = False
        elif((self.state == const.STATE_PAN) and (self.paned_image)):
            ren.ResetCamera()
            self.interactor.Render()
            self.paned_image = False

    def OnSpinMove(self, evt, obj):
        mouse_x, mouse_y = self.interactor.GetLastEventPosition()
        ren = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        cam = ren.GetActiveCamera()
        if (self.left_pressed):
            self.UpdateTextDirection(cam)    
            self.spined_image = True
            evt.Spin()
            evt.OnRightButtonDown()


    def OnSpinClick(self, evt, obj):
        evt.StartSpin()

    def OnEnterInteractor(self, evt, obj):
        self.slice_data.cursor.Show()
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        
    def OnLeaveInteractor(self, evt, obj):
        self.slice_data.cursor.Show(0)
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        self.interactor.Render()

    def SetWLText(self, window_width, window_level):
        value = STR_WL%(window_level, window_width) 
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
            # Orientation texea
            if self.orientation == 'AXIAL':
                values = [_('R'), _('L'), _('A'), _('P')]
            elif self.orientation == 'SAGITAL':
                values = [_('P'), _('A'), _('T'), _('B')]
            else:
                values = [_('R'), _('L'), _('T'), _('B')]
                
            left_text = self.left_text = vtku.TextZero()
            left_text.ShadowOff()
            left_text.SetColour(colour)
            left_text.SetPosition(const.TEXT_POS_VCENTRE_LEFT)
            left_text.SetVerticalJustificationToCentered()
            left_text.SetValue(values[0])

            right_text = self.right_text = vtku.TextZero()
            right_text.ShadowOff()
            right_text.SetColour(colour)
            right_text.SetPosition(const.TEXT_POS_VCENTRE_RIGHT_ZERO)
            right_text.SetVerticalJustificationToCentered()
            right_text.SetJustificationToRight()
            right_text.SetValue(values[1])

            up_text = self.up_text = vtku.TextZero()
            up_text.ShadowOff()
            up_text.SetColour(colour)
            up_text.SetPosition(const.TEXT_POS_HCENTRE_UP)
            up_text.SetJustificationToCentered()
            up_text.SetValue(values[2])

            down_text = self.down_text = vtku.TextZero()
            down_text.ShadowOff()
            down_text.SetColour(colour)
            down_text.SetPosition(const.TEXT_POS_HCENTRE_DOWN_ZERO)
            down_text.SetJustificationToCentered()
            down_text.SetVerticalJustificationToBottom()
            down_text.SetValue(values[3])

            self.orientation_texts = [left_text, right_text, up_text,
                                      down_text]


            self.slice_data.renderer.AddActor(self.wl_text.actor)
            self.slice_data.renderer.AddActor(left_text.actor)
            self.slice_data.renderer.AddActor(right_text.actor)
            self.slice_data.renderer.AddActor(up_text.actor)
            self.slice_data.renderer.AddActor(down_text.actor)

    def RenderTextDirection(self, directions):
        self.up_text.SetValue(directions[0])
        self.right_text.SetValue(directions[3])
        self.down_text.SetValue(directions[2])
        self.left_text.SetValue(directions[1])
        self.interactor.Render()


    def UpdateTextDirection(self, cam):
        croll = cam.GetRoll()
        if (self.orientation == 'AXIAL'):

            if (croll >= -2 and croll <= 1):
                self.RenderTextDirection([_("A"), _("R"), _("P"), _("L")])

            elif(croll > 1 and croll <= 44):
                self.RenderTextDirection([_("AL"), _("RA"), _("PR"), _("LP")])

            elif(croll > 44 and croll <= 88):
               self.RenderTextDirection([_("LA"), _("AR"), _("RP"), _("PL")])

            elif(croll > 89 and croll <= 91):
               self.RenderTextDirection([_("L"), _("A"), _("R"), _("P")])

            elif(croll > 91 and croll <= 135):
               self.RenderTextDirection([_("LP"), _("AL"), _("RA"), _("PR")])
     
            elif(croll > 135 and croll <= 177):
                self.RenderTextDirection([_("PL"), _("LA"), _("AR"), _("RP")])
     
            elif(croll >= -180 and croll <= -178) or (croll < 180 and croll > 177):
                self.RenderTextDirection([_("P"), _("L"), _("A"), _("R")])
            
            elif(croll >= -177 and croll <= -133):
                self.RenderTextDirection([_("PR"), _("LP"), _("AL"), _("RA")])
    
            elif(croll >= -132 and croll <= -101):
                self.RenderTextDirection([_("RP"), _("PL"), _("LA"), _("AR")])

            elif(croll >= -101 and croll <= -87):
                self.RenderTextDirection([_("R"), _("P"), _("L"), _("A")])
    
            elif(croll >= -86 and croll <= -42):
                self.RenderTextDirection([_("RA"), _("PR"), _("LP"), _("AL")])
     
            elif(croll >= -41 and croll <= -2):
                self.RenderTextDirection([_("AR"), _("RP"), _("PL"), _("LA")])

        elif(self.orientation == "CORONAL"):
           
            if (croll >= -2 and croll <= 1):
                self.RenderTextDirection([_("T"), _("R"), _("B"), _("L")])

            elif(croll > 1 and croll <= 44):
                self.RenderTextDirection([_("TL"), _("RT"), _("BR"), _("LI")])

            elif(croll > 44 and croll <= 88):
               self.RenderTextDirection([_("LS"), _("TR"), _("RB"), _("L")])

            elif(croll > 89 and croll <= 91):
               self.RenderTextDirection([_("L"), _("T"), _("R"), _("B")])

            elif(croll > 91 and croll <= 135):
               self.RenderTextDirection([_("BI"), _("TL"), _("RT"), _("BR")])
     
            elif(croll > 135 and croll <= 177):
                self.RenderTextDirection([_("BL"), _("LT"), _("TR"), _("RB")])
     
            elif(croll >= -180 and croll <= -178) or (croll < 180 and croll > 177):
                self.RenderTextDirection([_("B"), _("L"), _("T"), _("R")])
            
            elif(croll >= -177 and croll <= -133):
                self.RenderTextDirection([_("BR"), _("LB"), _("TL"), _("RT")])
    
            elif(croll >= -132 and croll <= -101):
                self.RenderTextDirection([_("RB"), _("BL"), _("LT"), _("TR")])

            elif(croll >= -101 and croll <= -87):
                self.RenderTextDirection([_("R"), _("B"), _("L"), _("T")])
    
            elif(croll >= -86 and croll <= -42):
                self.RenderTextDirection([_("RT"), _("BR"), _("LB"), _("TL")])
     
            elif(croll >= -41 and croll <= -2):
                self.RenderTextDirection([_("TR"), _("RB"), _("BL"), _("LT")])

        elif(self.orientation == "SAGITAL"):
           
            if (croll >= -2 and croll <= 1):
                self.RenderTextDirection([_("A"), _("T"), _("P"), _("B")])

            elif(croll > 1 and croll <= 44):
                self.RenderTextDirection([_("AB"), _("TA"), _("PT"), _("BP")])

            elif(croll > 44 and croll <= 88):
               self.RenderTextDirection([_("BA"), _("AS"), _("TP"), _("PB")])

            elif(croll > 89 and croll <= 91):
               self.RenderTextDirection([_("B"), _("A"), _("T"), _("P")])

            elif(croll > 91 and croll <= 135):
               self.RenderTextDirection([_("BP"), _("AB"), _("SA"), _("PT")])
     
            elif(croll > 135 and croll <= 177):
                self.RenderTextDirection([_("PB"), _("BA"), _("AT"), _("TP")])
     
            elif(croll >= -180 and croll <= -178) or (croll < 180 and croll > 177):
                self.RenderTextDirection([_("P"), _("B"), _("A"), _("T")])
            
            elif(croll >= -177 and croll <= -133):
                self.RenderTextDirection([_("PT"), _("BP"), _("AB"), _("TA")])
    
            elif(croll >= -132 and croll <= -101):
                self.RenderTextDirection([_("TP"), _("PB"), _("BA"), _("AT")])

            elif(croll >= -101 and croll <= -87):
                self.RenderTextDirection([_("T"), _("P"), _("B"), _("A")])
    
            elif(croll >= -86 and croll <= -42):
                self.RenderTextDirection([_("TA"), _("PT"), _("BP"), _("AB")])
     
            elif(croll >= -41 and croll <= -2):
                self.RenderTextDirection([_("AT"), _("TP"), _("PB"), _("BA")])


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

    def ChangeBrushSize(self, pubsub_evt):
        size = pubsub_evt.data
        self._brush_cursor_size = size
        #for slice_data in self.slice_data_list:
        self.slice_data.cursor.SetSize(size)

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
        if self.slice_data.cursor:
            self.slice_data.cursor.SetColour(colour_vtk)

    def ChangeBrushActor(self, pubsub_evt):
        brush_type = pubsub_evt.data
        slice_data = self.slice_data
        self._brush_cursor_type = brush_type

        if brush_type == const.BRUSH_SQUARE:
            cursor = ca.CursorRectangle()
        elif brush_type == const.BRUSH_CIRCLE:
            cursor = ca.CursorCircle()

        cursor.SetOrientation(self.orientation)
        coordinates = {"SAGITAL": [slice_data.number, 0, 0],
                       "CORONAL": [0, slice_data.number, 0],
                       "AXIAL": [0, 0, slice_data.number]}
        cursor.SetPosition(coordinates[self.orientation])
        cursor.SetSpacing(self.slice_.spacing)
        cursor.SetColour(self._brush_cursor_colour)
        cursor.SetSize(self._brush_cursor_size)
        slice_data.SetCursor(cursor)
        self.interactor.Render()

    def OnBrushClick(self, evt, obj):
        self.__set_editor_cursor_visibility(1)
 
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        render = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = self.get_slice_data(render)

        # TODO: Improve!
        #for i in self.slice_data_list:
            #i.cursor.Show(0)
        self.slice_data.cursor.Show()

        self.pick.Pick(mouse_x, mouse_y, 0, render)
        
        coord = self.get_coordinate_cursor()
        position = self.slice_data.actor.GetInput().FindPoint(coord)
        
        if position != -1:
            coord = self.slice_data.actor.GetInput().GetPoint(position)

        slice_data.cursor.SetPosition(coord)
        cursor = self.slice_data.cursor
        radius = cursor.radius

        if position < 0:
            position = self.calculate_matrix_position(coord)

        self.slice_.edit_mask_pixel(self._brush_cursor_op, cursor.GetPixels(),
                                    position, radius, self.orientation)
        self._flush_buffer = True

        # TODO: To create a new function to reload images to viewer.
        self.OnScrollBar()

    def OnBrushMove(self, evt, obj):
        self.__set_editor_cursor_visibility(1)
 
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        render = self.interactor.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = self.get_slice_data(render)

        # TODO: Improve!
        #for i in self.slice_data_list:
            #i.cursor.Show(0)

        self.pick.Pick(mouse_x, mouse_y, 0, render)
        
        #if (self.pick.GetViewProp()):
            #self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        #else:
            #self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
            
        coord = self.get_coordinate_cursor()
        position = self.slice_data.actor.GetInput().FindPoint(coord)

        # when position == -1 the cursos is not over the image, so is not
        # necessary to set the cursor position to world coordinate center of
        # pixel from slice image.
        if position != -1:
            coord = self.slice_data.actor.GetInput().GetPoint(position)
        slice_data.cursor.SetPosition(coord)
        #self.__update_cursor_position(slice_data, coord)
        
        if (self.left_pressed):
            cursor = self.slice_data.cursor
            position = self.slice_data.actor.GetInput().FindPoint(coord)
            radius = cursor.radius

            if position < 0:
                position = self.calculate_matrix_position(coord)
                
            self.slice_.edit_mask_pixel(self._brush_cursor_op, cursor.GetPixels(),
                                        position, radius, self.orientation)
            # TODO: To create a new function to reload images to viewer.
            self.OnScrollBar(update3D=False)

        else:
            self.interactor.Render()

    def OnBrushRelease(self, evt, obj):
        self.slice_.apply_slice_buffer_to_mask(self.orientation)
        self._flush_buffer = False

    def OnCrossMouseClick(self, evt, obj):
        self.ChangeCrossPosition()

    def OnCrossMove(self, evt, obj):
        # The user moved the mouse with left button pressed
        if self.left_pressed:
            self.ChangeCrossPosition()

    def ChangeCrossPosition(self):
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        renderer = self.slice_data.renderer
        self.pick.Pick(mouse_x, mouse_y, 0, renderer)

        # Get in what slice data the click occurred
        # pick to get click position in the 3d world
        coord_cross = self.get_coordinate_cursor()
        position = self.slice_data.actor.GetInput().FindPoint(coord_cross)
        # Forcing focal point to be setted in the center of the pixel.
        coord_cross = self.slice_data.actor.GetInput().GetPoint(position)

        coord = self.calcultate_scroll_position(position)   
        self.ScrollSlice(coord)

        Publisher.sendMessage('Update cross position', coord_cross)
        Publisher.sendMessage('Set ball reference position based on bound',
                                   coord_cross)
        Publisher.sendMessage('Set camera in volume', coord_cross)
        Publisher.sendMessage('Render volume viewer')
        
        self.interactor.Render()

    def Navigation(self, pubsub_evt):
        # Get point from base change
        x, y, z = pubsub_evt.data
        coord_cross = x, y, z      
        position = self.slice_data.actor.GetInput().FindPoint(x, y, z)
        coord_cross = self.slice_data.actor.GetInput().GetPoint(position)
        coord = self.calcultate_scroll_position(position)   
        Publisher.sendMessage('Update cross position', coord_cross)
        
        self.ScrollSlice(coord)
        self.interactor.Render()

    def ScrollSlice(self, coord):
        if self.orientation == "AXIAL":
            Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
                                       coord[0])
            Publisher.sendMessage(('Set scroll position', 'CORONAL'),
                                       coord[1])
        elif self.orientation == "SAGITAL":
            Publisher.sendMessage(('Set scroll position', 'AXIAL'),
                                       coord[2])
            Publisher.sendMessage(('Set scroll position', 'CORONAL'),
                                       coord[1])
        elif self.orientation == "CORONAL":
            Publisher.sendMessage(('Set scroll position', 'AXIAL'),
                                       coord[2])
            Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
                                       coord[0])

    def OnZoomMoveRight(self, evt, obj):
        if (self.right_pressed):
            evt.Dolly()
            evt.OnRightButtonDown()

    def OnZoomRightClick(self, evt, obj):
        evt.StartDolly()

    def get_slice_data(self, render):
        #for slice_data in self.slice_data_list:
            #if slice_data.renderer is render:
                #return slice_data
        # WARN: Return the only slice_data used in this slice_viewer. 
        return self.slice_data

    def calcultate_scroll_position(self, position):
        # Based in the given coord (x, y, z), returns a list with the scroll positions for each
        # orientation, being the first position the sagital, second the coronal
        # and the last, axial.
        image_width = self.slice_.buffer_slices[self.orientation].image.shape[1]

        if self.orientation == 'AXIAL':
            axial = self.slice_data.number
            coronal = position / image_width
            sagital = position % image_width

        elif self.orientation == 'CORONAL':
            axial = position / image_width
            coronal = self.slice_data.number
            sagital = position % image_width

        elif self.orientation == 'SAGITAL':
            axial = position / image_width
            coronal = position % image_width
            sagital = self.slice_data.number

        return sagital, coronal, axial

    def calculate_matrix_position(self, coord):
        x, y, z = coord
        xi, xf, yi, yf, zi, zf = self.slice_data.actor.GetBounds()
        if self.orientation == 'AXIAL':
            mx = round((x - xi)/self.slice_.spacing[0], 0)
            my = round((y - yi)/self.slice_.spacing[1], 0)
        elif self.orientation == 'CORONAL':
            mx = round((x - xi)/self.slice_.spacing[0], 0)
            my = round((z - zi)/self.slice_.spacing[2], 0)
        elif self.orientation == 'SAGITAL':
            mx = round((y - yi)/self.slice_.spacing[1], 0)
            my = round((z - zi)/self.slice_.spacing[2], 0)
        return my, mx

    def get_coordinate_cursor(self):
        # Find position
        x, y, z = self.pick.GetPickPosition()
        bounds = self.slice_data.actor.GetBounds()
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

        dimensions = self.slice_.matrix.shape

        try:
            x = (x * dimensions[2]) / dx
        except ZeroDivisionError:
            x = slice_number
        try:
            y = (y * dimensions[1]) / dy
        except ZeroDivisionError:
            y = slice_number
        try:
            z = (z * dimensions[0]) / dz
        except ZeroDivisionError:
            z = slice_number

        return x, y, z

    def __bind_events(self):
        Publisher.subscribe(self.LoadImagedata,
                                 'Load slice to viewer')
        Publisher.subscribe(self.SetBrushColour,
                                 'Change mask colour')
        Publisher.subscribe(self.UpdateRender,
                                 'Update slice viewer')
        Publisher.subscribe(self.ChangeSliceNumber,
                                 ('Set scroll position',
                                  self.orientation))
        Publisher.subscribe(self.__update_cross_position,
                                'Update cross position')
        Publisher.subscribe(self.Navigation,
                                 'Co-registered Points')
        ###
        Publisher.subscribe(self.ChangeBrushSize,
                                 'Set edition brush size')
        Publisher.subscribe(self.ChangeBrushColour,
                                 'Add mask')
        Publisher.subscribe(self.ChangeBrushActor,
                                 'Set brush format')
        Publisher.subscribe(self.ChangeBrushOperation,
                                 'Set edition operation')

        Publisher.subscribe(self.UpdateWindowLevelValue,\
                                 'Update window level value')

        #Publisher.subscribe(self.__set_cross_visibility,\
        #                         'Set cross visibility')
        ###
        Publisher.subscribe(self.__set_layout,
                                'Set slice viewer layout')

        Publisher.subscribe(self.OnSetInteractorStyle,
                                'Set slice interaction style')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')

        #####
        Publisher.subscribe(self.OnShowText,
                                 'Show text actors on viewers')
        Publisher.subscribe(self.OnHideText,
                                 'Hide text actors on viewers')
        Publisher.subscribe(self.OnExportPicture,'Export picture to file')
        Publisher.subscribe(self.SetDefaultCursor, 'Set interactor default cursor')
    
        Publisher.subscribe(self.AddActors, 'Add actors ' + str(ORIENTATIONS[self.orientation]))
        Publisher.subscribe(self.RemoveActors, 'Remove actors ' + str(ORIENTATIONS[self.orientation]))

        Publisher.subscribe(self.ReloadActualSlice, 'Reload actual slice')


    def SetDefaultCursor(self, pusub_evt):
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
    
    def OnExportPicture(self, pubsub_evt):
        Publisher.sendMessage('Begin busy cursor')
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

        Publisher.sendMessage('End busy cursor')

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
        self.pick = vtk.vtkWorldPointPicker()

    def OnSetInteractorStyle(self, pubsub_evt):
        state = pubsub_evt.data
        self.SetInteractorStyle(state)
        
        if (state != const.SLICE_STATE_EDITOR):
            Publisher.sendMessage('Set interactor default cursor')
        
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
        cursor.SetSpacing(self.slice_.spacing)
        cursor.Show(0)
        self.cursor_ = cursor
        return cursor

    def SetInput(self, imagedata, mask_dict):
        self.slice_ = sl.Slice()

        max_slice_number = sl.Slice().GetNumberOfSlices(self.orientation)
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                 max_slice_number)

        self.slice_data = self.create_slice_window()
        #self.slice_data.actor.SetInput(imagedata)
        self.slice_data.SetCursor(self.__create_cursor())
        self.cam = self.slice_data.renderer.GetActiveCamera()
        self.__build_cross_lines(imagedata)
        self.set_slice_number(0)
        self.__update_camera()
        self.slice_data.renderer.ResetCamera()
        self.interactor.GetRenderWindow().AddRenderer(self.slice_data.renderer)
        #if slice_.imagedata is None:
            #slice_.SetInput(imagedata, mask_dict)
            
        ##actor.SetInput(slice_.GetOutput())
        #self.LoadRenderers(slice_.GetOutput())
        #self.__configure_renderers()
        #ren = self.slice_data_list[0].renderer
        #actor = self.slice_data_list[0].actor
        #actor_bound = actor.GetBounds()
        #self.cam = ren.GetActiveCamera()

        #for slice_data in self.slice_data_list:
            #self.__update_camera(slice_data)
            #self.Reposition(slice_data)

        #number_of_slices = self.layout[0] * self.layout[1]
        #max_slice_number = actor.GetSliceNumberMax() + 1/ \
                #number_of_slices

        #if actor.GetSliceNumberMax() % number_of_slices:
            #max_slice_number += 1
        #self.set_scroll_position(0)

        #actor_bound = actor.GetBounds()
        self.interactor.Render()

        self.EnableText()
        ## Insert cursor
        self.SetInteractorStyle(const.STATE_DEFAULT)

    def __build_cross_lines(self, imagedata):
        renderer = self.slice_data.renderer

        cross = vtk.vtkCursor3D()
        cross.AllOff()
        cross.AxesOn()
        self.cross = cross

        c = vtk.vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        cross_mapper = vtk.vtkPolyDataMapper()
        cross_mapper.SetInput(cross.GetOutput())
        #cross_mapper.SetTransformCoordinate(c)

        p = vtk.vtkProperty()
        p.SetColor(1, 0, 0)

        cross_actor = vtk.vtkActor()
        cross_actor.SetMapper(cross_mapper)
        cross_actor.SetProperty(p)
        cross_actor.VisibilityOff()
        # Only the slices are pickable
        cross_actor.PickableOff()
        self.cross_actor = cross_actor

        renderer.AddActor(cross_actor)

    def __update_cross_position(self, pubsub_evt):
        pos = pubsub_evt.data
        self.cross.SetFocalPoint(pos)

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

    def create_slice_window(self):
        renderer = vtk.vtkRenderer()
        renderer.SetLayer(0)
        cam = renderer.GetActiveCamera()

        overlay_renderer = vtk.vtkRenderer()
        overlay_renderer.SetLayer(1)
        overlay_renderer.SetActiveCamera(cam)
        overlay_renderer.SetInteractive(0)
        

        self.interactor.GetRenderWindow().SetNumberOfLayers(2)
        self.interactor.GetRenderWindow().AddRenderer(overlay_renderer)
        self.interactor.GetRenderWindow().AddRenderer(renderer)

        actor = vtk.vtkImageActor()
        # TODO: Create a option to let the user set if he wants to interpolate
        # the slice images.
        #actor.InterpolateOff()
        slice_data = sd.SliceData()
        slice_data.SetOrientation(self.orientation)
        slice_data.renderer = renderer
        slice_data.overlay_renderer = overlay_renderer
        slice_data.actor = actor
        slice_data.SetBorderStyle(sd.BORDER_ALL)
        renderer.AddActor(actor)
        renderer.AddActor(slice_data.text.actor)
        renderer.AddViewProp(slice_data.box_actor)
        return slice_data

    def __update_camera(self):
        orientation = self.orientation
        proj = project.Project()
        orig_orien = 1 #proj.original_orientation

        self.cam.SetFocalPoint(0, 0, 0)
        self.cam.SetViewUp(const.SLICE_POSITION[orig_orien][0][self.orientation])
        self.cam.SetPosition(const.SLICE_POSITION[orig_orien][1][self.orientation])
        #self.cam.ComputeViewPlaneNormal()
        #self.cam.OrthogonalizeViewUp()
        self.cam.ParallelProjectionOn()

    def __update_display_extent(self, image):
        self.slice_data.actor.SetDisplayExtent(image.GetExtent())
        self.slice_data.renderer.ResetCameraClippingRange()

    def UpdateRender(self, evt):
        print "Updating viewer", self.orientation
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
        Publisher.sendMessage('Change slice from slice plane',\
                                   (self.orientation, pos))
                
    def OnScrollBar(self, evt=None, update3D=True):
        pos = self.scroll.GetThumbPosition() 
        self.set_slice_number(pos)
        if update3D:
            self.UpdateSlice3D(pos)
        if self.state == const.SLICE_STATE_CROSS:
            # Update other slice's cross according to the new focal point from
            # the actual orientation.
            focal_point = self.cross.GetFocalPoint()
            Publisher.sendMessage('Update cross position', focal_point)
            Publisher.sendMessage('Update slice viewer') 
        else:
            self.interactor.Render() 
        if evt:
            if self._flush_buffer:
                self.slice_.apply_slice_buffer_to_mask(self.orientation)
            evt.Skip()
            
    def OnScrollBarRelease(self, evt):
        pos = self.scroll.GetThumbPosition()
        evt.Skip()

    def OnKeyDown(self, evt=None, obj=None):
        pos = self.scroll.GetThumbPosition()

        min = 0
        max = self.slice_.GetMaxSliceNumber(self.orientation)

        if self._flush_buffer:
            self.slice_.apply_slice_buffer_to_mask(self.orientation)

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
            if self._flush_buffer:
                self.slice_.apply_slice_buffer_to_mask(self.orientation)
            pos = pos - 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()
    
    def OnScrollBackward(self, evt=None, obj=None):
        pos = self.scroll.GetThumbPosition()
        max = self.slice_.GetMaxSliceNumber(self.orientation)
        
        if(pos < max):
            if self._flush_buffer:
                self.slice_.apply_slice_buffer_to_mask(self.orientation)
            pos = pos + 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()

    def OnSize(self, evt):
        w, h = evt.GetSize() 
        w = float(w)
        h = float(h)
        if self.slice_data:
            self.slice_data.SetSize((w, h))
        evt.Skip()

    def set_slice_number(self, index):
        image = self.slice_.GetSlices(self.orientation, index)
        self.slice_data.actor.SetInput(image)
        for actor in self.actors_by_slice_number.get(self.slice_data.number, []):
            self.slice_data.renderer.RemoveActor(actor)
        for actor in self.actors_by_slice_number.get(index, []):
            self.slice_data.renderer.AddActor(actor)

        self.slice_data.SetNumber(index)
        self.__update_display_extent(image)
        self.cross.SetModelBounds(self.slice_data.actor.GetBounds())

    def ChangeSliceNumber(self, pubsub_evt):
        index = pubsub_evt.data
        #self.set_slice_number(index)
        self.scroll.SetThumbPosition(index)
        pos = self.scroll.GetThumbPosition()
        self.set_slice_number(pos)
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
        print x, y, z
        if self.pick.GetViewProp(): 
            self.render_to_add = slice_data.renderer
            Publisher.sendMessage("Add measurement point",
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
            Publisher.sendMessage("Add measurement point",
                    ((x, y,z), const.ANGULAR, ORIENTATIONS[self.orientation],
                        slice_number))
            self.interactor.Render()

    def ReloadActualSlice(self, pubsub_evt):
        pos = self.scroll.GetThumbPosition()
        self.set_slice_number(pos)
        self.interactor.Render()

    def AddActors(self, pubsub_evt):
        "Inserting actors"
        actors, n = pubsub_evt.data
        print actors
        #try:
            #renderer = self.renderers_by_slice_number[n]
            #for actor in actors:
                #renderer.AddActor(actor)
        #except KeyError:
            #pass
        for actor in actors:
            self.slice_data.renderer.AddActor(actor)

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
                self.slice_data.renderer.RemoveActor(actor)
        else:
            for actor in actors:
                # Remove the actor from the renderer
                renderer.RemoveActor(actor)
                # and remove the actor from the actor's list
                self.actors_by_slice_number[n].remove(actor)
