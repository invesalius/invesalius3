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
        self.position = (0 ,0, 1)
        self.points = []
        self.orientation = "AXIAL"
        self.spacing = (1, 1, 1)
        
        self.mapper = vtk.vtkPolyDataMapper()
        self.disk = vtk.vtkDiskSource()
        self.actor = vtk.vtkActor()
        
        self.__build_actor()
        self.__calculate_area_pixels()
        
    def __build_actor(self):
        """
        Function to plot the circle
        """

        disk = self.disk
        disk.SetInnerRadius(self.radius-1) # filled = self.radius
        disk.SetOuterRadius(self.radius) # filled = 0x
        disk.SetRadialResolution(50)
        disk.SetCircumferentialResolution(50)

        mapper = self.mapper
        mapper.SetInput(disk.GetOutput())

        actor = self.actor      
        actor.SetMapper(mapper)
        actor.GetProperty().SetOpacity(self.opacity)
        actor.GetProperty().SetColor(self.colour) 
        actor.SetPosition(self.position)
        actor.SetVisibility(1)
        actor.PickableOff()

    def __calculate_area_pixels(self):
        """
        Return the cursor's pixels.
        This method scans the circle line by line.
        Extracted equation. 
        http://www.mathopenref.com/chord.html
        """
        xc = 0.0
        yc = 0.0
        z = 0.0
        xs, ys, zs = self.spacing 
        
        proj = Project()
        orig_orien = proj.original_orientation
        
        xy = (xs, ys)
        yz = (ys, zs)
        xz = (xs, zs)
        
        if (orig_orien == const.SAGITAL):
            orientation_based_spacing = {"SAGITAL" : xy,
                                     "AXIAL" : yz,
                                     "CORONAL" : xz}
        elif(orig_orien == const.CORONAL):
            orientation_based_spacing = {"CORONAL" : xy,
                                         "AXIAL" : xz,
                                         "SAGITAL" : yz}
        else:
            orientation_based_spacing = {"AXIAL" : xy,
                                         "SAGITAL" : yz,
                                         "CORONAL" : xz}
        
        xs, ys = orientation_based_spacing[self.orientation]
        self.pixel_list = []
        radius = self.radius
        for i in utils.frange(yc - radius, yc + radius, ys):
            # distance from the line to the circle's center
            d = yc - i
            # line size
            line = sqrt(radius**2 - d**2) * 2
            # line initial x
            xi = xc - line/2.0
            # line final
            xf = line/2.0 + xc
            yi = i
            for k in utils.frange(xi,xf,xs):
                self.pixel_list.append((k, yi))

    def SetSize(self, diameter):
        radius = self.radius = diameter/2.0
        self.disk.SetInnerRadius(radius-1) # filled = self.radius
        self.disk.SetOuterRadius(radius) # filled = 0
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
        px, py, pz = self.edition_position
        orient = self.orientation
        xs, ys, zs = self.spacing
        proj = Project()
        orig_orien = proj.original_orientation
        xy1 = lambda x,y: (px + x / xs, py+(y/ys), pz)
        xy2 = lambda x,y: (px+(x/xs), py, pz+(y/zs))
        xy3 = lambda x,y: (px, py+(x/ys), pz+(y/zs))
        
        if (orig_orien == const.SAGITAL):
            abs_pixel = {"SAGITAL": xy1,
                         "AXIAL": xy2,
                         "CORONAL": xy3}
        elif(orig_orien == const.CORONAL):
            abs_pixel = {"CORONAL": xy1,
                         "SAGITAL": xy3,
                         "AXIAL": xy2}
        else:
            abs_pixel = {"AXIAL": xy1,
                        "CORONAL": xy2,
                        "SAGITAL": xy3}
            
        function_orientation = abs_pixel[orient]
        
        for pixel_0,pixel_1 in self.pixel_list:
            # The position of the pixels in this list is relative (based only on
            # the area, and not the cursor position).
            # Let's calculate the absolute position
            # TODO: Optimize this!!!!
            yield function_orientation(pixel_0, pixel_1)
            



class CursorRectangle:
    
    def __init__(self):
        
        self.colour = (0.0, 0.0, 1.0) 
        self.opacity = 1
        
        self.x_length = 30
        self.y_length = 30
        
        self.dimension = (self.x_length, self.y_length)
        self.position = (0 ,0)
        self.orientation = "AXIAL"
        self.spacing = (1, 1, 1)
                
        self.__build_actor()
        self.__calculate_area_pixels()
        
    def SetSize(self, size):
        self.x_length = size
        self.y_length = size
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
        actor.SetVisibility(1)

    def __calculate_area_pixels(self):
        xc = 0
        yc = 0
        z = 0
        xs, ys, zs = self.spacing 
        
        proj = Project()
        orig_orien = proj.original_orientation
        
        xy = (xs, ys)
        yz = (ys, zs)
        xz = (xs, zs)
        
        if (orig_orien == const.SAGITAL):
            orientation_based_spacing = {"SAGITAL" : xy,
                                     "AXIAL" : yz,
                                     "CORONAL" : xz}
        elif(orig_orien == const.CORONAL):
            orientation_based_spacing = {"CORONAL" : xy,
                                         "AXIAL" : xz,
                                         "SAGITAL" : yz}
        else:
            orientation_based_spacing = {"AXIAL" : xy,
                                         "SAGITAL" : yz,
                                         "CORONAL" : xz}
        
        xs, ys = orientation_based_spacing[self.orientation]
        self.pixel_list = []
        for i in utils.frange(yc - self.y_length/2, yc + self.y_length/2, ys):
            for k in utils.frange(xc - self.x_length/2, xc + self.x_length/2, xs):
                self.pixel_list.append((k, i))


    def GetPixels(self):
        """
        Return the points of the rectangle
        """
        px, py, pz = self.edition_position
        orient = self.orientation
        xs, ys, zs = self.spacing
        proj = Project()
        orig_orien = proj.original_orientation
        xy1 = lambda x,y: (px + x / xs, py+(y/ys), pz)
        xy2 = lambda x,y: (px+(x/xs), py, pz+(y/zs))
        xy3 = lambda x,y: (px, py+(x/ys), pz+(y/zs))
        
        if (orig_orien == const.SAGITAL):
            abs_pixel = {"SAGITAL": xy1,
                         "AXIAL": xy2,
                         "CORONAL": xy3}
        elif(orig_orien == const.CORONAL):
            abs_pixel = {"CORONAL": xy1,
                         "SAGITAL": xy3,
                         "AXIAL": xy2}
        else:
            abs_pixel = {"AXIAL": xy1,
                        "CORONAL": xy2,
                        "SAGITAL": xy3}
        function_orientation = abs_pixel[orient]
        for pixel_0,pixel_1 in self.pixel_list:
            # The position of the pixels in this list is relative (based only on
            # the area, and not the cursor position).
            # Let's calculate the absolute position
            # TODO: Optimize this!!!!
            yield function_orientation(pixel_0, pixel_1)
