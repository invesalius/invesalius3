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

from  math import *

import numpy
import vtk
import wx.lib.pubsub as ps
from project import Project
import constants as const
import utils

class CursorCircle:
   # TODO: Think and try to change this class to an actor
   # CursorCircleActor(vtk.vtkActor)
    
    def __init__(self):
        
        self.colour = (0.0, 0.0, 1.0)
        self.opacity = 1
        self.radius = 15.0
        #self.position = (0.5,0.5, 1)
        self.points = []
        self.orientation = "AXIAL"
        self.spacing = (1, 1, 1)
        
        self.mapper = vtk.vtkPolyDataMapper()
        self.actor = vtk.vtkActor()
        self.property = vtk.vtkProperty()
        
        self.__build_actor()
        self.__calculate_area_pixels()
        
    def __build_actor(self):
        """
        Function to plot the circle
        """

        r = self.radius
        t = 0
        
        self.posc_a = 0
        self.posc_b = 0
        
        self.segment = vtk.vtkAppendPolyData()
        
        self.xa = self.posc_a + r * cos(t)
        self.ya = self.posc_a + r * sin(t)
                    
        while(t <= 2 * pi):
            self.GenerateCicleSegment(t)
            t = t + 0.05

        self.GenerateCicleSegment(0)
        
        self.mapper.SetInputConnection(self.segment.GetOutputPort())
        self.actor.SetMapper(self.mapper)
        self.actor.PickableOff()
        
    def GenerateCicleSegment(self, t):
        """
        Generate cicle segment
        """
        x = self.posc_a + self.radius * cos(t)
        y = self.posc_b + self.radius * sin(t)
    
        ls = vtk.vtkLineSource()
        ls.SetPoint1(self.xa, self.ya, 0)
        ls.SetPoint2(x, y, 0)

        self.segment.AddInput(ls.GetOutput())
        self.xa, self.ya = x, y
        
    def __calculate_area_pixels(self):
        """
        Return the cursor's pixels.
        """
        radius = self.radius
        if self.orientation == 'AXIAL':
            sx = self.spacing[0]
            sy = self.spacing[1]
        elif self.orientation == 'CORONAL':
            sx = self.spacing[0]
            sy = self.spacing[2]
        elif self.orientation == 'SAGITAL':
            sx = self.spacing[1]
            sy = self.spacing[2]

        y,x = numpy.ogrid[-radius/sy:+radius/sy,
                          -radius/sx:+radius/sx]

        index = (y*sy)**2 + (x*sx)**2 <= radius**2
        self.points = index


    def SetSize(self, diameter):
        radius = self.radius = diameter/2.0
        #self.disk.SetInnerRadius(radius-1) # filled = self.radius
        #self.disk.SetOuterRadius(radius) # filled = 0
        self.__build_actor()
        self.__calculate_area_pixels()
        
        
        
    def SetColour(self, colour):
        self.colour = colour
        self.actor.GetProperty().SetColor(colour)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        proj = Project() 
        orig_orien = proj.original_orientation
        if (orig_orien == const.SAGITAL):
            if orientation == "CORONAL":
                self.actor.RotateY(90)
            if orientation == "AXIAL":
                self.actor.RotateX(90)
        elif(orig_orien == const.CORONAL):
            if orientation == "AXIAL":
                self.actor.RotateX(270)
            if orientation == "SAGITAL":
                self.actor.RotateY(90)
        else:
            if orientation == "CORONAL":
                self.actor.RotateX(90)
            if orientation == "SAGITAL":
                self.actor.RotateY(90)

    def SetPosition(self, position):
        self.position = position
        self.actor.SetPosition(position)

    def SetEditionPosition(self, position):
        self.edition_position = position

    def SetSpacing(self, spacing):
        self.spacing = spacing
        self.__calculate_area_pixels()

    def Show(self, value=1):
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()

    def GetPixels(self):
        return self.points


class CursorRectangle:
    
    def __init__(self):
        
        self.colour = (0.0, 0.0, 1.0) 
        self.opacity = 1
        
        self.x_length = 30
        self.y_length = 30
        self.radius = 15
        
        self.dimension = (self.x_length, self.y_length)
        self.position = (0 ,0)
        self.orientation = "AXIAL"
        self.spacing = (1, 1, 1)
                
        self.__build_actor()
        self.__calculate_area_pixels()
        
    def SetSize(self, size):
        self.x_length = size
        self.y_length = size
        self.radius = size / 2
        retangle = self.retangle
        retangle.SetXLength(size)
        retangle.SetYLength(size)        
        self.__calculate_area_pixels()
        
    def SetOrientation(self, orientation):
        self.orientation = orientation
        
    def SetColour(self, colour):
        self.colour = colour
        self.actor.GetProperty().SetColor(colour)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        proj = Project() 
        orig_orien = proj.original_orientation
        if (orig_orien == const.SAGITAL):
            if orientation == "CORONAL":
                self.actor.RotateY(90)
            if orientation == "AXIAL":
                self.actor.RotateX(90)
        elif(orig_orien == const.CORONAL):
            if orientation == "AXIAL":
                self.actor.RotateX(270)
            if orientation == "SAGITAL":
                self.actor.RotateY(90)
        else:
            if orientation == "CORONAL":
                self.actor.RotateX(90)
            if orientation == "SAGITAL":
                self.actor.RotateY(90)

    def SetPosition(self, position):
        x,y,z = position
        self.position = position
        self.actor.SetPosition(x,y,z)
        
    def SetEditionPosition(self, position):
        self.edition_position = position

    def SetSpacing(self, spacing):
        self.spacing = spacing

    def Show(self, value=1):
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()

    def __build_actor(self):
        """
        Function to plot the Retangle
        """
        mapper = vtk.vtkPolyDataMapper()
        self.retangle = vtk.vtkCubeSource()
        self.actor = actor = vtk.vtkActor()
        
        prop = vtk.vtkProperty()
        prop.SetRepresentationToWireframe()
        self.actor.SetProperty(prop)
        
        mapper.SetInput(self.retangle.GetOutput())
        actor.SetPosition(self.position[0] - self.x_length,\
                          self.position[1] - self.y_length, 1)
        
        actor.SetMapper(mapper)
        actor.GetProperty().SetOpacity(self.opacity)
        actor.GetProperty().SetColor(self.colour) 
        actor.SetVisibility(0)

    def __calculate_area_pixels(self):
        if self.orientation == 'AXIAL':
            sx = self.spacing[0]
            sy = self.spacing[1]
        elif self.orientation == 'CORONAL':
            sx = self.spacing[0]
            sy = self.spacing[2]
        elif self.orientation == 'SAGITAL':
            sx = self.spacing[1]
            sy = self.spacing[2]
        shape = (self.y_length/sy, self.x_length/sx)
        self.points = numpy.empty(shape, dtype='bool')
        self.points.fill(True)

    def GetPixels(self):
        """
        Return the points of the rectangle
        """
        return self.points
