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

try:
    import queue
except ImportError:
    import Queue as queue

import vtk
import wx
import wx.lib.agw.genericmessagedialog as GMD

from wx.lib.pubsub import pub as Publisher

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
import invesalius.data.polydata_utils as pu
import invesalius.project as prj
import invesalius.session as ses
import invesalius.data.surface_process as surface_process
import invesalius.utils as utl
import invesalius.data.vtk_utils as vu

from invesalius.gui import dialogs

from invesalius.data import cy_mesh
# TODO: Verificar ReleaseDataFlagOn and SetSource 


class Surface():
    """
    Represent both vtkPolyData and associated properties.
    """
    general_index = -1
    def __init__(self, index=None, name=""):
        Surface.general_index += 1
        if index is None:
            self.index = Surface.general_index
        else:
            self.index = index
            Surface.general_index -= 1
        self.polydata = ''
        self.colour = ''
        self.transparency = const.SURFACE_TRANSPARENCY
        self.volume = 0.0
        self.area = 0.0
        self.is_shown = 1
        if not name:
            self.name = const.SURFACE_NAME_PATTERN %(self.index+1)
        else:
            self.name = name

        self.filename = None

    def SavePlist(self, dir_temp, filelist):
        if self.filename and os.path.exists(self.filename):
            filename = u'surface_%d' % self.index
            vtp_filename = filename + u'.vtp'
            vtp_filepath = self.filename
        else:
            filename = u'surface_%d' % self.index
            vtp_filename = filename + u'.vtp'
            vtp_filepath = tempfile.mktemp()
            pu.Export(self.polydata, vtp_filepath, bin=True)
            self.filename = vtp_filepath

        filelist[vtp_filepath] = vtp_filename

        surface = {'colour': self.colour[:3],
                   'index': self.index,
                   'name': self.name,
                   'polydata': vtp_filename,
                   'transparency': self.transparency,
                   'visible': bool(self.is_shown),
                   'volume': self.volume,
                   'area': self.area,
                  }
        plist_filename = filename + u'.plist'
        #plist_filepath = os.path.join(dir_temp, filename + '.plist')
        temp_plist = tempfile.mktemp()
        plistlib.writePlist(surface, temp_plist)

        filelist[temp_plist] = plist_filename

        return plist_filename

    def OpenPList(self, filename):
        sp = plistlib.readPlist(filename)
        dirpath = os.path.abspath(os.path.split(filename)[0])
        self.index = sp['index']
        self.name = sp['name']
        self.colour = sp['colour']
        self.transparency = sp['transparency']
        self.is_shown = sp['visible']
        self.volume = sp['volume']
        try:
            self.area = sp['area']
        except KeyError:
            self.area = 0.0
        self.polydata = pu.Import(os.path.join(dirpath, sp['polydata']))
        Surface.general_index = max(Surface.general_index, self.index)

    def _set_class_index(self, index):
        Surface.general_index = index


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
    def __init__(self):
        self.actors_dict = {}
        self.last_surface_index = 0
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.AddNewActor, 'Create surface')
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

    def OnDuplicate(self, surface_indexes):
        proj = prj.Project()
        surface_dict = proj.surface_dict
        for index in surface_indexes:
            original_surface = surface_dict[index]
            # compute copy name
            name = original_surface.name
            names_list = [surface_dict[i].name for i in surface_dict.keys()]
            new_name = utl.next_copy_name(name, names_list)
            # create new mask
            self.CreateSurfaceFromPolydata(polydata = original_surface.polydata,
                                           overwrite = False,
                                           name = new_name,
                                           colour = original_surface.colour,
                                           transparency = original_surface.transparency,
                                           volume = original_surface.volume,
                                           area = original_surface.area)

    def OnRemove(self, surface_indexes):
        proj = prj.Project()

        old_dict = self.actors_dict
        new_dict = {}
        if surface_indexes:
            for index in surface_indexes:
                proj.RemoveSurface(index)
                if index in old_dict:
                    actor = old_dict[index]
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
                self.last_surface_index = 0
            else:
                self.last_surface_index = None

    def OnSeedSurface(self, seeds):
        """
        Create a new surface, based on the last selected surface,
        using as reference seeds user add to surface of reference.
        """
        points_id_list = seeds
        index = self.last_surface_index
        proj = prj.Project()
        surface = proj.surface_dict[index]

        new_polydata = pu.JoinSeedsParts(surface.polydata,
                                          points_id_list)
        index = self.CreateSurfaceFromPolydata(new_polydata)
        Publisher.sendMessage('Show single surface', index=index, visibility=True)
        #self.ShowActor(index, True)

    def OnSplitSurface(self):
        """
        Create n new surfaces, based on the last selected surface,
        according to their connectivity.
        """
        index = self.last_surface_index
        proj = prj.Project()
        surface = proj.surface_dict[index]

        index_list = []
        new_polydata_list = pu.SplitDisconectedParts(surface.polydata)
        for polydata in new_polydata_list:
            index = self.CreateSurfaceFromPolydata(polydata)
            index_list.append(index)
            #self.ShowActor(index, True)

        Publisher.sendMessage('Show multiple surfaces', index_list=index_list, visibility=True)

    def OnLargestSurface(self):
        """
        Create a new surface, based on largest part of the last
        selected surface.
        """
        index = self.last_surface_index
        proj = prj.Project()
        surface = proj.surface_dict[index]

        new_polydata = pu.SelectLargestPart(surface.polydata)
        new_index = self.CreateSurfaceFromPolydata(new_polydata)
        Publisher.sendMessage('Show single surface', index=new_index, visibility=True)

    def OnImportSurfaceFile(self, filename):
        """
        Creates a new surface from a surface file (STL, PLY, OBJ or VTP)
        """
        self.CreateSurfaceFromFile(filename)

    def CreateSurfaceFromFile(self, filename):
        if filename.lower().endswith('.stl'):
            reader = vtk.vtkSTLReader()
        elif filename.lower().endswith('.ply'):
            reader = vtk.vtkPLYReader()
        elif filename.lower().endswith('.obj'):
            reader = vtk.vtkOBJReader()
        elif filename.lower().endswith('.vtp'):
            reader = vtk.vtkXMLPolyDataReader()
        else:
            wx.MessageBox(_("File format not reconized by InVesalius"), _("Import surface error"))
            return

        if _has_win32api:
            reader.SetFileName(win32api.GetShortPathName(filename).encode(const.FS_ENCODE))
        else:
            reader.SetFileName(filename.encode(const.FS_ENCODE))

        reader.Update()
        polydata = reader.GetOutput()

        if polydata.GetNumberOfPoints() == 0:
            wx.MessageBox(_("InVesalius was not able to import this surface"), _("Import surface error"))
        else:
            name = os.path.splitext(os.path.split(filename)[-1])[0]
            self.CreateSurfaceFromPolydata(polydata, name=name)

    def CreateSurfaceFromPolydata(self, polydata, overwrite=False,
                                  name=None, colour=None,
                                  transparency=None, volume=None, area=None):
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(polydata)
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        mapper.ScalarVisibilityOff()
        mapper.ImmediateModeRenderingOn() # improve performance

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        if overwrite:
            surface = Surface(index = self.last_surface_index)
        else:
            surface = Surface()

        if not colour:
            surface.colour = random.choice(const.SURFACE_COLOUR)
        else:
            surface.colour = colour
        surface.polydata = polydata

        if transparency:
            surface.transparency = transparency

        if name:
            surface.name = name

        # Append surface into Project.surface_dict
        proj = prj.Project()
        if overwrite:
            proj.ChangeSurface(surface)
        else:
            index = proj.AddSurface(surface)
            surface.index = index
            self.last_surface_index = index

        # Set actor colour and transparency
        actor.GetProperty().SetColor(surface.colour)
        actor.GetProperty().SetOpacity(1-surface.transparency)
        self.actors_dict[surface.index] = actor

        session = ses.Session()
        session.ChangeProject()

        # The following lines have to be here, otherwise all volumes disappear
        if not volume or not area:
            triangle_filter = vtk.vtkTriangleFilter()
            triangle_filter.SetInputData(polydata)
            triangle_filter.Update()

            measured_polydata = vtk.vtkMassProperties()
            measured_polydata.SetInputConnection(triangle_filter.GetOutputPort())
            measured_polydata.Update()
            volume =  measured_polydata.GetVolume()
            area =  measured_polydata.GetSurfaceArea()
            surface.volume = volume
            surface.area = area
            print(">>>>", surface.volume)
        else:
            surface.volume = volume
            surface.area = area

        self.last_surface_index = surface.index

        Publisher.sendMessage('Load surface actor into viewer', actor=actor)

        Publisher.sendMessage('Update surface info in GUI', surface=surface)
        return surface.index

    def OnCloseProject(self):
        self.CloseProject()

    def CloseProject(self):
        for index in self.actors_dict:
            Publisher.sendMessage('Remove surface actor from viewer', actor=self.actors_dict[index])
        del self.actors_dict
        self.actors_dict = {}

        # restarting the surface index
        Surface.general_index = -1

    def OnSelectSurface(self, surface_index):
        #self.last_surface_index = surface_index
        # self.actors_dict.
        proj = prj.Project()
        surface = proj.surface_dict[surface_index]
        Publisher.sendMessage('Update surface info in GUI', surface=surface)
        self.last_surface_index = surface_index
        #  if surface.is_shown:
        self.ShowActor(surface_index, True)

    def OnLoadSurfaceDict(self, surface_dict):
        for key in surface_dict:
            surface = surface_dict[key]

            # Map polygonal data (vtkPolyData) to graphics primitives.
            normals = vtk.vtkPolyDataNormals()
            normals.SetInputData(surface.polydata)
            normals.SetFeatureAngle(80)
            normals.AutoOrientNormalsOn()
            #  normals.GetOutput().ReleaseDataFlagOn()

            # Improve performance
            stripper = vtk.vtkStripper()
            stripper.SetInputConnection(normals.GetOutputPort())
            stripper.PassThroughCellIdsOn()
            stripper.PassThroughPointIdsOn()

            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(stripper.GetOutputPort())
            mapper.ScalarVisibilityOff()
            mapper.ImmediateModeRenderingOn() # improve performance

            # Represent an object (geometry & properties) in the rendered scene
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)

            # Set actor colour and transparency
            actor.GetProperty().SetColor(surface.colour[:3])
            actor.GetProperty().SetOpacity(1-surface.transparency)

            self.actors_dict[surface.index] = actor

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

    def _on_complete_surface_creation(self, args, overwrite, surface_name, colour, dialog):
        surface_filename, surface_measures = args
        print(surface_filename, surface_measures)
        reader = vtk.vtkXMLPolyDataReader()
        reader.SetFileName(surface_filename)
        reader.Update()
        polydata = reader.GetOutput()

        # Map polygonal data (vtkPolyData) to graphics primitives.
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        mapper.ScalarVisibilityOff()
        #  mapper.ReleaseDataFlagOn()
        mapper.ImmediateModeRenderingOn() # improve performance

        # Represent an object (geometry & properties) in the rendered scene
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        del mapper
        #Create Surface instance
        if overwrite:
            surface = Surface(index = self.last_surface_index)
        else:
            surface = Surface(name=surface_name)
        surface.colour = colour
        surface.polydata = polydata
        surface.volume = surface_measures['volume']
        surface.area = surface_measures['area']
        del polydata

        # Set actor colour and transparency
        actor.GetProperty().SetColor(colour)
        actor.GetProperty().SetOpacity(1-surface.transparency)

        prop = actor.GetProperty()

        interpolation = int(ses.Session().surface_interpolation)

        prop.SetInterpolation(interpolation)

        proj = prj.Project()
        if overwrite:
            proj.ChangeSurface(surface)
        else:
            index = proj.AddSurface(surface)
            surface.index = index
            self.last_surface_index = index

        session = ses.Session()
        session.ChangeProject()

        Publisher.sendMessage('Load surface actor into viewer', actor=actor)

        # Send actor by pubsub to viewer's render
        if overwrite and self.actors_dict.keys():
            old_actor = self.actors_dict[self.last_surface_index]
            Publisher.sendMessage('Remove surface actor from viewer', actor=old_actor)

        # Save actor for future management tasks
        self.actors_dict[surface.index] = actor
        Publisher.sendMessage('Update surface info in GUI', surface=surface)
        Publisher.sendMessage('End busy cursor')

        dialog.running = False

    def _on_callback_error(self, e, dialog=None):
        dialog.running = False
        msg = utl.log_traceback(e)
        dialog.error = msg

    def AddNewActor(self, slice_, mask, surface_parameters):
        """
        Create surface actor, save into project and send it to viewer.
        """
        t_init = time.time()
        matrix = slice_.matrix
        filename_img = slice_.matrix_filename
        spacing = slice_.spacing

        algorithm = surface_parameters['method']['algorithm']
        options = surface_parameters['method']['options']

        surface_name = surface_parameters['options']['name']
        quality = surface_parameters['options']['quality']
        fill_holes = surface_parameters['options']['fill']
        keep_largest = surface_parameters['options']['keep_largest']

        fill_border_holes = surface_parameters['options'].get('fill_border_holes', True)

        mode = 'CONTOUR' # 'GRAYSCALE'
        min_value, max_value = mask.threshold_range
        colour = mask.colour[:3]

        try:
            overwrite = surface_parameters['options']['overwrite']
        except KeyError:
            overwrite = False
        mask.matrix.flush()

        if quality in const.SURFACE_QUALITY.keys():
            imagedata_resolution = const.SURFACE_QUALITY[quality][0]
            smooth_iterations = const.SURFACE_QUALITY[quality][1]
            smooth_relaxation_factor = const.SURFACE_QUALITY[quality][2]
            decimate_reduction = const.SURFACE_QUALITY[quality][3]

        pipeline_size = 4
        if decimate_reduction:
            pipeline_size += 1
        if (smooth_iterations and smooth_relaxation_factor):
            pipeline_size += 1
        if fill_holes:
            pipeline_size += 1
        if keep_largest:
            pipeline_size += 1

        language = ses.Session().language

        if (prj.Project().original_orientation == const.CORONAL):
            flip_image = False
        else:
            flip_image = True

        n_processors = multiprocessing.cpu_count()

        o_piece = 1
        piece_size = 20

        n_pieces = int(round(matrix.shape[0] / piece_size + 0.5, 0))

        filenames = []
        pool = multiprocessing.Pool(processes=min(n_pieces, n_processors))
        manager = multiprocessing.Manager()
        msg_queue = manager.Queue(1)

        # If InVesalius is running without GUI
        if wx.GetApp() is None:
            for i in range(n_pieces):
                init = i * piece_size
                end = init + piece_size + o_piece
                roi = slice(init, end)
                print("new_piece", roi)
                f = pool.apply_async(surface_process.create_surface_piece,
                                     args = (filename_img, matrix.shape, matrix.dtype,
                                             mask.temp_file, mask.matrix.shape,
                                             mask.matrix.dtype, roi, spacing, mode,
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
                surface_filename, surface_measures = f.get()
            except Exception as e:
                print(_("InVesalius was not able to create the surface"))
                print(traceback.print_exc())
                return

            reader = vtk.vtkXMLPolyDataReader()
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
            sp = dialogs.SurfaceProgressWindow()
            for i in range(n_pieces):
                init = i * piece_size
                end = init + piece_size + o_piece
                roi = slice(init, end)
                print("new_piece", roi)
                try:
                    f = pool.apply_async(surface_process.create_surface_piece,
                                         args = (filename_img, matrix.shape, matrix.dtype,
                                                 mask.temp_file, mask.matrix.shape,
                                                 mask.matrix.dtype, roi, spacing, mode,
                                                 min_value, max_value, decimate_reduction,
                                                 smooth_relaxation_factor,
                                                 smooth_iterations, language, flip_image,
                                                 algorithm != 'Default', algorithm,
                                                 imagedata_resolution, fill_border_holes),
                                         callback=lambda x: filenames.append(x),
                                         error_callback=functools.partial(self._on_callback_error,
                                                                          dialog=sp))
                # python2
                except TypeError:
                    f = pool.apply_async(surface_process.create_surface_piece,
                                         args = (filename_img, matrix.shape, matrix.dtype,
                                                 mask.temp_file, mask.matrix.shape,
                                                 mask.matrix.dtype, roi, spacing, mode,
                                                 min_value, max_value, decimate_reduction,
                                                 smooth_relaxation_factor,
                                                 smooth_iterations, language, flip_image,
                                                 algorithm != 'Default', algorithm,
                                                 imagedata_resolution, fill_border_holes),
                                         callback=lambda x: filenames.append(x))

            while len(filenames) != n_pieces:
                if sp.WasCancelled() or not sp.running:
                    break
                time.sleep(0.25)
                sp.Update(_("Creating 3D surface..."))
                wx.Yield()

            if not sp.WasCancelled() or sp.running:
                try:
                    f = pool.apply_async(surface_process.join_process_surface,
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
                # python2
                except TypeError:
                    f = pool.apply_async(surface_process.join_process_surface,
                                         args=(filenames, algorithm, smooth_iterations,
                                               smooth_relaxation_factor,
                                               decimate_reduction, keep_largest,
                                               fill_holes, options, msg_queue),
                                         callback=functools.partial(self._on_complete_surface_creation,
                                                                    overwrite=overwrite,
                                                                    surface_name=surface_name,
                                                                    colour=colour,
                                                                    dialog=sp))

                while sp.running:
                    if sp.WasCancelled():
                        break
                    time.sleep(0.25)
                    try:
                        msg = msg_queue.get_nowait()
                        sp.Update(msg)
                    except:
                        sp.Update(None)
                    wx.Yield()

            t_end = time.time()
            print("Elapsed time - {}".format(t_end-t_init))
            sp.Close()
            if sp.error:
                dlg = GMD.GenericMessageDialog(None, sp.error,
                                               "Exception!",
                                               wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()
            del sp

        pool.close()
        pool.terminate()
        del pool
        del manager
        del msg_queue
        import gc
        gc.collect()

    def UpdateSurfaceInterpolation(self):
        interpolation = int(ses.Session().surface_interpolation)
        key_actors = self.actors_dict.keys()

        for key in self.actors_dict:
            self.actors_dict[key].GetProperty().SetInterpolation(interpolation)
        Publisher.sendMessage('Render volume viewer')

    def RemoveActor(self, index):
        """
        Remove actor, according to given actor index.
        """
        Publisher.sendMessage('Remove surface actor from viewer', actor=index)
        self.actors_dict.pop(index)
        # Remove surface from project's surface_dict
        proj = prj.Project()
        proj.surface_dict.pop(index)

    def OnChangeSurfaceName(self, index, name):
        proj = prj.Project()
        proj.surface_dict[index].name = name

    def OnShowSurface(self, index, visibility):
        self.ShowActor(index, visibility)

    def ShowActor(self, index, value):
        """
        Show or hide actor, according to given actor index and value.
        """
        self.actors_dict[index].SetVisibility(value)
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[index].is_shown = value
        Publisher.sendMessage('Render volume viewer')

    def SetActorTransparency(self, surface_index, transparency):
        """
        Set actor transparency (oposite to opacity) according to given actor
        index and value.
        """
        self.actors_dict[surface_index].GetProperty().SetOpacity(1-transparency)
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[surface_index].transparency = transparency
        Publisher.sendMessage('Render volume viewer')

    def SetActorColour(self, surface_index, colour):
        """
        """
        self.actors_dict[surface_index].GetProperty().SetColor(colour[:3])
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[surface_index].colour = colour
        Publisher.sendMessage('Render volume viewer')

    def OnExportSurface(self, filename, filetype):
        ftype_prefix = {
            const.FILETYPE_STL: '.stl',
            const.FILETYPE_VTP: '.vtp',
            const.FILETYPE_PLY: '.ply',
            const.FILETYPE_STL_ASCII: '.stl',
        }
        if filetype in ftype_prefix:
            temp_file = tempfile.mktemp(suffix=ftype_prefix[filetype])

            if _has_win32api:
                utl.touch(temp_file)
                _temp_file = temp_file
                temp_file = win32api.GetShortPathName(temp_file)
                os.remove(_temp_file)

            temp_file = utl.decode(temp_file, const.FS_ENCODE)
            self._export_surface(temp_file, filetype)

            shutil.move(temp_file, filename)

    def _export_surface(self, filename, filetype):
        if filetype in (const.FILETYPE_STL,
                        const.FILETYPE_VTP,
                        const.FILETYPE_PLY,
                        const.FILETYPE_STL_ASCII):
            # First we identify all surfaces that are selected
            # (if any)
            proj = prj.Project()
            polydata_list = []

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

            # Having a polydata that represents all surfaces
            # selected, we write it, according to filetype
            if filetype == const.FILETYPE_STL:
                writer = vtk.vtkSTLWriter()
                writer.SetFileTypeToBinary()
            elif filetype == const.FILETYPE_STL_ASCII:
                writer = vtk.vtkSTLWriter()
                writer.SetFileTypeToASCII()
            elif filetype == const.FILETYPE_VTP:
                writer = vtk.vtkXMLPolyDataWriter()
            #elif filetype == const.FILETYPE_IV:
            #    writer = vtk.vtkIVWriter()
            elif filetype == const.FILETYPE_PLY:
                writer = vtk.vtkPLYWriter()
                writer.SetFileTypeToASCII()
                writer.SetColorModeToOff()
                #writer.SetDataByteOrderToLittleEndian()
                #writer.SetColorModeToUniformCellColor()
                #writer.SetColor(255, 0, 0)

            if filetype in (const.FILETYPE_STL,
                            const.FILETYPE_STL_ASCII,
                            const.FILETYPE_PLY):
                # Invert normals
                normals = vtk.vtkPolyDataNormals()
                normals.SetInputData(polydata)
                normals.SetFeatureAngle(80)
                normals.AutoOrientNormalsOn()
                #  normals.GetOutput().ReleaseDataFlagOn()
                normals.UpdateInformation()
                normals.Update()
                polydata = normals.GetOutput()

            filename = filename.encode(const.FS_ENCODE)
            writer.SetFileName(filename)
            writer.SetInputData(polydata)
            writer.Write()
