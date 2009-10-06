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

import dicom

class DicomGroups:
    """
    It is possible to separate sets of a set
    of files dicom.

    To use:
    list_dicoms = [c:\a.dcm, c:\a1.gdcm]
    dicom_splitter = DicomGroups()
    dicom_splitter.SetFileList(list_dicoms)
    dicom_splitter.Update()
    splitted = dicom_splitter.GetOutput()
    """

    def __init__(self):
        self.parser = dicom.Parser()
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
            print "Vai entrar na 2"
            self.__Split2()
            self.split_type = 1

        self.__Split3()

        self.__UpdateZSpacing()


    def GetOutput(self):
        """
        Returns a dictionary with groups
        of DICOM.
        """
        return self.groups_dcm

    def GetSplitterType(self):
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

            information = dicom.Dicom()
            information.SetParser(parser)

            self.filelist.append(information)
        self.filelist = filelist
        
        
    def __GetInformations(self, ind):
        """
        Return a list referring to a specific DICOM
        in dictionary. In some cases it is necessary
        to pass only the index
        """
        filelist = self.filelist
        return filelist[ind]


    def __Split1(self):
        """
        Bring together the series under the name of
        the patient, id of the study, serial number
        and label orientation of the image.
        """
        groups_dcm = self.groups_dcm

        for x in xrange(len(self.filelist)):            
            information = self.__GetInformations(x)

            key = (information.patient.name, information.acquisition.id_study,\
                   information.acquisition.serie_number, information.image.orientation_label)

            if (key in groups_dcm.keys()):
                groups_dcm[key][0].append(information)
            else:
                groups_dcm[key] = [[information]]

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
            information = self.__GetInformations(x)
            key = (information.patient.name, cont_series)

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
                        groups_dcm[key][0].append(information)
                    else:
                        groups_dcm[key] = [[information]]
                else:
                    cont_series = cont_series + 1
                    groups_dcm[key] = [[information]]

            else:

                if (cont_series in groups_dcm.keys()):
                    groups_dcm[key].append(information)
                else:
                    groups_dcm[key] = [[information]]

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
                information = groups_dcm[key][0][y]

                #Generate new key to dictionary
                image_pos = information.image.position
                key_ = (image_pos[0], image_pos[1], image_pos[2])

                #Add informations in the list
                list = [information]

                #If list Null, create dictionary
                #and add list with information
                #after add in a temporary list
                if (tmp_list == []):
                    tmp = {}
                    tmp[key_] = information
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
                            (tmp_list[a])[key_] = information
                            flag = 1
                        a = a + 1

                    if (flag == 0):
                        tmp = {}
                        tmp[key_] = information

                        tmp_list.append(tmp)


        #for each item on the list is created
        #a new position in the dictionary.
        size_tmp_list = len(tmp_list)

        for x in xrange(size_tmp_list):

            tmp1 = tmp_list[x]

            for m in xrange(len(tmp1.keys())):

                key = tmp1.keys()[m]
                information = tmp1[key]
                new_key = (information.patient.name, None, x, information.image.orientation_label, information.acquisition.time)


                list = [information]

                if (new_key in groups_dcm_.keys()):
                    groups_dcm_[new_key][0].append(information)
                else:
                    groups_dcm_[new_key] = [[information]]

        #the number of previously existing number is
        #greater or equal then the group keeps up,
        #but maintains the same group of positions.
        if len(self.groups_dcm.keys()) > len(groups_dcm_.keys()):
            self.groups_dcm = groups_dcm_

        for j in xrange(len(self.groups_dcm.keys())):
            key = self.groups_dcm.keys()[j]
            self.groups_dcm[key][0].sort(key=lambda x: x.image.number)


    def __UpdateZSpacing(self):
        """
         Calculate Z spacing from slices
        """

        for x in xrange(len(self.groups_dcm.keys())):

            key = self.groups_dcm.keys()[x]
            information = self.groups_dcm[key][0]
            if (len(self.groups_dcm[key][0]) > 1):
                #Catch a slice of middle and the next to find the spacing.
                center = len(self.groups_dcm[key][0])/2
                if (center == 1):
                    center = 0 

                information = self.groups_dcm[key][0][center]
                current_position = information.image.position

                information = self.groups_dcm[key][0][center + 1]
                next_position = information.image.position

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

            for information in self.groups_dcm[key][0]:
                if information.image.spacing:
                    information.image.spacing[2] = spacing
