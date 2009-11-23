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

import constants as const
import vtk_utils as vu

class SliceData(object):
    def __init__(self):
        self.actor = None
        self.cursor = None
        self.number = 0
        self.orientation = 'AXIAL'
        self.renderer = None
        self.__create_text()
        self.__create_box()

    def __create_text(self):
        colour = const.ORIENTATION_COLOUR[self.orientation]

        text = vu.Text()
        text.SetColour(colour)
        text.SetSize(const.TEXT_SIZE_LARGE)
        text.SetPosition(const.TEXT_POS_LEFT_DOWN)
        text.SetVerticalJustificationToBottom()
        text.SetValue(self.number)
        self.text = text

    def __create_box(self):
        xi = yi = 0.1
        xf = yf = 200
        line_i = vtk.vtkLineSource()
        line_i.SetPoint1((xi, yi, 0))
        line_i.SetPoint2((xf, yi, 0))
        self.line_i = line_i

        line_s = vtk.vtkLineSource()
        line_s.SetPoint1((xi, yf, 0))
        line_s.SetPoint2((xf, yf, 0))
        self.line_s = line_s

        line_l = vtk.vtkLineSource()
        line_l.SetPoint1((xi, yi, 0))
        line_l.SetPoint2((xi, yf, 0))
        self.line_l = line_l
        
        line_r = vtk.vtkLineSource()
        line_r.SetPoint1((xf, yi, 0))
        line_r.SetPoint2((xf, yf, 0))
        self.line_r = line_r
        
        box = vtk.vtkAppendPolyData()
        box.AddInput(line_i.GetOutput())
        box.AddInput(line_s.GetOutput())
        box.AddInput(line_l.GetOutput())
        box.AddInput(line_r.GetOutput())

        box_mapper = vtk.vtkPolyDataMapper2D()
        box_mapper.SetInput(box.GetOutput())

        box_actor = vtk.vtkActor2D()
        box_actor.SetMapper(box_mapper)
        self.box_actor = box_actor

    def SetCursor(self, cursor):
        if self.cursor:
            self.renderer.RemoveActor(self.cursor.actor)
        self.renderer.AddActor(cursor.actor)
        self.cursor = cursor

    def SetNumber(self, number):
        self.number = number
        self.text.SetValue("%d" % self.number)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        colour = const.ORIENTATION_COLOUR[self.orientation]
        self.text.SetColour(colour)
        self.box_actor.GetProperty().SetColor(colour)

    def SetSize(self, size):
        w, h = size
        xi = yi = 0.1
        xf = w - 0.1
        yf = h - 0.1

        self.line_i.SetPoint1((xi, yi, 0))
        self.line_i.SetPoint2((xf, yi, 0))

        self.line_s.SetPoint1((xi, yf, 0))
        self.line_s.SetPoint2((xf, yf, 0))

        self.line_l.SetPoint1((xi, yi, 0))
        self.line_l.SetPoint2((xi, yf, 0))

        self.line_r.SetPoint1((xf, yi, 0))
        self.line_r.SetPoint2((xf, yf, 0))

    def Hide(self):
        self.renderer.RemoveActor(self.actor)
        self.renderer.RemoveActor(self.text.actor)
        self.renderer.RemoveActor(self.box_actor)

    def Show(self):
        self.renderer.AddActor(self.actor)
        self.renderer.AddActor(self.text.actor)
        self.renderer.AddActor(self.box_actor)
