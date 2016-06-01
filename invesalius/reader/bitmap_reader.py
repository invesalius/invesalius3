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
import os
import Queue
import threading
import tempfile
import sys
import vtk
import re
import constants as const

from wx.lib.pubsub import pub as Publisher
from multiprocessing import cpu_count

class BitmapFiles:

    def __init__(self):
        self.bitmapfiles = []

    def Add(self, bmp):
        self.bitmapfiles.append(bmp)

    def Sort(self, x):

        c_re = re.compile('\d+')

        if len(c_re.findall(x[0])) > 0:
            return c_re.findall(x[0])[-1] 
        else:
            return '0'

    def GetValues(self):
        bmpfile = self.bitmapfiles
        bmpfile.sort(key = self.Sort)

        return bmpfile

class LoadBitmap:

    def __init__(self, bmp_file, filepath):
        self.bmp_file = bmp_file
        if sys.platform == 'win32':
            self.filepath = filepath.encode(utils.get_system_encoding())
        else:
            self.filepath = filepath
        
        self.run()
    
    def run(self):
        
        #----- verify extension ------------------
        ex = self.filepath.split('.')[-1]
        extension = ex.lower()

        if extension == 'bmp':
            reader = vtk.vtkBMPReader()

        reader.SetFileName(self.filepath)
        reader.Update()

        extent = reader.GetDataExtent()
        x = extent[1]
        y = extent[3]

        resample = vtk.vtkImageResample()
        resample.SetInputConnection(reader.GetOutputPort())
        resample.SetAxisMagnificationFactor ( 0, 0.25 )
        resample.SetAxisMagnificationFactor ( 1, 0.25 )
        resample.SetAxisMagnificationFactor ( 2, 1 )    
        resample.Update()

        thumbnail_path = tempfile.mktemp()

        write_png = vtk.vtkPNGWriter()
        write_png.SetInputConnection(resample.GetOutputPort())
        write_png.SetFileName(thumbnail_path)
        write_png.Write()

        bmp_item = [self.filepath, thumbnail_path, extension, x, y]
        self.bmp_file.Add(bmp_item)


def yGetBitmaps(directory, recursive=True, gui=True):
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


    counter = 0
    bmp_file = BitmapFiles()

    # Retrieve only TIFF, BMP, JPEG and PNG files
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            for name in filenames:
                filepath = os.path.join(dirpath, name)
                counter += 1
                if gui:
                    yield (counter,nfiles)
                #LoadDicom(grouper, filepath)
                LoadBitmap(bmp_file, filepath)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        for name in filenames:
            filepath = str(os.path.join(dirpath, name))
            counter += 1
            if gui:
                yield (counter,nfiles)
            #q.put(filepath)

    #for t in threads:
    #    q.put(0)

    #for t in threads:
    #    t.join()

    #TODO: Is this commented update necessary?
    #grouper.Update()
    yield bmp_file.GetValues()


class ProgressBitmapReader:
    def __init__(self):
        Publisher.subscribe(self.CancelLoad, "Cancel bitmap load")

    def CancelLoad(self, evt_pubsub):
        self.running = False
        self.stoped = True

    def SetWindowEvent(self, frame):
        self.frame = frame          

    def SetDirectoryPath(self, path,recursive=True):
        self.running = True
        self.stoped = False
        self.GetBitmaps(path,recursive)

    def UpdateLoadFileProgress(self,cont_progress):
        Publisher.sendMessage("Update bitmap load", cont_progress)

    def EndLoadFile(self, patient_list):
        Publisher.sendMessage("End bitmap load", patient_list)

    def GetBitmaps(self, path, recursive):

        #if not const.VTK_WARNING:
        #    log_path = os.path.join(const.LOG_FOLDER, 'vtkoutput.txt')
        #    fow = vtk.vtkFileOutputWindow()
        #    fow.SetFileName(log_path)
        #    ow = vtk.vtkOutputWindow()
        #    ow.SetInstance(fow)

        y = yGetBitmaps(path, recursive)
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


#def GetPatientsGroups(self):
#        """
#        How to use:
#        patient_list = grouper.GetPatientsGroups()
#        for patient in patient_list:
#            group_list = patient.GetGroups()
#            for group in group_list:
#                group.GetList()
#                # :) you've got a list of dicom.Dicom
#                # of the same series
#        """
#        plist = self.patients_dict.values()
#        plist = sorted(plist, key = lambda patient:patient.key[0])
#        return plist


