import time
import csv
import os
from dataclasses import dataclass, field
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from pydicom.dataset import Dataset
from pydicom import dcmread
from pynetdicom import AE, StoragePresentationContexts


@dataclass
class CStore:
    """
    Used to Upload DICOM Files to Remote PACS Server
    TODO: Use Chunking Concept to Upload Large Files
    TODO: Need to handle uploading large number of files
    TODO: Add Custom Compressor Handler for JPEG Files/DICOM Files before Upload
    TODO: Add FPS Custom Handler for MP4 Files
    """

    host: str
    port: int = 4242
    ae: AE = field(default_factory=AE)

    def __post_init__(self) -> None:
        self.ae.requested_contexts = StoragePresentationContexts

    def send_c_store(self, path: str) -> bool:
        ds = dcmread(path)
        patient_name = ds.PatientName
        study_description = ds.StudyDescription
        print(
            f"Patient name is: {patient_name}, Study Description is: {study_description}, File Path is: {path}")
        self.assoc = self.ae.associate(self.host, self.port)
        success = False
        if self.assoc.is_established:
            status = self.assoc.send_c_store(ds)
            if status:
                status_str = '0x{0:04x}'.format(status.Status)
                if status_str != '0x0000':
                    print(f"File {path} was not uploaded successfully")
                    error_cause = self.status_mapper(status_str)
                    print(f"Error Cause is: {error_cause}")
                else:
                    success = True
            else:
                print('Connection timed out, was aborted or received invalid response')
            self.assoc.release()
        else:
            print('Association rejected, aborted or never connected')
        return success

    @staticmethod
    def status_mapper(status_code: str) -> str:
        status_messages = {
            '0x0000': 'Success',
            '0x0001': 'Unrecognized Operation',
            '0x0106': 'Duplicate SOP Instance',
            '0x0122': 'Missing Attribute Value',
        }
        return status_messages.get(status_code, 'Unknown error')

    def upload_full_study(self, folder_path: str) -> bool:

        dummy_name = folder_path.split("\\")[-1]
        dummy_name = dummy_name.replace(" ", "_")
        failed = False
        with open(f'pacs_connection/upload_results/result_{dummy_name}.csv', mode='w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(['File Path', 'Status'])
            for file_name in os.listdir(folder_path):
                # create full path
                full_path = os.path.join(folder_path, file_name)
                # call send_c_store
                success = self.send_c_store(full_path)
                writer.writerow(
                    [full_path, 'Success' if success else 'Failed'])
                if not success:
                    failed = True
                    print(
                        'Connection timed out, was aborted or received invalid response')
        return not failed

    def upload_full_study_thread(self, folder_path: str) -> bool:
        dummy_name = folder_path.split("/")[-1]
        dummy_name = dummy_name.replace(" ", "_")
        failed = False
        with open(f'pacs_connection/upload_results/result_{dummy_name}.csv', mode='w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(['File Path', 'Status'])
            files = list(os.listdir(folder_path))
            full_files_path = [os.path.join(
                folder_path, file_name) for file_name in files]
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_obj = {executor.submit(
                    self.send_c_store, file_path): file_path for file_path in full_files_path}
                for future in concurrent.futures.as_completed(future_to_obj):
                    obj = future_to_obj[future]
                    try:
                        success = future.result()
                        writer.writerow(
                            [obj, 'Success' if success else 'Failed'])
                        if not success:
                            failed = True
                            print(
                                'Connection timed out, was aborted or received invalid response')
                    except Exception as exc:
                        print(f"{obj} generated an exception: {exc}")
        return failed

    def handle_failed_request(self, report_path: str) -> bool:
        print('failed_request report_path', report_path)
        failed = False
        updated_rows = []
        with open(report_path, 'r') as csv_file:
            reader = csv.reader(csv_file)
            for idx, row in enumerate(reader):
                if not row:
                    continue
                file_path = row[0]
                if file_path == 'File Path':
                    continue
                # skip the file if it's already success
                if row[1] == 'Success':
                    updated_rows.append(row)
                    continue
                print(f"Uploading file: {file_path}")
                success = self.send_c_store(file_path)

                # If the upload was successful, update the status in the CSV file
                if success:
                    row[1] = 'Success'
                else:
                    row[1] = 'Failed'
                    failed = True
                updated_rows.append(row)

        # Write the updated row to the CSV file
        with open(report_path, 'w', newline='') as csv_file:
            fieldnames = ['File Path', 'Status']
            writer = csv.DictWriter(
                csv_file, delimiter=',', fieldnames=fieldnames)
            writer.writeheader()
            for row in updated_rows:
                writer.writerow({'File Path': row[0], 'Status': row[1]})
        return not failed

    def upload(self, path: str, folder=True) -> bool:
        if folder:
            dummy_name = path.split("\\")[-1]
            dummy_name = dummy_name.replace(" ", "_")
            report_file = f"pacs_connection/upload_results/result_{dummy_name}.csv"
            if not self.upload_full_study(path):
                count = 0
                while count < 2:
                    if not self.handle_failed_request(report_file):
                        count += 1
                        print(f"Retrying failed request {count} time(s)")
                    else:
                        return True
            return False

        else:
            return self.send_c_store(path)
