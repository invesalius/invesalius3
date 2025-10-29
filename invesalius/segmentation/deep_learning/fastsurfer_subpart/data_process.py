# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

import logging
from pathlib import Path
from typing import Optional, cast

import nibabel as nib
import numpy as np
import pandas as pd
import scipy.ndimage
import torch
from nibabel.filebasedimages import FileBasedHeader as _Header
from numpy import typing as npt
from skimage.filters import gaussian
from skimage.measure import label, regionprops
from torch.utils.data import Dataset

from . import misc
from .misc import Config

SUPPORTED_OUTPUT_FILE_FORMATS = ("mgz", "nii", "nii.gz")
LOGGER = logging.getLogger(__name__)


def load_image(
    file: str | Path,
    name: str = "image",
    **kwargs,
) -> tuple[nib.analyze.SpatialImage, np.ndarray]:
    """
    Load file 'file' with nibabel, including all data.
    """
    img = cast(nib.analyze.SpatialImage, nib.load(file, **kwargs))
    data = np.asarray(img.dataobj)
    return img, data


def save_image(
    header_info: _Header,
    affine_info: npt.NDArray[float],
    img_array: np.ndarray,
    save_as: str | Path,
    dtype: npt.DTypeLike | None = None,
) -> None:
    """
    Save an image (nibabel MGHImage), according to the desired output file format.

    Parameters
    ----------
    header_info : _Header
        Image header information.
    affine_info : npt.NDArray[float]
        Image affine information.
    img_array : np.ndarray
        An array containing image data.
    save_as : Path, str
        Name under which to save prediction; this determines output file format.
    dtype : npt.DTypeLike, optional
        Image array type; if provided, the image object is explicitly set to match this
        type (Default value = None).
    """
    save_as = Path(save_as)
    if not (
        save_as.suffix[1:] in SUPPORTED_OUTPUT_FILE_FORMATS
        or save_as.suffixes[-2:] == [".nii", ".gz"]
    ):
        raise ValueError(
            f"Output filename does not contain a supported file format "
            f"{SUPPORTED_OUTPUT_FILE_FORMATS}!"
        )

    mgh_img = None
    if save_as.suffix == ".mgz":
        mgh_img = nib.MGHImage(img_array, affine_info, header_info)
    elif save_as.suffix == ".nii" or save_as.suffixes[-2:] == [".nii", ".gz"]:
        mgh_img = nib.nifti1.Nifti1Pair(img_array, affine_info, header_info)

    if dtype is not None:
        mgh_img.set_data_dtype(dtype)

    if save_as.suffix in (".mgz", ".nii"):
        nib.save(mgh_img, save_as)
    elif save_as.suffixes[-2:] == [".nii", ".gz"]:
        # For correct outputs, nii.gz files should be saved using the nifti1
        # sub-module's save():
        nib.nifti1.save(mgh_img, str(save_as))


def read_classes_from_lut(lut_file: str | Path):
    """
    Read in **FreeSurfer-like** LUT table.

    Parameters
    ----------
    lut_file : Path, str
        The path and name of FreeSurfer-style LUT file with classes of interest.
        Example entry:
        ID LabelName  R   G   B   A
        0   Unknown   0   0   0   0
        1   Left-Cerebral-Exterior 70  130 180 0
        ...
    """
    if not isinstance(lut_file, Path):
        lut_file = Path(lut_file)
    if lut_file.suffix == ".tsv":
        return pd.read_csv(lut_file, sep="\t")

    names = {
        "ID": "int",
        "LabelName": "str",
        "Category": "str",
        "Red": "int",
        "Green": "int",
        "Blue": "int",
        "Alpha": "int",
    }
    kwargs = {}
    if lut_file.suffix == ".csv":
        kwargs["sep"] = ","
    elif lut_file.suffix == ".txt":
        kwargs["sep"] = "\\s+"
    else:
        raise RuntimeError(f"Unknown LUT file extension {lut_file}, must be csv, txt or tsv.")
    return pd.read_csv(
        lut_file,
        index_col=False,
        skip_blank_lines=True,
        comment="#",
        header=None,
        names=list(names.keys()),
        dtype=names,
        **kwargs,
    )


def aparc_aseg_to_label(
    mapped_aseg: torch.Tensor, labels: torch.Tensor | npt.NDArray
) -> torch.Tensor:
    """
    Perform look-up table mapping from sequential label space to LUT space.

    Parameters
    ----------
    mapped_aseg : torch.Tensor
        Label space segmentation (aparc.DKTatlas + aseg).
    labels : Union[torch.Tensor, npt.NDArray]
        List of labels defining LUT space.
    """
    if isinstance(labels, np.ndarray):
        labels = torch.from_numpy(labels)
    labels = labels.to(mapped_aseg.device)
    return labels[mapped_aseg]


def get_largest_connected(segmentation: npt.NDArray) -> np.ndarray:
    """
    Return largest connected component of a segmentation.
    """
    labels = label(segmentation, background=0)
    assert labels.max() != 0  # assume at least 1 CC
    bincount = np.bincount(labels.flat)[1:]
    return labels == (np.argmax(bincount) + 1)


def split_cortex_labels(aparc: npt.NDArray) -> np.ndarray:
    """
    Split cortex labels to completely de-lateralize structures.
    """
    rh_wm = get_largest_connected(aparc == 41)
    lh_wm = get_largest_connected(aparc == 2)
    rh_wm = regionprops(label(rh_wm, background=0))
    lh_wm = regionprops(label(lh_wm, background=0))
    centroid_rh = np.asarray(rh_wm[0].centroid)
    centroid_lh = np.asarray(lh_wm[0].centroid)

    labels_list = np.array(
        [
            1003,
            1006,
            1007,
            1008,
            1009,
            1011,
            1015,
            1018,
            1019,
            1020,
            1025,
            1026,
            1027,
            1028,
            1029,
            1030,
            1031,
            1034,
            1035,
        ]
    )

    for label_current in labels_list:
        label_img = aparc == label_current

        if np.sum(label_img) == 0:
            continue

        # If we have the a rh label: 2003, 2006 etc.
        if (label_current + 1000) in aparc:
            label_img = label(label_img, background=0)  # get connected components of that label
            for region in regionprops(label_img):
                coord_current = np.asarray(
                    region.centroid
                )  # Get coordinates of current connected component

                # determine if connected component is closer to right or left centroid
                dist_to_rh = np.linalg.norm(coord_current - centroid_rh)
                dist_to_lh = np.linalg.norm(coord_current - centroid_lh)

                if dist_to_rh < dist_to_lh:
                    coords = region.coords
                    aparc[coords[:, 0], coords[:, 1], coords[:, 2]] = (
                        # assigning to right hemisphere (adding 1000 to the label)
                        label_current + 1000
                    )

    return aparc


def transform_axial(vol: npt.NDArray, coronal2axial: bool = True) -> np.ndarray:
    """
    Transform volume into Axial axis and back.

    Parameters
    ----------
    vol : npt.NDArray
        Image volume to transform.
    coronal2axial : bool, default=True
        Transform from coronal to axial if true, otherwise the other way around.
    """
    if coronal2axial:
        return np.moveaxis(vol, [0, 1, 2], [1, 2, 0])
    else:
        return np.moveaxis(vol, [0, 1, 2], [2, 0, 1])


def transform_sagittal(vol: npt.NDArray, coronal2sagittal: bool = True) -> np.ndarray:
    """
    Transform volume into Sagittal axis and back.

    Parameters
    ----------
    vol : npt.NDArray
        Image volume to transform.
    coronal2sagittal : bool, default=True
        Transform from coronal to sagittal if true, otherwise the other way around.
    """
    if coronal2sagittal:
        return np.moveaxis(vol, [0, 1, 2], [2, 1, 0])
    else:
        return np.moveaxis(vol, [0, 1, 2], [2, 1, 0])


def get_thick_slices(img_data: npt.NDArray, slice_thickness: int = 3) -> np.ndarray:
    """
    Extract thick slices from the image.

    Feed slice_thickness preceding and succeeding slices to network,label only middle one.
    """
    img_data_pad = np.pad(
        img_data, ((0, 0), (0, 0), (slice_thickness, slice_thickness)), mode="edge"
    )
    from numpy.lib.stride_tricks import sliding_window_view

    return sliding_window_view(img_data_pad, 2 * slice_thickness + 1, axis=2)


def get_labels_from_lut(
    lut: str | pd.DataFrame, label_extract: tuple[str, str] = ("Left-", "ctx-rh")
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract labels from the lookup tables.
    """
    if isinstance(lut, str):
        lut = read_classes_from_lut(lut)
    mask = lut["LabelName"].str.startswith(label_extract)
    return lut["ID"].values, lut["ID"][~mask].values


def infer_mapping_from_lut(num_classes_full: int, lut: str | pd.DataFrame) -> np.ndarray:
    """
    Guess the mapping from a lookup table.
    """
    labels, labels_sag = get_labels_from_lut(lut)
    idx_list = np.ndarray(shape=(num_classes_full,), dtype=np.int16)
    for idx in range(len(labels)):
        idx_in_sag = np.where(labels_sag == labels[idx])[0]
        if idx_in_sag.size == 0:  # Empty not subcortical
            idx_in_sag = np.where(labels_sag == (labels[idx] - 1000))[0]

        if idx_in_sag.size == 0:
            current_label_sag = sagittal_coronal_remap_lookup(labels[idx])
            idx_in_sag = np.where(labels_sag == current_label_sag)[0]

        idx_list[idx] = idx_in_sag
    return idx_list


def apply_sagittal_mapping(
    prediction_sag: npt.NDArray, num_classes: int = 51, lut: str | None = None
) -> np.ndarray:
    """
    Remap the prediction on the sagittal network to full label space used by coronal and axial networks.

    Create full aparc.DKTatlas+aseg.mgz.

    Parameters
    ----------
    prediction_sag : npt.NDArray
        Sagittal prediction (labels).
    num_classes : int
        Number of SAGITTAL classes (96 for full classes, 51 for hemi split, 21 for aseg) (Default value = 51).
    lut : Optional[str]
        Look-up table listing class labels (Default value = None).

    Returns
    -------
    np.ndarray
        Remapped prediction.
    """
    r = range
    _idx = []
    if num_classes == 96:
        _idx = [[0], r(5, 14), r(1, 4), [14, 15, 4], r(16, 19), r(5, 51), r(20, 51)]
    elif num_classes == 51:
        _idx = [[0], r(5, 14), r(1, 4), [14, 15, 4], r(16, 19), r(5, 51)]
        _idx.extend([[20, 22, 27], r(29, 32), [33, 34], r(38, 43), [45]])
    elif num_classes == 21:
        _idx = [[0], r(5, 15), r(1, 4), [15, 16, 4], r(17, 20), r(5, 21)]
    if _idx:
        from itertools import chain

        idx_list = list(chain(*_idx))
    else:
        assert lut is not None, "lut is not defined!"
        idx_list = infer_mapping_from_lut(num_classes, lut)
    return prediction_sag[:, idx_list, :, :]


class ToTensorTest:
    """
    Convert np.ndarrays in sample to Tensors for testing/inference.
    """

    def __call__(self, img: npt.NDArray) -> np.ndarray:
        """
        Convert the image to float within range [0, 1] and make it torch compatible.

        Parameters
        ----------
        img : npt.NDArray
            Image to be converted.

        Returns
        -------
        img : np.ndarray
            Conformed image.
        """
        img = img.astype(np.float32)

        # Normalize and clamp between 0 and 1
        img = np.clip(img / 255.0, a_min=0.0, a_max=1.0)

        # swap color axis because
        # numpy image: H x W x C
        # torch image: C X H X W
        img = img.transpose((2, 0, 1))

        return img


class ProcessDataThickSlices(Dataset):
    """
    Load MRI-Image and process it to correct format for network inference.
    """

    def __init__(
        self,
        orig_data: npt.NDArray,
        orig_zoom: npt.NDArray,
        cfg: Config,
        transforms: Optional = None,
    ):
        assert orig_data.max() > 0.8, f"Multi Dataset - orig fail, max removed {orig_data.max()}"
        self.plane = cfg.DATA.PLANE
        self.slice_thickness = cfg.MODEL.NUM_CHANNELS // 2
        self.base_res = cfg.MODEL.BASE_RES

        if self.plane == "sagittal":
            orig_data = transform_sagittal(orig_data)
            self.zoom = orig_zoom[::-1][:2]

        elif self.plane == "axial":
            orig_data = transform_axial(orig_data)
            self.zoom = orig_zoom[::-1][:2]

        else:
            self.zoom = orig_zoom[:2]

        # Create thick slices
        orig_thick = get_thick_slices(orig_data, self.slice_thickness)
        orig_thick = np.transpose(orig_thick, (2, 0, 1, 3))
        self.images = orig_thick
        self.count = self.images.shape[0]
        self.transforms = transforms

        LOGGER.info(f"Successfully loaded {self.count} {self.plane} slices")

    def _get_scale_factor(self) -> npt.NDArray[float]:
        """
        Get scaling factor to match original resolution of input image to final resolution of FastSurfer base network.
        Input resolution is taken from voxel size in image header.
        """
        scale = self.base_res / np.asarray(self.zoom)

        return scale

    def __getitem__(self, index: int) -> dict:
        """
        Return a single image and its scale factor.
        """
        img = self.images[index]

        scale_factor = self._get_scale_factor()
        if self.transforms is not None:
            img = self.transforms(img)

        return {"image": img, "scale_factor": scale_factor}

    def __len__(self) -> int:
        """
        Get length of dataset (Number of slices)
        """
        return self.count


##
# Essential Label Mapping Functions
##


def sagittal_coronal_remap_lookup(x: int) -> int:
    """
    Convert left labels to corresponding right labels for aseg with dictionary mapping.

    Parameters
    ----------
    x : int
        Label to look up.

    Returns
    -------
    int
        Mapped label.
    """
    return {
        2: 41,
        3: 42,
        4: 43,
        5: 44,
        7: 46,
        8: 47,
        10: 49,
        11: 50,
        12: 51,
        13: 52,
        17: 53,
        18: 54,
        26: 58,
        28: 60,
        31: 63,
    }[x]


LIA_AFFINE = np.array([[-1, 0, 0], [0, 0, 1], [0, -1, 0]])


class Criteria:
    """Constants for conformance criteria"""

    FORCE_LIA_STRICT = "lia strict"
    FORCE_LIA = "lia"
    FORCE_IMG_SIZE = "img size"
    FORCE_ISO_VOX = "iso vox"


DEFAULT_CRITERIA_DICT = {
    "lia": Criteria.FORCE_LIA,
    "strict_lia": Criteria.FORCE_LIA_STRICT,
    "iso_vox": Criteria.FORCE_ISO_VOX,
    "img_size": Criteria.FORCE_IMG_SIZE,
}
DEFAULT_CRITERIA = frozenset(DEFAULT_CRITERIA_DICT.values())


def is_resampling_vox2vox(
    vox2vox: npt.NDArray[float],
    eps: float = 1e-6,
) -> bool:
    """
    Check whether the affine is resampling or just reordering.

    Parameters
    ----------
    vox2vox : np.ndarray
        The affine matrix.
    eps : float, default=1e-6
        The epsilon for the affine check.

    Returns
    -------
    bool
        The result.
    """
    _v2v = np.abs(vox2vox[:3, :3])
    # check 1: have exactly 3 times 1/-1 rest 0, check 2: all 1/-1 or 0
    return abs(_v2v.sum() - 3) > eps or np.any(np.maximum(_v2v, abs(_v2v - 1)) > eps)


def is_lia(
    affine: npt.NDArray[float],
    strict: bool = True,
    eps: float = 1e-6,
) -> bool:
    """
    Checks whether the affine is LIA-oriented.

    Parameters
    ----------
    affine : np.ndarray
        The affine to check.
    strict : bool, default=True
        Whether the orientation should be "exactly" LIA or just similar to LIA (i.e.
        it is more LIA than other directions).
    eps : float, default=1e-6
        The threshold in strict mode.
    """
    iaffine = affine[:3, :3]
    lia_nonzero = LIA_AFFINE != 0
    signs = np.all(np.sign(iaffine[lia_nonzero]) == LIA_AFFINE[lia_nonzero])
    if strict:
        directions = np.all(iaffine[np.logical_not(lia_nonzero)] <= eps)
    else:

        def get_primary_dirs(a):
            return np.argmax(abs(a), axis=0)

        directions = np.all(get_primary_dirs(iaffine) == get_primary_dirs(LIA_AFFINE))
    is_correct_lia = directions and signs
    return is_correct_lia


def find_min_size(img: nib.analyze.SpatialImage, max_size: float = 1) -> float:
    """
    Find minimal voxel size <= 1mm.

    Parameters
    ----------
    img : nib.analyze.SpatialImage
        Loaded source image.
    max_size : float
        Maximal voxel size in mm (default: 1.0).

    Returns
    -------
    float
        Rounded minimal voxel size.

    Notes
    -----
    This function only needs the header (not the data).
    """
    # find minimal voxel side length
    sizes = np.array(img.header.get_zooms()[:3])
    min_vox_size = np.round(np.min(sizes) * 10000) / 10000
    # set to max_size mm if larger than that (usually 1mm)
    return min(min_vox_size, max_size)


def find_img_size_by_fov(img: nib.analyze.SpatialImage, vox_size: float, min_dim: int = 256) -> int:
    """
    Find the cube dimension (>= 256) to cover the field of view of img.

    If vox_size is one, the img_size MUST always be min_dim (the FreeSurfer standard).

    Parameters
    ----------
    img : nib.analyze.SpatialImage
        Loaded source image.
    vox_size : float
        The target voxel size in mm.
    min_dim : int
        Minimal image dimension in voxels (default 256).

    Returns
    -------
    int
        The number of voxels needed to cover field of view.
    """
    if vox_size == 1.0:
        return min_dim

    sizes = np.array(img.header.get_zooms()[:3])
    max_fov = np.max(sizes * np.array(img.shape[:3]))  # in mm
    conform_dim = int(
        np.ceil(int(max_fov / vox_size * 10000) / 10000)
    )  # compute number of voxels needed to cover field of view
    return max(min_dim, conform_dim)


def get_conformed_vox_img_size(
    img: nib.analyze.SpatialImage,
    conform_vox_size: misc.VoxSizeOption,
    conform_to_1mm_threshold: float | None = None,
) -> tuple[float, int]:
    """
    Extract the voxel size and the image size.
    """
    # this is similar to mri_convert --conform_min
    auto_values = ["min", "auto"]
    if isinstance(conform_vox_size, str) and conform_vox_size.lower() in auto_values:
        conformed_vox_size = find_min_size(img)
        if conform_to_1mm_threshold and conformed_vox_size > conform_to_1mm_threshold:
            conformed_vox_size = 1.0
    # this is similar to mri_convert --conform_size <float>
    elif isinstance(conform_vox_size, float) and 0.0 < conform_vox_size <= 1.0:
        conformed_vox_size = conform_vox_size
    else:
        raise ValueError("Invalid value for conform_vox_size passed.")
    conformed_img_size = find_img_size_by_fov(img, conformed_vox_size)
    return conformed_vox_size, conformed_img_size


def getscale(
    data: np.ndarray, dst_min: float, dst_max: float, f_low: float = 0.0, f_high: float = 0.999
) -> tuple[float, float]:
    """
    Get offset and scale of image intensities to robustly rescale to dst_min..dst_max.

    Parameters
    ----------
    data : np.ndarray
        Image data (intensity values).
    dst_min : float
        Future minimal intensity value.
    dst_max : float
        Future maximal intensity value.
    f_low : float, default=0.0
        Robust cropping at low end (0.0=no cropping).
    f_high : float, default=0.999
        Robust cropping at higher end (0.999=crop one thousandth of highest intensity).

    Returns
    -------
    tuple[float, float]
        Offset and scale values.
    """
    # get robust min and max
    sorted_data = np.sort(data.flatten())
    len_data = len(sorted_data)
    low_idx = int(f_low * len_data)
    high_idx = int(f_high * len_data)
    src_min = sorted_data[low_idx]
    src_max = sorted_data[high_idx]

    # get scale
    if src_max > src_min:
        scale = (dst_max - dst_min) / (src_max - src_min)
    else:
        scale = 1.0

    return src_min, scale


def scalecrop(
    data: np.ndarray, dst_min: float, dst_max: float, src_min: float, scale: float
) -> np.ndarray:
    """
    Crop the intensity ranges to specific min and max values.
    """
    data_new = dst_min + scale * (data - src_min)

    # clip
    data_new = np.clip(data_new, dst_min, dst_max)
    print("Output:   min: " + format(data_new.min()) + "  max: " + format(data_new.max()))

    return data_new


def map_image(
    img: nib.analyze.SpatialImage,
    out_affine: np.ndarray,
    out_shape: tuple[int, ...] | np.ndarray,
    ras2ras: np.ndarray | None = None,
    order: int = 1,
    dtype: type | None = None,
) -> np.ndarray:
    """
    Map image to new voxel space (RAS orientation).

    Parameters
    ----------
    img : nib.analyze.SpatialImage
        The src 3D image with data and affine set.
    out_affine : np.ndarray
        Trg image affine.
    out_shape : tuple[int, ...], np.ndarray
        The trg shape information.
    ras2ras : np.ndarray, optional
        An additional mapping that should be applied (default=id to just reslice).
    order : int, default=1
        Order of interpolation (0=nearest,1=linear,2=quadratic,3=cubic).
    dtype : Type, optional
        Target dtype of the resulting image (relevant for reorientation,
        default=keep dtype of img).
    """
    from numpy.linalg import inv
    from scipy.ndimage import affine_transform

    if ras2ras is None:
        ras2ras = np.eye(4)

    # compute vox2vox from src to trg
    vox2vox = inv(out_affine) @ ras2ras @ img.affine
    # here we apply the inverse vox2vox (to pull back the src info to the target image)
    image_data = np.asanyarray(img.dataobj)

    out_shape = tuple(out_shape)
    # if input has frames
    if image_data.ndim > 3:
        # if the output has no frames
        if len(out_shape) == 3:
            if any(s != 1 for s in image_data.shape[3:]):
                raise ValueError(f"Multiple input frames {tuple(image_data.shape)} not supported!")
            image_data = np.squeeze(image_data, axis=tuple(range(3, image_data.ndim)))
        # if the output has the same number of frames as the input
        elif image_data.shape[3:] == out_shape[3:]:
            # add a frame dimension to vox2vox
            _vox2vox = np.eye(5, dtype=vox2vox.dtype)
            _vox2vox[:3, :3] = vox2vox[:3, :3]
            _vox2vox[3:, 4:] = vox2vox[:3, 3:]
            vox2vox = _vox2vox
        else:
            raise ValueError(
                f"Input image and requested output shape have different frames:"
                f"{image_data.shape} vs. {out_shape}!"
            )

    if dtype is not None:
        image_data = image_data.astype(dtype)

    if not is_resampling_vox2vox(vox2vox):
        order = 0

    return affine_transform(
        image_data,
        inv(vox2vox),
        output_shape=out_shape,
        order=order,
    )


def is_conformed(
    img: nib.analyze.SpatialImage,
    conform_vox_size: misc.VoxSizeOption = 1.0,
    eps: float = 1e-06,
    check_dtype: bool = True,
    dtype: type | None = None,
    verbose: bool = True,
    conform_to_1mm_threshold: float | None = None,
    criteria: set = DEFAULT_CRITERIA,
) -> bool:
    """
    Check if an image is already conformed or not.

    Dimensions: 256x256x256, Voxel size: 1x1x1, LIA orientation, and data type UCHAR.

    Parameters
    ----------
    img : nib.analyze.SpatialImage
        Loaded source image.
    conform_vox_size : misc.VoxSizeOption, default=1.0
        Which voxel size to conform to. Can either be a float between 0.0 and
        1.0 or 'min' check, whether the image is conformed to the minimal voxels size,
        i.e. conforming to smaller, but isotropic voxel sizes for high-res.
    eps : float, default=1e-06
        Allowed deviation from zero for LIA orientation check.
        Small inaccuracies can occur through the inversion operation. Already conformed
        images are thus sometimes not correctly recognized. The epsilon accounts for
        these small shifts.
    check_dtype : bool, default=True
        Specifies whether the UCHAR dtype condition is checked for;
        this is not done when the input is a segmentation.
    dtype : Type, optional
        Specifies the intended target dtype (default or None: uint8 = UCHAR).
    verbose : bool, default=True
        If True, details of which conformance conditions are violated (if any)
        are displayed.
    conform_to_1mm_threshold : float, optional
        Above this threshold the image is conformed to 1mm (default or None: ignore).
    criteria : set[Criteria], default in DEFAULT_CRITERIA
        An enum/set of criteria to check.
    """
    conformed_vox_size, conformed_img_size = get_conformed_vox_img_size(
        img,
        conform_vox_size,
        conform_to_1mm_threshold=conform_to_1mm_threshold,
    )

    ishape = img.shape
    if len(ishape) > 3 and ishape[3] != 1:
        raise ValueError(f"ERROR: Multiple input frames ({ishape[3]}) not supported!")

    checks = {"Number of Dimensions 3": (len(ishape) == 3, f"image ndim {img.ndim}")}
    if Criteria.FORCE_IMG_SIZE in criteria:
        img_size_criteria = f"Dimensions {'x'.join([str(conformed_img_size)] * 3)}"
        is_correct_img_size = all(s == conformed_img_size for s in ishape[:3])
        checks[img_size_criteria] = is_correct_img_size, f"image dimensions {ishape}"

    izoom = np.array(img.header.get_zooms())
    is_correct_vox_size = np.max(np.abs(izoom[:3] - conformed_vox_size)) < eps
    _vox_sizes = conformed_vox_size if is_correct_vox_size else izoom[:3]
    if Criteria.FORCE_ISO_VOX in criteria:
        vox_size_criteria = f"Voxel Size {'x'.join([str(conformed_vox_size)] * 3)}"
        image_vox_size = "image " + "x".join(map(str, izoom))
        checks[vox_size_criteria] = (is_correct_vox_size, image_vox_size)

    if {Criteria.FORCE_LIA, Criteria.FORCE_LIA_STRICT} & criteria != {}:
        is_strict = Criteria.FORCE_LIA_STRICT in criteria
        lia_text = "strict" if is_strict else "lia"
        if not (is_correct_lia := is_lia(img.affine, is_strict, eps)):
            import re

            print_options = np.get_printoptions()
            np.set_printoptions(precision=2)
            lia_text += ": " + re.sub("\\s+", " ", str(img.affine[:3, :3]))
            np.set_printoptions(**print_options)
        checks["Orientation LIA"] = (is_correct_lia, lia_text)

    if check_dtype:
        if dtype is None or (isinstance(dtype, str) and dtype.lower() == "uchar"):
            dtype = "uint8"
        else:
            dtype = np.dtype(dtype).type.__name__
        is_correct_dtype = img.get_data_dtype() == dtype
        checks[f"Dtype {dtype}"] = (is_correct_dtype, f"dtype {img.get_data_dtype()}")

    _is_conformed = all(map(lambda x: x[0], checks.values()))

    if verbose and not _is_conformed:
        LOGGER.info("The input image is not conformed.")
        for condition, (value, message) in checks.items():
            if not value:
                LOGGER.info(f" - {condition}: {message}")
    return _is_conformed


def conform(
    img: nib.analyze.SpatialImage,
    order: int = 1,
    conform_vox_size: misc.VoxSizeOption = 1.0,
    dtype: type | None = None,
    conform_to_1mm_threshold: float | None = None,
    criteria: set = DEFAULT_CRITERIA,
) -> nib.MGHImage:
    conformed_vox_size, conformed_img_size = get_conformed_vox_img_size(
        img,
        conform_vox_size,
        conform_to_1mm_threshold=conform_to_1mm_threshold,
    )
    from nibabel.freesurfer.mghformat import MGHHeader

    h1 = MGHHeader.from_header(img.header)
    mdc_affine = h1["Mdc"]
    img_shape = img.header.get_data_shape()
    vox_size = img.header.get_zooms()
    do_interp = False
    affine = img.affine[:3, :3]
    if {Criteria.FORCE_LIA, Criteria.FORCE_LIA_STRICT} & criteria != {}:
        do_interp = bool(Criteria.FORCE_LIA_STRICT in criteria and is_lia(affine, True))
        re_order_axes = [np.abs(affine[:, j]).argmax() for j in (0, 2, 1)]
    else:
        re_order_axes = [0, 1, 2]

    if Criteria.FORCE_IMG_SIZE in criteria:
        h1.set_data_shape([conformed_img_size] * 3 + [1])
    else:
        h1.set_data_shape([img_shape[i] for i in re_order_axes] + [1])
    if Criteria.FORCE_ISO_VOX in criteria:
        h1.set_zooms([conformed_vox_size] * 3)
        do_interp |= not np.allclose(vox_size, conformed_vox_size)
    else:
        h1.set_zooms([vox_size[i] for i in re_order_axes])

    if Criteria.FORCE_LIA_STRICT in criteria:
        mdc_affine = LIA_AFFINE
    elif Criteria.FORCE_LIA in criteria:
        mdc_affine = affine[:3, re_order_axes]
        if mdc_affine[0, 0] > 0:  # make 0,0 negative
            mdc_affine[:, 0] = -mdc_affine[:, 0]
        if mdc_affine[1, 2] < 0:  # make 1,2 positive
            mdc_affine[:, 2] = -mdc_affine[:, 2]
        if mdc_affine[2, 1] > 0:  # make 2,1 negative
            mdc_affine[:, 1] = -mdc_affine[:, 1]
    else:
        mdc_affine = img.affine[:3, :3]

    mdc_affine = mdc_affine / np.linalg.norm(mdc_affine, axis=1)
    h1["Mdc"] = np.linalg.inv(mdc_affine)

    h1["fov"] = max(i * v for i, v in zip(h1.get_data_shape(), h1.get_zooms(), strict=False))
    center = np.asarray(img.shape[:3], dtype=float) / 2.0
    h1["Pxyz_c"] = img.affine.dot(np.hstack((center, [1.0])))[:3]

    if not is_resampling_vox2vox(np.linalg.inv(h1.get_affine()) @ img.affine):
        ishape = np.asarray(img.shape)[re_order_axes]
        delta_shape = np.subtract(ishape, h1.get_data_shape()[:3])
        if not np.allclose(np.remainder(delta_shape, 2), 0):
            delta_shape[re_order_axes] = delta_shape
            new_center = (center + delta_shape / 2.0, [1.0])
            h1["Pxyz_c"] = img.affine.dot(np.hstack(new_center))[:3]

    affine = h1.get_affine()

    sctype = np.uint8 if dtype is None else np.dtype(dtype).type
    target_dtype = np.dtype(sctype)

    src_min, scale = 0, 1.0

    img_dtype = img.get_data_dtype()
    if any(img_dtype != dtyp for dtyp in (np.dtype(np.uint8), target_dtype)):
        src_min, scale = getscale(np.asanyarray(img.dataobj), 0, 255)

    kwargs = {}
    if sctype != np.uint:
        kwargs["dtype"] = "float"
    mapped_data = map_image(img, affine, h1.get_data_shape(), order=order, **kwargs)

    if img_dtype != np.dtype(np.uint8) or (img_dtype != target_dtype and scale != 1.0):
        scaled_data = scalecrop(mapped_data, 0, 255, src_min, scale)

        scaled_data[mapped_data == 0] = 0
        mapped_data = scaled_data

    if target_dtype == np.dtype(np.uint8):
        mapped_data = np.clip(np.rint(mapped_data), 0, 255)
    new_img = nib.MGHImage(sctype(mapped_data), affine, h1)

    from nibabel.freesurfer import mghformat

    try:
        new_img.set_data_dtype(target_dtype)
    except mghformat.MGHError as e:
        if "not recognized" not in e.args[0]:
            raise
        dtype_codes = mghformat.data_type_codes.code.keys()
        codes = set(k.name for k in dtype_codes if isinstance(k, np.dtype))
        print(
            f"The data type '{dtype}' is not recognized for MGH images, "
            f"switching to '{new_img.get_data_dtype()}' (supported: {tuple(codes)})."
        )

    return new_img


def reduce_to_aseg(data_inseg: np.ndarray) -> np.ndarray:
    """
    Reduce the input segmentation to a simpler segmentation.
    """
    print("Reducing to aseg ...")
    # replace 2000... with 42
    data_inseg[data_inseg >= 2000] = 42
    # replace 1000... with 3
    data_inseg[data_inseg >= 1000] = 3
    return data_inseg


def create_mask(aseg_data, dnum, enum):
    """
    Create dilated mask.
    """
    print("Creating dilated mask ...")

    # treat lateral orbital frontal and parsorbitalis special to avoid capturing too much of eye nerve
    lat_orb_front_mask = np.logical_or(aseg_data == 2012, aseg_data == 1012)
    parsorbitalis_mask = np.logical_or(aseg_data == 2019, aseg_data == 1019)
    frontal_mask = np.logical_or(lat_orb_front_mask, parsorbitalis_mask)
    print("Frontal region special treatment: ", format(np.sum(frontal_mask)))

    # reduce to binary
    datab = aseg_data > 0
    datab[frontal_mask] = 0
    datab = scipy.ndimage.binary_dilation(datab, np.ones((3, 3, 3)), iterations=dnum)
    datab = scipy.ndimage.binary_erosion(datab, np.ones((3, 3, 3)), iterations=enum)

    labels = label(datab)
    assert labels.max() != 0
    print(f"  Found {labels.max()} connected component(s)!")

    if labels.max() > 1:
        print("  Selecting largest component!")
        datab = labels == np.argmax(np.bincount(labels.flat)[1:]) + 1

    # add frontal regions back to mask
    datab[frontal_mask] = 1

    aseg_data[~datab] = 0
    aseg_data[datab] = 1
    return aseg_data


def flip_wm_islands(aseg_data: np.ndarray) -> np.ndarray:
    """
    Flip labels of disconnected white matter islands to the other hemisphere.
    """

    lh_wm = 2
    lh_gm = 3
    rh_wm = 41
    rh_gm = 42

    # for lh get largest component and islands
    mask = aseg_data == lh_wm
    labels = label(mask, background=0)
    assert labels.max() != 0
    bc = np.bincount(labels.flat)[1:]
    largestID = np.argmax(bc) + 1
    largestCC = labels == largestID
    lh_islands = (~largestCC) & (labels > 0)

    # same for rh
    mask = aseg_data == rh_wm
    labels = label(mask, background=0)
    assert labels.max() != 0
    bc = np.bincount(labels.flat)[1:]
    largestID = np.argmax(bc) + 1
    largestCC = labels == largestID
    rh_islands = (labels != largestID) & (labels > 0)

    lhmask = (aseg_data == lh_wm) | (aseg_data == lh_gm)
    rhmask = (aseg_data == rh_wm) | (aseg_data == rh_gm)
    ii = gaussian(lhmask.astype(float) * (-1) + rhmask.astype(float), sigma=1.5)

    rhswap = rh_islands & (ii < 0.0)
    lhswap = lh_islands & (ii > 0.0)
    flip_data = aseg_data.copy()
    flip_data[rhswap] = lh_wm
    flip_data[lhswap] = rh_wm
    print(f"FlipWM: rh {rhswap.sum()} and lh {lhswap.sum()} flipped.")

    return flip_data
