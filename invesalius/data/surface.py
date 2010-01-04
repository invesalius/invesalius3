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

from imagedata_utils import BuildEditedImage
import constants as const
import imagedata_utils as iu
import multiprocessing
import os
import plistlib
import polydata_utils as pu
import project as prj
import session as ses
import tempfile
import vtk
import vtk_utils as vu
import wx.lib.pubsub as ps


#------------------------------------------------------------------
class SurfaceProcess(multiprocessing.Process):
    
    def __init__(self, pipe, filename, mode, min_value, max_value,
                 decimate_reduction, smooth_relaxation_factor, 
                 smooth_iterations):
        
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.filename = filename
        self.mode = mode
        self.min_value = min_value
        self.max_value = max_value
        self.decimate_reduction = decimate_reduction
        self.smooth_relaxation_factor = smooth_relaxation_factor
        self.smooth_iterations = smooth_iterations
        
    def run(self):
        self.CreateSurface()
    
    def SendProgress(self, obj, msg):
        prog = obj.GetProgress()
        self.pipe.send([prog, msg])
    
    def CreateSurface(self):
        
        reader = vtk.vtkXMLImageDataReader()
        reader.SetFileName(self.filename)
        reader.Update()
        
        # Flip original vtkImageData
        flip = vtk.vtkImageFlip()
        flip.SetInput(reader.GetOutput())
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        
        # Create vtkPolyData from vtkImageData
        if self.mode == "CONTOUR":
            contour = vtk.vtkContourFilter()
            contour.SetInput(flip.GetOutput())
            contour.SetValue(0, self.min_value) # initial threshold
            contour.SetValue(1, self.max_value) # final threshold
            contour.GetOutput().ReleaseDataFlagOn()
            contour.AddObserver("ProgressEvent", lambda obj,evt: 
                    self.SendProgress(obj, "Generating 3D surface..."))
            polydata = contour.GetOutput()
        else: #mode == "GRAYSCALE":
            mcubes = vtk.vtkMarchingCubes()
            mcubes.SetInput(flip.GetOutput())
            mcubes.SetValue(0, 255)
            mcubes.ComputeScalarsOn()
            mcubes.ComputeGradientsOn()
            mcubes.ComputeNormalsOn()
            mcubes.ThresholdBetween(self.min_value, self.max_value)
            mcubes.GetOutput().ReleaseDataFlagOn()
            mcubes.AddObserver("ProgressEvent", lambda obj,evt: 
                    self.SendProgress(obj, "Generating 3D surface..."))
            polydata = mcubes.GetOutput()
        
        if self.decimate_reduction:
            decimation = vtk.vtkQuadricDecimation()
            decimation.SetInput(polydata)
            decimation.SetTargetReduction(self.decimate_reduction)
            decimation.GetOutput().ReleaseDataFlagOn()
            decimation.AddObserver("ProgressEvent", lambda obj,evt: 
                    self.SendProgress(obj, "Generating 3D surface..."))
            polydata = decimation.GetOutput()            
        
        if self.smooth_iterations and self.smooth_relaxation_factor:
            smoother = vtk.vtkSmoothPolyDataFilter()
            smoother.SetInput(polydata)
            smoother.SetNumberOfIterations(self.smooth_iterations)
            smoother.SetFeatureAngle(80)
            smoother.SetRelaxationFactor(self.smooth_relaxation_factor)
            smoother.FeatureEdgeSmoothingOn()
            smoother.BoundarySmoothingOn()
            smoother.GetOutput().ReleaseDataFlagOn()
            smoother.AddObserver("ProgressEvent", lambda obj,evt: 
                    self.SendProgress(obj, "Generating 3D surface..."))
            polydata = smoother.GetOutput()

        # Filter used to detect and fill holes. Only fill boundary edges holes.
        #TODO: Hey! This piece of code is the same from
        # polydata_utils.FillSurfaceHole, we need to review this.
        filled_polydata = vtk.vtkFillHolesFilter()
        filled_polydata.SetInput(polydata)
        filled_polydata.SetHoleSize(500)
        filled_polydata.AddObserver("ProgressEvent", lambda obj,evt: 
                self.SendProgress(obj, "Generating 3D surface..."))        
        polydata = filled_polydata.GetOutput()
        

        filename = tempfile.mktemp()
        writer = vtk.vtkXMLPolyDataWriter()
        writer.SetInput(polydata)
        writer.SetFileName(filename)
        writer.Write()
        
        self.pipe.send(None)
        self.pipe.send(filename)
        
#----------------------------------------------------------------------------------------------
class Surface():
    """
    Represent both vtkPolyData and associated properties.
    """
    general_index = -1
    def __init__(self):
        Surface.general_index += 1
        self.index = Surface.general_index
        self.polydata = ''
        self.colour = ''
        self.transparency = const.SURFACE_TRANSPARENCY
        self.volume = 0
        self.is_shown = 1
        self.name = const.SURFACE_NAME_PATTERN %(Surface.general_index+1)

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

    def OnCloseProject(self, pubsub_evt):
        self.CloseProject()

    def CloseProject(self):
        del self.actors_dict
        self.actors_dict = {}


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
            
            stripper = vtk.vtkStripper()
            stripper.SetInput(normals.GetOutput())
            stripper.PassThroughCellIdsOn()
            stripper.PassThroughPointIdsOn()
            
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInput(stripper.GetOutput())
            mapper.ScalarVisibilityOff()

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
                                        "Surface created.")
    
            # The following lines have to be here, otherwise all volumes disappear

            ps.Publisher().sendMessage('Update surface info in GUI',
                                        (surface.index, surface.name,
                                        surface.colour, surface.volume,
                                        surface.transparency))




    def AddNewActor(self, pubsub_evt):
        """
        Create surface actor, save into project and send it to viewer.
        """
        imagedata, colour, [min_value, max_value], edited_points = pubsub_evt.data
        quality='Optimal'
        mode = 'CONTOUR' # 'GRAYSCALE'
                        
        imagedata_tmp = None
        if (edited_points):
            imagedata_tmp = vtk.vtkImageData()
            imagedata_tmp.DeepCopy(imagedata)
            imagedata_tmp.Update()
            imagedata = BuildEditedImage(imagedata_tmp, edited_points)

        if quality in const.SURFACE_QUALITY.keys():
            imagedata_resolution = const.SURFACE_QUALITY[quality][0]
            smooth_iterations = const.SURFACE_QUALITY[quality][1]
            smooth_relaxation_factor = const.SURFACE_QUALITY[quality][2]
            decimate_reduction = const.SURFACE_QUALITY[quality][3]

        if imagedata_resolution:
            imagedata = iu.ResampleImage3D(imagedata, imagedata_resolution)

        pipeline_size = 2
        if decimate_reduction:
            pipeline_size += 1
        if (smooth_iterations and smooth_relaxation_factor):
            pipeline_size += 1

        # Update progress value in GUI
        
        filename_img = tempfile.mktemp()
        
        writer = vtk.vtkXMLImageDataWriter()
        writer.SetFileName(filename_img)
        writer.SetInput(imagedata)
        writer.Write()
        
        #pipeline_size = 4
        UpdateProgress = vu.ShowProgress(pipeline_size)
        
        pipe_in, pipe_out = multiprocessing.Pipe()
        sp = SurfaceProcess(pipe_in, filename_img, mode, min_value, max_value,
                 decimate_reduction, smooth_relaxation_factor, 
                 smooth_iterations)
        sp.start()
        
        while 1:
            msg = pipe_out.recv()
            if(msg is None):
                break
            UpdateProgress(msg[0],msg[1])
        
        filename_polydata = pipe_out.recv()
        
        reader = vtk.vtkXMLPolyDataReader()
        reader.SetFileName(filename_polydata)
        reader.Update()
        
        polydata = reader.GetOutput()
       
        # Orient normals from inside to outside
        normals = vtk.vtkPolyDataNormals()
        normals.SetInput(polydata)
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.GetOutput().ReleaseDataFlagOn()
    
        stripper = vtk.vtkStripper()
        stripper.SetInput(normals.GetOutput())
        stripper.PassThroughCellIdsOn()
        stripper.PassThroughPointIdsOn()
        
        # Map polygonal data (vtkPolyData) to graphics primitives.
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInput(stripper.GetOutput())
        mapper.ScalarVisibilityOff()

        # Represent an object (geometry & properties) in the rendered scene
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        # Create Surface instance
        surface = Surface()
        surface.colour = colour
        surface.polydata = polydata


        # Set actor colour and transparency
        actor.GetProperty().SetColor(colour)
        actor.GetProperty().SetOpacity(1-surface.transparency)
        
        #Remove all temp file
        os.remove(filename_img)
        os.remove(filename_polydata)
        
        # Append surface into Project.surface_dict
        proj = prj.Project()
        index = proj.AddSurface(surface)
        surface.index = index


        session = ses.Session()
        session.ChangeProject()


        # Save actor for future management tasks
        self.actors_dict[surface.index] = actor

        # Send actor by pubsub to viewer's render
        ps.Publisher().sendMessage('Load surface actor into viewer', (actor))

        ps.Publisher().sendMessage('Update status text in GUI',
                                    "Surface created.")

        # The following lines have to be here, otherwise all volumes disappear
        measured_polydata = vtk.vtkMassProperties()
        measured_polydata.SetInput(polydata)
        volume =  measured_polydata.GetVolume()
        surface.volume = volume

        ps.Publisher().sendMessage('Update surface info in GUI',
                                    (surface.index, surface.name,
                                    surface.colour, surface.volume,
                                    surface.transparency))

        #Destroy Copy original imagedata
        if(imagedata_tmp):
            del imagedata_tmp

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
        #print "OnShowSurface", index, value
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
           (filetype == const.FILETYPE_PLY) :

            # First we identify all surfaces that are selected
            # (if any)
            proj = prj.Project()
            polydata_list = []

            for index in proj.surface_dict:
                surface = proj.surface_dict[index]
                if surface.is_shown:
                    polydata_list.append(surface.polydata)

            if len(polydata_list) == 0:
                print "oops - no polydata"
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

