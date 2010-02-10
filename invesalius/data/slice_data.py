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

BORDER_UP = 1
BORDER_DOWN = 2
BORDER_LEFT = 4
BORDER_RIGHT = 8
BORDER_ALL = BORDER_UP | BORDER_DOWN | BORDER_LEFT | BORDER_RIGHT
BORDER_NONE = 0


class SliceData(object):
    def __init__(self):
        self.actor = None
        self.cursor = None
        self.text = None

        self.number = 0
        self.orientation = 'AXIAL'
        self.renderer = None
        self.__create_text()
        self.__create_box()

    def __create_text(self):
        colour = const.ORIENTATION_COLOUR[self.orientation]

        text = vu.TextZero()
        text.SetColour(colour)
        text.SetSize(const.TEXT_SIZE_LARGE)
        text.SetPosition(const.TEXT_POS_LEFT_DOWN_ZERO)
        #text.SetVerticalJustificationToBottom()
        text.SetValue(self.number)
        self.text = text

    def __create_line_actor(self, line):
        line_mapper = vtk.vtkPolyDataMapper2D()
        line_mapper.SetInput(line.GetOutput())

        line_actor = vtk.vtkActor2D()
        line_actor.SetMapper(line_mapper)
        return line_actor

    def __create_box(self):
        xi = yi = 0.1
        xf = yf = 200
        line_i = vtk.vtkLineSource()
        line_i.SetPoint1((xi, yi, 0))
        line_i.SetPoint2((xf, yi, 0))
        self.line_i = line_i
        self.line_i_actor = self.__create_line_actor(line_i)

        line_s = vtk.vtkLineSource()
        line_s.SetPoint1((xi, yf, 0))
        line_s.SetPoint2((xf, yf, 0))
        self.line_s = line_s
        self.line_s_actor = self.__create_line_actor(line_s)

        line_l = vtk.vtkLineSource()
        line_l.SetPoint1((xi, yi, 0))
        line_l.SetPoint2((xi, yf, 0))
        self.line_l = line_l
        self.line_l_actor = self.__create_line_actor(line_l)

        line_r = vtk.vtkLineSource()
        line_r.SetPoint1((xf, yi, 0))
        line_r.SetPoint2((xf, yf, 0))
        self.line_r = line_r
        self.line_r_actor = self.__create_line_actor(line_r)

        box_actor = vtk.vtkPropAssembly()
        box_actor.AddPart(self.line_i_actor)
        box_actor.AddPart(self.line_s_actor)
        box_actor.AddPart(self.line_l_actor)
        box_actor.AddPart(self.line_r_actor)
        self.box_actor = box_actor

    def __set_border_colours(self, colours_borders):
        for colour, actors in colours_borders.items():
            for actor in actors:
                actor.GetProperty().SetColor(colour)

    def SetBorderStyle(self, style=BORDER_NONE):
        colour_e = const.ORIENTATION_COLOUR[self.orientation]
        colour_i = (1, 1, 1)

        extern_borders = []
        intern_borders = []

        if style & BORDER_UP:
            extern_borders.append(self.line_s_actor)
        else:
            intern_borders.append(self.line_s_actor)

        if style & BORDER_DOWN:
            extern_borders.append(self.line_i_actor)
        else:
            intern_borders.append(self.line_i_actor)

        if style & BORDER_LEFT:
            extern_borders.append(self.line_l_actor)
        else:
            intern_borders.append(self.line_l_actor)

        if style & BORDER_RIGHT:
            extern_borders.append(self.line_r_actor)
        else:
            intern_borders.append(self.line_r_actor)

        self.__set_border_colours({colour_i: intern_borders, 
                                   colour_e: extern_borders})

    def SetCursor(self, cursor):
        if self.cursor:
            self.renderer.RemoveActor(self.cursor.actor)
        self.renderer.AddActor(cursor.actor)
        self.cursor = cursor

    def SetNumber(self, number):
        self.number = number
        self.text.SetValue("%d" % self.number)
        self.text.SetPosition(const.TEXT_POS_LEFT_DOWN_ZERO)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        colour = const.ORIENTATION_COLOUR[self.orientation]
        self.text.SetColour(colour)
        #self.box_actor.GetProperty().SetColor(colour)


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

    def Show(self):
        self.renderer.AddActor(self.actor)
        self.renderer.AddActor(self.text.actor)
