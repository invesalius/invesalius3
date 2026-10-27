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
"""Scalar point data prepared for surface visualization."""

from dataclasses import dataclass

from vtkmodules.vtkCommonDataModel import vtkPolyData


@dataclass
class SurfaceScalarMap:
    polydata: vtkPolyData
    name: str
    unit: str

    def __post_init__(self):
        scalars = self.polydata.GetPointData().GetScalars()
        if scalars is not None and (
            scalars.GetNumberOfComponents() != 1
            or scalars.GetNumberOfTuples() != self.polydata.GetNumberOfPoints()
        ):
            raise ValueError("A scalar value is required for each surface point.")
