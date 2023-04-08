import gdcm
import invesalius.utils as utils

class DicomNet:
    
    def __init__(self) -> None:
        self.address: Literal[''] = ''
        self.port: Literal[''] = ''
        self.aetitle_call: Literal[''] = ''
        self.aetitle: Literal[''] = ''
        self.search_word: Literal[''] = ''
        self.search_type = 'patient'

    def __call__(self) -> Self:
        return self
   
    def SetHost(self, address) -> None:
        self.address = address

    def SetPort(self, port) -> None:
        self.port = port

    def SetAETitleCall(self, name) -> None:
        self.aetitle_call = name

    def SetAETitle(self, ae_title) -> None:
        self.aetitle = ae_title

    def SetSearchWord(self, word) -> None:
        self.search_word = word

    def SetSearchType(self, stype) -> None:
        self.search_type = stype

    def GetValueFromDICOM(self, ret, tag) -> str:
        value = str(ret.GetDataElement(gdcm.Tag(tag[0],\
                                        tag[1])).GetValue())
        if value == 'None' and tag != (0x0008,0x103E):
            value: Literal[''] = ''
        return value


    def RunCEcho(self):
        cnf = gdcm.CompositeNetworkFunctions()
        return cnf.CEcho(self.address, int(self.port),\
                         self.aetitle, self.aetitle_call)

    def RunCFind(self)-> dict:

        tags = [(0x0010, 0x0010), (0x0010, 0x1010), (0x0010,0x0040), (0x0008,0x1030),\
                (0x0008,0x0060), (0x0008,0x0022), (0x0008,0x0080), (0x0010,0x0030),\
                (0x0008,0x0050), (0x0008,0x0090), (0x0008,0x103E), (0x0008,0x0033),\
                (0x0008,0x0032), (0x0020,0x000d)]


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

                name: str = self.GetValueFromDICOM(rt, (0x0010, 0x0010))
                age: str = self.GetValueFromDICOM(rt, (0x0010, 0x1010))
                gender: str = self.GetValueFromDICOM(rt, (0x0010,0x0040))
                study_description: str = self.GetValueFromDICOM(rt, (0x0008,0x1030))
                modality: str = self.GetValueFromDICOM(rt, (0x0008,0x0060))
                institution: str = self.GetValueFromDICOM(rt, (0x0008,0x0080))
                date_of_birth: str = utils.format_date(self.GetValueFromDICOM(rt, (0x0010,0x0030)))
                acession_number: str = self.GetValueFromDICOM(rt, (0x0008,0x0050))
                ref_physician: str = self.GetValueFromDICOM(rt, (0x0008,0x0090))
                serie_description: str = self.GetValueFromDICOM(rt, (0x0008,0x103E))
                acquisition_time = utils.format_time(self.GetValueFromDICOM(rt, (0x0008,0x0032)))
                acquisition_date: str = utils.format_date(self.GetValueFromDICOM(rt, (0x0008,0x0022)))

                teste = self.GetValueFromDICOM(rt, (0x0020,0x000d))

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


    def RunCMove(self, values) -> None:

        ds = gdcm.DataSet()

        #for v in values:


        tg_patient = gdcm.Tag(0x0010, 0x0020)
        tg_serie = gdcm.Tag(0x0020, 0x000e)

        de_patient = gdcm.DataElement(tg_patient)
        de_serie = gdcm.DataElement(tg_serie)

        patient_id = str(values[0])        
        serie_id = str(values[1])

        de_patient.SetByteValue(patient_id,  gdcm.VL(len(patient_id)))
        de_serie.SetByteValue(serie_id, gdcm.VL(len(serie_id)))

        ds.Insert(de_patient)
        ds.Insert(de_serie)


        cnf = gdcm.CompositeNetworkFunctions()
        theQuery = cnf.ConstructQuery(gdcm.ePatientRootType, gdcm.eImageOrFrame, ds)
        #ret = gdcm.DataSetArrayType()

        """
        CMove (const char *remote, 
        uint16_t portno, 
        const BaseRootQuery *query, 

        uint16_t portscp, 
        const char *aetitle=NULL, 
        const char *call=NULL, 
        const char *outputdir=NULL)"""

        print(">>>>>", self.address, int(self.port), theQuery, 11112, self.aetitle,
                  self.aetitle_call, "/home/phamorim/Desktop/output/")


        cnf.CMove(self.address, int(self.port), theQuery, 11112, self.aetitle,\
                  self.aetitle_call, "/home/phamorim/Desktop/")

        print("BAIXOUUUUUUUU")
        #ret = gdcm.DataSetArrayType()

        #cnf.CFind(self.address, int(self.port), theQuery, ret, self.aetitle,\
        #          self.aetitle_call)

        #print "aetitle",self.aetitle
        #print "call",self.aetitle_call
        #print "Baixados..........."


        #for r in ret:
        #    print r
        #    print "\n"
