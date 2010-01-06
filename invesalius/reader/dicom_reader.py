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
import math
import os
import Queue
import tempfile
import threading

from multiprocessing import cpu_count

import vtk
import vtkgdcm
import gdcm
import wx
import wx.lib.pubsub as ps

from vtk.util.colors import yellow

import constants as const
import dicom
import dicom_grouper
import data.imagedata_utils as iu
import session

def ReadDicomGroup(dir_):
    
    patient_group = GetDicomGroups(dir_)
    if len(patient_group) > 0:
        filelist, dicom, zspacing = SelectLargerDicomGroup(patient_group)
        filelist = SortFiles(filelist, dicom)
        imagedata = CreateImageData(filelist, zspacing)
        session.Session().project_status = const.NEW_PROJECT
        return imagedata, dicom
    else:
        return False


def SelectLargerDicomGroup(patient_group):
    maxslices = 0
    for patient in patient_group:
        group_list = patient.GetGroups()
        for group in group_list:
            if group.nslices > maxslices:
                maxslices = group.nslices
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

class LoadDicom(threading.Thread):
    def __init__(self, grouper, tempdir, q, l):
        threading.Thread.__init__(self)
        self.grouper = grouper
        self.tempdir = tempdir
        self.q = q
        self.l = l
    def run(self):
        grouper = self.grouper
        q = self.q
        tempdir = self.tempdir
        while 1:
            filepath = q.get()
            print "thread %s consumed %s" % (self.getName(), filepath)
            if not filepath:
                break
            parser = dicom.Parser()
            if parser.SetFileName(filepath):
                dcm = dicom.Dicom()
                self.l.acquire()
                dcm.SetParser(parser)
                grouper.AddFile(dcm)
                self.l.release()
                dcm.image.SetTempDir(tempdir)


def yGetDicomGroups(directory, recursive=True, gui=True):
    """
    Return all full paths to DICOM files inside given directory.
    """
    nfiles = 0
    tempdir = tempfile.mkdtemp()
    # Find total number of files
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            nfiles += len(filenames)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        nfiles = len(filenames)
    
    counter = 0
    grouper = dicom_grouper.DicomPatientGrouper()
    q = Queue.Queue()
    l = threading.Lock()
    threads = []
    for i in xrange(cpu_count()):
        t = LoadDicom(grouper, tempdir, q, l)
        t.start()
        threads.append(t)
    # Retrieve only DICOM files, splited into groups
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            for name in filenames:
                filepath = str(os.path.join(dirpath, name))
                counter += 1
                if gui:
                    yield (counter,nfiles)
                q.put(filepath)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        for name in filenames:
            filepath = str(os.path.join(dirpath, name))
            counter += 1
            if gui:
                yield (counter,nfiles)
            q.put(filepath)

    for t in threads:
        q.put(0)

    for t in threads:
        t.join()

    yield grouper.GetPatientsGroups()

def GetDicomGroups(directory, recursive=True):
    return yGetDicomGroups(directory, recursive, gui=False).next()


class ProgressDicomReader:
    def __init__(self):
        ps.Publisher().subscribe(self.CancelLoad, "Cancel DICOM load")

    def CancelLoad(self, evt_pubsub):
        self.running = False
        self.stoped = True
        
    def SetWindowEvent(self, frame):
        self.frame = frame
        
    def SetDirectoryPath(self, path,recursive=True):
        self.running = True
        self.stoped = False
        self.GetDicomGroups(path,recursive)

    def UpdateLoadFileProgress(self,cont_progress):
        ps.Publisher().sendMessage("Update dicom load", cont_progress)

    def EndLoadFile(self, patient_list):
        ps.Publisher().sendMessage("End dicom load", patient_list)

    def GetDicomGroups(self, path, recursive):
        
        if not const.VTK_WARNING:
            fow = vtk.vtkFileOutputWindow()
            fow.SetFileName('vtkoutput.txt')
            ow = vtk.vtkOutputWindow()
            ow.SetInstance(fow)
        
        y = yGetDicomGroups(path, recursive)
        for value_progress in y:
            if not self.running:
                break
            if isinstance(value_progress, tuple):
                self.UpdateLoadFileProgress(value_progress)
            else:
                self.EndLoadFile(value_progress)

        #Is necessary in the case user cancel
        #the load, ensure that dicomdialog is closed
        if(self.stoped):
            self.UpdateLoadFileProgress(None)
            self.stoped = False
