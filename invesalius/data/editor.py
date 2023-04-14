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

from invesalius.pubsub import pub as Publisher
from typing import Tuple

from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkImagingCore import vtkImageBlend, vtkImageMapToColors
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleImage
from vtkmodules.vtkRenderingCore import vtkImageActor, vtkCellPicker, vtkImageMapper

AXIAL: int = 2
CORONAL: int = 1
SAGITAL: int = 0

class Editor:
    """
    To Use:
    
    editor = Editor()
    editor.SetInteractor(self.interector)
    editor.SetOperationType(2, (50,1200)) #threshold 50, 1200
    editor.SetInput(img_original.GetOutput(), img_threshold.GetOutput())
    editor.Render()
    """
    
    def __init__(self) -> None:
        
        self.interactor: vtkRenderWindowInteractor = None
        self.image_original: vtkImageData = None
        self.image_threshold: vtkImageData = None
        self.render: vtkRenderer = None
    
        self.lut: vtkLookupTable = vtkLookupTable()
        self.lut_original: vtkLookupTable = vtkLookupTable()
        self.image_color: vtkImageMapToColors = vtkImageMapToColors()
        self.blend: vtkImageBlend = vtkImageBlend()
        self.map: vtkImageMapper = vtkImageMapper()
        
        self.actor: vtkImageActor = vtkImageActor()
        self.actor2: vtkImageActor = vtkImageActor()
        self.actor3: vtkImageActor = vtkImageActor()
        
        self.image_color_o: vtkImageMapToColors = vtkImageMapToColors()
        
        self.operation_type: int = 0
        self.w: Tuple[int, int] = None
   
        self.slice: int = 0
        self.clicked: int = 0
        self.orientation: int = AXIAL

        self.w: Tuple[int, int] = (200, 1200)
    
        #self.plane_widget_x = vtkImagePlaneWidget()
    
        #self.actor.PickableOff()

    
    def SetInteractor(self, interactor: vtkRenderWindowInteractor) -> None:
            
            self.interactor = interactor
            self.render = interactor.GetRenderWindow().GetRenderers().GetFirstRenderer()          
    
            istyle: vtkInteractorStyleImage = vtkInteractorStyleImage()
            istyle.SetInteractor(interactor)
            istyle.AutoAdjustCameraClippingRangeOn()
            interactor.SetInteractorStyle(istyle)
            
            istyle.AddObserver("LeftButtonPressEvent", self.Click)
            istyle.AddObserver("LeftButtonReleaseEvent", self.Release)
            istyle.AddObserver("MouseMoveEvent",self.Moved)
    
            pick = self.pick = vtkCellPicker()
    
    def SetActor(self, actor: vtkImageActor) -> None:
        self.actor = actor

    def SetImage(self, image: vtkImageData) -> None:
        self.image = image

    def SetCursor(self, cursor: Cursor) -> None:
        self.cursor = cursor
        self.cursor.CursorCircle(self.render)

    def SetOrientation(self, orientation: int) -> None:
        self.orientation = orientation

    def Click(self, obj: Any, evt: Any) -> None:
        self.clicked = 1

    def Release(self, obj: Any, evt: Any) -> None:
        self.clicked = 0

    def Moved(self, obj: Any, evt: Any) -> None:
        pos: Tuple[int, int] = self.interactor.GetEventPosition()
        wx: int = pos[0] #- last[0]
        wy: int = pos[1] #- last[1]
        self.pick.Pick(wx, wy, 0, self.render)
        x,y,z = self.pick.GetPickPosition()

        self.cursor.SetPosition(x, y, z)  
        self.cursor.Update()    
        if self.clicked == 1:
        #    op = self.rbOptions.GetSelection()
        #    a = (int(self.txtThresI.GetValue()), int(self.txtThresF.GetValue()))
        #    self.editor.SetOperationType(op, a)
            wx, wy, wz = self.From3dToImagePixel(pos, (x, y, z))
            self.DoOperation(wx, wy, wz)
            Publisher.sendMessage('Update images', self.image)
            Publisher.sendMessage('Update viewer', None)

        #self.cursor.Update()
        obj.OnMouseMove()

        self.interactor.Render()
    

    def From3dToImagePixel(self, mPos: Tuple[int, int], pPos: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        mPos - The mouse position in the screen position.
        pPos - the pick position in the 3d world
        """
        x, y, z = pPos
        bounds: Tuple[float, float, float, float, float, float] = self.actor.GetBounds()

        #c = vtkCoordinate()
        #c.SetCoordinateSystemToWorld()
        #c.SetValue(bounds[::2])
        #xi, yi = c.GetComputedViewportValue(self.render)

        #c.SetValue(bounds[1::2])
        #xf, yf = c.GetComputedViewportValue(self.render)
        
        xi: float = bounds[0]
        xf: float = bounds[1]
        yi: float = bounds[2]
        yf: float = bounds[3]
        zi: float = bounds[4]
        zf: float = bounds[5]

        #c.SetValue(x, y, z)
        #wx, wy = c.GetComputedViewportValue(self.render)

        wx: float = x - xi
        wy: float = y - yi
        wz: float = z - zi
        
        dx: float = xf - xi
        dy: float = yf - yi
        dz: float = zf - zi

        try:
            wx = (wx * self.image.GetDimensions()[0]) / dx
        except ZeroDivisionError:
            wx = self.slice 
        try:
            wy = (wy * self.image.GetDimensions()[1]) / dy
        except ZeroDivisionError:
            wy = self.slice
        try:
            wz = (wz * self.image.GetDimensions()[2]) / dz
        except ZeroDivisionError:
            wz = self.slice
        
        return wx, wy, wz


    
    def __init__(self):
        self.image_original: vtkImageData = None
        self.image_threshold: vtkImageData = None
        self.slice: int = 0
        self.map = None
        self.interactor = None
        self.image: vtkImageData = None
        self.w: Tuple[float, float] = (0.0, 0.0)

    def SetInput(self, image_original: vtkImageData, image_threshold: vtkImageData) -> None:
        self.image_original = image_original
        self.image_threshold = image_threshold
    
    def SetSlice(self, a: int) -> None:
        self.slice = a

    def ChangeShowSlice(self, value: int) -> None:
        self.map.SetZSlice(value) 
        self.interactor.Render()

    def ErasePixel(self, x: int, y: int, z: int) -> None:
        """
        Deletes pixel, it is necessary to pass x, y and z.
        """
        self.image.SetScalarComponentFromDouble(x, y, z, 0, 0)
        self.image.Update()
        
    def FillPixel(self, x: int, y: int, z: int, colour: int = 3200) -> None:
        """
        Fill pixel, it is necessary to pass x, y and z 
        """

        self.image.SetScalarComponentFromDouble(x, y, z, 0, colour)
        
    def PixelThresholdLevel(self, x: int, y: int, z: int) -> None:
        """
        Erase or Fill with Threshold level
        """
        pixel_colour: float = self.image.GetScalarComponentAsDouble(x, y, z, 0)
        
        thres_i: float = self.w[0]
        thres_f: float = self.w[1]
    
        if (pixel_colour >= thres_i) and (pixel_colour <= thres_f):
            
            if (pixel_colour <= 0):
                self.FillPixel(x, y, z, 1)
            else:
                self.FillPixel(x, y, z, int(pixel_colour))
    
        else:
            self.ErasePixel(x, y, z)
    
    
    def DoOperation(self, xc: int, yc: int, zc: int) -> None:
        """
        This method scans the circle line by line.
        Extracted equation. 
        http://www.mathopenref.com/chord.html
        """
        extent = self.image.GetWholeExtent()
        cursor = self.cursor
        b = [0,0,0,0,0,0]
        self.actor.GetDisplayBounds(b)
        xs, ys, zs = self.image.GetSpacing()
        try:
            zs = (b[-1]-b[-2]) / self.image.GetDimensions()[2]
        except ZeroDivisionError:
            pass
        if self.orientation == AXIAL:
            o = lambda x, y: (xc + x, y + yc, zc)
        elif self.orientation == CORONAL:
            o = lambda x, y: (xc + x, yc, zc + y/zs)
        elif self.orientation == SAGITAL:
            o = lambda x, y: (xc, yc + x, zc + y/zs)

        if (self.operation_type == 0):
            operation = self.ErasePixel
        elif(self.operation_type == 1):
            operation = self.FillPixel
        else:
            operation = self.PixelThresholdLevel
        try:
            [operation(*o(k, yi)) for k, yi in cursor.GetPoints()]
        except:
            pass
        #if extent[0] <= k+xc <= extent[1] \
            #and extent[2] <= yi+yc <=extent[3]]
        
    def SetOperationType(self, operation_type: int = 0, w: Tuple[float, float] = (100,1200)) -> None:
        """
        Set Operation Type
        0 -> Remove
        1 -> Add
        2 -> Add or Remove with Threshold Level
        """            
        self.operation_type = operation_type
        self.w = w #threshold_value
