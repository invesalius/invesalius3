import os
import tempfile
import zipfile

import requests

from invesalius.reader import dicom_reader

DICOM_ZIP_URL = "https://github.com/invesalius/invesalius3/releases/download/v3.0/0051.zip"
DICOM_ZIP_FILENAME = "0051.zip"
DICOM_FOLDER_NAME = "0051"


def download_and_extract_dicom_zip(dest_folder):
    zip_path = os.path.join(dest_folder, DICOM_ZIP_FILENAME)
    extract_path = os.path.join(dest_folder, DICOM_FOLDER_NAME)
    response = requests.get(DICOM_ZIP_URL)
    response.raise_for_status()
    with open(zip_path, "wb") as f:
        f.write(response.content)
    # Extracting since its zip
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(dest_folder)
    return zip_path, extract_path


def test_dicom_loading():
    with tempfile.TemporaryDirectory() as dicom_dir:
        zip_path, dicom_data_dir = download_and_extract_dicom_zip(dicom_dir)
        patients = dicom_reader.GetDicomGroups(dicom_data_dir, recursive=True)
        groups = patients[0].GetGroups()
        group = groups[0]
        expected_key = ("CT 0051 - InVesalius Sample", "000001", "000002", "AXIAL", 0)
        assert (
            group.key == expected_key
        ), f"Group key {group.key} does not match expected {expected_key}"
        slices = list(group.GetList())
        assert len(slices) == 108, f"Expected 108 slices, got {len(slices)}"
        dicom = slices[0]
        assert (
            dicom.patient.name == "CT 0051 - InVesalius Sample"
        ), f"Expected patient name 'CT 0051 - InVesalius Sample', got '{dicom.patient.name}'"
        spacing = dicom.image.spacing
        assert spacing == [
            0.4785156,
            0.4785156,
            2.0,
        ], f"Expected spacing [0.4785156, 0.4785156, 2.0], got {spacing}"
        size = dicom.image.size
        assert size == (512, 512), f"Expected size (512, 512), got {size}"
        assert (
            dicom.image.orientation_label == "AXIAL"
        ), f"Expected orientation label 'AXIAL', got '{dicom.image.orientation_label}'"
        assert os.path.exists(dicom.image.file)
