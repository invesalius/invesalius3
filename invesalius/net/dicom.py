from pynetdicom.sop_class import PatientRootQueryRetrieveInformationModelFind
from pydicom.dataset import Dataset
import invesalius.utils as utils
import pynetdicom
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
        """ Get value from DICOM tag. """

        value = str(ret[tag].value)
        if value == 'None' and tag != (0x0008, 0x103E):
            value = ''

        return value

    def RunCEcho(self):
        """ run CEcho to check if the server is alive. """

        try:

            ae = pynetdicom.AE()
            ae.add_requested_context('1.2.840.10008.1.1')
            assoc = ae.associate(self.address, int(self.port))
            if assoc.is_established:

                assoc.release()
                return True

            return False

        except Exception as e:

            print ("Unexpected error:", e)
            return False

    def RunCFind(self):

        ae = pynetdicom.AE()
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelFind)

        ds = Dataset()
        ds.QueryRetrieveLevel = 'INSTANCE'
        ds.PatientName = self.search_word
        ds.PatientID = ''
        ds.PatientBirthDate = ''
        ds.PatientAge = ''
        ds.PatientSex = ''
        ds.StudyDescription = ''
        ds.InstitutionName = ''
        ds.Modality = ''
        ds.AccessionNumber = ''
        ds.ReferringPhysicianName = ''
        ds.SeriesInstanceUID = ''
        ds.SeriesDescription = ''
        ds.AcquisitionTime = ''
        ds.AcquisitionDate = ''

        assoc = ae.associate(self.address, int(self.port))
        if assoc.is_established:

            patients = {}

            response = assoc.send_c_find(ds, PatientRootQueryRetrieveInformationModelFind)
            for (status, identifier) in response:

                if status and status.Status in (0xFF00, 0xFF01):

                    patient_id = identifier.PatientID
                    serie_id = identifier.SeriesInstanceUID
                    
                    if not(patient_id in patients.keys()):
                        patients[patient_id] = {}
                    
                    if not(serie_id in patients[patient_id]):

                        name = identifier.PatientName
                        age = identifier.PatientAge
                        gender = identifier.PatientSex
                        study_description = identifier.StudyDescription
                        modality = identifier.Modality
                        institution = identifier.InstitutionName
                        date_of_birth = identifier.PatientBirthDate
                        acession_number = identifier.AccessionNumber
                        ref_physician = identifier.ReferringPhysicianName
                        serie_description = identifier.SeriesDescription
                        acquisition_time = identifier.AcquisitionTime
                        acquisition_date = identifier.AcquisitionDate

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

            assoc.release()
            return patients
        
        return False


    def RunCMove(self, values):

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

    def __str__(self):

        return "Address: %s\nPort: %s\nAETitle: %s\nAETitleCall: %s\nSearchWord: %s\nSearchType: %s\n" %\
               (self.address, self.port, self.aetitle, self.aetitle_call, self.search_word, self.search_type)
