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

import dicom as ivDicom

class ivDicomGroups:
    """
    It is possible to separate sets of a set
    of files dicom.

    To use:
    list_dicoms = [c:\a.dcm, c:\a1.gdcm]
    dicom_splitter = ivDicomGroups()
    dicom_splitter.SetFileList(list_dicoms)
    dicom_splitter.Update()
    splitted = dicom_splitter.GetOutput()
    """

    def __init__(self):
        self.parser = ivDicom.Parser()
        #List of DICOM from Directory
        self.filenamelist = []
        # List of DICOM with Informations
        self.filelist = []
        #is output
        self.groups_dcm = {}
        #It is the kind of group that was used.
        self.split_type = 0

    def SetFileList(self, filenamelist):
        """
        Input is a list with the complete address
        of each DICOM.
        """
        self.filenamelist = filenamelist

    def Update(self):
        """
        Trigger processing group of series
        """

        self.__ParseFiles()

        self.__Split1()

        if (len(self.GetOutput().keys()) == len(self.filenamelist)):
            self.__Split2()
            self.split_type = 1

        self.__Split3()

        self.__Info()


    def GetOutput(self):
        """
        Returns a dictionary with groups
        of DICOM.
        """
        return self.groups_dcm

    def GetSplitterTyoe(self):
        """
        Return Integer with the SplitterType
        0 option used the name of patient information,
        id of the study, number of series and orientation
        of the image (AXIAL, SAGITAL and CORONAL).
        1 option was checked is used to splitted the if distance
        of the images (tag image position) is more 2x Thickness.
        """
        return self.split_type

    def __ParseFiles(self):
        """
        It generates a list with information
        concerning dicom files within a directory.
        The Input is a List containing andress of
        the DICOM
        """
        filenamelist = self.filenamelist
        filelist = self.filelist
        parser = self.parser
        for x in xrange(len(filenamelist)):

            if not parser.SetFileName(filenamelist[x]):
                return None

            file = filenamelist[x]
            patient_name = parser.GetPatientName()
            serie_number = parser.GetImageSeriesNumber()

            image_position = parser.GetImagePosition()
            image_number = parser.GetImageNumber()

            try:
                image_type = parser.GetImageType()[2]
            except(IndexError):
                image_type = None

            patient_position = parser.GetImagePatientOrientation()
            image_orientation_label = parser.GetImageOrientationLabel()
            series_description = parser.GetSeriesDescrition()
            spacing = parser.GetPixelSpacing()
            id_study = parser.GetStudyID()
            tilt = parser.GetAcquisitionGantryTilt()
            localization = parser.GetImageLocation()

            if (parser.GetImageThickness()):
                spacing.append(parser.GetImageThickness())
            else:
                spacing.append(1.5)

            spacing[0] = round(spacing[0],2)
            spacing[1] = round(spacing[1],2)
            spacing[2] = round(spacing[2],2)

            filelist.append([image_number, serie_number, spacing,
                           image_position, patient_position,
                           image_type,patient_name,
                           image_orientation_label, file,
                           series_description, id_study, tilt, localization])
        self.filelist = filelist

    def __GetInformations(self, ind):
        """
        Return a list referring to a specific DICOM
        in dictionary. In some cases it is necessary
        to pass only the index
        """
        filelist = self.filelist

        self.filelist.sort()

        image_number = filelist[ind][0]
        serie_number = filelist[ind][1]
        spacing = filelist[ind][2]
        image_position = filelist[ind][3]
        patient_position =  filelist[ind][4]
        image_type = filelist[ind][5]
        patient_name = filelist[ind][6]
        image_orientation_label = filelist[ind][7]
        file =  filelist[ind][8]
        series_description = filelist[ind][9]
        id_study = filelist[ind][10]
        tilt = filelist[ind][11]
        localization = filelist[ind][12]

        list = [image_number, serie_number, spacing,
               image_position, patient_position,
               image_type,patient_name,
               image_orientation_label, file,
               series_description, id_study, tilt, 
               localization]

        return list


    def __Split1(self):
        """
        Bring together the series under the name of
        the patient, id of the study, serial number
        and label orientation of the image.
        """
        groups_dcm = self.groups_dcm

        for x in xrange(len(self.filelist)):

            list = self.__GetInformations(x)

            patient_name = list[6]
            serie_number = list[1]
            id_study = list[10]
            image_orientation_label = list[7]

            key = (patient_name, id_study, serie_number,
                   image_orientation_label)

            if (key in groups_dcm.keys()):
                groups_dcm[key][0].append(list)
            else:
                groups_dcm[key] = [[list]]

        self.groups_dcm = groups_dcm


    def __Split2(self):
        """
        Separate according to the difference of the current
        share with the next.
        If the else them is higher than the z axis
        multiplied by two.
        """
        self.groups_dcm = {}
        cont_series = 0
        groups_dcm = self.groups_dcm

        #Through in the series (index of the dictionary)
        for x in xrange(len(self.filelist)):
            #Slices through in the serie
            list = self.__GetInformations(x)

            spacing = list[2]
            image_position = list[3]
            image_orientation_label = list[7]
            patient_name = list[6]
            serie_number = list[1]
            id_study = list[10]
            image_orientation_label = list[7]

            key = (patient_name, cont_series)

            #If there exists only one slice.
            if (len(self.filelist) > 1):
                #If the number of slices in the series is
                #less than the all number of slices.
                #It is necessary to whether and the
                #last slice.
                if ((x < len(self.filelist) and (x != len(self.filelist) - 1))):
                    #position of next slice
                    image_position_prox =  self.__GetInformations(x + 1)[3]
                else:
                    #slice up the position.
                    image_position_prox =  self.__GetInformations(x - 1)[3]

                #According to the orientation of the image subtraction
                #will be between a specific position in the vector of positions.
                if(image_orientation_label == "SAGITTAL"):
                    dif_image_position = image_position_prox[0] - image_position[0]

                elif (image_orientation_label == "AXIAL"):
                    dif_image_position = image_position_prox[1] - image_position[1]
                else:
                    dif_image_position = image_position_prox[2] - image_position[2]

                #If the difference in the positions is less than the
                #spacing z-axis (thickness) multiplied by two.
                #Otherwise this key create and add value
                if ((dif_image_position) <= spacing[2] * 2):
                    #If there is already such a key in the dictionary,
                    #only adds value. Otherwise this key create in the
                    #dictionary and add value
                    if (key in groups_dcm.keys()):
                        groups_dcm[key][0].append(list)
                    else:
                        groups_dcm[key] = [[list]]
                else:
                    cont_series = cont_series + 1
                    groups_dcm[key] = [[list]]

            else:

                if (cont_series in groups_dcm.keys()):
                    groups_dcm[key].append(list)
                else:
                    groups_dcm[key] = [[list]]

                cont_series = cont_series + 1

        self.groups_dcm = groups_dcm


    def __Split3(self):
        """
        Separate the slice with the positions
        repeated.
        """
        groups_dcm = self.groups_dcm
        groups_dcm_ = {}
        size_groups = len(groups_dcm.keys())
        tmp1 = {}
        tmp_list = []

        #goes according to the serial number
        #already separated.
        for n in xrange(size_groups):

            #Key of dictionary
            key = groups_dcm.keys()[n]

            #Number of slices in the series
            size_list = len(groups_dcm[key][0])

            for y in xrange(size_list):

                #Slices walks in the series
                image_pos = groups_dcm[key][0][y][3]
                image_number = groups_dcm[key][0][y][0]
                serie_number = groups_dcm[key][0][y][1]
                spacing = groups_dcm[key][0][y][2]
                image_position = groups_dcm[key][0][y][3]
                patient_position =  groups_dcm[key][0][y][4]
                image_type = groups_dcm[key][0][y][5]
                patient_name = groups_dcm[key][0][y][6]
                image_orientation_label = groups_dcm[key][0][y][7]
                file =  groups_dcm[key][0][y][8]
                series_description = groups_dcm[key][0][y][9]
                id_study = groups_dcm[key][0][y][10]
                tilt = groups_dcm[key][0][y][11]
                localization = groups_dcm[key][0][y][12]

                #Generate new key to dictionary
                key_ = (image_pos[0], image_pos[1], image_pos[2])

                #Add informations in the list
                list = [image_number, serie_number, spacing,
                       image_position, patient_position,
                       image_type,patient_name,
                       image_orientation_label, file,
                       series_description, id_study, tilt, localization]

                #If list Null, create dictionary
                #and add list with information
                #after add in a temporary list
                if (tmp_list == []):
                    tmp = {}
                    tmp[key_] = list
                    tmp_list.append(tmp)

                else:
                    b = len(tmp_list)
                    a = 0
                    #flag is to control when be necessary
                    #to create another position in the list.
                    flag = 0

                    while a < b:
                        #if there is to share the same
                        #position create new key in the
                        #dictionary

                        if not (key_ in (tmp_list[a]).keys()):
                            (tmp_list[a])[key_] = list
                            flag = 1
                        a = a + 1

                    if (flag == 0):
                        tmp = {}
                        tmp[key_] = list

                        tmp_list.append(tmp)


        #for each item on the list is created
        #a new position in the dictionary.
        size_tmp_list = len(tmp_list)

        for x in xrange(size_tmp_list):

            tmp1 = tmp_list[x]

            for m in xrange(len(tmp1.keys())):

                key = tmp1.keys()[m]

                image_pos = tmp1[key][3]
                image_number = tmp1[key][0]
                serie_number = tmp1[key][1]
                spacing = tmp1[key][2]
                image_position = tmp1[key][3]
                patient_position =  tmp1[key][4]
                image_type = tmp1[key][5]
                patient_name = tmp1[key][6]
                image_orientation_label = tmp1[key][7]
                file =  tmp1[key][8]
                series_description = tmp1[key][9]
                id_study = tmp1[key][10]
                tilt = tmp1[key][11]
                localization = tmp1[key][12]

                new_key = (patient_name, None, x, image_orientation_label)


                list = [image_number, serie_number, spacing,
                       image_position, patient_position,
                       image_type,patient_name,
                       image_orientation_label, file,
                       series_description, id_study, tilt,
                       localization]


                if (new_key in groups_dcm_.keys()):
                    groups_dcm_[new_key][0].append(list)
                else:
                    groups_dcm_[new_key] = [[list]]

        for j in xrange(len(groups_dcm_.keys())):
            key = groups_dcm_.keys()[j]
            groups_dcm_[key][0].sort()
        #the number of previously existing number is
        #greater or equal then the group keeps up,
        #but maintains the same group of positions.
        if len(self.groups_dcm.keys()) < len(groups_dcm_.keys()):
            self.groups_dcm = groups_dcm_


    def __Info(self):
        """
        This INFO is used in InVesalius 2 to learn the
        characteristics of the test. Add a list at the end
        of each series.
        """
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

        for x in xrange(len(self.groups_dcm.keys())):

            key = self.groups_dcm.keys()[x]

            file = self.groups_dcm[key][0][0][8]

            self.parser.SetFileName(file)

            acquisition_date = self.parser.GetAcquisitionDate()
            acquisition_gantry_tilt = self.parser.GetAcquisitionGantryTilt()
            acquisition_number = self.parser.GetAcquisitionNumber()
            acquision_sequence = self.parser.GetAcquisionSequence()
            acquisition_time = self.parser.GetAcquisitionTime()
            equipment_kvp = self.parser.GetEquipmentKVP()
            equipment_institution_name = self.parser.GetEquipmentInstitutionName()
            equipment_manufacturer = self.parser.GetEquipmentManufacturer()
            equipmentxraytubecurrent = self.parser.GetEquipmentXRayTubeCurrent()
            image_column_orientation = self.parser.GetImageColumnOrientation()
            image_convolution_kernel = self.parser.GetImageConvolutionKernel()
            image_data_type = self.parser.GetImageDataType()
            image_location = self.parser.GetImageLocation()
            image_number = self.parser.GetImageNumber()
            image_pixel_spacing_x = self.parser.GetImagePixelSpacingX()
            image_pixel_spacing_y = self.parser.GetImagePixelSpacingY()
            image_position = self.parser.GetImagePosition()
            image_row_orientation = self.parser.GetImageRowOrientation()
            image_samples_perpixel = self.parser.GetImageSamplesPerPixel()
            image_series_number = self.parser.GetImageSeriesNumber()
            image_thickness = self.parser.GetImageThickness()
            image_window_level = self.parser.GetImageWindowLevel()
            image_windowWidth = self.parser.GetImageWindowWidth()
            patient_age = self.parser.GetPatientAge()
            patient_birth_date = self.parser.GetPatientBirthDate()
            patient_gender = self.parser.GetPatientGender()
            patient_name = self.parser.GetPatientName()
            study_id = self.parser.GetStudyID()
            study_instance_UID = self.parser.GetStudyInstanceUID()
            study_admitting_diagnosis = self.parser.GetStudyAdmittingDiagnosis()
            image_dimension = (self.parser.GetDimensionX(), self.parser.GetDimensionY())

            if (len(self.groups_dcm[key][0]) > 1 ):
                #Catch a slice of middle and the next to find the spacing.
                center = len(self.groups_dcm[key][0])/2
                if (center == 1):
                    center = 0
                current_position = self.groups_dcm[key][0][center][3]
                next_position = self.groups_dcm[key][0][center + 1][3]

                try:
                    image_orientation_label = self.groups_dcm.keys()[x][3]
                except(IndexError):
                    image_orientation_label = None

                if(image_orientation_label == "SAGITTAL"):
                    spacing = current_position[0] - next_position[0]
                elif(image_orientation_label == "CORONAL"):
                    spacing = current_position[1] - next_position[1]
                else:
                    spacing = current_position[2] - next_position[2]

                spacing = abs(spacing)

            else:
                spacing = None

            info = [acquisition_date, acquisition_gantry_tilt, acquisition_number,
                    acquision_sequence, acquisition_time, equipment_kvp,
                    equipment_institution_name, equipment_manufacturer,
                    equipmentxraytubecurrent, image_column_orientation,
                    image_convolution_kernel, image_data_type, image_location,
                    image_number, image_pixel_spacing_x, image_pixel_spacing_y,
                    image_position, image_row_orientation, image_samples_perpixel,
                    image_series_number, image_thickness, image_window_level,
                    image_windowWidth,patient_age, patient_birth_date,patient_gender,
                    patient_name, study_id, study_instance_UID, study_admitting_diagnosis,
                    spacing, image_dimension]

            self.groups_dcm[key].append(info)
