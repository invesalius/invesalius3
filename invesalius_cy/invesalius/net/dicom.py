import gdcm

import invesalius.utils as utils


class DicomNet:
    def __init__(self):
        self.address = ""
        self.port = ""
        self.aetitle_call = ""
        self.aetitle = ""
        self.search_word = ""
        self.search_type = "patient"

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
        value = str(ret.GetDataElement(gdcm.Tag(tag[0], tag[1])).GetValue())
        if value == "None" and tag != (0x0008, 0x103E):
            value = ""
        return value

    def RunCEcho(self):
        cnf = gdcm.CompositeNetworkFunctions()
        return cnf.CEcho(self.address, int(self.port), self.aetitle, self.aetitle_call)

    def RunCFind(self):
        tags = [
            (0x0010, 0x0010),
            (0x0010, 0x1010),
            (0x0010, 0x0040),
            (0x0008, 0x1030),
            (0x0008, 0x0060),
            (0x0008, 0x0022),
            (0x0008, 0x0080),
            (0x0010, 0x0030),
            (0x0008, 0x0050),
            (0x0008, 0x0090),
            (0x0008, 0x103E),
            (0x0008, 0x0033),
            (0x0008, 0x0032),
            (0x0020, 0x000D),
        ]

        ds = gdcm.DataSet()

        for tag in tags:
            tg = gdcm.Tag(tag[0], tag[1])

            de = gdcm.DataElement(tg)

            if self.search_type == "patient" and tag == (0x0010, 0x0010):
                bit_size = len(self.search_word) + 1
                de.SetByteValue(str(self.search_word + "*"), gdcm.VL(bit_size))
            else:
                de.SetByteValue("*", gdcm.VL(1))

            ds.Insert(de)

        cnf = gdcm.CompositeNetworkFunctions()
        theQuery = cnf.ConstructQuery(gdcm.ePatientRootType, gdcm.eImageOrFrame, ds)
        ret = gdcm.DataSetArrayType()

        cnf.CFind(self.address, int(self.port), theQuery, ret, self.aetitle, self.aetitle_call)

        patients = {}

        exist_images = False
        c = 0
        for i in range(0, ret.size()):
            patient_id = str(ret[i].GetDataElement(gdcm.Tag(0x0010, 0x0020)).GetValue())
            serie_id = str(ret[i].GetDataElement(gdcm.Tag(0x0020, 0x000E)).GetValue())

            if not (patient_id in patients.keys()):
                patients[patient_id] = {}

            if not (serie_id in patients[patient_id]):
                rt = ret[i]

                name = self.GetValueFromDICOM(rt, (0x0010, 0x0010))
                age = self.GetValueFromDICOM(rt, (0x0010, 0x1010))
                gender = self.GetValueFromDICOM(rt, (0x0010, 0x0040))
                study_description = self.GetValueFromDICOM(rt, (0x0008, 0x1030))
                modality = self.GetValueFromDICOM(rt, (0x0008, 0x0060))
                institution = self.GetValueFromDICOM(rt, (0x0008, 0x0080))
                date_of_birth = utils.format_date(self.GetValueFromDICOM(rt, (0x0010, 0x0030)))
                acession_number = self.GetValueFromDICOM(rt, (0x0008, 0x0050))
                ref_physician = self.GetValueFromDICOM(rt, (0x0008, 0x0090))
                serie_description = self.GetValueFromDICOM(rt, (0x0008, 0x103E))
                acquisition_time = utils.format_time(self.GetValueFromDICOM(rt, (0x0008, 0x0032)))
                acquisition_date = utils.format_date(self.GetValueFromDICOM(rt, (0x0008, 0x0022)))

                teste = self.GetValueFromDICOM(rt, (0x0020, 0x000D))

                patients[patient_id][serie_id] = {
                    "name": name,
                    "age": age,
                    "gender": gender,
                    "study_description": study_description,
                    "modality": modality,
                    "acquisition_time": acquisition_time,
                    "acquisition_date": acquisition_date,
                    "institution": institution,
                    "date_of_birth": date_of_birth,
                    "acession_number": acession_number,
                    "ref_physician": ref_physician,
                    "serie_description": serie_description,
                }

                patients[patient_id][serie_id]["n_images"] = 1
            else:
                patients[patient_id][serie_id]["n_images"] += 1

        return patients

    def RunCMove(self, values):
        ds = gdcm.DataSet()

        # for v in values:

        tg_patient = gdcm.Tag(0x0010, 0x0020)
        tg_serie = gdcm.Tag(0x0020, 0x000E)

        de_patient = gdcm.DataElement(tg_patient)
        de_serie = gdcm.DataElement(tg_serie)

        patient_id = str(values[0])
        serie_id = str(values[1])

        de_patient.SetByteValue(patient_id, gdcm.VL(len(patient_id)))
        de_serie.SetByteValue(serie_id, gdcm.VL(len(serie_id)))

        ds.Insert(de_patient)
        ds.Insert(de_serie)

        cnf = gdcm.CompositeNetworkFunctions()
        theQuery = cnf.ConstructQuery(gdcm.ePatientRootType, gdcm.eImageOrFrame, ds)
        # ret = gdcm.DataSetArrayType()

        """
        CMove (const char *remote, 
        uint16_t portno, 
        const BaseRootQuery *query, 

        uint16_t portscp, 
        const char *aetitle=NULL, 
        const char *call=NULL, 
        const char *outputdir=NULL)"""

        print(
            ">>>>>",
            self.address,
            int(self.port),
            theQuery,
            11112,
            self.aetitle,
            self.aetitle_call,
            "/home/phamorim/Desktop/output/",
        )

        cnf.CMove(
            self.address,
            int(self.port),
            theQuery,
            11112,
            self.aetitle,
            self.aetitle_call,
            "/home/phamorim/Desktop/",
        )

        print("BAIXOUUUUUUUU")
        # ret = gdcm.DataSetArrayType()

        # cnf.CFind(self.address, int(self.port), theQuery, ret, self.aetitle,\
        #          self.aetitle_call)

        # print "aetitle",self.aetitle
        # print "call",self.aetitle_call
        # print "Baixados..........."

        # for r in ret:
        #    print r
        #    print "\n"
