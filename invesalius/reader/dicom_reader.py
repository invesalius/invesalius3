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

from multiprocessing import cpu_count

import vtk
import vtkgdcm
import gdcm
import wx.lib.pubsub as ps

import constants as const
import dicom
import dicom_grouper
import session

import glob
import utils


import plistlib

def ReadDicomGroup(dir_):

    patient_group = GetDicomGroups(dir_)
    if len(patient_group) > 0:
        filelist, dicom, zspacing = SelectLargerDicomGroup(patient_group)
        filelist = SortFiles(filelist, dicom)
        size = dicom.image.size
        bits = dicom.image.bits_allocad

        imagedata = CreateImageData(filelist, zspacing, size, bits)
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

tag_labels = {}
main_dict = {}
dict_file = {}

class LoadDicom:
    
    def __init__(self, grouper, filepath):
        self.grouper = grouper
        if sys.platform == 'win32':
            self.filepath = filepath.encode(utils.get_system_encoding())
        else:
            self.filepath = filepath
        
        self.run()
    
    def run(self):

        grouper = self.grouper
        reader = gdcm.ImageReader()
        reader.SetFileName(self.filepath)
        if (reader.Read()):
            file = reader.GetFile()
             
            # Retrieve data set
            dataSet = file.GetDataSet()
        
            # Retrieve header
            header = file.GetHeader()
            stf = gdcm.StringFilter()

            field_dict = {}
            data_dict = {}


            tag = gdcm.Tag(0x0008, 0x0005)
            ds = reader.GetFile().GetDataSet()
            if ds.FindDataElement(tag):
                encoding_value = str(ds.GetDataElement(tag).GetValue())
                
                if encoding_value.startswith("Loaded"):
                    encoding = "ISO_IR 100"
                else:
                    encoding = const.DICOM_ENCODING_TO_PYTHON[encoding_value]
            else:
                encoding = "ISO_IR 100"


            # Iterate through the Header
            iterator = header.GetDES().begin()
            while (not iterator.equal(header.GetDES().end())):
                dataElement = iterator.next()
                stf.SetFile(file)
                tag = dataElement.GetTag()
                data = stf.ToStringPair(tag)
                stag = tag.PrintAsPipeSeparatedString()
                
                group = str(tag.GetGroup())
                field = str(tag.GetElement())

                tag_labels[stag] = data[0]
                
                if not group in data_dict.keys():
                    data_dict[group] = {}

                if not(utils.VerifyInvalidPListCharacter(data[1])):
                    data_dict[group][field] = data[1].decode(encoding)
                else:
                    data_dict[group][field] = "Invalid Character"

            
            # Iterate through the Data set
            iterator = dataSet.GetDES().begin()
            while (not iterator.equal(dataSet.GetDES().end())):
                dataElement = iterator.next()
                
                stf.SetFile(file)
                tag = dataElement.GetTag()
                data = stf.ToStringPair(tag)
                stag = tag.PrintAsPipeSeparatedString()

                group = str(tag.GetGroup())
                field = str(tag.GetElement())

                tag_labels[stag] = data[0]

                if not group in data_dict.keys():
                    data_dict[group] = {}

                if not(utils.VerifyInvalidPListCharacter(data[1])):
                    data_dict[group][field] = data[1].decode(encoding)
                else:
                    data_dict[group][field] = "Invalid Character"
            


            # -------------- To Create DICOM Thumbnail -----------
            rvtk = vtkgdcm.vtkGDCMImageReader()
            rvtk.SetFileName(self.filepath)
            rvtk.Update()
            
            try:
                data = data_dict[str(0x028)][str(0x1050)]
                level = [float(value) for value in data.split('\\')][0]
                data = data_dict[str(0x028)][str(0x1051)]
                window =  [float(value) for value in data.split('\\')][0]
            except(KeyError):
                level = 300.0
                window = 2000.0 
     
            colorer = vtk.vtkImageMapToWindowLevelColors()
            colorer.SetInput(rvtk.GetOutput())
            colorer.SetWindow(float(window))
            colorer.SetLevel(float(level))
            colorer.SetOutputFormatToRGB()
            colorer.Update()           
            
            resample = vtk.vtkImageResample()
            resample.SetInput(colorer.GetOutput())
            resample.SetAxisMagnificationFactor ( 0, 0.25 )
            resample.SetAxisMagnificationFactor ( 1, 0.25 )
            resample.SetAxisMagnificationFactor ( 2, 1 )    
            resample.Update()

            thumbnail_path = tempfile.mktemp()

            write_png = vtk.vtkPNGWriter()
            write_png.SetInput(resample.GetOutput())
            write_png.SetFileName(thumbnail_path)
            write_png.Write()
            
            #------ Verify the orientation --------------------------------

            img = reader.GetImage()
            direc_cosines = img.GetDirectionCosines()
            orientation = gdcm.Orientation()
            try:
                type = orientation.GetType(tuple(direc_cosines))
            except TypeError:
                type = orientation.GetType(direc_cosines)
            label = orientation.GetLabel(type)

 
            # ----------   Refactory --------------------------------------
            data_dict['invesalius'] = {'orientation_label' : label}

            # -------------------------------------------------------------
            dict_file[self.filepath] = data_dict
            
            #----------  Verify is DICOMDir -------------------------------
            is_dicom_dir = 1
            try: 
                if (data_dict[str(0x002)][str(0x002)] != "1.2.840.10008.1.3.10"): #DICOMDIR
                    is_dicom_dir = 0
            except(KeyError):
                    is_dicom_dir = 0
                                        
            if not(is_dicom_dir):
                parser = dicom.Parser()
                parser.SetDataImage(dict_file[self.filepath], self.filepath, thumbnail_path)
                
                dcm = dicom.Dicom()
                #self.l.acquire()
                dcm.SetParser(parser)
                grouper.AddFile(dcm)

                #self.l.release()
        

        #==========  used in test =======================================
        #print dict_file
        #main_dict = dict(
        #                data  = dict_file,
        #                labels  = tag_labels)
        #print main_dict
        #print "\n" 
        #plistlib.writePlist(main_dict, ".//teste.plist")


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

    counter = 0
    grouper = dicom_grouper.DicomPatientGrouper() 
    #q = Queue.Queue()
    #l = threading.Lock()
    #threads = []
    #for i in xrange(cpu_count()):
    #    t = LoadDicom(grouper, q, l)
    #    t.start()
    #    threads.append(t)
    # Retrieve only DICOM files, splited into groups
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            for name in filenames:
                filepath = os.path.join(dirpath, name)
                counter += 1
                if gui:
                    yield (counter,nfiles)
                LoadDicom(grouper, filepath)
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
            log_path = os.path.join(const.LOG_FOLDER, 'vtkoutput.txt')
            fow = vtk.vtkFileOutputWindow()
            fow.SetFileName(log_path)
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


