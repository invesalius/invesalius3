from pynetdicom.sop_class import (PatientRootQueryRetrieveInformationModelFind,
                                  PatientRootQueryRetrieveInformationModelMove)
from pydicom.dataset import Dataset
from datetime import datetime
import pynetdicom


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
            assoc = ae.associate(self.address, int(
                self.port), ae_title=self.aetitle)
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

        assoc = ae.associate(self.address, int(
            self.port), ae_title=self.aetitle)
        if not assoc.is_established:

            return False

        patients = {}

        patient_ds = Dataset()
        patient_ds.QueryRetrieveLevel = 'PATIENT'
        patient_ds.PatientName = f'*{self.search_word}*'
        patient_ds.PatientID = ''

        patientsId = []
        response = assoc.send_c_find(
            patient_ds, PatientRootQueryRetrieveInformationModelFind)
        for (patient_status, patient_identifier) in response:

            if patient_status and patient_status.Status in (0xFF00, 0xFF01):

                patientsId.append(patient_identifier.get('PatientID', None))

        for patientId in patientsId:

            patientStudies = {}

            study_ds = Dataset()
            study_ds.QueryRetrieveLevel = 'STUDY'
            study_ds.PatientID = patientId
            study_ds.StudyInstanceUID = ''
            response = assoc.send_c_find(
                study_ds, PatientRootQueryRetrieveInformationModelFind)
            for (status, identifier) in response:

                if status and status.Status in (0xFF00, 0xFF01):

                    if not patientId in patientStudies.keys():
                        patientStudies[patientId] = []

                    patientStudies[patientId].append(
                        identifier.get('StudyInstanceUID', None))

            for study_id in patientStudies[patientId]:

                studySeries = {}

                series_ds = Dataset()
                series_ds.QueryRetrieveLevel = 'SERIES'
                series_ds.PatientID = patientId
                series_ds.StudyInstanceUID = study_id
                series_ds.SeriesInstanceUID = ''
                response = assoc.send_c_find(
                    series_ds, PatientRootQueryRetrieveInformationModelFind)
                for (status, identifier) in response:

                    if status and status.Status in (0xFF00, 0xFF01):

                        if not study_id in studySeries.keys():
                            studySeries[study_id] = []

                        studySeries[study_id].append(
                            identifier.get('SeriesInstanceUID', None))

                for serie_id in studySeries[study_id]:

                    image_ds = Dataset()
                    image_ds.QueryRetrieveLevel = 'IMAGE'
                    image_ds.PatientID = patientId
                    image_ds.StudyInstanceUID = study_id
                    image_ds.SeriesInstanceUID = serie_id
                    image_ds.SOPInstanceUID = ''
                    image_ds.PatientName = ''
                    image_ds.PatientBirthDate = ''
                    image_ds.PatientAge = ''
                    image_ds.PatientSex = ''
                    image_ds.StudyDescription = ''
                    image_ds.InstitutionName = ''
                    image_ds.Modality = ''
                    image_ds.AccessionNumber = ''
                    image_ds.ReferringPhysicianName = ''
                    image_ds.SeriesDescription = ''
                    image_ds.AcquisitionTime = ''
                    image_ds.AcquisitionDate = ''
                    response = assoc.send_c_find(
                        image_ds, PatientRootQueryRetrieveInformationModelFind)
                    for (status, identifier) in response:

                        if status and status.Status in (0xFF00, 0xFF01):

                            if not (patientId in patients.keys()):
                                patients[patientId] = {}

                            if not (serie_id in patients[patientId]):

                                name = identifier.get('PatientName', None)
                                age = identifier.get(
                                    'PatientAge', None)
                                age = age.rstrip('Y').lstrip(
                                    '0') if age else ''
                                gender = identifier.get('PatientSex', None)
                                study_instance_uid = identifier.get(
                                    'StudyInstanceUID', None)
                                study_description = identifier.get(
                                    'StudyDescription', None)
                                modality = identifier.get('Modality', None)
                                institution = identifier.get(
                                    'InstitutionName', None)
                                date_of_birth = identifier.get(
                                    'PatientBirthDate', None)
                                date_of_birth = self._date_format(
                                    date_of_birth) if date_of_birth else ''
                                acession_number = identifier.get(
                                    'AccessionNumber', None)
                                ref_physician = identifier.get(
                                    'ReferringPhysicianName', None)
                                serie_description = identifier.get(
                                    'SeriesDescription', None)
                                acquisition_time = identifier.get(
                                    'AcquisitionTime', None)
                                acquisition_time = self._time_format(
                                    acquisition_time) if acquisition_time else ''
                                acquisition_date = identifier.get(
                                    'AcquisitionDate', None)
                                acquisition_date = self._date_format(
                                    acquisition_date) if acquisition_date else ''

                                patients[patientId][serie_id] = {'name': name, 'age': age, 'gender': gender,
                                                                 'study_id': study_instance_uid,
                                                                 'study_description': study_description,
                                                                 'modality': modality,
                                                                 'acquisition_time': acquisition_time,
                                                                 'acquisition_date': acquisition_date,
                                                                 'institution': institution,
                                                                 'date_of_birth': date_of_birth,
                                                                 'acession_number': acession_number,
                                                                 'ref_physician': ref_physician,
                                                                 'serie_description': serie_description, 'n_images': 1}

                            else:

                                patients[patientId][serie_id]['n_images'] += 1

                    break

                break

        assoc.release()
        return patients

    def RunCMove(self, values, progress_callback):
        """ Run CMove to download the DICOM files. """

        completed_responses = 0

        def handle_store(event):
            """Handle a C-MOVE request event."""

            nonlocal completed_responses

            ds = event.dataset
            ds.file_meta = event.file_meta

            dest = values['destination'].joinpath(
                f'{ds.SOPInstanceUID}.dcm')
            ds.save_as(dest, write_like_original=False)

            completed_responses += 1

            return 0x0000

        ae = pynetdicom.AE()
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelMove)
        ae.supported_contexts = pynetdicom.StoragePresentationContexts

        handlers = [(pynetdicom.evt.EVT_C_STORE, handle_store)]

        ds = Dataset()
        ds.QueryRetrieveLevel = 'SERIES'
        ds.PatientID = values['patient_id']
        ds.StudyInstanceUID = values['study_id']
        ds.SeriesInstanceUID = values['serie_id']

        assoc = ae.associate(self.address, int(
            self.port), ae_title=self.aetitle)
        if assoc.is_established:

            scp = ae.start_server(
                (self.ip_call, int(self.port_call)), ae_title=self.aetitle_call, block=False, evt_handlers=handlers)
            total_responses = values['n_images']
            progress_callback(completed_responses, total_responses)
            try:

                responses = assoc.send_c_move(
                    ds, self.aetitle_call, PatientRootQueryRetrieveInformationModelMove)
                for (status, identifier) in responses:

                    # pending status, keep moving and updating progress
                    if status and status.Status in (0xFF00, 0xFF01):

                        progress_callback(completed_responses, total_responses)

                    # completed case, subtract 1 to avoid reaches 100% and get stuck
                    elif status and status.Status == 0x0000:

                        progress_callback(
                            completed_responses - 1, total_responses)
                        break

                    # there is no status or it returned an error
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

    def _date_format(self, date):

        date = date.split('.')[0] if '.' in date else date
        date = datetime.strptime(date, '%Y%m%d').strftime('%d/%m/%Y')
        return date

    def _time_format(self, time):

        time = time.split('.')[0] if '.' in time else time
        time = datetime.strptime(time, '%H%M%S').strftime('%H:%M:%S')
        return time
