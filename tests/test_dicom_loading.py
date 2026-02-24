import os
import tempfile
import zipfile

import requests
import numpy as np

from invesalius.reader import dicom_reader
from invesalius.reader.dicom import Parser, ResampleVolume

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

def test_get_pixel_spacing():
    parser = Parser()
    parser.data_image = {"spacing": [0.5, 0.5]}
    parser.GetSliceSpacing = lambda: 1.0 
    result = parser.GetPixelSpacing()
    assert result == [0.5, 0.5, 1.0], f"Expected [0.5, 0.5, 1.0], got {result}"

def test_get_slice_spacing():
    parser = Parser()
    parser.data_image = {"slice_positions": [0.0, 1.5, 3.0]}
    result = parser.GetSliceSpacing()
    assert result == 1.5, f"Expected 1.5, got {result}"

def test_load_dicom_series():
    with tempfile.TemporaryDirectory() as dicom_dir:
        _, dicom_data_dir = download_and_extract_dicom_zip(dicom_dir)
        parser = Parser()
        dicom_files = [
            os.path.join(dicom_data_dir, f)
            for f in os.listdir(dicom_data_dir)
            if f.endswith(".dcm")
        ]
        volume = parser.LoadDicomSeries(dicom_files)
        assert volume is not None, "Volume loading failed"
        assert volume.shape[0] > 0, "Volume has no slices"

def test_resample_volume():
    volume = np.ones((5, 5, 5))
    original_spacing = [2.0, 2.0, 2.0]
    new_spacing = [1.0, 1.0, 1.0]
    resampled = ResampleVolume(volume, original_spacing, new_spacing)
    assert resampled.shape == (10, 10, 10), f"Expected shape (10, 10, 10), got {resampled.shape}"