import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import gdcm
import wx
from pydicom.dataset import Dataset
from pynetdicom import (
    AE,
    AllStoragePresentationContexts,
    StoragePresentationContexts,
    build_role,
    debug_logger,
    evt,
)
from pynetdicom.sop_class import (
    CTImageStorage,
    PatientRootQueryRetrieveInformationModelFind,
    PatientRootQueryRetrieveInformationModelGet,
    PatientRootQueryRetrieveInformationModelMove,
    Verification,
)

import invesalius.utils as utils

# debug_logger()


class DicomNet:
    def __init__(self, address: str, port: int, aetitle: str, aetitle_call: str = "INVESALIUS"):
        self.SetAddress(address)
        self.SetPort(port)
        self.SetAETitleCall(aetitle_call)
        self.SetAETitle(aetitle)
        self.server_aetitle = ""
        self.ip_call = ''
        self.port_call = 0
        self.store_path = ""
        self.search_word = ""
        self.search_type = "patient"
        self._executor = ThreadPoolExecutor(max_workers=os.cpu_count())

    def __call__(self):
        return self

    def SetAddress(self, address: str):
        self.address = address

    def SetPort(self, port: int):
        self.port = port

    def SetAETitleCall(self, name: str):
        self.aetitle_call = name

    def SetAETitle(self, ae_title: str):
        self.aetitle = ae_title

    def SetIPCall(self, ip):
        self.ip_call = ip

    def ServerAETitle(self, server_aetitle: str):
        self.server_aetitle = server_aetitle

    def SetPortCall(self, port: int):
        self.port_call = port

    def SetStorePath(self, path: str):
        self.store_path = path

    def SetSearchWord(self, word: str):
        self.search_word = word

    def SetSearchType(self, stype: str):
        self.search_type = stype

    def GetValueFromDICOM(self, ret, tag):
        value = str(ret.GetDataElement(gdcm.Tag(tag[0], tag[1])).GetValue())
        if value == "None" and tag != (0x0008, 0x103E):
            value = ""
        return value

    # Async Wrappers

    def RunCEcho(self, callback=None):
        def _task():
            try:
                result = self.__RunCEcho()
                if callback:
                    wx.CallAfter(callback, result, None)
            except Exception as e:
                if callback:
                    wx.CallAfter(callback, None, str(e))

        self._executor.submit(_task)

    def RunCFind(self, callback=None):
        def _task():
            try:
                result = self.__RunCFind()
                if callback:
                    wx.CallAfter(callback, result, None)
            except Exception as e:
                if callback:
                    wx.CallAfter(callback, None, str(e))

        self._executor.submit(_task)

    # def RunCGet(self, data, callback=None):
    #     def _task():
    #         result = self.__RunCGet(data)
    #         if callback:
    #             callback(result)

    #     self._executor.submit(_task)

    def RunCMove(self, data, dest, progress_callback, callback=None):
        def _task():
            try:
                result = self.__RunCMove(data, dest, progress_callback)
                if callback:
                    wx.CallAfter(callback, dest, result, None)
            except Exception as e:
                if callback:
                    wx.CallAfter(callback, dest, None, str(e))

        self._executor.submit(_task)

    # Sync Methods

    def __RunCEcho(self):
        """run CEcho to check if the server is alive."""

        try:
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

    def __RunCFind(self):
        ae = AE(self.aetitle_call)
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelFind)

        assoc = ae.associate(self.address, self.port, ae_title=self.aetitle)
        if not assoc.is_established:
            return False

        patients = {}

        #Patient Level
        patient_ds = Dataset()
        patient_ds.QueryRetrieveLevel = "PATIENT"
        patient_ds.PatientName = f"*{self.search_word}*"
        patient_ds.PatientID = ""

        patient_response = assoc.send_c_find(
            patient_ds, PatientRootQueryRetrieveInformationModelFind
        )
        for patient_status, patient_identifier in patient_response:
            if patient_status and patient_status.Status in (0xFF00, 0xFF01):
                patient_id = patient_identifier.get("PatientID")
                if not patient_id:
                    continue
                if patient_id not in patients:
                    patients[patient_id] = {}
        
        #Study Level
        for patientId in patients.keys():
            study_ds = Dataset()
            study_ds.QueryRetrieveLevel = "STUDY"
            study_ds.PatientID = patientId
            study_ds.StudyInstanceUID = ""
            study_response = assoc.send_c_find(
                study_ds, PatientRootQueryRetrieveInformationModelFind
            )
            for study_status, study_identifier in study_response:
                if study_status and study_status.Status in (0xFF00, 0xFF01):
                    study_uid = study_identifier.get("StudyInstanceUID")
                    if study_uid:
                        patients[patientId][study_uid] = {}
            
            #Series Level
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
                        series_uid = series_identifier.get("SeriesInstanceUID")
                        if series_uid:
                            patients[patientId][study_id][series_uid] = {
                                "name": "",
                                "age": "",
                                "gender": "",
                                "study_id": study_id,
                                "study_description": "",
                                "modality": "",
                                "acquisition_time": "",
                                "acquisition_date": "",
                                "institution": "",
                                "date_of_birth": "",
                                "acession_number": "",
                                "ref_physician": "",
                                "serie_description": "",
                                "n_images": 0, 
                                "image_uids": []
                            }

                # IMAGE level
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
                    
                    image_response = assoc.send_c_find(image_ds, PatientRootQueryRetrieveInformationModelFind)
                    first_image = True

                    for image_status, image_identifier in image_response:
                        if image_status and image_status.Status in (0xFF00, 0xFF01):
                            if first_image:
                                patients[patientId][study_id][serie_id] = {
                                    "name": image_identifier.get("PatientName", ""),
                                    "age": self._format_age(image_identifier.get("PatientAge", "")),
                                    "gender": image_identifier.get("PatientSex", ""),
                                    "study_id": image_identifier.get("StudyInstanceUID", study_id),
                                    "study_description": image_identifier.get("StudyDescription", ""),
                                    "modality": image_identifier.get("Modality", ""),
                                    "acquisition_time": self._time_format(image_identifier.get("AcquisitionTime", "")),
                                    "acquisition_date": self._date_format(image_identifier.get("AcquisitionDate", "")),
                                    "institution": image_identifier.get("InstitutionName", ""),
                                    "date_of_birth": self._date_format(image_identifier.get("PatientBirthDate", "")),
                                    "acession_number": image_identifier.get("AccessionNumber", ""),
                                    "ref_physician": image_identifier.get("ReferringPhysicianName", ""),
                                    "serie_description": image_identifier.get("SeriesDescription", ""),
                                    "n_images": 0,
                                    "image_uids": []
                                }
                                first_image = False
                            
                            # Increment image count and store UID
                            patients[patientId][study_id][serie_id]["n_images"] += 1
                            sop_uid = image_identifier.get("SOPInstanceUID")
                            if sop_uid:
                                patients[patientId][study_id][serie_id]["image_uids"].append(sop_uid)

        assoc.release()
        return patients

    def RunCGet(
        self,
        QueryRetrieveLevel,
        PatientID,
        StudyInstanceUID,
        SeriesInstanceUID,
        SOPInstanceUID,
        directory="../Data/",
    ):
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

        assoc = ae.associate(
            self.address, self.port, ext_neg=[role], evt_handlers=handlers, ae_title=self.aetitle
        )

        # Use the C-GET service to send the identifier
        responses = assoc.send_c_get(ds, PatientRootQueryRetrieveInformationModelGet)
        for status, identifier in responses:
            if status:
                print(f"C-GET query status: 0x{status.Status:04x}")
            else:
                print("Connection timed out, was aborted or received invalid response")

        if assoc and assoc.is_established:
            assoc.release()

    def __RunCMove(self, data, dest, progress_callback):
        
        handlers = [(evt.EVT_C_STORE, self._handle_store)]
        self._current_dest = dest

        ae = AE(ae_title=self.aetitle_call)
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelMove)
        ae.supported_contexts = StoragePresentationContexts

        scp = ae.start_server((self.ip_call, int(self.port_call)), block=False, evt_handlers=handlers)

        ds = Dataset()
        ds.PatientID = data.get("patient", "")
        ds.StudyInstanceUID = data.get("study", "")
        ds.SeriesInstanceUID = data.get("series", "")
        ds.QueryRetrieveLevel = data["type"]

        assoc = ae.associate(self.address, self.port, ae_title=self.aetitle)

        if not assoc.is_established:
            scp.shutdown()
            raise RuntimeError("Failed to establish association")

        total_images = data.get('n_images', 0)
        completed = 0
        
        try:
            wx.CallAfter(progress_callback, 0, total_images)

            responses = assoc.send_c_move(
                ds, self.server_aetitle, PatientRootQueryRetrieveInformationModelMove
            )
            
            for status, identifier in responses:
                if status and status.Status in (0xFF00, 0xFF01):
                    completed += 1
                    wx.CallAfter(progress_callback, completed, total_images)
                elif status and status.Status == 0x0000:
                        break
                else:
                    raise RuntimeError('C-MOVE failed with status: 0x{0:04x}'.format(status.Status))
        
        except Exception as e:
            raise e
        
        finally:
            assoc.release()
            scp.shutdown()
        
    def _handle_store(self, event):

        try:
            ds = event.dataset
            ds.file_meta = event.file_meta

            dest = self._current_dest
            
            if not os.path.exists(dest):
                os.makedirs(dest)

            filename = os.path.join(dest, f'{ds.SOPInstanceUID}.dcm')

            ds.save_as(filename, write_like_original=False)
            
            return 0x0000
        
        except Exception as e:
            print(f"Error in _handle_store: {e}")
            return 0xC001

    def _date_format(self, date):
        date = date.split(".")[0] if "." in date else date
        date = datetime.strptime(date, "%Y%m%d").strftime("%d/%m/%Y")
        return date

    def _time_format(self, time):
        time = time.split(".")[0] if "." in time else time
        time = datetime.strptime(time, "%H%M%S").strftime("%H:%M:%S")
        return time


    def _format_age(self, age):
        if not age:
            return ""
        return age.rstrip("Y").lstrip("0")

    def __str__(self):
        return (
            "Address: %s\nPort: %s\nAETitle: %s\nAETitleCall: %s\nSearchWord: %s\nSearchType: %s\n"
            % (
                self.address,
                self.port,
                self.aetitle,
                self.aetitle_call,
                self.search_word,
                self.search_type,
            )
        )
