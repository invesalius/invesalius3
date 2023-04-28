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

import functools
import multiprocessing
import os
import plistlib
import random
import shutil
import sys
import tempfile
import time
import traceback
import weakref
from typing import Union, List, Tuple, Dict, Any, Optional, Callable

import numpy as np

try:
    import queue
except ImportError:
    import Queue as queue

import wx
import wx.lib.agw.genericmessagedialog as GMD
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import (
    vtkMassProperties,
    vtkPolyDataNormals,
    vtkStripper,
    vtkTriangleFilter,
)
from vtkmodules.vtkCommonCore import (vtkIdList,
                                      vtkPoints,
                                     )
from vtkmodules.vtkCommonDataModel import (
    vtkCellArray,
    vtkPolyData,
    vtkTriangle
)
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkIOGeometry import vtkOBJReader, vtkSTLReader, vtkSTLWriter
from vtkmodules.vtkIOPLY import vtkPLYReader, vtkPLYWriter
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader, vtkXMLPolyDataWriter
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

from invesalius.pubsub import pub as Publisher

if sys.platform == 'win32':
    try:
        import win32api
        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

import invesalius.constants as const
import invesalius.data.imagedata_utils as iu
import invesalius.data.slice_ as sl
import invesalius.data.polydata_utils as pu
import invesalius.project as prj
import invesalius.session as ses
import invesalius.data.surface_process as surface_process
import invesalius.utils as utl
import invesalius.data.vtk_utils as vtk_utils
from invesalius.data.converters import convert_custom_bin_to_vtk

from invesalius.gui import dialogs
from invesalius_cy import cy_mesh

# TODO: Verificar ReleaseDataFlagOn and SetSource


class Surface():
    """
    Represent both vtkPolyData and associated properties.
    """
    general_index: int = -1
    def __init__(self, index: Union[int, None] = None, name: str = "") -> None:
        Surface.general_index += 1
        if index is None:
            self.index: int = Surface.general_index
        else:
            self.index: int = index
            Surface.general_index -= 1
        self.polydata: str = ''
        self.colour: str = ''
        self.transparency: float = const.SURFACE_TRANSPARENCY
        self.volume: float = 0.0
        self.area: float = 0.0
        self.is_shown: int = 1
        if not name:
            self.name: str = const.SURFACE_NAME_PATTERN %(self.index+1)
        else:
            self.name: str = name

        self.filename: Union[str, None] = None

    def SavePlist(self, dir_temp: str, filelist: Dict[str, str]) -> str:
        if self.filename and os.path.exists(self.filename):
            filename: str = u'surface_%d' % self.index
            vtp_filename: str = filename + u'.vtp'
            vtp_filepath: str = self.filename
        else:
            filename: str = u'surface_%d' % self.index
            vtp_filename: str = filename + u'.vtp'
            vtp_filepath: str = tempfile.mktemp()
            pu.Export(self.polydata, vtp_filepath, bin=True)
            self.filename = vtp_filepath

        filelist[vtp_filepath] = vtp_filename

        surface: Dict[str, Union[int, str, float, bool]] = {'colour': self.colour[:3],
                   'index': self.index,
                   'name': self.name,
                   'polydata': vtp_filename,
                   'transparency': self.transparency,
                   'visible': bool(self.is_shown),
                   'volume': self.volume,
                   'area': self.area,
                  }
        plist_filename: str = filename + u'.plist'
        #plist_filepath = os.path.join(dir_temp, filename + '.plist')
        temp_plist: str = tempfile.mktemp()
        with open(temp_plist, 'w+b') as f:
            plistlib.dump(surface, f)

        filelist[temp_plist] = plist_filename

        return plist_filename


    def OpenPList(self, filename: str) -> None:
        with open(filename, 'r+b') as f:
            sp = plistlib.load(f, fmt=plistlib.FMT_XML)
        dirpath: str = os.path.abspath(os.path.split(filename)[0])
        self.index: int = sp['index']
        self.name: str = sp['name']
        self.colour: list = sp['colour']
        self.transparency: float = sp['transparency']
        self.is_shown: bool = sp['visible']
        self.volume: float = sp['volume']
        try:
            self.area: float = sp['area']
        except KeyError:
            self.area: float = 0.0
        self.polydata: vtkPolyData = pu.Import(os.path.join(dirpath, sp['polydata']))
        Surface.general_index: int = max(Surface.general_index, self.index)

    def _set_class_index(self, index: int) -> None:
        Surface.general_index: int = index


# TODO: will be initialized inside control as it is being done?
class SurfaceManager():
    """
    Responsible for:
     - creating new surfaces;
     - managing surfaces' properties;
     - removing existing surfaces.

    Send pubsub events to other classes:
     - GUI: Update progress status
     - volume_viewer: Sends surface actors as the are created

    """
    def __init__(self) -> None:
        self.actors_dict: dict = {}
        self.last_surface_index: int = 0
        self.convert_to_inv: bool = None
        self.__bind_events()

        self._default_parameters: dict = {
            'algorithm': 'Default',
            'quality': const.DEFAULT_SURFACE_QUALITY,
            'fill_holes': False,
            'keep_largest': False,
            'fill_border_holes': True,
        }

        self._load_user_parameters()

    def _load_user_parameters(self) -> None:
        session: ses.Session = ses.Session()

        surface: dict = session.GetConfig('surface')
        if surface is not None:
            self._default_parameters.update(surface)
        else:
            session.SetConfig('surface', self._default_parameters)

    def __bind_events(self) -> None:
        Publisher.subscribe(self.AddNewActor, 'Create surface')
        Publisher.subscribe(self.GetActor, 'Get Actor')
        Publisher.subscribe(self.SetActorTransparency,
                                 'Set surface transparency')
        Publisher.subscribe(self.SetActorColour,
                                 'Set surface colour')

        Publisher.subscribe(self.OnChangeSurfaceName, 'Change surface name')
        Publisher.subscribe(self.OnShowSurface, 'Show surface')
        Publisher.subscribe(self.OnExportSurface,'Export surface to file')
        Publisher.subscribe(self.OnLoadSurfaceDict, 'Load surface dict')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        Publisher.subscribe(self.OnSelectSurface, 'Change surface selected')
        #----
        Publisher.subscribe(self.OnSplitSurface, 'Split surface')
        Publisher.subscribe(self.OnLargestSurface,
                                'Create surface from largest region')
        Publisher.subscribe(self.OnSeedSurface, "Create surface from seeds")

        Publisher.subscribe(self.OnDuplicate, "Duplicate surfaces")
        Publisher.subscribe(self.OnRemove,"Remove surfaces")
        Publisher.subscribe(self.UpdateSurfaceInterpolation, 'Update Surface Interpolation')

        Publisher.subscribe(self.OnImportSurfaceFile, 'Import surface file')
        Publisher.subscribe(self.OnImportCustomBinFile, 'Import bin file')
        Publisher.subscribe(self.OnWriteCustomBinFile, 'Write bin file')

        Publisher.subscribe(self.UpdateConvertToInvFlag, 'Update convert_to_inv flag')

        Publisher.subscribe(self.CreateSurfaceFromPolydata, 'Create surface from polydata')

    def OnDuplicate(self, surface_indexes: list) -> None:
        proj: prj.Project = prj.Project()
        surface_dict: dict = proj.surface_dict
        for index in surface_indexes:
            original_surface: Surface = surface_dict[index]
            # compute copy name
            name: str = original_surface.name
            names_list: list = [surface_dict[i].name for i in surface_dict.keys()]
            new_name: str = utl.next_copy_name(name, names_list)
            # create new mask
            self.CreateSurfaceFromPolydata(polydata=original_surface.polydata,
                                           overwrite=False,
                                           name=new_name,
                                           colour=original_surface.colour,
                                           transparency=original_surface.transparency,
                                           volume=original_surface.volume,
                                           area=original_surface.area)

    def OnRemove(self, surface_indexes: list) -> None:
        proj: prj.Project = prj.Project()

        old_dict: dict = self.actors_dict
        new_dict: dict = {}
        if surface_indexes:
            for index in surface_indexes:
                proj.RemoveSurface(index)
                if index in old_dict:
                    actor: vtkActor = old_dict[index]
                    for i in old_dict:
                        if i < index:
                            new_dict[i] = old_dict[i]
                        if i > index:
                            new_dict[i-1] = old_dict[i]
                    old_dict = new_dict
                    Publisher.sendMessage('Remove surface actor from viewer', actor=actor)
            self.actors_dict = new_dict

        if self.last_surface_index in surface_indexes:
            if self.actors_dict:
                self.last_surface_index: int = 0
            else:
                self.last_surface_index: None = None

    def OnSeedSurface(self, seeds: list) -> None:
        """
        Create a new surface, based on the last selected surface,
        using as reference seeds user add to surface of reference.
        """
        points_id_list: list = seeds
        index: int = self.last_surface_index
        proj: prj.Project = prj.Project()
        surface: Surface = proj.surface_dict[index]

        new_polydata: vtkPolyData = pu.JoinSeedsParts(surface.polydata,
                                                     points_id_list)
        index: int = self.CreateSurfaceFromPolydata(new_polydata)
        Publisher.sendMessage('Show single surface', index=index, visibility=True)
        #self.ShowActor(index, True)

    def OnSplitSurface(self) -> None:
        """
        Create n new surfaces, based on the last selected surface,
        according to their connectivity.
        """
        index: int = self.last_surface_index
        proj: prj.Project = prj.Project()
        surface: Surface = proj.surface_dict[index]

        index_list: list = []
        new_polydata_list: list = pu.SplitDisconectedParts(surface.polydata)
        for polydata in new_polydata_list:
            index: int = self.CreateSurfaceFromPolydata(polydata)
            index_list.append(index)
            #self.ShowActor(index, True)

        Publisher.sendMessage('Show multiple surfaces', index_list=index_list, visibility=True)

    def OnLargestSurface(self) -> None:
        """
        Create a new surface, based on largest part of the last
        selected surface.
        """
        index: int = self.last_surface_index
        proj: prj.Project = prj.Project()
        surface: Surface = proj.surface_dict[index]

        new_polydata: vtkPolyData = pu.SelectLargestPart(surface.polydata)
        new_index: int = self.CreateSurfaceFromPolydata(new_polydata)
        Publisher.sendMessage('Show single surface', index=new_index, visibility=True)

    def OnImportCustomBinFile(self, filename: str) -> None:
        scalar: bool = True
        if filename.lower().endswith('.bin'):
            polydata: vtkPolyData = convert_custom_bin_to_vtk(filename)
        elif filename.lower().endswith('.stl'):
            scalar: bool = False
            reader: vtkSTLReader = vtkSTLReader()

            if _has_win32api:
                reader.SetFileName(win32api.GetShortPathName(filename).encode(const.FS_ENCODE))
            else:
                reader.SetFileName(filename.encode(const.FS_ENCODE))
            reader.Update()
            polydata: vtkPolyData = reader.GetOutput()
            polydata: vtkPolyData = self.CoverttoMetersPolydata(polydata)

        if polydata.GetNumberOfPoints() == 0:
            wx.MessageBox(_("InVesalius was not able to import this surface"), _("Import surface error"))
        else:
            name: str = os.path.splitext(os.path.split(filename)[-1])[0]
            self.CreateSurfaceFromPolydata(polydata, name=name, scalar=scalar)

    def CoverttoMetersPolydata(self, polydata: vtkPolyData) -> vtkPolyData:
        idlist: vtkIdList = vtkIdList()
        points: np.ndarray = np.zeros((polydata.GetNumberOfPoints(), 3))
        elements: np.ndarray = np.zeros((polydata.GetNumberOfCells(), 3), dtype= np.int32)
        for i in range(polydata.GetNumberOfPoints()):
            x: tuple = polydata.GetPoint(i)
            points[i] = [j * 1000 for j in x]
        for i in range(polydata.GetNumberOfCells()):
            polydata.GetCellPoints(i, idlist)
            elements[i, 0] = idlist.GetId(0)
            elements[i, 1] = idlist.GetId(1)
            elements[i, 2] = idlist.GetId(2)
        points_vtk: vtkPoints = vtkPoints()
        triangles: vtkCellArray = vtkCellArray()
        polydata: vtkPolyData = vtkPolyData()
        for i in range(len(points)):
            points_vtk.InsertNextPoint(points[i])
        for i in range(len(elements)):
            triangle: vtkTriangle = vtkTriangle()
            triangle.GetPointIds().SetId(0, elements[i, 0])
            triangle.GetPointIds().SetId(1, elements[i, 1])
            triangle.GetPointIds().SetId(2, elements[i, 2])

            triangles.InsertNextCell(triangle)

        polydata.SetPoints(points_vtk)
        polydata.SetPolys(triangles)

        return polydata

    def OnWriteCustomBinFile(self, polydata: vtkPolyData, filename: str) -> None:
        idlist: vtkIdList = vtkIdList()
        points: np.ndarray = np.zeros((polydata.GetNumberOfPoints(), 3))
        elements: np.ndarray = np.zeros((polydata.GetNumberOfCells(), 3))
        id: int = 0
        nop: int = polydata.GetNumberOfPoints()
        noe: int = polydata.GetNumberOfCells()
        for i in range(polydata.GetNumberOfPoints()):
            x: list = polydata.GetPoint(i)
            points[i] = [j / 1000 for j in x]
        for i in range(polydata.GetNumberOfCells()):
            polydata.GetCellPoints(i, idlist)
            elements[i, 0] = idlist.GetId(0)
            elements[i, 1] = idlist.GetId(1)
            elements[i, 2] = idlist.GetId(2)
        data: dict = {'p': points, 'e': elements}
        with open(filename, 'wb') as f:
            np.array(id, dtype=np.int32).tofile(f)
            np.array(nop, dtype=np.int32).tofile(f)
            np.array(noe, dtype=np.int32).tofile(f)
            np.array(data['p'], dtype=np.float32).tofile(f)
            np.array(data['e'], dtype=np.int32).tofile(f)

    def OnImportSurfaceFile(self, filename: str) -> None:
        """
        Creates a new surface from a surface file (STL, PLY, OBJ or VTP)
        """
        self.CreateSurfaceFromFile(filename)

    def CreateSurfaceFromFile(self, filename: str) -> None:
        scalar: bool = False
        if filename.lower().endswith('.stl'):
            reader: vtkSTLReader = vtkSTLReader()
        elif filename.lower().endswith('.ply'):
            reader: vtkPLYReader = vtkPLYReader()
            scalar: bool = True
        elif filename.lower().endswith('.obj'):
            reader: vtkOBJReader = vtkOBJReader()
        elif filename.lower().endswith('.vtp'):
            reader: vtkXMLPolyDataReader = vtkXMLPolyDataReader()
            scalar: bool = True
        else:
            wx.MessageBox(_("File format not reconized by InVesalius"), _("Import surface error"))
            return

        if _has_win32api:
            reader.SetFileName(win32api.GetShortPathName(filename).encode(const.FS_ENCODE))
        else:
            reader.SetFileName(filename.encode(const.FS_ENCODE))

        reader.Update()
        polydata: vtkPolyData = reader.GetOutput()

        if polydata.GetNumberOfPoints() == 0:
            wx.MessageBox(_("InVesalius was not able to import this surface"), _("Import surface error"))
        else:
            name: str = os.path.splitext(os.path.split(filename)[-1])[0]
            self.CreateSurfaceFromPolydata(polydata, name=name, scalar=scalar)

    def UpdateConvertToInvFlag(self, convert_to_inv: bool = False) -> None:
        self.convert_to_inv = convert_to_inv

    def CreateSurfaceFromPolydata(self, polydata: vtkPolyData, overwrite: bool = False, index: int = None,
                                  name: str = None, colour: list = None, transparency: float = None,
                                  volume: float = None, area: float = None, scalar: bool = False) -> int:
        if self.convert_to_inv:
            # convert between invesalius and world space with shift in the Y coordinate
            matrix_shape: tuple = sl.Slice().matrix.shape
            spacing: tuple = sl.Slice().spacing
            img_shift: float = spacing[1] * (matrix_shape[1] - 1)
            affine: np.ndarray = sl.Slice().affine.copy()
            affine[1, -1] -= img_shift
            affine_vtk: vtkMatrix4x4 = vtk_utils.numpy_to_vtkMatrix4x4(affine)

            polydata_transform: vtkTransform = vtkTransform()
            polydata_transform.PostMultiply()
            polydata_transform.Concatenate(affine_vtk)

            transformFilter: vtkTransformPolyDataFilter = vtkTransformPolyDataFilter()
            transformFilter.SetTransform(polydata_transform)
            transformFilter.SetInputData(polydata)
            transformFilter.Update()
            polydata: vtkPolyData = transformFilter.GetOutput()
            self.convert_to_inv: bool = False

        normals: vtkPolyDataNormals = vtkPolyDataNormals()
        normals.SetInputData(polydata)
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        mapper: vtkPolyDataMapper = vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        if scalar:
            mapper.ScalarVisibilityOn()
        else:
            mapper.ScalarVisibilityOff()
        #  mapper.ImmediateModeRenderingOn() # improve performance

        actor: vtkActor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetBackfaceCulling(1)

        if overwrite:
            if index is None:
                index: int = self.last_surface_index
            surface: Surface = Surface(index=index)
        else:
            surface: Surface = Surface()

        if not colour:
            surface.colour: list = random.choice(const.SURFACE_COLOUR)
        else:
            surface.colour: list = colour
        surface.polydata: vtkPolyData = polydata

        if transparency:
            surface.transparency: float = transparency

        if name:
            surface.name: str = name

        # Append surface into Project.surface_dict
        proj: prj.Project = prj.Project()
        if overwrite:
            proj.ChangeSurface(surface)
        else:
            index: int = proj.AddSurface(surface)
            surface.index: int = index
            self.last_surface_index: int = index

        # Set actor colour and transparency
        actor.GetProperty().SetColor(surface.colour)
        actor.GetProperty().SetOpacity(1-surface.transparency)

        if overwrite and self.actors_dict.keys():
            try:
                old_actor: vtkActor = self.actors_dict[index]
                Publisher.sendMessage('Remove surface actor from viewer', actor=old_actor)
            except KeyError:
                pass

        self.actors_dict[surface.index]: vtkActor = actor

        session: ses.Session = ses.Session()
        session.ChangeProject()

        # The following lines have to be here, otherwise all volumes disappear
        if not volume or not area:
            triangle_filter: vtkTriangleFilter = vtkTriangleFilter()
            triangle_filter.SetInputData(polydata)
            triangle_filter.Update()

            measured_polydata: vtkMassProperties = vtkMassProperties()
            measured_polydata.SetInputConnection(triangle_filter.GetOutputPort())
            measured_polydata.Update()
            volume: float =  measured_polydata.GetVolume()
            area: float =  measured_polydata.GetSurfaceArea()
            surface.volume: float = volume
            surface.area: float = area
            print(">>>>", surface.volume)
        else:
            surface.volume: float = volume
            surface.area: float = area

        self.last_surface_index: int = surface.index

        Publisher.sendMessage('Load surface actor into viewer', actor=actor)
        Publisher.sendMessage('Update surface info in GUI', surface=surface)
        return surface.index

    def OnCloseProject(self) -> None:
        self.CloseProject()

    def CloseProject(self) -> None:
        for index in self.actors_dict:
            Publisher.sendMessage('Remove surface actor from viewer', actor=self.actors_dict[index])
        del self.actors_dict
        self.actors_dict: dict = {}

        # restarting the surface index
        Surface.general_index: int = -1

        self.affine_vtk: vtkMatrix4x4 = None
        self.convert_to_inv: bool = False


    def OnSelectSurface(self, surface_index: int) -> None:
        #self.last_surface_index = surface_index
        # self.actors_dict.
        proj: prj.Project = prj.Project()
        surface: Surface = proj.surface_dict[surface_index]
        Publisher.sendMessage('Update surface info in GUI', surface=surface)
        self.last_surface_index: int = surface_index
        #  if surface.is_shown:
        self.ShowActor(surface_index, True)

    def OnLoadSurfaceDict(self, surface_dict: dict) -> None:
        for key in surface_dict:
            surface: Surface = surface_dict[key]

            # Map polygonal data (vtkPolyData) to graphics primitives.
            normals: vtkPolyDataNormals = vtkPolyDataNormals()
            normals.SetInputData(surface.polydata)
            normals.SetFeatureAngle(80)
            normals.AutoOrientNormalsOn()
            #  normals.GetOutput().ReleaseDataFlagOn()

            # Improve performance
            stripper: vtkStripper = vtkStripper()
            stripper.SetInputConnection(normals.GetOutputPort())
            stripper.PassThroughCellIdsOn()
            stripper.PassThroughPointIdsOn()

            mapper: vtkPolyDataMapper = vtkPolyDataMapper()
            mapper.SetInputConnection(stripper.GetOutputPort())
            mapper.ScalarVisibilityOff()
            #  mapper.ImmediateModeRenderingOn() # improve performance

            # Represent an object (geometry & properties) in the rendered scene
            actor = vtkActor()
            actor.GetProperty().SetBackfaceCulling(1)
            actor.SetMapper(mapper)

            # Set actor colour and transparency
            actor.GetProperty().SetColor(surface.colour[:3])
            actor.GetProperty().SetOpacity(1-surface.transparency)

            self.actors_dict[surface.index: int] = actor

            # Send actor by pubsub to viewer's render
            Publisher.sendMessage('Load surface actor into viewer', actor=actor)

            Publisher.sendMessage('Update status text in GUI',
                                  label=_("Ready"))

            # The following lines have to be here, otherwise all volumes disappear
            Publisher.sendMessage('Update surface info in GUI', surface=surface)
            if not surface.is_shown:
                self.ShowActor(key, False)

    ####
    #(mask_index, surface_name, quality, fill_holes, keep_largest)

    def _on_complete_surface_creation(self, args: tuple, overwrite: bool, surface_name: str, colour: list, dialog: object) -> None:
        surface_filename, surface_measures: dict = args
        wx.CallAfter(self._show_surface, surface_filename, surface_measures, overwrite, surface_name, colour, dialog)

    def _show_surface(self, surface_filename: str, surface_measures: dict, overwrite: bool, surface_name: str, colour: list, dialog: object) -> None:
        print(surface_filename, surface_measures)
        reader: vtkXMLPolyDataReader = vtkXMLPolyDataReader()
        reader.SetFileName(surface_filename)
        reader.Update()
        polydata: vtkPolyData = reader.GetOutput()

        # Map polygonal data (vtkPolyData) to graphics primitives.
        mapper: vtkPolyDataMapper = vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        mapper.ScalarVisibilityOff()
        #  mapper.ReleaseDataFlagOn()
        #  mapper.ImmediateModeRenderingOn() # improve performance

        # Represent an object (geometry & properties) in the rendered scene
        actor: vtkActor = vtkActor()
        actor.GetProperty().SetBackfaceCulling(1)
        actor.SetMapper(mapper)
        del mapper
        #Create Surface instance
        if overwrite:
            surface: Surface = Surface(index = self.last_surface_index)
        else:
            surface: Surface = Surface(name=surface_name)
        surface.colour: list = colour
        surface.polydata: vtkPolyData = polydata
        surface.volume: float = surface_measures['volume']
        surface.area: float = surface_measures['area']
        del polydata

        # Set actor colour and transparency
        actor.GetProperty().SetColor(colour)
        actor.GetProperty().SetOpacity(1-surface.transparency)

        prop: vtkProperty = actor.GetProperty()

        session: ses.Session = ses.Session()
        interpolation: int = session.GetConfig('surface_interpolation')

        prop.SetInterpolation(interpolation)

        proj: prj.Project = prj.Project()
        if overwrite:
            proj.ChangeSurface(surface)
        else:
            index: int = proj.AddSurface(surface)
            surface.index: int = index
            self.last_surface_index: int = index

        session.ChangeProject()

        Publisher.sendMessage('Load surface actor into viewer', actor=actor)

        # Send actor by pubsub to viewer's render
        if overwrite and self.actors_dict.keys():
            old_actor: vtkActor = self.actors_dict[self.last_surface_index: int]
            Publisher.sendMessage('Remove surface actor from viewer', actor=old_actor)

        # Save actor for future management tasks
        self.actors_dict[surface.index: int] = actor
        Publisher.sendMessage('Update surface info in GUI', surface=surface)
        Publisher.sendMessage('End busy cursor')

    def _on_callback_error(self, e: Exception, dialog: object = None) -> None:
        dialog.running: bool = False
        msg: str = utl.log_traceback(e)
        dialog.error: str = msg

    def AddNewActor(self, slice_: Slice, mask: Mask, surface_parameters: dict) -> None:
        """
        Create surface actor, save into project and send it to viewer.
        """
        if mask.matrix.max() < 127:
            wx.MessageBox(_("It's not possible to create a surface because there is not any voxel selected on mask"), _("Create surface warning"))
            return
        t_init: float = time.time()
        matrix = slice_.matrix
        filename_img = slice_.matrix_filename
        spacing = slice_.spacing

        mask_temp_file = mask.temp_file
        mask_shape = mask.matrix.shape
        mask_dtype = mask.matrix.dtype

        algorithm = surface_parameters['method']['algorithm']
        options = surface_parameters['method']['options']

        surface_name = surface_parameters['options']['name']
        quality: int = surface_parameters['options']['quality']
        fill_holes: bool = surface_parameters['options']['fill']
        keep_largest: bool = surface_parameters['options']['keep_largest']

        fill_border_holes: bool = surface_parameters['options'].get('fill_border_holes', True)

        print(surface_parameters)

        mode = 'CONTOUR' # 'GRAYSCALE'
        min_value, max_value = mask.threshold_range
        colour = mask.colour[:3]

        try:
            overwrite: bool = surface_parameters['options']['overwrite']
        except KeyError:
            overwrite = False
        mask.matrix.flush()

        if quality in const.SURFACE_QUALITY.keys():
            imagedata_resolution: float = const.SURFACE_QUALITY[quality][0]
            smooth_iterations: int = const.SURFACE_QUALITY[quality][1]
            smooth_relaxation_factor: float = const.SURFACE_QUALITY[quality][2]
            decimate_reduction: float = const.SURFACE_QUALITY[quality][3]

        pipeline_size: int = 4
        if decimate_reduction:
            pipeline_size += 1
        if (smooth_iterations and smooth_relaxation_factor):
            pipeline_size += 1
        if fill_holes:
            pipeline_size += 1
        if keep_largest:
            pipeline_size += 1

        session = ses.Session()
        language = session.GetConfig('language')

        if (prj.Project().original_orientation == const.CORONAL):
            flip_image: bool = False
        else:
            flip_image: bool = True

        if imagedata_resolution > 0:
            spacing = tuple([s * imagedata_resolution for s in spacing])
            matrix = iu.resize_image_array(matrix, 1.0/imagedata_resolution, True)
            mask = iu.resize_image_array(mask.matrix, 1.0/imagedata_resolution, True)

            filename_img = matrix.filename
            mask_temp_file = mask.filename
            mask_shape = mask.shape
            mask_dtype = mask.dtype

        n_processors: int = multiprocessing.cpu_count()

        o_piece: int = 1
        piece_size: int = 20

        n_pieces: int = int(round(matrix.shape[0] / piece_size + 0.5, 0))

        filenames = []
        ctx: SpawnContext = multiprocessing.get_context('spawn')
        pool = ctx.Pool(processes=min(n_pieces, n_processors))
        manager: SyncManager = multiprocessing.Manager()
        msg_queue = manager.Queue(1)

        print("Resolution", imagedata_resolution)

        # If InVesalius is running without GUI
        if wx.GetApp() is None:
            for i in range(n_pieces):
                init = i * piece_size
                end = init + piece_size + o_piece
                roi = slice(init, end)
                print("new_piece", roi)
                f = pool.apply_async(surface_process.create_surface_piece,
                                     args = (filename_img, matrix.shape, matrix.dtype,
                                             mask_temp_file, mask_shape,
                                             mask_dtype, roi, spacing, mode,
                                             min_value, max_value, decimate_reduction,
                                             smooth_relaxation_factor,
                                             smooth_iterations, language, flip_image,
                                             algorithm != 'Default', algorithm,
                                             imagedata_resolution, fill_border_holes),
                                     callback=lambda x: filenames.append(x))

            while len(filenames) != n_pieces:
                time.sleep(0.25)

            f = pool.apply_async(surface_process.join_process_surface,
                                 args=(filenames, algorithm, smooth_iterations,
                                       smooth_relaxation_factor,
                                       decimate_reduction, keep_largest,
                                       fill_holes, options, msg_queue))

            while not f.ready():
                time.sleep(0.25)

            try:
                surface_filename, surface_measures: dict = f.get()
            except Exception as e:
                print(_("InVesalius was not able to create the surface"))
                print(traceback.print_exc())
                return

            reader = vtkXMLPolyDataReader()
            reader.SetFileName(surface_filename)
            reader.Update()

            polydata = reader.GetOutput()

            proj = prj.Project()
            #Create Surface instance
            if overwrite:
                surface = Surface(index = self.last_surface_index)
                proj.ChangeSurface(surface)
            else:
                surface = Surface(name=surface_name)
                index = proj.AddSurface(surface)
                surface.index = index
                self.last_surface_index = index

            surface.colour = colour
            surface.polydata = polydata
            surface.volume = surface_measures['volume']
            surface.area = surface_measures['area']

        # With GUI
        else:
            sp: dialogs.SurfaceProgressWindow = dialogs.SurfaceProgressWindow()
            for i in range(n_pieces):
                init: int = i * piece_size
                end: int = init + piece_size + o_piece
                roi: slice = slice(init, end)
                print("new_piece", roi)
                f: multiprocessing.pool.ApplyResult = pool.apply_async(surface_process.create_surface_piece,
                                        args = (filename_img, matrix.shape, matrix.dtype,
                                                mask_temp_file, mask_shape,
                                                mask_dtype, roi, spacing, mode,
                                                min_value, max_value, decimate_reduction,
                                                smooth_relaxation_factor,
                                                smooth_iterations, language, flip_image,
                                                algorithm != 'Default', algorithm,
                                                imagedata_resolution, fill_border_holes),
                                        callback=lambda x: filenames.append(x),
                                        error_callback=functools.partial(self._on_callback_error,
                                                                        dialog=sp))

            while len(filenames) != n_pieces:
                if sp.WasCancelled() or not sp.running:
                    break
                time.sleep(0.25)
                sp.Update(_("Creating 3D surface..."))
                wx.Yield()

            if not sp.WasCancelled() or sp.running:
                f: multiprocessing.pool.ApplyResult = pool.apply_async(surface_process.join_process_surface,
                                        args=(filenames, algorithm, smooth_iterations,
                                            smooth_relaxation_factor,
                                            decimate_reduction, keep_largest,
                                            fill_holes, options, msg_queue),
                                        callback=functools.partial(self._on_complete_surface_creation,
                                                                    overwrite=overwrite,
                                                                    surface_name=surface_name,
                                                                    colour=colour,
                                                                    dialog=sp),
                                        error_callback=functools.partial(self._on_callback_error,
                                                                        dialog=sp))

                while sp.running:
                    if sp.WasCancelled():
                        break
                    time.sleep(0.25)
                    try:
                        msg: str = msg_queue.get_nowait()
                        sp.Update(msg)
                    except:
                        sp.Update(None)
                    wx.Yield()

            t_end: float = time.time()
            print("Elapsed time - {}".format(t_end-t_init))
            sp.Close()
            if sp.error:
                dlg: GMD.GenericMessageDialog = GMD.GenericMessageDialog(None, sp.error,
                                                "Exception!",
                                                wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()
            del sp

        pool.close()
        try:
            pool.terminate()
        except AssertionError:
            pass
        del pool
        del manager
        del msg_queue
        import gc
        gc.collect()

    def GetActor(self, surface_index: int) -> None:
        Publisher.sendMessage('Send Actor', e_field_actor=self.actors_dict[surface_index])

    def UpdateSurfaceInterpolation(self) -> None:
        session = ses.Session()
        surface_interpolation: int = session.GetConfig('surface_interpolation')

        for key in self.actors_dict:
            self.actors_dict[key].GetProperty().SetInterpolation(surface_interpolation)
        Publisher.sendMessage('Render volume viewer')

    def RemoveActor(self, index: int) -> None:
        """
        Remove actor, according to given actor index.
        """
        Publisher.sendMessage('Remove surface actor from viewer', actor=index)
        self.actors_dict.pop(index)
        # Remove surface from project's surface_dict
        proj = prj.Project()
        proj.surface_dict.pop(index)

    def OnChangeSurfaceName(self, index: int, name: str) -> None:
        proj = prj.Project()
        proj.surface_dict[index].name = name

    def OnShowSurface(self, index: int, visibility: bool) -> None:
        self.ShowActor(index, visibility)

    def ShowActor(self, index: int, value: bool) -> None:
        """
        Show or hide actor, according to given actor index and value.
        """
        self.actors_dict[index].SetVisibility(value)
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[index].is_shown = value
        Publisher.sendMessage('Render volume viewer')

    def SetActorTransparency(self, surface_index: int, transparency: float) -> None:
        """
        Set actor transparency (oposite to opacity) according to given actor
        index and value.
        """
        self.actors_dict[surface_index].GetProperty().SetOpacity(1-transparency)
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[surface_index].transparency = transparency
        Publisher.sendMessage('Render volume viewer')

    def SetActorColour(self, surface_index: int, colour: list) -> None:
        """
        """
        self.actors_dict[surface_index].GetProperty().SetColor(colour[:3])
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[surface_index].colour = colour
        Publisher.sendMessage('Render volume viewer')

    def OnExportSurface(self, filename: str, filetype: int) -> None:
        ftype_prefix: dict = {
            const.FILETYPE_STL: '.stl',
            const.FILETYPE_VTP: '.vtp',
            const.FILETYPE_PLY: '.ply',
            const.FILETYPE_STL_ASCII: '.stl',
        }
        if filetype in ftype_prefix:
            temp_file: str = tempfile.mktemp(suffix=ftype_prefix[filetype])

            if _has_win32api:
                utl.touch(temp_file)
                _temp_file: str = temp_file
                temp_file: str = win32api.GetShortPathName(temp_file)
                os.remove(_temp_file)

            temp_file: str = utl.decode(temp_file, const.FS_ENCODE)
            try:
                self._export_surface(temp_file, filetype)
            except ValueError:
                if wx.GetApp() is None:
                    print("It was not possible to export the surface because the surface is empty")
                else:
                    wx.MessageBox(_("It was not possible to export the surface because the surface is empty"), _("Export surface error"))
                return

            try:
                shutil.move(temp_file, filename)
            except PermissionError as err:
                dirpath: str = os.path.split(filename)[0]
                if wx.GetApp() is None:
                    print(_("It was not possible to export the surface because you don't have permission to write to {} folder: {}".format(dirpath, err)))
                else:
                    dlg: dialogs.ErrorMessageBox = dialogs.ErrorMessageBox(
                        None,
                        _("Export surface error"),
                        "It was not possible to export the surface because you don't have permission to write to {}:\n{}".format(dirpath, err)
                    )
                    dlg.ShowModal()
                    dlg.Destroy()
                os.remove(temp_file)


    def _export_surface(self, filename: str, filetype: int) -> None:
        if filetype in (const.FILETYPE_STL,
                        const.FILETYPE_VTP,
                        const.FILETYPE_PLY,
                        const.FILETYPE_STL_ASCII):
            # First we identify all surfaces that are selected
            # (if any)
            proj = prj.Project()
            polydata_list: list = []

            for index in proj.surface_dict:
                surface = proj.surface_dict[index]
                if surface.is_shown:
                    polydata_list.append(surface.polydata)

            if len(polydata_list) == 0:
                utl.debug("oops - no polydata")
                return
            elif len(polydata_list) == 1:
                polydata = polydata_list[0]
            else:
                polydata = pu.Merge(polydata_list)

            if polydata.GetNumberOfPoints() == 0:
                raise ValueError

            # Having a polydata that represents all surfaces
            # selected, we write it, according to filetype
            if filetype == const.FILETYPE_STL:
                writer = vtkSTLWriter()
                writer.SetFileTypeToBinary()
            elif filetype == const.FILETYPE_STL_ASCII:
                writer = vtkSTLWriter()
                writer.SetFileTypeToASCII()
            elif filetype == const.FILETYPE_VTP:
                writer = vtkXMLPolyDataWriter()
            #elif filetype == const.FILETYPE_IV:
            #    writer = vtkIVWriter()
            elif filetype == const.FILETYPE_PLY:
                writer = vtkPLYWriter()
                writer.SetFileTypeToASCII()
                writer.SetColorModeToOff()
                #writer.SetDataByteOrderToLittleEndian()
                #writer.SetColorModeToUniformCellColor()
                #writer.SetColor(255, 0, 0)

            if filetype in (const.FILETYPE_STL,
                            const.FILETYPE_STL_ASCII,
                            const.FILETYPE_PLY):
                # Invert normals
                normals = vtkPolyDataNormals()
                normals.SetInputData(polydata)
                normals.SetFeatureAngle(80)
                normals.AutoOrientNormalsOn()
                #  normals.GetOutput().ReleaseDataFlagOn()
                normals.UpdateInformation()
                normals.Update()
                polydata = normals.GetOutput()

            filename: bytes = filename.encode(const.FS_ENCODE)
            writer.SetFileName(filename)
            writer.SetInputData(polydata)
            writer.Write()
