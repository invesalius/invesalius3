import gdcm

class DicomNet:
    
    def __init__(self):
        self.address = ''
        self.port = ''
        self.aetitle_call = ''
        self.aetitle = ''
        self.search_word = ''
        self.search_type = 'patient'

    def __call__(self):
        return self
   
    def SetHost(self, address):
        self.address = address

    def SetPort(self, port):
        self.port = port

    def SetAETitleCall(self, name):
        self.aetitle_call = name

    def SetAETitle(self, ae_title):
        self.aetitle = ae_title

    def SetSearchWord(self, word):
        self.search_word = word

    def SetSearchType(self, stype):
        self.search_type = stype

    def GetValueFromDICOM(self, ret, tag):
        value = str(ret.GetDataElement(gdcm.Tag(tag[0],\
                                        tag[1])).GetValue())
        return value


    def RunCEcho(self):
        cnf = gdcm.CompositeNetworkFunctions()
        return cnf.CEcho(self.address, int(self.port),\
                         self.aetitle, self.aetitle_call)

    def RunCFind(self):

        tags = [(0x0010, 0x0010), (0x0010, 0x1010), (0x0010,0x0040), (0x0008,0x1030),\
                (0x0008,0x0060), (0x0008,0x0022), (0x0008,0x0080), (0x0010,0x0030),\
                (0x0008,0x0050), (0x0008,0x0090)]


        ds = gdcm.DataSet()

        for tag in tags:

            bit_size = len(self.search_word) + 1

            tg = gdcm.Tag(tag[0], tag[1])

            de = gdcm.DataElement(tg)

            if self.search_type == 'patient':
                de.SetByteValue(str(self.search_word + '*'), gdcm.VL(bit_size))
            else:
                de.SetByteValue('*', gdcm.VL(1))

            ds.Insert(de)


        cnf = gdcm.CompositeNetworkFunctions()
        theQuery = cnf.ConstructQuery(gdcm.ePatientRootType, gdcm.eImageOrFrame, ds)
        ret = gdcm.DataSetArrayType()

        cnf.CFind(self.address, int(self.port), theQuery, ret, self.aetitle,\
                  self.aetitle_call)

        patients = {}

        exist_images = False
        c = 0
        for i in range(0,ret.size()):
            patient_id = str(ret[i].GetDataElement(gdcm.Tag(0x0010, 0x0020)).GetValue())
            serie_id = str(ret[i].GetDataElement(gdcm.Tag(0x0020, 0x000e)).GetValue())

            if not(patient_id in patients.keys()):
                patients[patient_id] = {}
            
                
            if not(serie_id in patients[patient_id]):
        
                rt = ret[i]

                
                name = self.GetValueFromDICOM(rt, ((0x0010, 0x0010)))
                age = self.GetValueFromDICOM(rt, ((0x0010, 0x1010)))
                gender = self.GetValueFromDICOM(rt, ((0x0010),(0x0040)))
                study_description = self.GetValueFromDICOM(rt, ((0x0008),(0x1030)))
                modality = self.GetValueFromDICOM(rt, ((0x0008),(0x0060)))
                date_acquisition = self.GetValueFromDICOM(rt, ((0x0008),(0x0022)))
                institution = self.GetValueFromDICOM(rt, ((0x0008),(0x0080)))
                date_of_birth = self.GetValueFromDICOM(rt, ((0x0010),(0x0030)))
                acession_number = self.GetValueFromDICOM(rt, ((0x0008),(0x0050)))
                ref_physician = self.GetValueFromDICOM(rt, ((0x0008),(0x0090)))

                patients[patient_id][serie_id] = {'name':name, 'age':age, 'gender':gender,\
                                                  'study_description':study_description,\
                                                  'modality':modality, \
                                                  'date_acquision':date_acquisition,\
                                                  'institution':institution,\
                                                  'date_of_birth':date_of_birth,\
                                                  'acession_number':acession_number,\
                                                  'ref_physician':ref_physician}

                patients[patient_id][serie_id]['n_images'] = 1
            else:
                patients[patient_id][serie_id]['n_images'] += 1 

