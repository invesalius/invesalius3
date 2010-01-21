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

import glob
import os
import plistlib
import shutil
import tarfile
import tempfile

import wx
import wx.lib.pubsub as ps
import vtk

import constants as const
import data.imagedata_utils as iu
import data.mask as msk
import data.polydata_utils as pu
import data.surface as srf
from presets import Presets
from utils import Singleton
import version

class Project(object):
    # Only one project will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__= Singleton

    def __init__(self):
        # Patient/ acquistion information
        self.name = ''
        #self.dicom = ''
        self.modality = ''
        self.original_orientation = ''
        self.min_threshold = ''
        self.max_threshold = ''
        self.window = ''
        self.level = ''

        # Original imagedata (shouldn't be changed)
        self.imagedata = ''

        # Masks (vtkImageData)
        self.mask_dict = {}
        self.last_mask_index = 0

        # Surfaces are (vtkPolyData)
        self.surface_dict = {}
        self.last_surface_index = -1

        # TODO: Future
        self.measure_dict = {}

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
        self.last_mask_index = mask.index
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
        self.mask_dict = new_dict

    def GetMask(self, index):
        return self.mask_dict[index]

    def AddSurface(self, surface):
        self.last_surface_index = surface.index
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
        self.surface_dict = new_dict

    def SetAcquisitionModality(self, type_=None):
        if type_ is None:
            type_ = self.modality

        if type_ == "MRI":
            self.threshold_modes = self.presets.thresh_mri
        elif type_ == "CT":
            self.threshold_modes = self.presets.thresh_ct
        else:
            print "Different Acquisition Modality!!!"
        self.modality = type_

    def SetRaycastPreset(self, label):
        path = os.path.join(RAYCASTING_PRESETS_DIRECTORY, label + '.plist')
        preset = plistlib.readPlist(path)
        ps.Publisher.sendMessage('Set raycasting preset', preset)

    def SavePlistProject(self, dir_, filename):

        # Some filenames have non-ascii characters and encoded in a strange
        # encoding, in that cases a UnicodeEncodeError is raised. To avoid
        # that we encode in utf-8.
        filename = filename.encode('utf-8')
        dir_temp = tempfile.mkdtemp(filename)
        filename_tmp = os.path.join(dir_temp, filename)

        project = {}

        for key in self.__dict__:
            if getattr(self.__dict__[key], 'SavePlist', None):
                project[key] = {'#plist':
                                self.__dict__[key].SavePlist(filename_tmp).decode('utf-8')}
            else:
                project[key] = self.__dict__[key]

        masks = {}
        for index in self.mask_dict:
            masks[str(index)] = {'#mask':\
                                 self.mask_dict[index].SavePlist(filename_tmp).decode('utf-8')}
            print index

        surfaces = {}
        for index in self.surface_dict:
            surfaces[str(index)] = {'#surface':\
                                    self.surface_dict[index].SavePlist(filename_tmp)}
            print index

        project['surface_dict'] = surfaces
        project['mask_dict'] = masks
        img_file = '%s_%s.vti' % (filename_tmp, 'imagedata')
        iu.Export(self.imagedata, img_file, bin=True)
        project['imagedata'] = {'$vti':os.path.split(img_file)[1].decode('utf-8')}

        plistlib.writePlist(project, filename_tmp + '.plist')

        path = os.path.join(dir_,filename)
        Compress(dir_temp, path)#os.path.join("~/Desktop/","teste.inv3"))
        shutil.rmtree(dir_temp)

    def OpenPlistProject(self, filename):
        
        if not const.VTK_WARNING:
            fow = vtk.vtkFileOutputWindow()
            fow.SetFileName('vtkoutput.txt')
            ow = vtk.vtkOutputWindow()
            ow.SetInstance(fow)
            
        filelist = Extract(filename, tempfile.gettempdir())
        main_plist = min(filelist, key=lambda x: len(x))
        #print main_plist
        project = plistlib.readPlist(main_plist)

        #print "antes", self.__dict__

        # Path were extracted project is
        dirpath = os.path.abspath(os.path.split(filelist[0])[0])
        #print "* dirpath", dirpath

        for key in project:
            if key == 'imagedata':
                filepath = os.path.split(project[key]["$vti"])[-1]
                path = os.path.join(dirpath, filepath)
                self.imagedata = iu.Import(path)
            elif key == 'presets':
                filepath = os.path.split(project[key]["#plist"])[-1]
                path = os.path.join(dirpath, filepath)
                p = Presets()
                p.OpenPlist(path)
                p.Test()
                self.presets = p
            elif key == 'mask_dict':
                self.mask_dict = {}
                for mask in project[key]:
                    filepath = os.path.split(project[key][mask]["#mask"])[-1]
                    path = os.path.join(dirpath, filepath)
                    m = msk.Mask()
                    m.OpenPList(path)
                    self.mask_dict[m.index] = m
            elif key == 'surface_dict':
                self.surface_dict = {}
                for surface in project[key]:
                    filepath = os.path.split(project[key][surface]["#surface"])[-1]
                    path = os.path.join(dirpath, filepath)
                    s = srf.Surface()
                    s.OpenPList(path)
                    self.surface_dict[s.index] = s
            else: 
                setattr(self, key, project[key])
        #print "depois", self.__dict__



def Compress(folder, filename):
    tmpdir, tmpdir_ = os.path.split(folder)
    current_dir = os.path.abspath(".")
    os.chdir(tmpdir)
    file_list = glob.glob(os.path.join(tmpdir_,"*"))
    
    tar = tarfile.open(tmpdir_ + ".inv3", "w:gz")
    for name in file_list:
        tar.add(name)
    tar.close()
    shutil.move(tmpdir_+ ".inv3", filename)
    os.chdir(current_dir)
    
def Extract(filename, folder):
    tar = tarfile.open(filename, "r:gz")
    #tar.list(verbose=True)
    tar.extractall(folder)
    filelist = [os.path.join(folder, i) for i in tar.getnames()]
    tar.close()
    return filelist
