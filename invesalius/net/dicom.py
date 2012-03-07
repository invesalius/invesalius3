import gdcm
import utils


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
        if value == 'None' and tag != (0x0008,0x103E):
            value = ''
        return value


    def RunCEcho(self):
        cnf = gdcm.CompositeNetworkFunctions()
        return cnf.CEcho(self.address, int(self.port),\
                         self.aetitle, self.aetitle_call)

    def RunCFind(self):

        tags = [(0x0010, 0x0010), (0x0010, 0x1010), (0x0010,0x0040), (0x0008,0x1030),\
                (0x0008,0x0060), (0x0008,0x0022), (0x0008,0x0080), (0x0010,0x0030),\
                (0x0008,0x0050), (0x0008,0x0090), (0x0008,0x103E), (0x0008,0x0033),\
                (0x0008,0x0032)]


        ds = gdcm.DataSet()

        for tag in tags:


            tg = gdcm.Tag(tag[0], tag[1])

            de = gdcm.DataElement(tg)

            if self.search_type == 'patient' and tag == (0x0010, 0x0010):

                bit_size = len(self.search_word) + 1
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

                name = self.GetValueFromDICOM(rt, (0x0010, 0x0010))
                age = self.GetValueFromDICOM(rt, (0x0010, 0x1010))
                gender = self.GetValueFromDICOM(rt, (0x0010,0x0040))
                study_description = self.GetValueFromDICOM(rt, (0x0008,0x1030))
                modality = self.GetValueFromDICOM(rt, (0x0008,0x0060))
                institution = self.GetValueFromDICOM(rt, (0x0008,0x0080))
                date_of_birth = utils.format_date(self.GetValueFromDICOM(rt, (0x0010,0x0030)))
                acession_number = self.GetValueFromDICOM(rt, (0x0008,0x0050))
                ref_physician = self.GetValueFromDICOM(rt, (0x0008,0x0090))
                serie_description = self.GetValueFromDICOM(rt, (0x0008,0x103E))
                acquisition_time = utils.format_time(self.GetValueFromDICOM(rt, (0x0008,0x0032)))
                acquisition_date = utils.format_date(self.GetValueFromDICOM(rt, (0x0008,0x0022)))

                patients[patient_id][serie_id] = {'name':name, 'age':age, 'gender':gender,\
                                                  'study_description':study_description,\
                                                  'modality':modality, \
                                                  'acquisition_time':acquisition_time,\
                                                  'acquisition_date':acquisition_date,\
                                                  'institution':institution,\
                                                  'date_of_birth':date_of_birth,\
                                                  'acession_number':acession_number,\
                                                  'ref_physician':ref_physician,\
                                                  'serie_description':serie_description}

                patients[patient_id][serie_id]['n_images'] = 1
            else:
                patients[patient_id][serie_id]['n_images'] += 1 

        return patients 
