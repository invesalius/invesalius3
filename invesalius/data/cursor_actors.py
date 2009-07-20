from  math import *
import vtk
import utils

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
        xc = 0
        yc = 0
        z = 0
        xs, ys, zs = self.spacing 
        orientation_based_spacing = {"AXIAL" : (xs, ys),
                                     "SAGITAL" : (ys, zs),
                                     "CORONAL" : (xs, zs) }
        xs, ys = orientation_based_spacing[self.orientation]
        self.pixel_list = []
        radius = self.radius
        for i in utils.frange(yc - radius, yc + radius, ys):
            # distance from the line to the circle's center
            d = yc - i
            # line size
            line = sqrt(radius**2 - d**2) * 2
            # line initial x
            xi = xc - line/2
            # line final
            xf = line/2 + xc
            yi = i
            for k in utils.frange(xi,xf,xs):
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

    def SetEditionPosition(self, position):
        self.edition_position = position

    def SetSpacing(self, spacing):
        self.spacing = spacing

    def GetPixels(self):
        px, py, pz = self.edition_position
        orient = self.orientation
        xs, ys, zs = self.spacing
        for pixel_0,pixel_1 in self.pixel_list:
            # The position of the pixels in this list is relative (based only on
            # the area, and not the cursor position).
            # Let's calculate the absolute position
            # TODO: Optimize this!!!!
            absolute_pixel = {"AXIAL": (px + pixel_0 / xs , py + pixel_1 / ys, pz),
                              "CORONAL": (px + pixel_0 / xs, py, pz + pixel_1 / zs),
                              "SAGITAL": (px, py + pixel_0 / ys, pz + pixel_1 / zs) }
            yield absolute_pixel[orient]
