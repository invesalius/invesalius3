from pynetdicom.sop_class import (PatientRootQueryRetrieveInformationModelFind,
                                  PatientRootQueryRetrieveInformationModelMove)
from pydicom.dataset import Dataset
import invesalius.utils as utils
import pynetdicom
import gdcm


class DicomNet:

    def __init__(self):
        self.address = ''
        self.port = ''
        self.ip_call = ''
        self.aetitle_call = ''
        self.port_call = ''
        self.aetitle = ''
        self.search_word = ''
        self.search_type = 'patient'

    def __call__(self):
        return self

    def SetHost(self, address):
        self.address = address

    def SetPort(self, port):
        self.port = port

    def SetPortCall(self, port):
        self.port_call = port

    def SetAETitleCall(self, name):
        self.aetitle_call = name

    def SetAETitle(self, ae_title):
        self.aetitle = ae_title

    def SetIPCall(self, ip):
        self.ip_call = ip

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

            print("Unexpected error:", e)
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

            response = assoc.send_c_find(
                ds, PatientRootQueryRetrieveInformationModelFind)
            for (status, identifier) in response:

                if status and status.Status in (0xFF00, 0xFF01):

                    patient_id = identifier.get('PatientID', None)
                    serie_id = identifier.get('SeriesInstanceUID', None)

                    if not patient_id or not serie_id:

                        continue

                    if not (patient_id in patients.keys()):
                        patients[patient_id] = {}

                    if not (serie_id in patients[patient_id]):

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

                        patients[patient_id][serie_id] = {'name': name, 'age': age, 'gender': gender,
                                                          'study_description': study_description,
                                                          'modality': modality,
                                                          'acquisition_time': acquisition_time,
                                                          'acquisition_date': acquisition_date,
                                                          'institution': institution,
                                                          'date_of_birth': date_of_birth,
                                                          'acession_number': acession_number,
                                                          'ref_physician': ref_physician,
                                                          'serie_description': serie_description}

                        patients[patient_id][serie_id]['n_images'] = 1

                    else:

                        patients[patient_id][serie_id]['n_images'] += 1

            assoc.release()
            return patients

        return False

    def RunCMove(self, values, progress_callback):
        """ Run CMove to download the DICOM files. """

        def handle_store(event):
            """Handle a C-MOVE request event."""

            ds = event.dataset
            ds.file_meta = event.file_meta

            dest = values['destination'].joinpath(
                f'{ds.SOPInstanceUID}.dcm')
            ds.save_as(dest, write_like_original=False)

            return 0x0000

        ae = pynetdicom.AE()
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelMove)
        ae.supported_contexts = pynetdicom.StoragePresentationContexts

        handlers = [(pynetdicom.evt.EVT_C_STORE, handle_store)]

        ds = Dataset()
        ds.QueryRetrieveLevel = 'SERIES'
        ds.PatientID = values['patient_id']
        ds.SeriesInstanceUID = values['serie_id']

        assoc = ae.associate(self.address, int(
            self.port), ae_title=self.aetitle)
        if assoc.is_established:

            scp = ae.start_server(
                (self.ip_call, int(self.port_call)), block=False, evt_handlers=handlers)

            total_responses = values['n_images']
            completed_responses = 0
            progress_callback(completed_responses, total_responses)
            try:

                responses = assoc.send_c_move(
                    ds, self.aetitle_call, PatientRootQueryRetrieveInformationModelMove)
                for (status, identifier) in responses:

                    if status and status.Status in (0xFF00, 0x0000):

                        completed_responses += 1
                        progress_callback(completed_responses, total_responses)

                    else:

                        raise RuntimeError(
                            'C-MOVE failed with status: 0x{0:04x}'.format(status.Status))

            except Exception as e:

                raise e

            finally:

                assoc.release()
                scp.shutdown()

        else:

            raise RuntimeError(
                'Association rejected, aborted or never connected')

    def __str__(self):

        return "Address: %s\nPort: %s\nAETitle: %s\nAETitleCall: %s\nSearchWord: %s\nSearchType: %s\n" %\
               (self.address, self.port, self.aetitle,
                self.aetitle_call, self.search_word, self.search_type)
