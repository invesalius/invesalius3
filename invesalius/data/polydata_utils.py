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
from typing import Iterable, List

import numpy as np
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkIdList, vtkIdTypeArray
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkSelection, vtkSelectionNode
from vtkmodules.vtkFiltersCore import (
    vtkAppendPolyData,
    vtkCleanPolyData,
    vtkIdFilter,
    vtkMassProperties,
    vtkPolyDataConnectivityFilter,
    vtkQuadricDecimation,
    vtkSmoothPolyDataFilter,
    vtkTriangleFilter,
)
from vtkmodules.vtkFiltersExtraction import vtkExtractSelection
from vtkmodules.vtkFiltersGeometry import vtkGeometryFilter
from vtkmodules.vtkFiltersModeling import vtkFillHolesFilter
from vtkmodules.vtkIOGeometry import vtkOBJReader, vtkSTLReader
from vtkmodules.vtkIOPLY import vtkPLYReader
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader, vtkXMLPolyDataWriter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkRenderer,
    vtkRenderWindow,
    vtkSelectVisiblePoints,
)

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


def ApplyDecimationFilter(polydata: vtkPolyData, reduction_factor: float) -> vtkPolyData:
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


def ApplySmoothFilter(
    polydata: vtkPolyData, iterations: int, relaxation_factor: float
) -> vtkPolyData:
    """
    Smooth given vtkPolyData surface, based on iteration and relaxation_factor.
    """
    smoother = vtkSmoothPolyDataFilter()
    smoother.SetInputData(polydata)
    smoother.SetNumberOfIterations(iterations)
    smoother.SetFeatureAngle(80)
    smoother.SetRelaxationFactor(relaxation_factor)
    smoother.FeatureEdgeSmoothingOff()
    smoother.BoundarySmoothingOff()
    smoother.Update()
    filler = vtkFillHolesFilter()
    filler.SetInputConnection(smoother.GetOutputPort())
    filler.SetHoleSize(1000)
    filler.Update()
    smoother.AddObserver(
        "ProgressEvent", lambda obj, evt: UpdateProgress(smoother, "Smoothing surface...")
    )

    return filler.GetOutput()


def FillSurfaceHole(polydata: vtkPolyData) -> "vtkPolyData":
    """
    Fill holes in the given polydata.
    """
    # Filter used to detect and fill holes. Only fill
    print("Filling polydata")
    filled_polydata = vtkFillHolesFilter()
    filled_polydata.SetInputData(polydata)
    filled_polydata.SetHoleSize(500)
    return filled_polydata.GetOutput()


def CalculateSurfaceVolume(polydata: vtkPolyData) -> float:
    """
    Calculate the volume from the given polydata
    """
    # Filter used to calculate volume and area from a polydata
    measured_polydata = vtkMassProperties()
    measured_polydata.SetInputData(polydata)
    return measured_polydata.GetVolume()


def CalculateSurfaceArea(polydata: vtkPolyData) -> float:
    """
    Calculate the volume from the given polydata
    """
    # Filter used to calculate volume and area from a polydata
    measured_polydata = vtkMassProperties()
    measured_polydata.SetInputData(polydata)
    return measured_polydata.GetSurfaceArea()


def Merge(polydata_list: Iterable[vtkPolyData]) -> vtkPolyData:
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


def Export(polydata: vtkPolyData, filename: str, bin: bool = False) -> None:
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


def Import(filename: str) -> vtkPolyData:
    reader = vtkXMLPolyDataReader()
    try:
        reader.SetFileName(filename.encode())
    except AttributeError:
        reader.SetFileName(filename)
    reader.Update()
    return reader.GetOutput()


def LoadPolydata(path: str) -> vtkPolyData:
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


def JoinSeedsParts(polydata: vtkPolyData, point_id_list: List[int]) -> vtkPolyData:
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


def SelectLargestPart(polydata: vtkPolyData) -> vtkPolyData:
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


def SplitDisconectedParts(polydata: vtkPolyData) -> List[vtkPolyData]:
    """ """
    conn = vtkPolyDataConnectivityFilter()
    conn.SetInputData(polydata)
    conn.SetExtractionModeToAllRegions()
    conn.Update()

    nregions = conn.GetNumberOfExtractedRegions()

    conn.SetExtractionModeToSpecifiedRegions()
    conn.Update()

    polydata_collection: List[vtkPolyData] = []

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


def RemoveNonVisibleFaces(
    polydata,
    positions=[[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]],
    remove_visible=False,
):
    polydata.BuildLinks()

    mapper = vtkPolyDataMapper()
    mapper.SetInputData(polydata)
    mapper.Update()

    actor = vtkActor()
    actor.SetMapper(mapper)

    renderer = vtkRenderer()
    renderer.AddActor(actor)

    render_window = vtkRenderWindow()
    render_window.AddRenderer(renderer)
    render_window.SetSize(800, 800)
    render_window.OffScreenRenderingOn()

    camera = renderer.GetActiveCamera()
    renderer.ResetCamera()

    pos = np.array(camera.GetPosition())
    fp = np.array(camera.GetFocalPoint())
    v = pos - fp
    mag = np.linalg.norm(v)
    vn = v / mag

    id_filter = vtkIdFilter()
    id_filter.SetInputData(polydata)
    id_filter.PointIdsOn()
    id_filter.Update()

    set_points = None

    for position in positions:
        pos = fp + np.array(position) * mag
        camera.SetPosition(pos.tolist())
        renderer.ResetCamera()
        render_window.Render()

        select_visible_points = vtkSelectVisiblePoints()
        select_visible_points.SetInputData(id_filter.GetOutput())
        select_visible_points.SetRenderer(renderer)
        select_visible_points.Update()
        output = select_visible_points.GetOutput()
        id_points = numpy_support.vtk_to_numpy(
            output.GetPointData().GetAbstractArray("vtkIdFilter_Ids")
        )
        if set_points is None:
            set_points = set(id_points.tolist())
        else:
            set_points.update(id_points.tolist())

    if remove_visible:
        set_points = set(range(polydata.GetNumberOfPoints())) - set_points
    cells_ids = set()
    for p_id in set_points:
        id_list = vtkIdList()
        polydata.GetPointCells(p_id, id_list)
        for i in range(id_list.GetNumberOfIds()):
            cells_ids.add(id_list.GetId(i))

    try:
        id_list = numpy_support.numpy_to_vtkIdTypeArray(np.array(list(cells_ids), dtype=np.int64))
    except ValueError:
        id_list = vtkIdTypeArray()

    selection_node = vtkSelectionNode()
    selection_node.SetFieldType(vtkSelectionNode.CELL)
    selection_node.SetContentType(vtkSelectionNode.INDICES)
    selection_node.SetSelectionList(id_list)

    selection = vtkSelection()
    selection.AddNode(selection_node)

    extract_selection = vtkExtractSelection()
    extract_selection.SetInputData(0, polydata)
    extract_selection.SetInputData(1, selection)
    extract_selection.Update()

    geometry_filter = vtkGeometryFilter()
    geometry_filter.SetInputData(extract_selection.GetOutput())
    geometry_filter.Update()

    clean_polydata = vtkCleanPolyData()
    clean_polydata.SetInputData(geometry_filter.GetOutput())
    clean_polydata.Update()

    return clean_polydata.GetOutput()
