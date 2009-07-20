from  math import *

import vtk

class CursorCircle:
   # TODO: Think and try to change this class to an actor
   # CursorCircleActor(vtk.vtkActor)
    
    def __init__(self):
        
        self.colour = (0.0, 0.0, 1.0)
        self.opacity = 1
        self.radius = 20
        self.position = (0 ,0, 1)
        self.points = []
        self.orientation = "AXIAL"
        
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
        disk.SetInnerRadius(self.radius)
        disk.SetOuterRadius(0) # filled
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
        xc = 0
        yc = 0
        z = 0
        self.pixel_list = []
        radius = int(self.radius)
        for i in xrange(int(yc - radius), int(yc + radius)):
            # distance from the line to the circle's center
            d = yc - i
            # line size
            line = sqrt(round(radius ** 2) - round(d ** 2)) * 2
            # line initial x
            xi = int(xc - line/2)
            # line final
            xf = int(line/2 + xc)
            yi = i
            for k in xrange(xi,xf):
                self.pixel_list.append((k, yi))

    def SetSize(self, radius):
        self.radius = radius
        disk.SetInnerRadius(radius)
        self.__calculate_area_pixels()
        
    def SetColour(self, colour):
        self.actor.GetProperty().SetColor(self.colour)

    def SetOrientation(self, orientation):
        self.orientation = orientation

        if orientation == "CORONAL":
            self.actor.RotateX(90)

        if orientation == "SAGITAL":
            self.actor.RotateY(90)

    def SetPosition(self, position):
    
        #if self.orientation == "AXIAL":
        #    z = 1
        #elif self.orientation == "CORONAL":
        #    y = 1
        #elif self.orientation == "SAGITAL":
        #    x = 1
        self.position = position
        self.actor.SetPosition(position)

    def GetPixels(self):
        px, py, pz = self.position
        orient = self.orientation
        for pixel_0,pixel_1 in self.pixel_list:
            # The position of the pixels in this list is relative (based only on
            # the area, and not the cursor position).
            # Let's calculate the absolute position
            # TODO: Optimize this!!!!
            absolute_pixel = {"AXIAL": (px + pixel_0, py + pixel_1, pz),
                              "CORONAL": (px + pixel_0, py, pz + pixel_1),
                              "SAGITAL": (px, py + pixel_0, pz + pixel_1)}
            yield absolute_pixel[orient]
