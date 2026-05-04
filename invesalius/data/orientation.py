# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------
AXIAL = 2
CORONAL = 1
SAGITAL = 0


class Orientation:
    def __init__(self, interactor, actor):
        self.interactor = interactor
        self.actor = actor
        self.image = actor.GetInput()
        self.ren = interactor.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self.slice = 0

    def SetOrientation(self, orientation):
        cam = self.ren.GetActiveCamera()
        self.orientation = orientation
        extent = self.image.GetWholeExtent()

        if orientation == AXIAL:
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(0, 0, 1)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 1, 0)

            xs = extent[1] - extent[0] + 1
            # ys = extent[3] - extent[2] + 1

        elif orientation == CORONAL:
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(0, -1, 0)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 0, 1)

            xs = extent[1] - extent[0] + 1
            # ys = extent[5] - extent[4] + 1

        elif orientation == SAGITAL:
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(1, 0, 0)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 0, 1)

            xs = extent[3] - extent[2] + 1
            # ys = extent[5] - extent[4] + 1

        if xs < 150:
            scale = 75
        else:
            scale = (xs - 1) / 2.0

        cam.OrthogonalizeViewUp()
        self.UpdateDisplayExtent()
        # self.ren.ResetCamera()
        cam.ParallelProjectionOn()
        cam.SetParallelScale(scale)
        self.ren.AddActor(self.actor)
        self.ren.ResetCamera()
        # cam.SetParallelScale(130)

        self.ren.Render()

    def UpdateDisplayExtent(self):
        extent = self.image.GetWholeExtent()
        if self.orientation == AXIAL:
            # xs = extent[1] - extent[0] + 1
            # ys = extent[3] - extent[2] + 1

            actor = self.actor
            actor.SetInput(self.image)
            actor.SetDisplayExtent(
                extent[0], extent[1], extent[2], extent[3], self.slice, self.slice
            )

        elif self.orientation == CORONAL:
            # xs = extent[1] - extent[0] + 1
            # ys = extent[5] - extent[4] + 1

            actor = self.actor
            actor.SetInput(self.image)
            actor.SetDisplayExtent(
                extent[0], extent[1], self.slice, self.slice, extent[4], extent[5]
            )

        elif self.orientation == SAGITAL:
            # xs = extent[3] - extent[2] + 1
            # ys = extent[5] - extent[4] + 1

            actor = self.actor
            actor.SetInput(self.image)
            actor.SetDisplayExtent(
                self.slice, self.slice, extent[2], extent[3], extent[4], extent[5]
            )

        self.ren.AddActor(self.actor)

        self.ren.ResetCameraClippingRange()

        cam = self.ren.GetActiveCamera()

        bounds = self.actor.GetBounds()
        spos = bounds[self.orientation * 2]
        cpos = cam.GetPosition()[self.orientation]
        range = abs(spos - cpos)
        spacing = self.actor.GetInput().GetSpacing()
        avg_spacing = sum(spacing) / 3.0
        cam.SetClippingRange(range - avg_spacing * 3.0, range + avg_spacing * 3.0)

        self.ren.Render()

    def SetSlice(self, slice):
        self.slice = slice
        self.UpdateDisplayExtent()

    def GetMaxSlice(self):
        return self.actor.GetSliceNumberMax()
