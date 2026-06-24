import gdcm
from datetime import datetime
from pydicom.dataset import Dataset
from pynetdicom import AE, debug_logger, evt, build_role, AllStoragePresentationContexts, StoragePresentationContexts
from pynetdicom.sop_class import (
    Verification,
    PatientRootQueryRetrieveInformationModelFind,
    PatientRootQueryRetrieveInformationModelGet,
    PatientRootQueryRetrieveInformationModelMove,
    CTImageStorage,
)
import os
import time

import invesalius.utils as utils

debug_logger()      

class DicomNet:
    def __init__(self, address: str, port: int, aetitle: str, aetitle_call: str="INVESALIUS"):
        self.SetHost(address)
        self.SetPort(port)
        self.SetAETitleCall(aetitle_call)
        self.SetAETitle(aetitle)
        self.search_word = ""
        self.search_type = "patient"
        self.directory = "../Data" 

    def __call__(self):
        return self

    def SetHost(self, address: str):
        self.address = address

    def SetPort(self, port: int):
        self.port = port

    def SetAETitleCall(self, name: str):
        self.aetitle_call = name

    def SetAETitle(self, ae_title: str):
        self.aetitle = ae_title

    def SetSearchWord(self, word: str):
        self.search_word = word

    def SetSearchType(self, stype: str):
        self.search_type = stype

    def GetValueFromDICOM(self, ret, tag):
        value = str(ret.GetDataElement(gdcm.Tag(tag[0], tag[1])).GetValue())
        if value == "None" and tag != (0x0008, 0x103E):
            value = ""
        return value

    def RunCEcho(self):
        """run CEcho to check if the server is alive."""

        try:
            print(self.port, self.address, self.aetitle, "echo")
            ae = AE(self.aetitle_call)
            ae.add_requested_context(Verification)

            assoc = ae.associate(self.address, self.port, ae_title=self.aetitle)

            if not assoc.is_established:
                print(f"C-ECHO: Association failed")
                return False

            status = assoc.send_c_echo()

            if status and status.Status == 0x0000:
                print("C-ECHO: Verification successful")
                assoc.release()
                return True

            else:
                print(f"C-ECHO: Verification failed with status {status}")
                assoc.release()
                return False

        except Exception as e:
            print("Unexpected error:", e)
            return False

    def RunCFind(self):
        ae = AE()
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelFind)

        assoc = ae.associate(self.address, int(self.port), ae_title=self.aetitle)
        if not assoc.is_established:
            return False

        patients = {}

        patient_ds = Dataset()
        patient_ds.QueryRetrieveLevel = "PATIENT"
        patient_ds.PatientName = f"*{self.search_word}*"
        patient_ds.PatientID = ""

        patient_response = assoc.send_c_find(patient_ds, PatientRootQueryRetrieveInformationModelFind)
        for patient_status, patient_identifier in patient_response:
            if patient_status and patient_status.Status in (0xFF00, 0xFF01):
                patient_id = patient_identifier.get("PatientID")
                if not patient_id:
                    continue
                if patient_id not in patients:
                    patients[patient_id] = {}

        for patientId in patients.keys():
            study_ds = Dataset()
            study_ds.QueryRetrieveLevel = "STUDY"
            study_ds.PatientID = patientId
            study_ds.StudyInstanceUID = ""
            study_response = assoc.send_c_find(study_ds, PatientRootQueryRetrieveInformationModelFind)
            for study_status, study_identifier in study_response:
                if study_status and study_status.Status in (0xFF00, 0xFF01):
                    patients[patientId][(study_identifier.get("StudyInstanceUID", None))] = {}

            for study_id in patients[patientId].keys():            
                series_ds = Dataset()
                series_ds.QueryRetrieveLevel = "SERIES"
                series_ds.PatientID = patientId
                series_ds.StudyInstanceUID = study_id
                series_ds.SeriesInstanceUID = ""
                series_response = assoc.send_c_find(
                    series_ds, PatientRootQueryRetrieveInformationModelFind
                )
                for series_status, series_identifier in series_response:
                    if series_status and series_status.Status in (0xFF00, 0xFF01):
                        patients[patientId][study_id][series_identifier.get("SeriesInstanceUID", None)] = {}

                for serie_id in patients[patientId][study_id].keys():
                    image_ds = Dataset()
                    image_ds.QueryRetrieveLevel = "IMAGE"
                    image_ds.PatientID = patientId
                    image_ds.StudyInstanceUID = study_id
                    image_ds.SeriesInstanceUID = serie_id
                    image_ds.SOPInstanceUID = ""
                    image_ds.PatientName = ""
                    image_ds.PatientBirthDate = ""
                    image_ds.PatientAge = ""
                    image_ds.PatientSex = ""
                    image_ds.StudyDescription = ""
                    image_ds.InstitutionName = ""
                    image_ds.Modality = ""
                    image_ds.AccessionNumber = ""
                    image_ds.ReferringPhysicianName = ""
                    image_ds.SeriesDescription = ""
                    image_ds.AcquisitionTime = ""
                    image_ds.AcquisitionDate = ""
                    image_response = assoc.send_c_find(
                        image_ds, PatientRootQueryRetrieveInformationModelFind
                    )
                    for image_status, image_identifier in image_response:
                        if image_status and image_status.Status in (0xFF00, 0xFF01):
                            name = image_identifier.get("PatientName", None)
                            age = image_identifier.get("PatientAge", None)
                            age = age.rstrip("Y").lstrip("0") if age else ""
                            gender = image_identifier.get("PatientSex", None)
                            study_instance_uid = image_identifier.get("StudyInstanceUID", None)
                            study_description = image_identifier.get("StudyDescription", None)
                            modality = image_identifier.get("Modality", None)
                            institution = image_identifier.get("InstitutionName", None)
                            date_of_birth = image_identifier.get("PatientBirthDate", None)
                            date_of_birth = (
                                self._date_format(date_of_birth) if date_of_birth else ""
                            )
                            acession_number = image_identifier.get("AccessionNumber", None)
                            ref_physician = image_identifier.get("ReferringPhysicianName", None)
                            serie_description = image_identifier.get("SeriesDescription", None)
                            acquisition_time = image_identifier.get("AcquisitionTime", None)
                            acquisition_time = (
                                self._time_format(acquisition_time) if acquisition_time else ""
                            )
                            acquisition_date = image_identifier.get("AcquisitionDate", None)
                            acquisition_date = (
                                self._date_format(acquisition_date) if acquisition_date else ""
                            )

                            patients[patientId][study_id][serie_id] = {
                                "name": name,
                                "age": age,
                                "gender": gender,
                                "study_id": study_instance_uid,
                                "study_description": study_description,
                                "modality": modality,
                                "acquisition_time": acquisition_time,
                                "acquisition_date": acquisition_date,
                                "institution": institution,
                                "date_of_birth": date_of_birth,
                                "acession_number": acession_number,
                                "ref_physician": ref_physician,
                                "serie_description": serie_description,
                                "n_images": 1,
                            }
        assoc.release()
        return patients

    def RunCGet(self, QueryRetrieveLevel, PatientID, StudyInstanceUID, SeriesInstanceUID, SOPInstanceUID, directory="../Data/"):
        handlers = [(evt.EVT_C_STORE, self._handle_store)]

        ae = AE(ae_title=self.aetitle_call)

        ae.add_requested_context(PatientRootQueryRetrieveInformationModelGet)
        ae.add_requested_context(CTImageStorage)

        role = build_role(CTImageStorage, scp_role=True)

        ds = Dataset()
        ds.QueryRetrieveLevel = QueryRetrieveLevel
        ds.PatientID = PatientID
        ds.StudyInstanceUID = StudyInstanceUID
        ds.SeriesInstanceUID = SeriesInstanceUID
        ds.SOPInstanceUID = SOPInstanceUID

        assoc = ae.associate(self.address, self.port, ext_neg=[role], evt_handlers=handlers, ae_title=self.aetitle)

        # Use the C-GET service to send the identifier
        responses = assoc.send_c_get(
            ds, PatientRootQueryRetrieveInformationModelGet)
        for (status, identifier) in responses:
            if status:
                print(f"C-GET query status: 0x{status.Status:04x}")
            else:
                print(responses)
                print('Connection timed out, was aborted or received invalid response')

        if assoc and assoc.is_established:
            assoc.release()

    def RunCMove(self, QueryRetrieveLevel, PatientID, StudyInstanceUID, SeriesInstanceUID, SOPInstanceUID, directory="../Data/"):
        handlers = [(evt.EVT_C_STORE, self._handle_store)]

        ae = AE(ae_title=self.aetitle_call)

        ae.add_requested_context(PatientRootQueryRetrieveInformationModelMove)
        ae.supported_contexts = StoragePresentationContexts
        
        scp = ae.start_server(("0.0.0.0", 11120), block=False, evt_handlers=handlers)

        ds = Dataset()
        ds.QueryRetrieveLevel = QueryRetrieveLevel
        ds.PatientID = PatientID
        ds.StudyInstanceUID = StudyInstanceUID
        ds.SeriesInstanceUID = SeriesInstanceUID
        ds.SOPInstanceUID = SOPInstanceUID


        assoc = ae.associate(self.address, self.port, ae_title=self.aetitle)

        responses = assoc.send_c_move(ds, self.aetitle_call, PatientRootQueryRetrieveInformationModelMove)
        for (status, identifier) in responses:
            if status:
                print(f"C-MOVE query status: 0x{status.Status:04x}")
            else:
                print(responses)
                print('Connection timed out, was aborted or received invalid response')

        if assoc and assoc.is_established:
            assoc.release()
        
        scp.shutdown()

    def _handle_store(self, event):
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)
        ds = event.dataset
        ds.file_meta = event.file_meta
        filename = f"{self.directory}/{ds.SOPInstanceUID}.dcm"
        ds.save_as(filename)
        return 0x0000

    def _date_format(self, date):
        date = date.split(".")[0] if "." in date else date
        date = datetime.strptime(date, "%Y%m%d").strftime("%d/%m/%Y")
        return date

    def _time_format(self, time):
        time = time.split(".")[0] if "." in time else time
        time = datetime.strptime(time, "%H%M%S").strftime("%H:%M:%S")
        return time