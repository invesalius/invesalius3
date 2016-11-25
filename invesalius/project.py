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

import datetime
import glob
import os
import plistlib
import shutil
import tarfile
import tempfile

import wx
from wx.lib.pubsub import pub as Publisher
import vtk

import invesalius.constants as const
import invesalius.data.polydata_utils as pu
from invesalius.presets import Presets 
from invesalius.utils import Singleton, debug 
import invesalius.version as version

class Project(object):
    # Only one project will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__= Singleton

    def __init__(self):
        # Patient/ acquistion information
        self.name = ''
        self.modality = ''
        self.original_orientation = ''
        self.window = ''
        self.level = ''

        # Masks (vtkImageData)
        self.mask_dict = {}

        # Surfaces are (vtkPolyData)
        self.surface_dict = {}
        self.last_surface_index = -1

        # Measurements
        self.measurement_dict = {}

        # TODO: Future ++
        self.annotation_dict = {}

        # InVesalius related data
        # So we can find bugs and reproduce user-related problems
        self.invesalius_version = version.get_svn_revision()    

        self.presets = Presets()

        self.threshold_modes = self.presets.thresh_ct
        self.threshold_range = ''

        self.raycasting_preset = ''


        #self.surface_quality_list = ["Low", "Medium", "High", "Optimal *",
        #                             "Custom"i]

        # TOOD: define how we will relate this quality possibilities to
        # values set as decimate / smooth
        # TODO: Future +
        # Allow insertion of new surface quality modes

    def Close(self):
        for name in self.__dict__:
            attr = getattr(self, name)
            del attr

        self.__init__()

    def AddMask(self, mask):
        """
        Insert new mask (Mask) into project data.

        input
            @ mask: Mask associated to mask

        output
            @ index: index of item that was inserted
        """
        index = len(self.mask_dict)
        self.mask_dict[index] = mask
        return index

    def RemoveMask(self, index):
        new_dict = {}
        for i in self.mask_dict:
            if i < index:
                new_dict[i] = self.mask_dict[i]
            if i > index:
                new_dict[i-1] = self.mask_dict[i]
                new_dict[i-1].index = i-1
        self.mask_dict = new_dict

    def GetMask(self, index):
        return self.mask_dict[index]

    def AddSurface(self, surface):
        #self.last_surface_index = surface.index
        index = len(self.surface_dict)
        self.surface_dict[index] = surface
        return index

    def ChangeSurface(self, surface):
        index = surface.index
        self.surface_dict[index] = surface

    def RemoveSurface(self, index):
        new_dict = {}
        for i in self.surface_dict:
            if i < index:
                new_dict[i] = self.surface_dict[i]
            if i > index:
                new_dict[i-1] = self.surface_dict[i]
                new_dict[i-1].index = i-1
        self.surface_dict = new_dict


    def AddMeasurement(self, measurement):
        index = len(self.measurement_dict)
        measurement.index = index
        self.measurement_dict[index] = measurement
        return index

    def ChangeMeasurement(self, measurement):
        index = measurement.index
        self.measurement_dict[index] = measurement

    def RemoveMeasurement(self, index):
        new_dict = {}
        for i in self.measurement_dict:
            if i < index:
                new_dict[i] = self.measurement_dict[i]
            if i > index:
                new_dict[i-1] = self.measurement_dict[i]
                new_dict[i-1].index = i-1
        self.measurement_dict = new_dict


    def SetAcquisitionModality(self, type_=None):
        if type_ is None:
            type_ = self.modality

        if type_ == "MRI":
            self.threshold_modes = self.presets.thresh_mri
        elif type_ == "CT":
            self.threshold_modes = self.presets.thresh_ct
        else:
            debug("Different Acquisition Modality!!!")
        self.modality = type_

    def SetRaycastPreset(self, label):
        path = os.path.join(RAYCASTING_PRESETS_DIRECTORY, label + '.plist')
        preset = plistlib.readPlist(path)
        Publisher.sendMessage('Set raycasting preset', preset)

    def GetMeasuresDict(self):
        measures = {}
        d = self.measurement_dict
        for i in d:
            m = d[i]
            item = {}
            item["index"] = m.index
            item["name"] = m.name
            item["colour"] = m.colour
            item["value"] = m.value
            item["location"] = m.location
            item["type"] = m.type
            item["slice_number"] = m.slice_number
            item["points"] = m.points
            item["visible"] = m.visible
            measures[str(m.index)] = item
        return measures

    def SavePlistProject(self, dir_, filename):
        dir_temp = tempfile.mkdtemp()
        filename_tmp = os.path.join(dir_temp, 'matrix.dat')
        filelist = {}

        project = {
                   # Format info
                   "format_version": 1,
                   "invesalius_version": const.INVESALIUS_VERSION,
                   "date": datetime.datetime.now().isoformat(),

                   # case info
                   "name": self.name, # patient's name
                   "modality": self.modality, # CT, RMI, ...
                   "orientation": self.original_orientation,
                   "window_width": self.window,
                   "window_level": self.level,
                   "scalar_range": self.threshold_range,
                   "spacing": self.spacing,
                  }

        # Saving the matrix containing the slices
        matrix = {'filename': u'matrix.dat',
                  'shape': self.matrix_shape,
                  'dtype': self.matrix_dtype,
                 }
        project['matrix'] = matrix
        filelist[self.matrix_filename] = 'matrix.dat'
        #shutil.copyfile(self.matrix_filename, filename_tmp)

        # Saving the masks
        masks = {}
        for index in self.mask_dict:
            masks[str(index)] = self.mask_dict[index].SavePlist(dir_temp,
                                                                filelist)
        project['masks'] = masks

        # Saving the surfaces
        surfaces = {}
        for index in self.surface_dict:
            surfaces[str(index)] = self.surface_dict[index].SavePlist(dir_temp,
                                                                     filelist)
        project['surfaces'] = surfaces

        # Saving the measurements
        measurements = self.GetMeasuresDict()
        measurements_filename = 'measurements.plist'
        temp_mplist = tempfile.mktemp() 
        plistlib.writePlist(measurements, 
                            temp_mplist)
        filelist[temp_mplist] = measurements_filename
        project['measurements'] = measurements_filename

        # Saving the annotations (empty in this version)
        project['annotations'] = {}

        # Saving the main plist
        temp_plist = tempfile.mktemp()
        plistlib.writePlist(project, temp_plist)
        filelist[temp_plist] = 'main.plist'

        # Compressing and generating the .inv3 file
        path = os.path.join(dir_,filename)
        Compress(dir_temp, path, filelist)

        # Removing the temp folder.
        shutil.rmtree(dir_temp)

        for f in filelist:
            if filelist[f].endswith('.plist'):
                os.remove(f)

    def OpenPlistProject(self, filename):
        import invesalius.data.measures as ms
        import invesalius.data.mask as msk
        import invesalius.data.surface as srf
        
        if not const.VTK_WARNING:
            log_path = os.path.join(const.LOG_FOLDER, 'vtkoutput.txt')
            fow = vtk.vtkFileOutputWindow()
            fow.SetFileName(log_path)
            ow = vtk.vtkOutputWindow()
            ow.SetInstance(fow)
            
        filelist = Extract(filename, tempfile.mkdtemp())
        dirpath = os.path.abspath(os.path.split(filelist[0])[0])

        # Opening the main file from invesalius 3 project
        main_plist =  os.path.join(dirpath ,'main.plist')
        project = plistlib.readPlist(main_plist)

        # case info
        self.name = project["name"]
        self.modality = project["modality"]
        self.original_orientation = project["orientation"]
        self.window = project["window_width"]
        self.level = project["window_level"]
        self.threshold_range = project["scalar_range"]
        self.spacing = project["spacing"]

        # Opening the matrix containing the slices
        filepath = os.path.join(dirpath, project["matrix"]["filename"])
        self.matrix_filename = filepath
        self.matrix_shape = project["matrix"]['shape']
        self.matrix_dtype = project["matrix"]['dtype']

        # Opening the masks
        self.mask_dict = {}
        for index in project["masks"]:
            filename = project["masks"][index]
            filepath = os.path.join(dirpath, filename)
            m = msk.Mask()
            m.OpenPList(filepath)
            self.mask_dict[m.index] = m

        # Opening the surfaces
        self.surface_dict = {}
        for index in project["surfaces"]:
            filename = project["surfaces"][index]
            filepath = os.path.join(dirpath, filename)
            s = srf.Surface(int(index))
            s.OpenPList(filepath)
            self.surface_dict[s.index] = s

        # Opening the measurements
        self.measurement_dict = {}
        measurements = plistlib.readPlist(os.path.join(dirpath,
                                                       project["measurements"]))
        for index in measurements:
            measure = ms.Measurement()
            measure.Load(measurements[index])
            self.measurement_dict[int(index)] = measure

def Compress(folder, filename, filelist):
    tmpdir, tmpdir_ = os.path.split(folder)
    current_dir = os.path.abspath(".")
    #os.chdir(tmpdir)
    #file_list = glob.glob(os.path.join(tmpdir_,"*"))
    tar_filename = tmpdir_ + ".inv3"
    tar = tarfile.open(filename.encode(wx.GetDefaultPyEncoding()), "w:gz")
    for name in filelist:
        tar.add(name, arcname=os.path.join(tmpdir_, filelist[name]))
    tar.close()
    #shutil.move(tmpdir_+ ".inv3", filename)
    #os.chdir(current_dir)

def Extract(filename, folder):
    tar = tarfile.open(filename, "r:gz")
    idir = os.path.split(tar.getnames()[0])[0]
    os.mkdir(os.path.join(folder, idir.decode('utf8')))
    filelist = []
    for t in tar.getmembers():
        fsrc = tar.extractfile(t)

        fname = os.path.join(folder, t.name.decode('utf-8'))
        fdst = file(fname, 'wb')

        shutil.copyfileobj(fsrc, fdst)

        filelist.append(fname)
        fsrc.close()
        fdst.close()
        del fsrc
        del fdst
    tar.close()
    return filelist

    
def Extract_(filename, folder):
    tar = tarfile.open(filename, "r:gz")
    #tar.list(verbose=True)
    tar.extractall(folder)
    filelist = [os.path.join(folder, i) for i in tar.getnames()]
    tar.close()
    return filelist
