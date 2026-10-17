import nibabel as nib
import numpy as np
import pytest

import invesalius.constants as const
import invesalius.data.slice_ as slc
import invesalius.project as prj
import invesalius.reader.others_reader as oth

CASES = [
    (const.AXIAL, [1.0, 0.0, 0.0, 0.0, 1.0, 0.0], ("L", "P", "S")),  # DICOM project
    (const.CORONAL, None, ("R", "A", "S")),  # project imported from NIfTI
]


class FakeSlice:
    spacing = (0.5, 0.75, 2.0)
    matrix = np.arange(4 * 6 * 8, dtype=np.int16).reshape(4, 6, 8)

    def do_threshold_to_all_slices(self, mask):
        pass


class FakeMask:
    index = 0
    name = "bone"
    matrix = np.zeros((5, 7, 9), dtype=np.uint8)
    matrix[1:3, 2:5, 1:4] = 255  # off-centre block, so any flip shows up


@pytest.fixture(params=CASES)
def exported(request, tmp_path, monkeypatch):
    orientation, patient_orientation, axcodes = request.param
    project = prj.Project()
    monkeypatch.setattr(slc, "Slice", FakeSlice)
    monkeypatch.setattr(project, "mask_dict", {0: FakeMask()})
    monkeypatch.setattr(project, "original_orientation", orientation)
    monkeypatch.setattr(project, "patient_orientation", patient_orientation)
    project.export_project_to_nifti(str(tmp_path / "out.nii"))
    return project, axcodes, tmp_path / "out.nii", tmp_path / "out_mask_0_bone.nii"


def test_image_and_mask_share_affine(exported):
    _, axcodes, image_path, mask_path = exported
    image, mask = nib.load(image_path), nib.load(mask_path)
    assert np.allclose(image.affine, mask.affine)
    assert nib.aff2axcodes(image.affine) == axcodes
    assert np.allclose(image.header.get_zooms(), FakeSlice.spacing)


def test_mask_round_trip(exported):
    from invesalius.reader.nifti_utils import reorient_to_affine

    project, _, _, mask_path = exported
    # Same steps as the Masks tab import (Controller.OnImportMaskNifti)
    affine = project.get_nifti_affine(FakeSlice.spacing)
    data = reorient_to_affine(oth.ReadOthers(str(mask_path)), affine)
    assert np.array_equal(np.fliplr(np.swapaxes(data, 0, 2)), FakeMask.matrix[1:, 1:, 1:])
