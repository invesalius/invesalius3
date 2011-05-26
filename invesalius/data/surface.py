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

import multiprocessing
import os
import plistlib
import random
import sys
import tempfile

import vtk
import wx.lib.pubsub as ps

import constants as const
import imagedata_utils as iu
import polydata_utils as pu
import project as prj
import session as ses
import surface_process
import utils as utl
import vtk_utils as vu

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
        self.volume = 0
        self.is_shown = 1
        if not name:
            self.name = const.SURFACE_NAME_PATTERN %(self.index+1)
        else:
            self.name = name

    def SavePlist(self, filename):
        surface = {}
        filename = '%s$%s$%d' % (filename, 'surface', self.index)
        d = self.__dict__
        for key in d:
            if isinstance(d[key], vtk.vtkPolyData):
                img_name = '%s_%s.vtp' % (filename, key)
                pu.Export(d[key], img_name, bin=True)
                surface[key] = {'$vtp': os.path.split(img_name)[1]}
            else:
                surface[key] = d[key]


        plistlib.writePlist(surface, filename + '.plist')
        return os.path.split(filename)[1] + '.plist'

    def OpenPList(self, filename):
        surface = plistlib.readPlist(filename)
        dirpath = os.path.abspath(os.path.split(filename)[0])
        for key in surface:
            if key == 'polydata':
                filepath = os.path.split(surface[key]["$vtp"])[-1]
                path = os.path.join(dirpath, filepath)
                self.polydata = pu.Import(path)
            else:
                setattr(self, key, surface[key])

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
        ps.Publisher().subscribe(self.AddNewActor, 'Create surface')
        ps.Publisher().subscribe(self.SetActorTransparency,
                                 'Set surface transparency')
        ps.Publisher().subscribe(self.SetActorColour,
                                 'Set surface colour')

        ps.Publisher().subscribe(self.OnChangeSurfaceName, 'Change surface name')
        ps.Publisher().subscribe(self.OnShowSurface, 'Show surface')
        ps.Publisher().subscribe(self.OnExportSurface,'Export surface to file')
        ps.Publisher().subscribe(self.OnLoadSurfaceDict, 'Load surface dict')
        ps.Publisher().subscribe(self.OnCloseProject, 'Close project data')
        ps.Publisher().subscribe(self.OnSelectSurface, 'Change surface selected')
        #----
        ps.Publisher().subscribe(self.OnSplitSurface, 'Split surface')
        ps.Publisher().subscribe(self.OnLargestSurface,
                                'Create surface from largest region')
        ps.Publisher().subscribe(self.OnSeedSurface, "Create surface from seeds")

        ps.Publisher().subscribe(self.OnDuplicate, "Duplicate surfaces")
        ps.Publisher().subscribe(self.OnRemove,"Remove surfaces")
        ps.Publisher().subscribe(self.UpdateSurfaceInterpolation, 'Update Surface Interpolation')
    
    def OnDuplicate(self, pubsub_evt):
        selected_items = pubsub_evt.data
        proj = prj.Project()
        surface_dict = proj.surface_dict
        for index in selected_items:
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
                                           volume = original_surface.volume)


    def OnRemove(self, pubsub_evt):
        selected_items = pubsub_evt.data
        proj = prj.Project()

        old_dict = self.actors_dict
        new_dict = {}
        if selected_items:
            for index in selected_items:
                proj.RemoveSurface(index)
                actor = old_dict[index]
                for i in old_dict:
                    if i < index:
                        new_dict[i] = old_dict[i]
                    if i > index:
                        new_dict[i-1] = old_dict[i]
                old_dict = new_dict
                ps.Publisher().sendMessage('Remove surface actor from viewer', actor)
            self.actors_dict = new_dict

        if self.last_surface_index in selected_items:
            if self.actors_dict:
                self.last_surface_index = 0
            else:
                self.last_surface_index = None
                

    def OnSeedSurface(self, pubsub_evt):
        """
        Create a new surface, based on the last selected surface,
        using as reference seeds user add to surface of reference.
        """
        points_id_list = pubsub_evt.data
        index = self.last_surface_index
        proj = prj.Project()
        surface = proj.surface_dict[index]

        new_polydata = pu.JoinSeedsParts(surface.polydata,
                                          points_id_list)
        index = self.CreateSurfaceFromPolydata(new_polydata)
        ps.Publisher().sendMessage('Show single surface', (index, True))
        #self.ShowActor(index, True)


    def OnSplitSurface(self, pubsub_evt):
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

        ps.Publisher().sendMessage('Show multiple surfaces', (index_list, True)) 
        

    def OnLargestSurface(self, pubsub_evt):
        """
        Create a new surface, based on largest part of the last
        selected surface.
        """
        index = self.last_surface_index
        proj = prj.Project()
        surface = proj.surface_dict[index]

        new_polydata = pu.SelectLargestPart(surface.polydata)
        new_index = self.CreateSurfaceFromPolydata(new_polydata)
        ps.Publisher().sendMessage('Show single surface', (new_index, True))

    def CreateSurfaceFromPolydata(self, polydata, overwrite=False,
                                  name=None, colour=None,
                                  transparency=None, volume=None):
        normals = vtk.vtkPolyDataNormals()
        normals.SetInput(polydata)
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInput(normals.GetOutput())
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
        if not volume:
            measured_polydata = vtk.vtkMassProperties()
            measured_polydata.SetInput(polydata)
            volume =  measured_polydata.GetVolume()
            surface.volume = volume
        else:
            surface.volume = volume
        self.last_surface_index = surface.index

        ps.Publisher().sendMessage('Load surface actor into viewer', actor)

        ps.Publisher().sendMessage('Update surface info in GUI',
                                        (surface.index, surface.name,
                                        surface.colour, surface.volume,
                                        surface.transparency))

        return surface.index


    def OnCloseProject(self, pubsub_evt):
        self.CloseProject()

    def CloseProject(self):
        for index in self.actors_dict:
            ps.Publisher().sendMessage('Remove surface actor from viewer', self.actors_dict[index])
        del self.actors_dict
        self.actors_dict = {}

    def OnSelectSurface(self, pubsub_evt):
        index = pubsub_evt.data
        #self.last_surface_index = index
        # self.actors_dict.
        proj = prj.Project()
        surface = proj.surface_dict[index]
        ps.Publisher().sendMessage('Update surface info in GUI',
                                    (index, surface.name,
                                    surface.colour, surface.volume,
                                    surface.transparency))
        self.last_surface_index = index
        self.ShowActor(index, True)



    def OnLoadSurfaceDict(self, pubsub_evt):
        surface_dict = pubsub_evt.data
        for key in surface_dict:
            surface = surface_dict[key]
            # Map polygonal data (vtkPolyData) to graphics primitives.
            normals = vtk.vtkPolyDataNormals()
            normals.SetInput(surface.polydata)
            normals.SetFeatureAngle(80)
            normals.AutoOrientNormalsOn()
            normals.GetOutput().ReleaseDataFlagOn()

	    # Improve performance
            stripper = vtk.vtkStripper()
            stripper.SetInput(normals.GetOutput())
            stripper.PassThroughCellIdsOn()
            stripper.PassThroughPointIdsOn()

            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInput(stripper.GetOutput())
            mapper.ScalarVisibilityOff()
	    mapper.ImmediateModeRenderingOn() # improve performance

            # Represent an object (geometry & properties) in the rendered scene
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)

            # Set actor colour and transparency
            actor.GetProperty().SetColor(surface.colour)
            actor.GetProperty().SetOpacity(1-surface.transparency)

            self.actors_dict[surface.index] = actor


            # Send actor by pubsub to viewer's render
            ps.Publisher().sendMessage('Load surface actor into viewer', (actor))

            ps.Publisher().sendMessage('Update status text in GUI',
                                        _("Ready"))

            # The following lines have to be here, otherwise all volumes disappear

            ps.Publisher().sendMessage('Update surface info in GUI',
                                        (surface.index, surface.name,
                                        surface.colour, surface.volume,
                                        surface.transparency))
            if not surface.is_shown:
                self.ShowActor(key, False)

    ####
    #(mask_index, surface_name, quality, fill_holes, keep_largest)

    def AddNewActor(self, pubsub_evt):
        """
        Create surface actor, save into project and send it to viewer.
        """
        matrix, filename_img, mask, spacing = pubsub_evt.data
        min_value, max_value = mask.threshold_range
        fill_holes = True

        #if len(surface_data) == 5:
            #imagedata, colour, [min_value, max_value], \
            #edited_points, overwrite = pubsub_evt.data
            #quality=_('Optimal *')
            #surface_name = ""
            #fill_holes = True
            #keep_largest = False
        #else:
            #imagedata, colour, [min_value, max_value],\
            #edited_points, overwrite, surface_name,\
            #quality, fill_holes, keep_largest =\
            #pubsub_evt.data

        mode = 'CONTOUR' # 'GRAYSCALE'
        quality=_('Optimal *')
        keep_largest = True
        surface_name = ""
        colour = mask.colour

        #ps.Publisher().sendMessage('Begin busy cursor')
        #imagedata_tmp = None
        #if (edited_points):
            #imagedata_tmp = vtk.vtkImageData()
            #imagedata_tmp.DeepCopy(imagedata)
            #imagedata_tmp.Update()
            #imagedata = iu.BuildEditedImage(imagedata_tmp, edited_points)

        if quality in const.SURFACE_QUALITY.keys():
            imagedata_resolution = const.SURFACE_QUALITY[quality][0]
            smooth_iterations = const.SURFACE_QUALITY[quality][1]
            smooth_relaxation_factor = const.SURFACE_QUALITY[quality][2]
            decimate_reduction = const.SURFACE_QUALITY[quality][3]

        #if imagedata_resolution:
            #imagedata = iu.ResampleImage3D(imagedata, imagedata_resolution)

        #pipeline_size = 4
        #if decimate_reduction:
            #pipeline_size += 1
        #if (smooth_iterations and smooth_relaxation_factor):
            #pipeline_size += 1
        #if fill_holes:
            #pipeline_size += 1
        #if keep_largest:
            #pipeline_size += 1

        ## Update progress value in GUI
        #UpdateProgress = vu.ShowProgress(pipeline_size)
        #UpdateProgress(0, _("Generating 3D surface..."))

        #filename_img = tempfile.mktemp()

        #writer = vtk.vtkXMLImageDataWriter()
        #writer.SetFileName(filename_img)
        #writer.SetInput(imagedata)
        #writer.Write()

        language = ses.Session().language

        overwrite = 0
        
        if (prj.Project().original_orientation == const.CORONAL):
            flip_image = False
        else:
            flip_image = True

        n_processors = multiprocessing.cpu_count()
            
        pipe_in, pipe_out = multiprocessing.Pipe()
        o_piece = 1
        piece_size = 20

        n_pieces = int(round(matrix.shape[0] / piece_size + 0.5, 0))
        print "n_pieces", n_pieces, matrix.shape

        q_in = multiprocessing.Queue()
        q_out = multiprocessing.Queue()

        p = []
        for i in xrange(n_processors):
            sp = surface_process.SurfaceProcess(pipe_in, filename_img,
                    matrix.shape, matrix.dtype, spacing, 
                    mode, min_value, max_value,
                    decimate_reduction, smooth_relaxation_factor,
                    smooth_iterations, language, fill_holes, keep_largest,
                                                flip_image, q_in, q_out)
            p.append(sp)
            sp.start()

        for i in xrange(n_pieces):
            init = i * piece_size
            end = init + piece_size + o_piece
            roi = slice(init, end)
            q_in.put(roi)
            print "new_piece", roi

        for i in p:
            q_in.put(None)

        polydata_append = vtk.vtkAppendPolyData()
        t = n_pieces
        while t:
            filename_polydata = q_out.get()

            reader = vtk.vtkXMLPolyDataReader()
            reader.SetFileName(filename_polydata)
            reader.Update()
            polydata_append.AddInput(reader.GetOutput())

            t -= 1
        polydata = polydata_append.GetOutput()

        clean = vtk.vtkCleanPolyData()
        clean.SetInput(polydata)
        clean.PointMergingOn()
        polydata = clean.GetOutput()

        smoother = vtk.vtkWindowedSincPolyDataFilter()
        smoother.SetInput(polydata)
        smoother.SetNumberOfIterations(smooth_iterations)
        smoother.SetFeatureAngle(120)
        smoother.BoundarySmoothingOn()
        smoother.SetPassBand(0.1)
        #smoother.FeatureEdgeSmoothingOn()
        #smoother.NonManifoldSmoothingOn()
        #smoother.NormalizeCoordinatesOn()
        smoother.Update()
        polydata = smoother.GetOutput()

        
        normals = vtk.vtkPolyDataNormals()
        normals.SetInput(polydata)
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        polydata = normals.GetOutput()
        #decimation = vtk.vtkDecimatePro()
        #decimation.SetInput(polydata)
        #decimation.SetTargetReduction(0.3)
        #decimation.PreserveTopologyOn()
        #decimation.SplittingOff()
        #decimation.BoundaryVertexDeletionOff()
        #polydata = decimation.GetOutput()

        # Improve performance
        stripper = vtk.vtkStripper()
        stripper.SetInput(polydata)
        stripper.PassThroughCellIdsOn()
        stripper.PassThroughPointIdsOn()

        # Map polygonal data (vtkPolyData) to graphics primitives.
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInput(stripper.GetOutput())
        mapper.ScalarVisibilityOff()
        mapper.ImmediateModeRenderingOn() # improve performance

        # Represent an object (geometry & properties) in the rendered scene
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        # Create Surface instance
        if overwrite:
            surface = Surface(index = self.last_surface_index)
        else:
            surface = Surface(name=surface_name)
        surface.colour = colour
        surface.polydata = polydata

        # Set actor colour and transparency
        actor.GetProperty().SetColor(colour)
        actor.GetProperty().SetOpacity(1-surface.transparency)

        prop = actor.GetProperty()

        interpolation = int(ses.Session().surface_interpolation)

        prop.SetInterpolation(interpolation)
        #prop.SetInterpolationToPhong()       

        # Remove temporary files
        #if sys.platform == "win32":
        #    try:
        #        os.remove(filename_img)
        #        os.remove(filename_polydata)
        #    except (WindowsError):
        #        print "Error while removing surface temporary file"
        #else: # sys.platform == "linux2" or sys.platform == "darwin"
        #    try:
        #        os.remove(filename_img)
        #        os.remove(filename_polydata)
        #    except (OSError):
        #        print "Error while removing surface temporary file"

        # Append surface into Project.surface_dict
        proj = prj.Project()
        if overwrite:
            proj.ChangeSurface(surface)
        else:
            index = proj.AddSurface(surface)
            surface.index = index
            self.last_surface_index = index


        session = ses.Session()
        session.ChangeProject()


        # The following lines have to be here, otherwise all volumes disappear
        measured_polydata = vtk.vtkMassProperties()
        measured_polydata.SetInput(polydata)
        volume =  measured_polydata.GetVolume()
        surface.volume = volume
        self.last_surface_index = surface.index

        ps.Publisher().sendMessage('Load surface actor into viewer', actor)

        # Send actor by pubsub to viewer's render
        if overwrite and self.actors_dict.keys():
            old_actor = self.actors_dict[self.last_surface_index]
            ps.Publisher().sendMessage('Remove surface actor from viewer', old_actor)

        # Save actor for future management tasks
        self.actors_dict[surface.index] = actor


        ps.Publisher().sendMessage('Update status text in GUI',
                                    _("Ready"))

        ps.Publisher().sendMessage('Update surface info in GUI',
                                    (surface.index, surface.name,
                                    surface.colour, surface.volume,
                                    surface.transparency))

        ps.Publisher().sendMessage('End busy cursor')


    def UpdateSurfaceInterpolation(self, pub_evt):
        interpolation = int(ses.Session().surface_interpolation)
        key_actors = self.actors_dict.keys()
        
        for key in self.actors_dict:
            self.actors_dict[key].GetProperty().SetInterpolation(interpolation)
        ps.Publisher().sendMessage('Render volume viewer')


    def RemoveActor(self, index):
        """
        Remove actor, according to given actor index.
        """
        ps.Publisher().sendMessage('Remove surface actor from viewer', (index))
        self.actors_dict.pop(index)
        # Remove surface from project's surface_dict
        proj = prj.Project()
        proj.surface_dict.pop(index)


    def OnChangeSurfaceName(self, pubsub_evt):
        index, name = pubsub_evt.data
        proj = prj.Project()
        proj.surface_dict[index].name = name

    def OnShowSurface(self, pubsub_evt):
        index, value = pubsub_evt.data
        self.ShowActor(index, value)

    def ShowActor(self, index, value):
        """
        Show or hide actor, according to given actor index and value.
        """
        self.actors_dict[index].SetVisibility(value)
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[index].is_shown = value
        ps.Publisher().sendMessage('Render volume viewer')

    def SetActorTransparency(self, pubsub_evt):
        """
        Set actor transparency (oposite to opacity) according to given actor
        index and value.
        """
        index, value = pubsub_evt.data
        self.actors_dict[index].GetProperty().SetOpacity(1-value)
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[index].transparency = value
        ps.Publisher().sendMessage('Render volume viewer')

    def SetActorColour(self, pubsub_evt):
        """
        """
        index, colour = pubsub_evt.data
        self.actors_dict[index].GetProperty().SetColor(colour)
        # Update value in project's surface_dict
        proj = prj.Project()
        proj.surface_dict[index].colour = colour
        ps.Publisher().sendMessage('Render volume viewer')


    def OnExportSurface(self, pubsub_evt):
        filename, filetype = pubsub_evt.data
        if (filetype == const.FILETYPE_STL) or\
           (filetype == const.FILETYPE_VTP) or\
           (filetype == const.FILETYPE_PLY) or\
           (filetype == const.FILETYPE_STL_ASCII):

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
                writer.SetFileTypeToBinary()
                writer.SetDataByteOrderToLittleEndian()
                #writer.SetColorModeToUniformCellColor()
                #writer.SetColor(255, 0, 0)

            if filetype == const.FILETYPE_STL:
                # Invert normals
                normals = vtk.vtkPolyDataNormals()
                normals.SetInput(polydata)
                normals.SetFeatureAngle(80)
                normals.AutoOrientNormalsOn()
                normals.GetOutput().ReleaseDataFlagOn()
                normals.UpdateInformation()
                polydata = normals.GetOutput()

            writer.SetFileName(filename)
            writer.SetInput(polydata)
            writer.Write()

