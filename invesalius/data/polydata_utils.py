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

import sys

import wx
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkFiltersCore import (
    vtkAppendPolyData,
    vtkCleanPolyData,
    vtkMassProperties,
    vtkPolyDataConnectivityFilter,
    vtkQuadricDecimation,
    vtkSmoothPolyDataFilter,
    vtkTriangleFilter,
)
from vtkmodules.vtkFiltersModeling import vtkFillHolesFilter
from vtkmodules.vtkIOGeometry import vtkOBJReader, vtkSTLReader
from vtkmodules.vtkIOPLY import vtkPLYReader
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader, vtkXMLPolyDataWriter

import invesalius.constants as const
import invesalius.data.vtk_utils as vu
from invesalius.i18n import tr as _
from invesalius.utils import touch

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

# Update progress value in GUI
UpdateProgress = vu.ShowProgress()


def ApplyDecimationFilter(polydata, reduction_factor):
    """
    Reduce number of triangles of the given vtkPolyData, based on
    reduction_factor.
    """
    # Important: vtkQuadricDecimation presented better results than
    # vtkDecimatePro
    decimation = vtkQuadricDecimation()
    decimation.SetInputData(polydata)
    decimation.SetTargetReduction(reduction_factor)
    decimation.GetOutput().ReleaseDataFlagOn()
    decimation.AddObserver(
        "ProgressEvent",
        lambda obj, evt: UpdateProgress(decimation, "Reducing number of triangles..."),
    )
    return decimation.GetOutput()


def ApplySmoothFilter(polydata, iterations, relaxation_factor):
    """
    Smooth given vtkPolyData surface, based on iteration and relaxation_factor.
    """
    smoother = vtkSmoothPolyDataFilter()
    smoother.SetInputData(polydata)
    smoother.SetNumberOfIterations(iterations)
    smoother.SetFeatureAngle(80)
    smoother.SetRelaxationFactor(relaxation_factor)
    smoother.FeatureEdgeSmoothingOn()
    smoother.BoundarySmoothingOn()
    smoother.GetOutput().ReleaseDataFlagOn()
    smoother.AddObserver(
        "ProgressEvent", lambda obj, evt: UpdateProgress(smoother, "Smoothing surface...")
    )

    return smoother.GetOutput()


def FillSurfaceHole(polydata):
    """
    Fill holes in the given polydata.
    """
    # Filter used to detect and fill holes. Only fill
    print("Filling polydata")
    filled_polydata = vtkFillHolesFilter()
    filled_polydata.SetInputData(polydata)
    filled_polydata.SetHoleSize(500)
    return filled_polydata.GetOutput()


def CalculateSurfaceVolume(polydata):
    """
    Calculate the volume from the given polydata
    """
    # Filter used to calculate volume and area from a polydata
    measured_polydata = vtkMassProperties()
    measured_polydata.SetInputData(polydata)
    return measured_polydata.GetVolume()


def CalculateSurfaceArea(polydata):
    """
    Calculate the volume from the given polydata
    """
    # Filter used to calculate volume and area from a polydata
    measured_polydata = vtkMassProperties()
    measured_polydata.SetInputData(polydata)
    return measured_polydata.GetSurfaceArea()


def Merge(polydata_list):
    append = vtkAppendPolyData()

    for polydata in polydata_list:
        triangle = vtkTriangleFilter()
        triangle.SetInputData(polydata)
        triangle.Update()
        append.AddInputData(triangle.GetOutput())

    append.Update()
    clean = vtkCleanPolyData()
    clean.SetInputData(append.GetOutput())
    clean.Update()

    return append.GetOutput()


def Export(polydata, filename, bin=False):
    writer = vtkXMLPolyDataWriter()
    if _has_win32api:
        touch(filename)
        filename = win32api.GetShortPathName(filename)
    writer.SetFileName(filename.encode(const.FS_ENCODE))
    if bin:
        writer.SetDataModeToBinary()
    else:
        writer.SetDataModeToAscii()
    writer.SetInputData(polydata)
    writer.Write()


def Import(filename):
    reader = vtkXMLPolyDataReader()
    try:
        reader.SetFileName(filename.encode())
    except AttributeError:
        reader.SetFileName(filename)
    reader.Update()
    return reader.GetOutput()


def LoadPolydata(path):
    if path.lower().endswith(".stl"):
        reader = vtkSTLReader()

    elif path.lower().endswith(".ply"):
        reader = vtkPLYReader()

    elif path.lower().endswith(".obj"):
        reader = vtkOBJReader()

    elif path.lower().endswith(".vtp"):
        reader = vtkXMLPolyDataReader()

    else:
        assert False, "Not a valid extension."

    reader.SetFileName(path)
    reader.Update()
    polydata = reader.GetOutput()

    return polydata


def JoinSeedsParts(polydata, point_id_list):
    """
    The function require vtkPolyData and point id
    from vtkPolyData.
    """
    conn = vtkPolyDataConnectivityFilter()
    conn.SetInputData(polydata)
    conn.SetExtractionModeToPointSeededRegions()
    UpdateProgress = vu.ShowProgress(1 + len(point_id_list))
    pos = 1
    for seed in point_id_list:
        conn.AddSeed(seed)
        UpdateProgress(pos, _("Analysing selected regions..."))
        pos += 1

    conn.AddObserver(
        "ProgressEvent", lambda obj, evt: UpdateProgress(conn, "Getting selected parts")
    )
    conn.Update()

    result = vtkPolyData()
    result.DeepCopy(conn.GetOutput())
    return result


def SelectLargestPart(polydata):
    """ """
    UpdateProgress = vu.ShowProgress(1)
    conn = vtkPolyDataConnectivityFilter()
    conn.SetInputData(polydata)
    conn.SetExtractionModeToLargestRegion()
    conn.AddObserver(
        "ProgressEvent", lambda obj, evt: UpdateProgress(conn, "Getting largest part...")
    )
    conn.Update()

    result = vtkPolyData()
    result.DeepCopy(conn.GetOutput())
    return result


def SplitDisconectedParts(polydata):
    """ """
    conn = vtkPolyDataConnectivityFilter()
    conn.SetInputData(polydata)
    conn.SetExtractionModeToAllRegions()
    conn.Update()

    nregions = conn.GetNumberOfExtractedRegions()

    conn.SetExtractionModeToSpecifiedRegions()
    conn.Update()

    polydata_collection = []

    # Update progress value in GUI
    progress = nregions - 1
    if progress:
        UpdateProgress = vu.ShowProgress(progress)

    for region in range(nregions):
        conn.InitializeSpecifiedRegionList()
        conn.AddSpecifiedRegion(region)
        conn.Update()

        p = vtkPolyData()
        p.DeepCopy(conn.GetOutput())

        polydata_collection.append(p)
        if progress:
            UpdateProgress(region, _("Splitting disconnected regions..."))

    return polydata_collection
