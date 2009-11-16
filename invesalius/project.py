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
        # TODO: Discuss
        # [Tati] Will this type of data be written on project file? What if user
        # changes file name and directory? I guess no... But, who knows...
        #self.name = "Default"
        #self.dir_ = "C:\\"

        # Original vtkImageData, build based on medical images read.
        # To be used for general 2D slices rendering both on 2D and 3D
        # coordinate systems. It might be used, as well, for 3D raycasting.
        # rendering.
        # TODO: Discuss when this will be used.
        self.imagedata = ''

        self.name = ''
        #self.dicom = ''
        self.modality = ''
        self.original_orientation = -1

        # Masks are related to vtkImageData
        self.mask_dict = {}
        # Predefined threshold values
        self.min_threshold = ''
        self.max_threshold = ''

        self.window = ''
        self.level = ''

        self.presets = Presets()
        self.threshold_modes = self.presets.thresh_ct
        self.threshold_range = ''
        
        self.original_orientation = ''
        # MRI ? CT?


        # TODO: define how we will relate these threshold values to
        # default threshold labels
        # TODO: Future +
        # Allow insertion of new threshold modes

        # Surfaces are related to vtkPolyDataa
        self.surface_dict = {}
        #self.surface_quality_list = ["Low", "Medium", "High", "Optimal *",
        #                             "Custom"]
        # TOOD: define how we will relate this quality possibilities to
        # values set as decimate / smooth
        # TODO: Future +
        # Allow insertion of new surface quality modes

        self.measure_dict = {}

        # TODO: Future ++
        #self.annotation_dict = {}

        # TODO: Future +
        # Volume rendering modes related to vtkImageData
        # this will need to be inserted both in the project and in the user
        # InVesalius configuration file
        # self.render_mode = {}

        # The raycasting preset setted in this project
        self.raycasting_preset = ''

        self.invesalius_version = version.get_svn_revision() 
        print self.invesalius_version

        self.debug = 0

    ####### MASK OPERATIONS

    def AddMask(self, index, mask):
        """
        Insert new mask (Mask) into project data.

        input
            @ mask: Mask associated to mask

        output
            @ index: index of item that was inserted
        """
        self.mask_dict[index] = mask

    def GetMask(self, index):
        return self.mask_dict[index]


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
        filename = os.path.join(dir_, filename)
        project = {}
        
        for key in self.__dict__:
            if getattr(self.__dict__[key], 'SavePlist', None):
                project[key] = {'#plist': self.__dict__[key].SavePlist(filename)}
            else:
                project[key] = self.__dict__[key]

        masks = {}
        for index in self.mask_dict:
            masks[str(index)] = {'#mask':\
                                 self.mask_dict[index].SavePlist(filename)}
            print index

        surfaces = {}
        for index in self.surface_dict:
            surfaces[str(index)] = {'#surface':\
                                    self.surface_dict[index].SavePlist(filename)}
            print index

        project['surface_dict'] = surfaces
        project['mask_dict'] = masks
        img_file = '%s_%s.vti' % (filename, 'imagedata')
        iu.Export(self.imagedata, img_file, bin=True)
        project['imagedata'] = {'$vti':img_file}
        print project
        plistlib.writePlist(project, filename + '.plist')
        
        Compress(dir_, "teste.inv3")#os.path.join("~/Desktop/","teste.inv3"))
        shutil.rmtree(dir_)

    def OpenPlistProject(self, filename):
        filelist = Extract(filename, tempfile.gettempdir())
        main_plist = min(filelist, key=lambda x: len(x))
        #print main_plist
        project = plistlib.readPlist(main_plist)

        #print "antes", self.__dict__

        # Path were extracted project is
        dirpath = os.path.split(filelist[0])[0]
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
    file_list = glob.glob(os.path.join(folder,"*"))
    tar = tarfile.open(filename, "w:gz")
    for name in file_list:
        tar.add(name)
    tar.close()

def Extract(filename, folder):
    tar = tarfile.open(filename, "r:gz")
    #tar.list(verbose=True)
    tar.extractall(folder)
    filelist = [os.path.join(folder, i) for i in tar.getnames()]
    tar.close()
    return filelist
