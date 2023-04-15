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
AXIAL: int = 2
CORONAL: int = 1
SAGITAL: int = 0

from typing import Any, Optional, Tuple

class Orientation(object):
    def __init__(self, interactor: object, actor: object) -> None:
        self.interactor: object = interactor
        self.actor: object = actor
        self.image: object = actor.GetInput()
        self.ren: object = interactor.GetRenderWindow().GetRenderers().GetFirstRenderer()          
        self.slice: int = 0

    def SetOrientation(self, orientation: int) -> None:
        cam: object = self.ren.GetActiveCamera()
        self.orientation: int = orientation
        extent: tuple = self.image.GetWholeExtent()

        if orientation == AXIAL:
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(0, 0, 1)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 1, 0)

            xs: int = extent[1] - extent[0] + 1
            ys: int = extent[3] - extent[2] + 1

        elif orientation == CORONAL:
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(0, -1, 0)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 0, 1)
            
            xs: int = extent[1] - extent[0] + 1
            ys: int = extent[5] - extent[4] + 1

        elif orientation == SAGITAL:
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(1, 0, 0)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 0, 1)

            xs: int = extent[3] - extent[2] + 1
            ys: int = extent[5] - extent[4] + 1

        if xs < 150:
            scale: int = 75
        else:
           
            scale: int = (xs - 1)/2.0
             
             
        cam.OrthogonalizeViewUp()
        self.UpdateDisplayExtent()
        #self.ren.ResetCamera()
        cam.ParallelProjectionOn()
        cam.SetParallelScale(scale)
        self.ren.AddActor(self.actor)
        self.ren.ResetCamera()
        #cam.SetParallelScale(130)
        
        self.ren.Render()
        

    def UpdateDisplayExtent(self) -> None:
        extent: list = self.image.GetWholeExtent()
        if self.orientation == AXIAL:
            xs: int = extent[1] - extent[0] + 1
            ys: int = extent[3] - extent[2] + 1

            actor: object = self.actor            
            actor.SetInput(self.image)
            actor.SetDisplayExtent(extent[0], extent[1], 
                                    extent[2], extent[3], 
                                    self.slice, self.slice)

        elif self.orientation == CORONAL:
            xs: int = extent[1] - extent[0] + 1
            ys: int = extent[5] - extent[4] + 1

            actor: object = self.actor            
            actor.SetInput(self.image)
            actor.SetDisplayExtent(extent[0], extent[1],
                                    self.slice, self.slice,
                                    extent[4], extent[5])

        elif self.orientation == SAGITAL:
            xs: int = extent[3] - extent[2] + 1
            ys: int = extent[5] - extent[4] + 1

            actor: object = self.actor            
            actor.SetInput(self.image)
            actor.SetDisplayExtent(self.slice, self.slice, 
                                    extent[2], extent[3],
                                    extent[4], extent[5])

        self.ren.AddActor(self.actor)
        
        self.ren.ResetCameraClippingRange()

        cam: object = self.ren.GetActiveCamera()
        
        bounds: list = self.actor.GetBounds()
        spos: float = bounds[self.orientation*2]
        cpos: float = cam.GetPosition()[self.orientation]
        range: float = abs(spos - cpos)
        spacing: list = self.actor.GetInput().GetSpacing()
        avg_spacing: float = sum(spacing)/3.0
        cam.SetClippingRange(range - avg_spacing * 3.0, range +\
                                avg_spacing * 3.0)
        
        self.ren.Render()

    def SetSlice(self, slice: int) -> None:
        self.slice = slice
        self.UpdateDisplayExtent()
        
    def GetMaxSlice(self) -> int:
        
        return self.actor.GetSliceNumberMax()
    