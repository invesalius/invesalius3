#---------------------------------------------------------------------
# Software: InVesalius Software de Reconstrucao 3D de Imagens Medicas

# Copyright: (c) 2001  Centro de Pesquisas Renato Archer
# Homepage: http://www.softwarepublico.gov.br
# Contact:  invesalius@cenpra.gov.br
# License:  GNU - General Public License version 2 (LICENSE.txt/
#                                                         LICENCA.txt)
#
#    Este programa eh software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
#---------------------------------------------------------------------

# In DICOM file format, if multiple values are present for the
# "Window Center" (Level) and "Window Width", both attributes
# shall have the same number of values and shall be considered as
# pairs. Multiple values indicate that multiple alternative views
# may be presented. In this Parser, by default, we only consider
# one pair per  time. This pair is determined by WL_PRESET
# constant or might be set by the user when calling GetWindowWidth
# and GetWindowLevel.
WL_PRESET = 0 # index of selected window and level tuple (if multiple)
WL_MULT = 0 # allow selection of multiple window and level tuples if 1

# dictionary to be used by module functions
info = {}
# keys to be used to generate dictionary info
INFO_KEYS = \
['AcquisitionDate',
 'AcquisitionGantryTilt',
 'AcquisitionModality',
 'AcquisitionNumber',
 'AcquisionSequence',
 'AcquisitionTime',
 'EquipmentKVP',
 'EquipmentInstitutionName',
 'EquipmentManufacturer',
 'EquipmentXRayTubeCurrent',
 'ImageColumnOrientation',
 'ImageConvolutionKernel',
 'ImageDataType',
 'ImageLocation',
 'ImageNumber',
 'ImagePixelSpacingX',
 'ImagePixelSpacingY',
 'ImagePosition',
 'ImageRowOrientation',
 'ImageSamplesPerPixel',
 'ImageSeriesNumber',
 'ImageThickness',
 'ImageWindowLevel',
 'ImageWindowWidth',
 'PatientAge',
 'PatientBirthDate',
 'PatientGender',
 'PatientName',
 'PhysicianName',
 'StudyID',
 'StudyInstanceUID',
 'StudyAdmittingDiagnosis',
 ]

import vtkgdcm
import gdcm

class Parser():
    """
    Medical image parser. Used to parse medical image tags.
    It supports:
      - ACR-NEMA version 1 and 2
      - DICOM 3.0 (including JPEG-lossless and lossy-, RLE)
      - Papyrus V2 and V3 file headers
    GDCM was used to develop this class.

    How to use:
      >>> image = ivMedicalImageParser()
      >>> image.SetFileName("/home/usr/0.dcm")
      # then you might call method related to tag of interest
      >>> print image.GetImagePixelSpacing()
    """

    def __init__(self):
        self.filename = None
        self.vtkgdcm_reader = vtkgdcm.vtkGDCMImageReader()
            
    def GetAcquisitionDate(self):
        """
        Return string containing the acquisition date using the
        format "dd/mm/yyyy".
        Return "" (empty string) if not set.

        DICOM standard tag (0x0008,0x0022) was used.
        """
        # TODO: internationalize data
        date = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetAcquisitionDate()
        if (date):
            year = date[0:4]
            month = date[4:6]
            day = date[6:8]
            return day + "/" + month + "/" + year
        return ""

    def GetAcquisitionNumber(self):
        """
        Return integer related to acquisition of this slice.
        Return None if field is not defined.

        DICOM standard tag (0x0020, 0x0012) was used.
        """
        tag = gdcm.Tag(0x0020, 0x0012)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  ds.GetDataElement(tag).GetValue()
            if (data):
                return int(str(data))
        return None

    def GetAccessionNumber(self):
        """
        Return integer related to acession number

        DICOM standard tag (0x0008, 0x0050) was used.
        """
        tag = gdcm.Tag(0x0008, 0x0050)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  ds.GetDataElement(tag).GetValue()
            if (data):
                return int(str(data))
        return None
    
    def GetAcquisitionTime(self):
        """
        Return string containing the acquisition time using the
        format "hh:mm:ss".
        Return "" (empty string) if not set.

        DICOM standard tag (0x0008,0x0032) was used.
        """
        time = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetAcquisitionTime()
        if (time):
            hh = time[0:2]
            mm = time[2:4]
            ss = time[4:6]
            return hh + ":" + mm + ":" + ss
        return ""

    def GetPatientAdmittingDiagnosis(self):
        """
        Return admitting diagnosis description (string).
        Return "" (empty string) if not defined.

        DICOM standard tag (0x0008,0x1080) was used.
        """

        tag = gdcm.Tag(0x0008, 0x1080)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)

        if (res[1]):
            return int(res[1])
        return ""



    def SetFileName(self, filename):
        """
        Set file name to be parsed given its filename (this should
        include the full path of the file of interest).

        Return True/False if file could be read.
        """
        import os.path as path

        filename = path.abspath(filename)

        if path.isfile(filename):
            # Several information can be acquired from DICOM using
            # vtkgdcm.vtkGDCMImageReader.GetMedicalImageProperties()
            # but some tags (such as spacing) can only be achieved
            # with gdcm.ImageReader()

            # used to parse DICOM files - similar to vtkDICOMParser
            gdcm_reader = gdcm.ImageReader()
            
            gdcm_reader.SetFileName(filename)
            
            # if DICOM file is null vtkGDCMImageReader raises vtk
            # exception
            if not gdcm_reader.Read():
                return False
            
            vtkgdcm_reader = self.vtkgdcm_reader
            vtkgdcm_reader.SetFileName(filename)
            vtkgdcm_reader.Update()
           
            self.filename = filename
            self.gdcm_reader = gdcm_reader
            self.vtkgdcm_reader = vtkgdcm_reader
            return True

        return False

    def GetImageWindowLevel(self, preset=WL_PRESET, multiple=WL_MULT):
        """
        Return image window center / level (related to brightness).
        This is an integer or a floating point. If the value can't
        be read, return None.

        By default, only one level value is returned, according to
        "preset" parameter. If no value is passed, WL_PRESET constant
        is used. In case one wishes to acquire a list with all
        level values, one should set "multiple" parameter to True.

        Return None if field is not defined.

        DICOM standard tag (0x0028,0x1050) was used.
        """

        tag = gdcm.Tag(0x0028, 0x1050)
        ds = self.gdcm_reader.GetFile().GetDataSet()

        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                # Usually 'data' is a number. However, in some DICOM
                # files, there are several values separated by '\'.
                # If multiple values are present for the "Window Center"
                # we choose only one. As this should be paired to "Window
                # Width", it is set based on WL_PRESET
                value_list = [float(value) for value in data.split('\\')]
                if multiple:
                    return value_list
                else:
                    return value_list[preset]
        return None

    def GetImageWindowWidth(self, preset=WL_PRESET, multiple=WL_MULT):
        """
        Return image window width (related to contrast). This is an
        integer or a floating point. If the value can't be read,
        return None.

        By default, only one width value is returned, according to
        "preset" parameter. If no value is passed, WL_PRESET constant
        is used. In case one wishes to acquire a list with all
        preset values, one should set "multiple" parameter to True.

        Return None if field is not defined.

        DICOM standard tag (0x0028,0x1051) was used.
        """

        tag = gdcm.Tag(0x0028,0x1051)
        ds = self.gdcm_reader.GetFile().GetDataSet()

        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                # Usually 'data' is a number. However, in some DICOM
                # files, there are several values separated by '\'.
                # If multiple values are present for the "Window Center"
                # we choose only one. As this should be paired to "Window
                # Width", it is set based on WL_PRESET
                value_list = [float(value) for value in data.split('\\')]
                
                if multiple:
                    return str(value_list)
                else:
                    return str(value_list[preset])
        return None

    def GetImagePosition(self):
        """
        Return [x, y, z] (number list) related to coordinates
        of the upper left corner voxel (first voxel transmitted).
        This value is given in mm. Number might be floating point
        or integer.
        Return None if field is not defined.

        DICOM standard tag (0x0020, 0x0032) was used.
        """
        tag = gdcm.Tag(0x0020, 0x0032)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  str(ds.GetDataElement(tag).GetValue())
            if (data):
                return [eval(value) for value in data.split('\\')]
        return None

    def GetImageLocation(self):
        """
        Return image location (floating value), related to the
        series acquisition.
        Return None if field is not defined.

        DICOM standard tag (0x0020, 0x0032) was used.
        """
        tag = gdcm.Tag(0x0020, 0x1041)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  str(ds.GetDataElement(tag).GetValue())
            if (data):
                return eval(data)
        return None

    def GetImageOffset(self):
        """
        Return image pixel offset (memory position).
        Return None if field is not defined.

        DICOM standard tag (0x7fe0, 0x0010) was used.
        """
        tag = gdcm.Tag(0x7fe0, 0x0010)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  str(ds.GetDataElement(tag).GetValue())
            if (data):
                return int(data.split(':')[1])
        return None


    def GetImageSeriesNumber(self):
        """
        Return integer related to acquisition series where this
        slice is included.
        Return None if field is not defined.

        DICOM standard tag (0x0020, 0x0011) was used.
        """
        tag = gdcm.Tag(0x0020, 0x0011)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  str(ds.GetDataElement(tag).GetValue())
            if (data) and (data != 'None'):
                return int(data)
        return None


    def GetPixelSpacing(self):
        """
        Return [x, y] (number list) related to the distance between
        each pair of pixel. That is, adjacent row spacing (delimiter)
        and adjacent column spacing. Values are usually floating point
        and represent mm.
        Return None if field is not defined.

        DICOM standard tag (0x0028, 0x0030) was used.
        """
        tag = gdcm.Tag(0x0028, 0x0030)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return [eval(value) for value in data.split('\\')]
        return None

    def GetImagePixelSpacingY(self):
        """
        Return spacing between adjacent pixels considerating y axis
        (height). Values are usually floating point and represent mm.
        Return None if field is not defined.

        DICOM standard tag (0x0028, 0x0030) was used.
        """
        spacing = self.GetPixelSpacing()
        if spacing:
            return spacing[1]
        return None

    def GetImagePixelSpacingX(self):
        """
        Return spacing between adjacent pixels considerating x axis
        (width). Values are usually floating point and represent mm.
        Return None if field is not defined.

        DICOM standard tag (0x0028, 0x0030) was used.
        """

        spacing = self.GetPixelSpacing()
        if spacing:
            return spacing[0]
        return None

    def GetPatientWeight(self):
        """
        Return patient's weight as a float value (kilograms).
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x1030) was used.
        """
        tag = gdcm.Tag(0x0010, 0x1030)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return float(data)
        return None

    def GetPatientHeight(self):
        """
        Return patient's height as a float value (meters).
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x1030) was used.
        """
        tag = gdcm.Tag(0x0010, 0x1020)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return float(data)
        return None

    def GetPatientAddress(self):
        """
        Return string containing patient's address.

        DICOM standard tag (0x0010, 0x1040) was used.
        """
        tag = gdcm.Tag(0x0010, 0x1040)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientMilitarRank(self):
        """
        Return string containing patient's militar rank.
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x1080) was used.
        """
        tag = gdcm.Tag(0x0010,0x1080)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientMilitarBranch(self):
        """
        Return string containing the militar branch.
        The country allegiance may also be included
        (e.g. B.R. Army).
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x1081) was used.
        """
        tag = gdcm.Tag(0x0010,0x1081)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientCountry(self):
        """
        Return string containing the country where the patient
        currently resides.
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x2150) was used.
        """
        tag = gdcm.Tag(0x0010,0x2150)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientRegion(self):
        """
        Return string containing the region where the patient
        currently resides.
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x2152) was used.
        """
        tag = gdcm.Tag(0x0010,0x2152)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientTelephone(self):
        """
        Return string containing the patient's telephone number.
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x2154) was used.
        """
        tag = gdcm.Tag(0x0010,0x2154)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientResponsible(self):
        """
        Return string containing the name of the person with
        medical decision authority in regards to this patient.
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x2297) was used.
        """
        tag = gdcm.Tag(0x0010,0x2297)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientResponsibleRole(self):
        """
        Return string containing the relationship of the responsible
        person in regards to this patient.
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x2298) was used.
        """
        tag = gdcm.Tag(0x0010,0x2298)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientResponsibleOrganization(self):
        """
        Return string containing the organization name with
        medical decision authority in regards to this patient.
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x2299) was used.
        """
        tag = gdcm.Tag(0x0010,0x2299)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientMedicalCondition(self):
        """
        Return string containing patient medical conditions
        (e.g. contagious illness, drug allergies, etc.).
        Return None if field is not defined.

        DICOM standard tag (0x0010, 0x2000) was used.
        """
        tag = gdcm.Tag(0x0010,0x2000)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientContrastAllergies(self):
        """
        Return string containing description of prior alergical
        reactions to contrast agents.
        Return None if field is not defined.

        DICOM standard tag (0x0008, 0x2110) was used.
        """
        tag = gdcm.Tag(0x0008, 0x2110)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None


    def GetPhysicianReferringName(self):
        """
        Return string containing physician
        of the patient.
        Return None if field is not defined.

        DICOM standard tag (0x0008, 0x0090) was used.
        """
        tag = gdcm.Tag(0x0008,0x0090)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return ""

    
    def GetPhysicianReferringAddress(self):
        """
        Return string containing physician's address.
        Return None if field is not defined.

        DICOM standard tag (0x0008, 0x0092) was used.
        """
        tag = gdcm.Tag(0x0008, 0x0092)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPhysicianeReferringTelephone(self):
        """
        Return string containing physician's telephone.
        Return None if field is not defined.

        DICOM standard tag (0x0008, 0x0094) was used.
        """
        tag = gdcm.Tag(0x0008, 0x0094)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetImageType(self):
        """
        Return list containing strings related to image origin.
        Eg: ["ORIGINAL", "PRIMARY", "AXIAL"] or ["DERIVED",
        "SECONDARY", "OTHER"]
        Return None if field is not defined.

        Critical DICOM tag (0x0008, 0x0008). Cannot be editted.
        """
        tag = gdcm.Tag(0x0008, 0x0008)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):

                return data.split('\\')
        return None

    def GetSOPClassUID(self):
        """
        Return string containing the Unique Identifier for the SOP
        class.
        Return None if field is not defined.

        Critical DICOM tag (0x0008, 0x0016). Cannot be edited.
        """
        tag = gdcm.Tag(0x0008, 0x0016)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetSOPInstanceUID(self):
        """
        Return string containing Unique Identifier for the SOP
        instance.
        Return None if field is not defined.

        Critical DICOM tag (0x0008, 0x0018). Cannot be edited.
        """
        tag = gdcm.Tag(0x0008, 0x0018)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetSeriesDescription(self):
        """
        Return string containing Series description.

        DICOM tag (0x0008, 0x1030). Cannot be edited.
        """
        tag = gdcm.Tag(0x0008, 0x1030)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None
    
    def GetStudyInstanceUID(self):
        """
        Return string containing Unique Identifier of the
        Study Instance.
        Return None if field is not defined.

        Critical DICOM Tag (0x0020,0x000D). Cannot be edited.
        """
        tag = gdcm.Tag(0x0020,0x000D)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetImagePatientOrientation(self):
        """
        Return matrix [x0, x1, x2, y0, y1, y2] related to patient
        image acquisition orientation. All values are in floating
        point representation. The first three values are associated
        to row orientation and the three last values are related
        to column orientation.
        Return None if field is not defined.

        Critical DICOM tag (0x0020,0x0037). Cannot be edited.
        """
        tag = gdcm.Tag(0x0020,0x0037)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return [float(value) for value in data.split('\\')]
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]

    def GetImageColumnOrientation(self):
        """
        Return matrix [x0, x1, x2] related to patient images'
        column acquisition orientation. All values are in floating
        point representation.
        Return None if field is not defined.

        Critical DICOM tag (0x0020,0x0037). Cannot be edited.
        """
        tag = gdcm.Tag(0x0020,0x0037)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return [float(value) for value in data.split('\\')[3:6]]
        return [0.0, 1.0, 0.0]

    def GetImageRowOrientation(self):
        """
        Return matrix [y0, y1, y2] related to patient images'
        row acquisition orientation. All values are in floating
        point representation.
        Return None if field is not defined.

        Critical DICOM tag (0x0020,0x0037). Cannot be edited.
        """
        tag = gdcm.Tag(0x0020,0x0037)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return [float(value) for value in data.split('\\')[0:3]]
        return [1.0, 0.0, 0.0]

    def GetFrameReferenceUID(self):
        """
        Return string containing Frame of Reference UID.
        Return None if field is not defined.

        Critical DICOM tag (0x0020,0x0052). Cannot be edited.
        """
        tag = gdcm.Tag(0x0020,0x0052)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetImageSamplesPerPixel(self):
        """
        Return integer related to Samples per Pixel. Eg. 1.
        Return None if field is not defined.

        Critical DICOM tag (0x0028,0x0002). Cannot be edited.
        """
        tag = gdcm.Tag(0x0028, 0x0002)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)
        if (res[1]):
            return int(res[1])
        return None

    def GetPhotometricInterpretation(self):
        """
        Return string containing the photometric interpretation.
        Eg. "MONOCHROME2".
        Return None if field is not defined.

        Critical DICOM tag (0x0028,0x0004). Cannot be edited.
        """
        tag = gdcm.Tag(0x0028, 0x0004)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)
        if (res[1]):
            return res[1]
        return None

    def GetBitsStored(self):
        """
        Return number related to number of bits stored.
        Eg. 12 or 16.
        Return None if field is not defined.

        Critical DICOM tag (0x0028,0x0101). Cannot be edited.
        """
        tag = gdcm.Tag(0x0028, 0x0101)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)
        if (res[1]):
            return int(res[1])
        return None

    def GetHighBit(self):
        """
        Return string containing hight bit. This is commonly 11 or 15.
        Return None if field is not defined.

        Critical DICOM tag (0x0028,0x0102). Cannot be edited.
        """
        tag = gdcm.Tag(0x0028, 0x0102)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)
        if (res[1]):
            return int(res[1])
        return None

    def GetProtocolName(self):
        """
        Return protocol name (string). This info varies according to
        manufactor and software interface. Eg. "FACE", "aFaceSpi",
        "1551515/2" or "./protocols/user1.pfossa.pro".
        Return None if field is not defined.

        DICOM standard tag (0x0018, 0x1030) was used.
        """
        tag = gdcm.Tag(0x0018, 0x1030)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetAcquisionSequence(self):
        """
        Return description (string) of the sequence how data was
        acquired. That is:
          - SE = Spin Echo
          - IR = Inversion Recovery
          - GR = Gradient Recalled
          - EP = Echo Planar
          - RM = Research Mode
        In some cases this information is presented in other forms:
          - HELICAL_CT
          - SCANOSCOPE
        Return None if field is not defined.

        Critical DICOM tag (0x0018, 0x0020). Cannot be edited.
        """
        tag = gdcm.Tag(0x0018, 0x0020)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetInstitutionName(self):
        """
        Return instution name (string) of the institution where the
        acquisitin quipment is located.

        DICOM standard tag (0x0008, 0x0080) was used.
        """
        tag = gdcm.Tag(0x0008, 0x0080)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        
        0x0008, 0x0081

    def GetInstitutionAddress(self):
        """
        Return mailing address (string) of the institution where the
        acquisitin quipment is located. Some institutions record only
        the city, other record the full address.
        Return None if field is not defined.

        DICOM standard tag (0x0008, 0x0081) was used.
        """
        tag = gdcm.Tag(0x0008, 0x0081)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetStudyInstanceUID(self):
        """
        Return Study Instance UID (string), related to series being
        analized.
        Return None if field is not defined.

        Critical DICOM tag (0x0020, 0x000D). Cannot be edited.
        """
        tag = gdcm.Tag(0x0020, 0x000D)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def GetPatientOccupation(self):
        """
        Return occupation of the patient (string).
        Return None if field is not defined.

        DICOM standard tag (0x0010,0x2180) was used.
        """
        tag = gdcm.Tag(0x0010, 0x2180)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data = str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None

    def _GetPixelRepresentation(self):
        """
        Return pixel representation of the data sample. Each sample
        should have the same pixel representation. Common values are:
          - 0000H = unsigned integer.
          - 0001H = 2's complement.

        DICOM standard tag (0x0028, 0x0103) was used.
        """
        tag = gdcm.Tag(0x0028, 0x0103)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)
        if (res[1]):
            return int(res[1])
        return None

    def _GetBitsAllocated(self):
        """
        Return integer containing the number of bits allocated for
        each pixel sample. Each sample should have the same number
        of bits allocated. Usually this value is 8, *16*, 32, 64.

        DICOM standard tag (0x0028, 0x0100) was used.
        """
        tag = gdcm.Tag(0x0028, 0x0100)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)

        if (res[1]):
            return int(res[1])
        return None

    def GetImageDataType(self):
        """
        Return image's pixel representation data type (string). This
        might be:
          - Float64
          - Int8
          - Int16
          - Int32
          - UInt16
        Return None otherwise.
        """
        repres = self._GetPixelRepresentation()

        bits = self._GetBitsAllocated()

        if not bits:
            answer = None
        else:
            answer = "UInt16"

        if bits == 8:
            answer = "Int8"
        elif bits == 16:
            if repres:
                answer = "Int16"
        elif bits == 32:
            answer = "Int32"
        elif bits == 64:
            answer = "Float64"

        return answer


    def GetPatientBirthDate(self):
        """
        Return string containing the patient's birth date using the
        format "dd/mm/yyyy".
        Return "" (empty string) if not set.

        DICOM standard tag (0x0010,0x0030) was used.
        """
        # TODO: internationalize data
        date = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                        .GetPatientBirthDate()
        if (date):
            year = date[0:4]
            month = date[4:6]
            day = date[6:8]
            return day + "/" + month + "/" + year
        return ""



    def GetStudyID(self):
        """
        Return string containing the Study ID.
        Return None if not set.

        DICOM standard tag (0x0020,0x0010) was used.
        """

        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                                .GetStudyID()
        if (data):
            return data
        return None

    def GetAcquisitionGantryTilt(self):
        """
        Return floating point containing nominal angle of
        tilt (in degrees) accordingly to the scanning gantry.
        If empty field, return 0.0.

        DICOM standard tag (0x0018,0x1120) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                                .GetGantryTilt()
        if (data):
            return float(data)
        return 0.0

    def GetPatientGender(self):
        """
        Return patient gender (string):
          - M: male
          - F: female
          - O: other
        If not defined, return None.

        DICOM standard tag (0x0010,0x0040) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                                .GetPatientSex()
        if (data):
            return data
        return None

    def GetPatientAge(self):
        """
        Return patient's age (integer). In case there are alpha
        characters in this field, a string is returned.
        If not defined field, return None.

        DICOM standard tag (0x0010, 0x1010) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                                .GetPatientAge()
        if (data):
            age = (data.split('Y')[0])
            try:
                return int(age)
            except ValueError:
                return age
        return None

    def GetPatientName(self):
        """
        Return patient's full legal name (string).
        If not defined, return None.

        DICOM standard tag (0x0010,0x0010) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetPatientName()
        if (data):
            return data
        return None

    def GetPatientID(self):
        """
        Return primary hospital identification number (string)
        or patient's identification number (string).
        Return None if not defined.

        DICOM standard tag (0x0010,0x0020) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                                .GetPatientID()
        if (data):
            return data
        return None


    def GetDimensionX(self):
        """
        Return integer associated to X dimension. This is related
        to the number of columns on the image.
        Return None if not defined.
        """

        data = self.vtkgdcm_reader.GetOutput()\
                            .GetDimensions()[0]
        if (data):
            return int(data)
        return None

    def GetDimensionY(self):
        """
        Return integer associated to Y dimension. This is related
        to the number of rows on the image.
        Return None if not defined.
        """
        data = self.vtkgdcm_reader.GetOutput()\
                            .GetDimensions()[1]
        if (data):
            return int(data)
        return None

    def GetDimensionZ(self):
        """
        Return float value associated to Z dimension.
        Return None if not defined.
        """
        data = self.vtkgdcm_reader.GetOutput()\
                            .GetDimensions()[2]
        if (data):
            return float(data)
        return None


    def GetEquipmentXRayTubeCurrent(self):
        """
        Return float value associated to the X-ray tube current
        (expressed in mA).
        Return None if not defined.

        DICOM standard tag (0x0018,0x1151) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                        .GetXRayTubeCurrent()
        if (data):
            return data
        return None

    def GetExposureTime(self):
        """
        Return float value associated to the time of X-ray tube current
        exposure (expressed in s).
        Return None if not defined.

        DICOM standard tag (0x0018, 0x1152) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetExposureTime()
        if (data):
            return float(data)
        return None

    def GetEquipmentKVP(self):
        """
        Return float value associated to the kilo voltage peak
        output of the (x-ray) used generator.
        Return None if not defined.

        DICOM standard tag (0x0018,0x0060) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                                    .GetKVP()
        if (data):
            return float(data)
        return None

    def GetImageThickness(self):
        """
        Return float value related to the nominal reconstructed
        slice thickness (expressed in mm).
        Return None if not defined.

        DICOM standard tag (0x0018,0x0050) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetSliceThickness()
        if (data):
            return float(data)
        return 0

    def GetImageConvolutionKernel(self):
        """
        Return string related to convolution kernel or algorithm
        used to reconstruct the data. This is very dependent on the
        model and the manufactor. Eg. "standard" kernel could be
        written on various ways (STD, STND, Stand, STANDARD).
        Return None if not defined.

        DICOM standard tag (0x0018,0x1210) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                        .GetConvolutionKernel()
        if (data):
            return data
        return None

    def GetEquipmentInstitutionName(self):
        """
        Return institution name (string) where the acquisition
        equipment is located.
        Return "" (empty string) if not defined.

        DICOM standard tag (0x0008,0x0080) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                        .GetInstitutionName()
        if (data):
            return data
        return ""

    def GetStationName(self):
        """
        Return user defined machine name (string) used to produce exam
        files.
        Return None if not defined.

        DICOM standard tag (0x0008, 0x1010) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetStationName()
        if (data):
            return data
        return None

    def GetManufacturerModelName(self):
        """
        Return equipment model name (string) used to generate exam
        files.
        Return None if not defined.

        DICOM standard tag (0x0008,0x1090) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                    .GetManufacturerModelName()
        if (data):
            return data
        return None

    def GetEquipmentManufacturer(self):
        """
        Return manufacturer name (string).
        Return None if not defined.

        DICOM standard tag (0x0008, 0x1010) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetManufacturer()
        if (data):
            return data
        return None

    def GetAcquisitionModality(self):
        """
        Return modality of acquisition:
          - CT: Computed Tomography
          - MR: Magnetic Ressonance
        Return None if not defined.

        DICOM standard tag (0x0008,0x0060) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                                .GetModality()
        if (data):
            return data
        return None


    def GetImageNumber(self):
        """
        Return slice number (integer).
        Return None if not defined.

        DICOM standard tag (0x0020,0x0013) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                            .GetImageNumber()
        if (data):
            return int(data)
        return None

    def GetStudyDescription(self):
        """
        Return study description (string).
        Return None if not defined.

        DICOM standard tag (0x0008,0x1030) was used.
        """
        data = self.vtkgdcm_reader.GetMedicalImageProperties()\
                                        .GetStudyDescription()
        if (data):
            return data
        return None

    def GetStudyAdmittingDiagnosis(self):
        """
        Return admitting diagnosis description (string).
        Return "" (empty string) if not defined.

        DICOM standard tag (0x0008,0x1080) was used.
        """

        tag = gdcm.Tag(0x0008, 0x1080)
        sf = gdcm.StringFilter()
        sf.SetFile(self.gdcm_reader.GetFile())
        res = sf.ToStringPair(tag)

        if (res[1]):
            return str(res[1])
        return ""

    def GetImageOrientationLabel(self):
        """
        Return Label regarding the orientation of
        an image. (AXIAL, SAGITTAL, CORONAL,
        OBLIQUE or UNKNOWN)
        """
        img = self.gdcm_reader.GetImage()
        direc_cosines = img.GetDirectionCosines()
        orientation = gdcm.Orientation()
        try:
            type = orientation.GetType(tuple(direc_cosines))
        except TypeError:
            type = orientation.GetType(direc_cosines)
        label = orientation.GetLabel(type)
        
        if (label):
            return label
        else:
            return None

    def GetSeriesDescrition(self):
        """
        Return a string with a description of the series.
        DICOM standard tag (0x0008, 0x103E) was used.
        """
        tag = gdcm.Tag(0x0008, 0x103E)
        ds = self.gdcm_reader.GetFile().GetDataSet()
        if ds.FindDataElement(tag):
            data =  str(ds.GetDataElement(tag).GetValue())
            if (data):
                return data
        return None



class DicomWriter:

    """
    This class is dicom to edit files and create new
    files with images of dicom vtkImageData.

    Example of use:

    Editing Patient Tag:

    >> write = ivDicomWriter.DicomWriter()
    >> write.SetFileName("C:\\my_dicom.dcm")
    >> write.SetPatientName("InVesalius")
    >> write.Save()


    Creating new dicom:

    >>> jpeg = vtk.vtkJPEGReader()
    >>> jpeg.SetFileName("c:\\img.jpg")
    >>> jpeg.Update()

    >>> write = ivDicomWriter.DicomWriter()
    >>> write.SetFileName("C:\\my_new_dicom.dcm")
    >>> write.SaveIsNew(jpeg.GetOutput())
    >>> write.SetPatientName("InVesalius")
    >>> write.Save()
    """

    def __init__(self):
    
        self.reader = None
        self.anony = gdcm.Anonymizer()
        self.path = None
        self.new_dicom = vtkgdcm.vtkGDCMImageWriter()
        reader = self.reader = gdcm.Reader()


    def SetFileName(self, path):
        """
        Set Dicom File Name
        """        
        self.path = path

        self.reader.SetFileName(path)
             
        if (self.reader.Read()):
            
            self.anony.SetFile(self.reader.GetFile())



    def SetInput(self, img_data):
        """
        Input vtkImageData
        """
        self.img_data = img_data
    
        
    def __CreateNewDicom(self, img_data):
        """
        Create New Dicom File, input is 
        a vtkImageData
        """
        new_dicom = self.new_dicom
        new_dicom.SetFileName(self.path)
        new_dicom.SetInput(img_data)
        new_dicom.Write()

        
    def SaveIsNew(self, img_data):
        """
        Write Changes in Dicom file or Create 
        New Dicom File
        """
        
        self.__CreateNewDicom(img_data)

        #Is necessary to create and add
        #information in the dicom tag
        self.SetFileName(self.path)
        self.anony.SetFile(self.reader.GetFile())

        
    def Save(self):

        reader = self.reader
        
        writer = gdcm.Writer()
        writer.SetFile(self.reader.GetFile())
        writer.SetFileName(self.path)
        writer.Write()    
            

    def SetPatientName(self, patient):
        """ 
        Set Patient Name requeries string type
        """
        self.anony.Replace(gdcm.Tag(0x0010,0x0010), \
                           str(patient))


    def SetImageThickness(self, thickness):
        """ 
        Set thickness value requeries float type
        """
        self.anony.Replace(gdcm.Tag(0x0018,0x0050), \
                           str(thickness))
       
        
    def SetImageSeriesNumber(self, number):
        """ 
        Set Serie Number value requeries int type
        """
        self.anony.Replace(gdcm.Tag(0x0020,0x0011), \
                           str(number))
       
        
    def SetImageNumber(self, number):
        """ 
        Set image Number value requeries int type
        """
        self.anony.Replace(gdcm.Tag(0x0020,0x0013),
                           str(number))
        
          
    def SetImageLocation(self, location):
        """ 
        Set slice location value requeries float type
        """
        self.anony.Replace(gdcm.Tag(0x0020,0x1041),\
                           str(number))
    
    
    def SetImagePosition(self, position):
        """ 
        Set slice position value requeries list 
        with three values x, y and z
        """
        self.anony.Replace(gdcm.Tag(0x0020,0x0032), \
                           str(position[0]) + \
                           "\\" + str(position[1]) + \
                           "\\" + str(position[2]))
   
    
    def SetAcquisitionModality(self, modality):
        """ 
        Set modality study CT or RM
        """
        self.anony.Replace(gdcm.Tag(0x0008,0x0060), \
                           str(modality))
        
        
    def SetPixelSpacing(self, spacing):
        """
        Set pixel spacing x and y
        """
        self.anony.Replace(gdcm.Tag(0x0028,0x0030), \
                           str(spacing))
        
        
    def SetInstitutionName(self, institution):
        """
        Set institution name
        """
        self.anony.Replace(gdcm.Tag(0x0008, 0x0080), \
                           str(institution))
        





def BuildDictionary(filename):
    """
    Given a DICOM filename, generate dictionary containing parsed
    information.
    """

    info = {}

    parser = Parser()
    parser.SetFileName(filename)

    # Next statement will fill up dictionary info, parsing the DICOM
    # file, given keys in info_keys list. Example:
    # info["AcquisitionDate"] = dicom.GetAcquisitionDate()
    for key in INFO_KEYS:
        info[key] = eval("parser.Get"+key+"()")

    return info

def LoadDictionary(filename):
    """
    Given a binary file (containing a dictionary), return dictionary
    containing parsed DICOM information.
    """
    import pickle

    fp = open(filename, "rb")
    info = pickle.load(fp)
    fp.close()
    return info


def DumpDictionary(filename, dictionary=info):
    """
    Given a filename and a dictionary (optional), write DICOM
    information to file in binary form.
    """
    import pickle

    fp = open(filename, "wb")
    pickle.dump(info, fp)
    fp.close()

if __name__ == "__main__":

    # Example of how to use Parser
    fail_count = 0
    total = 48

    for i in xrange(1,total+1):
        filename = "..//data//"+str(i)+".dcm"
        print "\nfilename:", filename
        parser = Parser()
        if parser.SetFileName(filename):
            print "p:", parser.GetPatientName()
            print "l:", parser.GetImageLocation()
            print "o:", parser.GetImagePatientOrientation()
            print "t:", parser.GetImageThickness()
            print "s:", parser.GetPixelSpacing()
            print "x:", parser.GetDimensionX()
            print "y:", parser.GetDimensionY()
            print "z:", parser.GetDimensionZ()
        else:
            print "--------------------------------------------------"
            total-=1
            fail_count+=1

    print "\nREPORT:"
    print "failed: ", fail_count
    print "sucess: ", total

    # Example of how to use auxiliary functions
    total = 38
    for i in xrange(1,total+1):
        if (i==8) or (i==9) or (i==13):
            pass
        else:
            filename = "..//data//"+str(i)+".dcm"
            info = BuildDictionary(filename)
            #print info





class Dicom(object):
    def __init__(self):
        pass

    def SetParser(self, parser):
        self.parser = parser

        self.LoadImageInfo()
        self.LoadPatientInfo()
        self.LoadAcquisitionInfo()
        #self.LoadStudyInfo()

    def LoadImageInfo(self):
        self.image = Image()
        self.image.SetParser(self.parser)

    def LoadPatientInfo(self):
        self.patient = Patient()
        self.patient.SetParser(self.parser)

    def LoadAcquisitionInfo(self):
        self.acquisition = Acquisition()
        self.acquisition.SetParser(self.parser)



class Patient(object):
    def __init__(self):
        pass

    def SetParser(self, parser):
        self.name = parser.GetPatientName()
        self.id = parser.GetPatientID()
        self.age = parser.GetPatientAge()
        self.birthdate = parser.GetPatientBirthDate() 
        self.gender = parser.GetPatientGender()
        self.physician = parser.GetPhysicianReferringName()
        
        
class Acquisition(object):

    def __init__(self):
        pass

    def SetParser(self, parser):
        self.patient_orientation = parser.GetImagePatientOrientation()
        self.series_description = parser.GetSeriesDescrition()
        self.tilt = parser.GetAcquisitionGantryTilt()
        self.serie_number = parser.GetImageSeriesNumber()
        self.id_study = parser.GetStudyID()
        self.modality = parser.GetAcquisitionModality()
        self.study_description = parser.GetStudyDescription()
        self.acquisition_date = parser.GetAcquisitionDate()
        self.institution = parser.GetInstitutionName()
        self.date = parser.GetAcquisitionDate()
        self.acession_number = parser.GetAccessionNumber()
        self.series_description = parser.GetSeriesDescription()
        
class Image(object):

    def __init__(self):
        pass

    def SetParser(self, parser):
        self.level = parser.GetImageWindowLevel()
        self.window = parser.GetImageWindowWidth()
        
        self.position = parser.GetImagePosition()
        if not (self.position):
            self.position = [1, 1, 1]
            
        self.number = parser.GetImageNumber()
        self.spacing = spacing = parser.GetPixelSpacing()
        self.orientation_label = parser.GetImageOrientationLabel()
        self.file = parser.filename

        if (parser.GetImageThickness()):
            try:
                spacing.append(parser.GetImageThickness())
            except(AttributeError):
                spacing = [1, 1, 1]                            
        else:
            try:
                spacing.append(1.5)
            except(AttributeError):
                spacing = [1, 1, 1]
                
        spacing[0] = round(spacing[0],2)
        spacing[1] = round(spacing[1],2)
        spacing[2] = round(spacing[2],2)
        self.spacing = spacing
        
        try:
            self.type = parser.GetImageType()[2]
        except(IndexError):
            self.type = None
            
