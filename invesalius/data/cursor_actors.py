from  math import *

import vtk
import wx.lib.pubsub as ps

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
        orientation_based_spacing = {"AXIAL" : (xs, ys),
                                     "SAGITAL" : (ys, zs),
                                     "CORONAL" : (xs, zs)}
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

    def GetPixels(self):
        px, py, pz = self.edition_position
        orient = self.orientation
        xs, ys, zs = self.spacing
        for pixel_0,pixel_1 in self.pixel_list:
            # The position of the pixels in this list is relative (based only on
            # the area, and not the cursor position).
            # Let's calculate the absolute position
            # TODO: Optimize this!!!!
            abs_pixel = {"AXIAL": [px+pixel_0/xs, py+(pixel_1/ys), pz],
                         "CORONAL": [px+(pixel_0/xs), py, pz+(pixel_1/zs)],
                         "SAGITAL": [px, py+(pixel_0/ys), pz+(pixel_1/zs)]}
            yield abs_pixel[orient]
            
            
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------

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
        
        self.mapper = vtk.vtkPolyDataMapper()
    
        self.retangle = vtk.vtkCubeSource()
        self.actor = vtk.vtkActor()
        
        self.seeds_yi = vtk.vtkLineSource()
        self.seeds_yf = vtk.vtkLineSource()
        self.seeds_xi = vtk.vtkLineSource()
        self.seeds_xf = vtk.vtkLineSource()
        self.join_lines = vtk.vtkAppendPolyData()
        
        self.__build_actor()
        self.__calculate_area_pixels()
        
    def SetSize(self, size):
        print "SetSize", size
        self.x_length = size
        self.y_length = size
        retangle = self.retangle
        retangle.SetXLength(size)
        retangle.SetYLength(size)
        
        seeds_yi = self.seeds_yi
        seeds_yi.SetPoint1(0, 0, 0)
        seeds_yi.SetPoint2(0, self.y_length, 0)
        
        seeds_yf = self.seeds_yf
        seeds_yf.SetPoint1(self.x_length, self.y_length, 0)
        seeds_yf.SetPoint2(self.x_length, 0, 0)
        
        seeds_xi = self.seeds_xi
        seeds_xi.SetPoint1(0, self.y_length, 0)
        seeds_xi.SetPoint2(self.x_length, self.y_length, 0)
        
        seeds_xf = self.seeds_xf
        seeds_xf.SetPoint1(0, 0, 0)
        seeds_xf.SetPoint2(self.x_length, 0, 0)
        
        #join_lines = self.join_lines
        #join_lines.AddInput(seeds_yi.GetOutput())
        #join_lines.AddInput(seeds_yf.GetOutput())
        #join_lines.AddInput(seeds_xi.GetOutput())
        #join_lines.AddInput(seeds_xf.GetOutput())
        
        self.__calculate_area_pixels()
        
    def SetOrientation(self, orientation):
        self.orientation = orientation
        
    def SetColour(self, colour):
        self.colour = colour
        self.actor.GetProperty().SetColor(colour)

    def SetOrientation(self, orientation):
        self.orientation = orientation

        if orientation == "CORONAL":
            self.actor.RotateX(90)

        if orientation == "SAGITAL":
            self.actor.RotateY(90)

    def SetPosition(self, position):
        x,y,z = position
        x_half = self.x_length / 2.0
        y_half = self.y_length / 2.0
        orientation_position_based = {"AXIAL" : (x - x_half,y - y_half, z),
                                      "CORONAL" : (x - x_half, y, z - y_half),
                                      "SAGITAL" : (x, y - y_half, z + x_half)}
        xc,yc,zc = orientation_position_based[self.orientation]
        self.position = (xc,yc,zc)
        self.actor.SetPosition(xc,yc,zc)

    def SetEditionPosition(self, position):
        self.edition_position = position

    def SetSpacing(self, spacing):
        self.spacing = spacing

    def __build_actor(self):
        """
        Function to plot the Retangle
        """
        retangle = self.retangle
        retangle.SetXLength(self.x_length)
        retangle.SetYLength(self.y_length)
        
        seeds_yi = self.seeds_yi
        seeds_yi.SetPoint1(0, 0, 0)
        seeds_yi.SetPoint2(0, self.y_length, 0)
        
        seeds_yf = self.seeds_yf
        seeds_yf.SetPoint1(self.x_length, self.y_length, 0)
        seeds_yf.SetPoint2(self.x_length, 0, 0)
        
        seeds_xi = self.seeds_xi
        seeds_xi.SetPoint1(0, self.y_length, 0)
        seeds_xi.SetPoint2(self.x_length, self.y_length, 0)
        
        seeds_xf = self.seeds_xf
        seeds_xf.SetPoint1(0, 0, 0)
        seeds_xf.SetPoint2(self.x_length, 0, 0)
        
        join_lines = self.join_lines
        join_lines.AddInput(seeds_yi.GetOutput())
        join_lines.AddInput(seeds_yf.GetOutput())
        join_lines.AddInput(seeds_xi.GetOutput())
        join_lines.AddInput(seeds_xf.GetOutput())

        mapper = self.mapper
        mapper.SetScalarRange(0, 360)
        
        actor = self.actor

        mapper.SetInput(join_lines.GetOutput())
        actor.SetPosition(self.position[0]-self.x_length/2, # if filled remov -
                            self.position[1]-self.y_length/2, 1) # idem
        
        actor.SetMapper(mapper)
        actor.GetProperty().SetOpacity(self.opacity)
        actor.GetProperty().SetColor(self.colour) 
        actor.SetVisibility(1)

    def __calculate_area_pixels(self):
        xc = 0
        yc = 0
        z = 0
        xs, ys, zs = self.spacing 
        orientation_based_spacing = {"AXIAL" : (xs, ys),
                                     "SAGITAL" : (ys, zs),
                                     "CORONAL" : (xs, zs)}
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
        for pixel_0,pixel_1 in self.pixel_list:
            # The position of the pixels in this list is relative (based only on
            # the area, and not the cursor position).
            # Let's calculate the absolute position
            # TODO: Optimize this!!!!
            abs_pixel = {"AXIAL": [px+pixel_0/xs, py+(pixel_1/ys), pz],
                         "CORONAL": [px+(pixel_0/xs), py, pz+(pixel_1/zs)],
                         "SAGITAL": [px, py+(pixel_0/ys), pz+(pixel_1/zs)]}
            yield abs_pixel[orient]
        
