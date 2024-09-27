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

import datetime
import os
import plistlib
import shutil
import sys
import tarfile
import tempfile
from typing import TYPE_CHECKING, Dict, List, Union

import numpy as np
from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow

import invesalius.constants as const
from invesalius import inv_paths

# from invesalius.data import imagedata_utils
from invesalius.presets import Presets
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton, TwoWaysDictionary, debug, decode

if TYPE_CHECKING:
    from invesalius.data.mask import Mask

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False


# Only one project will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Project(metaclass=Singleton):
    def __init__(self):
        # Patient/ acquistion information
        self.name = ""
        self.modality = ""
        self.original_orientation = ""
        self.window = ""
        self.level = ""
        self.affine = ""

        # Masks (vtkImageData)
        self.mask_dict = TwoWaysDictionary()

        # Surfaces are (vtkPolyData)
        self.surface_dict = {}
        self.last_surface_index = -1

        # Measurements
        self.measurement_dict = {}

        # TODO: Future ++
        self.annotation_dict = {}

        self.compress = False

        self.invesalius_version = const.INVESALIUS_VERSION

        self.presets = Presets()

        self.threshold_modes = self.presets.thresh_ct
        self.threshold_range = ""

        self.raycasting_preset = ""

        # Image fiducials for navigation
        self.image_fiducials = np.full([3, 3], np.nan)

        # self.surface_quality_list = ["Low", "Medium", "High", "Optimal *",
        #                             "Custom"i]

        # TOOD: define how we will relate this quality possibilities to
        # values set as decimate / smooth
        # TODO: Future +
        # Allow insertion of new surface quality modes

    def Close(self) -> None:
        for name in self.__dict__:
            attr = getattr(self, name)
            del attr

        self.__init__()

    def AddMask(self, mask: "Mask") -> int:
        """
        Insert new mask (Mask) into project data.

        input
            @ mask: Mask associated to mask

        output
            @ index: index of item that was inserted
        """
        index = len(self.mask_dict)
        self.mask_dict[index] = mask
        mask.index = index
        return index

    def RemoveMask(self, index: int) -> None:
        new_dict = TwoWaysDictionary()
        new_index = 0
        for i in self.mask_dict:
            if i == index:
                mask = self.mask_dict[i]
                mask.cleanup()
            else:
                new_dict[new_index] = self.mask_dict[i]
                self.mask_dict[i] = new_index
                new_index += 1
        self.mask_dict = new_dict

    def GetMask(self, index):
        return self.mask_dict[index]

    def AddSurface(self, surface):
        # self.last_surface_index = surface.index
        index = len(self.surface_dict)
        self.surface_dict[index] = surface
        return index

    def ChangeSurface(self, surface):
        index = surface.index
        self.surface_dict[index] = surface

    def RemoveSurface(self, index):
        new_dict = {}
        for i in self.surface_dict:
            if i < index:
                new_dict[i] = self.surface_dict[i]
            if i > index:
                new_dict[i - 1] = self.surface_dict[i]
                new_dict[i - 1].index = i - 1
        self.surface_dict = new_dict

    def AddMeasurement(self, measurement):
        index = len(self.measurement_dict)
        measurement.index = index
        self.measurement_dict[index] = measurement
        return index

    def ChangeMeasurement(self, measurement):
        index = measurement.index
        self.measurement_dict[index] = measurement

    def RemoveMeasurement(self, index):
        new_dict = {}
        for i in self.measurement_dict:
            if i < index:
                new_dict[i] = self.measurement_dict[i]
            if i > index:
                new_dict[i - 1] = self.measurement_dict[i]
                new_dict[i - 1].index = i - 1
        self.measurement_dict = new_dict

    def SetAcquisitionModality(self, type_=None):
        if type_ is None:
            type_ = self.modality

        if type_ == "MRI":
            self.threshold_modes = self.presets.thresh_mri
        elif type_ == "CT":
            self.threshold_modes = self.presets.thresh_ct
        else:
            debug("Different Acquisition Modality!!!")
        self.modality = type_

    def SetRaycastPreset(self, label: str) -> None:
        path = os.path.join(inv_paths.RAYCASTING_PRESETS_DIRECTORY, label + ".plist")
        with open(path, "r+b") as f:
            preset = plistlib.load(f, fmt=plistlib.FMT_XML)
        Publisher.sendMessage("Set raycasting preset", preset)

    def GetMeasuresDict(self):
        measures = {}
        d = self.measurement_dict
        for i in d:
            m = d[i]
            measures[str(m.index)] = m.get_as_dict()
        return measures

    def SavePlistProject(self, dir_, filename, compress=False):
        dir_temp = decode(tempfile.mkdtemp(), const.FS_ENCODE)

        self.compress = compress

        # filename_tmp = os.path.join(dir_temp, "matrix.dat")
        filelist = {}

        project = {
            # Format info
            "format_version": const.INVESALIUS_ACTUAL_FORMAT_VERSION,
            "invesalius_version": const.INVESALIUS_VERSION,
            "date": datetime.datetime.now().isoformat(),
            "compress": self.compress,
            # case info
            "name": self.name,  # patient's name
            "modality": self.modality,  # CT, RMI, ...
            "orientation": self.original_orientation,
            "window_width": self.window,
            "window_level": self.level,
            "scalar_range": self.threshold_range,
            "spacing": self.spacing,
            "affine": self.affine,
            "image_fiducials": self.image_fiducials.tolist(),
        }

        # Saving the matrix containing the slices
        matrix = {
            "filename": "matrix.dat",
            "shape": self.matrix_shape,
            "dtype": self.matrix_dtype,
        }
        project["matrix"] = matrix
        filelist[self.matrix_filename] = "matrix.dat"
        # shutil.copyfile(self.matrix_filename, filename_tmp)

        # Saving the masks
        masks = {}
        for index in self.mask_dict:
            masks[str(index)] = self.mask_dict[index].SavePlist(dir_temp, filelist)
        project["masks"] = masks

        # Saving the surfaces
        surfaces = {}
        for index in self.surface_dict:
            surfaces[str(index)] = self.surface_dict[index].SavePlist(dir_temp, filelist)
        project["surfaces"] = surfaces

        # Saving the measurements
        measurements = self.GetMeasuresDict()
        measurements_filename = "measurements.plist"
        fd_mplist, temp_mplist = tempfile.mkstemp()
        with open(temp_mplist, "w+b") as f:
            plistlib.dump(measurements, f)
        filelist[temp_mplist] = measurements_filename
        project["measurements"] = measurements_filename
        os.close(fd_mplist)

        # Saving the annotations (empty in this version)
        project["annotations"] = {}

        # Saving the main plist
        temp_fd, temp_plist = tempfile.mkstemp()
        with open(temp_plist, "w+b") as f:
            plistlib.dump(project, f)
        filelist[temp_plist] = "main.plist"
        os.close(temp_fd)

        # Compressing and generating the .inv3 file
        path = os.path.join(dir_, filename)
        Compress(dir_temp, path, filelist, compress)

        # Removing the temp folder.
        shutil.rmtree(dir_temp)

        for f in filelist:
            if filelist[f].endswith(".plist"):
                os.remove(f)

    def OpenPlistProject(self, filename):
        if not const.VTK_WARNING:
            log_path = os.path.join(inv_paths.USER_LOG_DIR, "vtkoutput.txt")
            fow = vtkFileOutputWindow()
            fow.SetFileName(log_path.encode(const.FS_ENCODE))
            ow = vtkOutputWindow()
            ow.SetInstance(fow)

        filelist = Extract(filename, tempfile.mkdtemp())
        dirpath = os.path.abspath(os.path.split(filelist[0])[0])
        self.load_from_folder(dirpath)

    def load_from_folder(self, dirpath):
        """
        Loads invesalius3 project files from dipath.
        """
        import invesalius.data.mask as msk
        import invesalius.data.measures as ms
        import invesalius.data.surface as srf

        # Opening the main file from invesalius 3 project
        main_plist = os.path.join(dirpath, "main.plist")
        with open(main_plist, "r+b") as f:
            project = plistlib.load(f, fmt=plistlib.FMT_XML)

        format_version = project["format_version"]
        if format_version > const.INVESALIUS_ACTUAL_FORMAT_VERSION:
            from invesalius.gui.dialogs import ImportOldFormatInvFile

            ImportOldFormatInvFile()

        # case info
        self.name = project["name"]
        self.modality = project["modality"]
        self.original_orientation = project["orientation"]
        self.window = project["window_width"]
        self.level = project["window_level"]
        self.threshold_range = project["scalar_range"]
        self.spacing = project["spacing"]

        self.compress = project.get("compress", True)

        # Opening the matrix containing the slices
        filepath: str = os.path.join(dirpath, project["matrix"]["filename"])
        self.matrix_filename = filepath
        self.matrix_shape = project["matrix"]["shape"]
        self.matrix_dtype = project["matrix"]["dtype"]

        if project.get("affine", ""):
            self.affine = project["affine"]

        try:
            self.image_fiducials = np.asarray(project["image_fiducials"])
        except KeyError:
            pass

        # Opening the masks
        self.mask_dict = TwoWaysDictionary()
        for index in sorted(project.get("masks", []), key=lambda x: int(x)):
            filename = project["masks"][index]
            filepath = os.path.join(dirpath, filename)
            m = msk.Mask()
            m.spacing = self.spacing
            m.OpenPList(filepath)
            m.index = len(self.mask_dict)
            self.mask_dict[m.index] = m

        # Opening the surfaces
        self.surface_dict: dict[int, srf.Surface] = {}
        for index in sorted(project.get("surfaces", []), key=lambda x: int(x)):
            filename = project["surfaces"][index]
            filepath = os.path.join(dirpath, filename)
            s = srf.Surface(int(index))
            s.OpenPList(filepath)
            self.surface_dict[s.index] = s

        # Opening the measurements
        self.measurement_dict = {}
        measures_file = os.path.join(dirpath, project.get("measurements", "measurements.plist"))
        if os.path.exists(measures_file):
            with open(measures_file, "r+b") as f:
                measurements = plistlib.load(f, fmt=plistlib.FMT_XML)
            for index in measurements:
                if measurements[index]["type"] in (const.DENSITY_ELLIPSE, const.DENSITY_POLYGON):
                    measure = ms.DensityMeasurement()
                else:
                    measure = ms.Measurement()
                measure.Load(measurements[index])
                self.measurement_dict[int(index)] = measure

    def create_project_file(
        self,
        name,
        spacing,
        modality,
        orientation,
        window_width,
        window_level,
        image,
        affine="",
        folder=None,
    ):
        if folder is None:
            folder = tempfile.mkdtemp()
        if not os.path.exists(folder):
            os.mkdir(folder)
        # image_file = os.path.join(folder, "matrix.dat")
        # image_mmap = imagedata_utils.array2memmap(image, image_file)
        matrix = {"filename": "matrix.dat", "shape": image.shape, "dtype": str(image.dtype)}
        project = {
            # Format info
            "format_version": const.INVESALIUS_ACTUAL_FORMAT_VERSION,
            "invesalius_version": const.INVESALIUS_VERSION,
            "date": datetime.datetime.now().isoformat(),
            "compress": True,
            # case info
            "name": name,  # patient's name
            "modality": modality,  # CT, RMI, ...
            "orientation": orientation,
            "window_width": window_width,
            "window_level": window_level,
            "scalar_range": (int(image.min()), int(image.max())),
            "spacing": spacing,
            "affine": affine,
            "image_fiducials": np.full([3, 3], np.nan).tolist(),
            "matrix": matrix,
        }

        path = os.path.join(folder, "main.plist")
        with open(path, "w+b") as f:
            plistlib.dump(project, f)

    def export_project(self, filename, save_masks=True):
        if filename.lower().endswith(".hdf5") or filename.lower().endswith(".h5"):
            self.export_project_to_hdf5(filename, save_masks)
        elif filename.lower().endswith(".nii") or filename.lower().endswith(".nii.gz"):
            self.export_project_to_nifti(filename, save_masks)

    def export_project_to_hdf5(self, filename, save_masks=True):
        import h5py

        import invesalius.data.slice_ as slc

        s = slc.Slice()
        with h5py.File(filename, "w") as f:
            f["image"] = s.matrix
            f["spacing"] = s.spacing

            f["invesalius_version"] = const.INVESALIUS_VERSION
            f["date"] = datetime.datetime.now().isoformat()
            f["compress"] = self.compress
            f["name"] = self.name  # patient's name
            f["modality"] = self.modality  # CT, RMI, ...
            f["orientation"] = self.original_orientation
            f["window_width"] = self.window
            f["window_level"] = self.level
            f["scalar_range"] = self.threshold_range

            if save_masks:
                for index in self.mask_dict:
                    mask = self.mask_dict[index]
                    s.do_threshold_to_all_slices(mask)
                    key = f"masks/{index}"
                    f[key + "/name"] = mask.name
                    f[key + "/matrix"] = mask.matrix[1:, 1:, 1:]
                    f[key + "/colour"] = mask.colour[:3]
                    f[key + "/opacity"] = mask.opacity
                    f[key + "/threshold_range"] = mask.threshold_range
                    f[key + "/edition_threshold_range"] = mask.edition_threshold_range
                    f[key + "/visible"] = mask.is_shown
                    f[key + "/edited"] = mask.was_edited

    def export_project_to_nifti(self, filename, save_masks=True):
        import nibabel as nib

        import invesalius.data.slice_ as slc

        s = slc.Slice()
        img_nifti = nib.Nifti1Image(np.swapaxes(np.fliplr(s.matrix), 0, 2), None)
        img_nifti.header.set_zooms(s.spacing)
        img_nifti.header.set_dim_info(slice=0)
        nib.save(img_nifti, filename)
        if save_masks:
            for index in self.mask_dict:
                mask = self.mask_dict[index]
                s.do_threshold_to_all_slices(mask)
                mask_nifti = nib.Nifti1Image(np.swapaxes(np.fliplr(mask.matrix), 0, 2), None)
                mask_nifti.header.set_zooms(s.spacing)
                if filename.lower().endswith(".nii"):
                    basename = filename[:-4]
                    ext = filename[-4::]
                elif filename.lower().endswith(".nii.gz"):
                    basename = filename[:-7]
                    ext = filename[-7::]
                else:
                    ext = ".nii"
                    basename = filename
                nib.save(mask_nifti, f"{basename}_mask_{mask.index}_{mask.name}{ext}")


def Compress(
    folder: Union[str, os.PathLike],
    filename: Union[str, os.PathLike],
    filelist: Dict[Union[str, os.PathLike], Union[str, os.PathLike]],
    compress: bool = False,
) -> None:
    tmpdir, tmpdir_ = os.path.split(folder)
    # current_dir = os.path.abspath(".")
    fd_inv3, temp_inv3 = tempfile.mkstemp()
    if _has_win32api:
        temp_inv3 = win32api.GetShortPathName(temp_inv3)

    temp_inv3 = decode(temp_inv3, const.FS_ENCODE)
    # os.chdir(tmpdir)
    # file_list = glob.glob(os.path.join(tmpdir_,"*"))
    if compress:
        tar = tarfile.open(temp_inv3, "w:gz")
    else:
        tar = tarfile.open(temp_inv3, "w")
    for name in filelist:
        tar.add(name, arcname=os.path.join(tmpdir_, filelist[name]))
    tar.close()
    os.close(fd_inv3)
    shutil.move(temp_inv3, filename)
    # os.chdir(current_dir)


def Extract(filename: Union[str, bytes, os.PathLike], folder: Union[str, bytes, os.PathLike]):
    if _has_win32api:
        folder = win32api.GetShortPathName(folder)
    folder = decode(folder, const.FS_ENCODE)

    tar = tarfile.open(filename, "r")
    idir = decode(os.path.split(tar.getnames()[0])[0], "utf8")
    os.mkdir(os.path.join(folder, idir))
    filelist = []
    tar_filter = getattr(tarfile, "tar_filter", None)  # For python < 3.12
    for t in tar.getmembers():
        try:
            tar.extract(t, path=folder, filter=tar_filter)
        except TypeError:
            tar.extract(t, path=folder)
        fname = os.path.join(folder, decode(t.name, "utf-8"))
        filelist.append(fname)
    tar.close()
    return filelist


def Extract_(
    filename: Union[str, bytes, os.PathLike], folder: Union[str, os.PathLike]
) -> List[str]:
    tar = tarfile.open(filename, "r:gz")
    # tar.list(verbose=True)
    tar.extractall(folder)
    filelist = [os.path.join(folder, i) for i in tar.getnames()]
    tar.close()
    return filelist
