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
from vtk.util.colors import yellow
import glob
import os
import math

import vtk
import vtkgdcm
import gdcm
import thread
import wx
import wx.lib.pubsub as ps

import constants as const
import dicom
import dicom_grouper
import data.imagedata_utils as iu

def ReadDicomGroup(dir_):
    
    patient_group = GetDicomGroups(dir_)
    
    if len(patient_group) > 0:
        filelist, dicom, zspacing = SelectLargerDicomGroup(patient_group)
        filelist = SortFiles(filelist, dicom)
        imagedata = CreateImageData(filelist, zspacing)
        return imagedata, dicom
    else:
        return False


def SelectLargerDicomGroup(patient_group):
    maxslices = 0
    for patient in patient_group:
        group_list = patient.GetGroups()
        for group in group_list:
            if group.nslices > maxslices:
                larger_group = group
    return larger_group

def SortFiles(filelist, dicom):
    # Sort slices
    # FIXME: Coronal Crash. necessary verify
    if (dicom.image.orientation_label <> "CORONAL"):
        #Organize reversed image
        sorter = gdcm.IPPSorter()
        sorter.SetComputeZSpacing(True)
        sorter.SetZSpacingTolerance(1e-10)
        sorter.Sort(filelist)

        #Getting organized image
        filelist = sorter.GetFilenames()

    return filelist


def yGetDicomGroups(directory, recursive=True, gui=True):
    """
    Return all full paths to DICOM files inside given directory.
    """
    nfiles = 0
    # Find total number of files
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            nfiles += len(filenames)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        nfiles = len(filenames)
    
    print "TOTAL FILES:", nfiles
    counter = 0.0
    grouper = dicom_grouper.DicomPatientGrouper()
    # Retrieve only DICOM files, splited into groups
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            print "@: ",dirpath
            for name in filenames:
                filepath = str(os.path.join(dirpath, name))
                parser = dicom.Parser()
                counter += 1
                if gui:
                    yield (counter,nfiles)
                if parser.SetFileName(filepath):
                    dcm = dicom.Dicom()
                    dcm.SetParser(parser)
                    grouper.AddFile(dcm)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        print "@: ",dirpath
        for name in filenames:
            filepath = str(os.path.join(dirpath, name))
            parser = dicom.Parser()
            counter += 1
            if gui:
                yield (counter,nfiles)
            if parser.SetFileName(filepath):
                dcm = dicom.Dicom()
                dcm.SetParser(parser)
                grouper.AddFile(dcm)

    yield grouper.GetPatientsGroups()

def GetDicomGroups(directory, recursive=True):
    return yGetDicomGroups(directory, recursive, gui=False).next()

class ProgressDicomReader:
    
    def __init__(self):
        (self.LoadFilesProgress, EVT_LOAD_FILE_PROGRESS) = wx.lib.newevent.NewEvent()
        (self.EndLoadFiles, EVT_END_LOAD_FILE) = wx.lib.newevent.NewEvent()
        
        self.evt_update_progress = EVT_LOAD_FILE_PROGRESS
        self.evt_end_load_file = EVT_END_LOAD_FILE
        
        ps.Publisher().subscribe(self.CancelLoad, "Cancel DICOM load")
    
    def CancelLoad(self, evt_pubsub):
        self.running = False
        self.stoped = True
        
    def SetWindowEvent(self, frame):
        self.frame = frame
        
    def SetDirectoryPath(self, path,recursive=True):
        self.running = True
        self.stoped = False
        thread.start_new_thread(self.GetDicomGroups,(path,recursive))
        
    def UpdateLoadFileProgress(self,cont_progress):
        evt = self.LoadFilesProgress(progress = cont_progress)
        wx.PostEvent(self.frame, evt)
                        
    def EndLoadFile(self, grouper):
        evt = self.EndLoadFiles(value = grouper)
        wx.PostEvent(self.frame, evt)
        
    def GetDicomGroups(self, path, recursive):
        y = yGetDicomGroups(path, recursive)
        while self.running:
            value_progress = y.next()
            if isinstance(value_progress, tuple):
                self.UpdateLoadFileProgress(value_progress)
            else:
                self.EndLoadFile(value_progress)
                self.running = False
              
        #Is necessary in the case user cancel
        #the load, ensure that dicomdialog is closed
        if(self.stoped):
            self.UpdateLoadFileProgress(None)
            self.stoped = False
                