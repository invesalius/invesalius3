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


# IMPORTS
import copy
import logging
from collections.abc import Iterator, Sequence
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

import nibabel as nib
import numpy as np
import torch

from . import data_process as dp
from . import misc
from .inference import CreateInference, PytorchInference, TinyGradInference
from .misc import create_config, handle_cuda_memory_exception
from .quick_qc import check_volume

LOGGER = logging.getLogger(__name__)


class Pipeline:
    """
    Run the model prediction on given data.

    Attributes
    ----------
    vox_size : float, 'min'
    current_plane : str
    models : Dict[str, Inference]
    view_ops : Dict[str, Dict[str, Any]]
    conform_to_1mm_threshold : float, optional
        threshold until which the image will be conformed to 1mm res

    Methods
    -------
    __init__()
        Construct object.
    set_and_create_outdir()
        Sets and creates output directory.
    conform_and_save()
        Saves original image.
    set_subject()
        Setter.
    get_subject_name()
        Getter.
    run_model()
        Calculates prediction.
    get_img()
        Getter.
    save_img()
        Saves image as file.
    set_up_model_params()
        Setter.
    """

    vox_size: float | Literal["min"]
    current_plane: misc.Plane
    models: dict[misc.Plane, PytorchInference | TinyGradInference]
    view_ops: dict[misc.Plane, dict[str, Any]]
    conform_to_1mm_threshold: float | None
    device: torch.device
    viewagg_device: torch.device
    _pool: Executor

    def __init__(
        self,
        lut: Path,
        ckpt_ax: Path | None = None,
        ckpt_sag: Path | None = None,
        ckpt_cor: Path | None = None,
        device: str = "cpu",
        viewagg_device: str = "cpu",
        threads: int = 1,
        batch_size: int = 1,
        vox_size: misc.VoxSizeOption = "min",
        async_io: bool = False,
        conform_to_1mm_threshold: float = 0.95,
        backend: str = "pytorch",
    ):
        """
        Construct Pipeline object.
        """
        self._threads = threads
        torch.set_num_threads(self._threads)
        self._async_io = async_io

        self.sf = 1.0

        self.device, self.viewagg_device = self._setup_devices(device, viewagg_device)

        try:
            self.lut = dp.read_classes_from_lut(lut)
        except FileNotFoundError as err:
            raise ValueError(
                f"Could not find the ColorLUT in {lut}, please make sure the "
                f"--lut argument is valid."
            ) from err
        self.labels = self.lut["ID"].values
        self.torch_labels = torch.from_numpy(self.lut["ID"].values)
        self.names = ["SubjectName", "Average", "Subcortical", "Cortical"]
        # Create configs for each plane with batch size
        cfg_cor = create_config("coronal", batch_size) if ckpt_cor else None
        cfg_sag = create_config("sagittal", batch_size) if ckpt_sag else None
        cfg_ax = create_config("axial", batch_size) if ckpt_ax else None

        # Use first available config as base config
        self.cfg_fin = cfg_cor or cfg_sag or cfg_ax
        # the order in this dictionary dictates the order in the view aggregation
        self.view_ops = {
            "coronal": {"cfg": cfg_cor, "ckpt": ckpt_cor},
            "sagittal": {"cfg": cfg_sag, "ckpt": ckpt_sag},
            "axial": {"cfg": cfg_ax, "ckpt": ckpt_ax},
        }
        self.num_classes = self.cfg_fin.MODEL.NUM_CLASSES  # Use FastSurfer default
        self.backend = backend
        self.models = self._initialize_models()

        if vox_size == "min":
            self.vox_size = "min"
        elif 0.0 < float(vox_size) <= 1.0:
            self.vox_size = float(vox_size)
        else:
            raise ValueError(
                f"Invalid value for vox_size, must be between 0 and 1 or 'min', was {vox_size}."
            )
        self.conform_to_1mm_threshold = conform_to_1mm_threshold

    def _setup_devices(self, device: str, viewagg_device: str) -> tuple[torch.device, torch.device]:
        """
        Setup main and view aggregation devices directly from device strings without using find_device.
        """
        # Validate main device
        if "cuda" in device and not torch.cuda.is_available():
            raise ValueError(f"Device '{device}' is not available, please use 'cpu' or 'auto'.")
        main_device = torch.device(device)

        # Validate view aggregation device and fall back to CPU if needed
        if "cuda" in viewagg_device and not torch.cuda.is_available():
            LOGGER.warning(
                f"View aggregation device '{viewagg_device}' is not available, falling back to 'cpu'."
            )
            viewagg_device = "cpu"
        va_device = torch.device(viewagg_device)

        LOGGER.info(f"Running on device: {main_device}")
        LOGGER.info(f"Running view aggregation on {va_device}")
        return main_device, va_device

    def _initialize_models(self) -> dict[misc.Plane, PytorchInference | TinyGradInference]:
        """
        Initialize models for all available planes.

        Returns
        -------
        dict[misc.Plane, Inference]
            Dictionary mapping planes to inference models
        """
        models = {}
        use_gpu = self.device.type == "cuda" if hasattr(self.device, "type") else False

        for plane, view in self.view_ops.items():
            if view["cfg"] is not None and view["ckpt"] is not None:
                models[plane] = CreateInference(
                    backend=self.backend,
                    cfg=view["cfg"],
                    ckpt=view["ckpt"],
                    device=self.device,
                    lut=self.lut,
                    use_gpu=use_gpu,
                )
        return models

    @property
    def pool(self) -> Executor:
        if not hasattr(self, "_pool"):
            if not self._async_io:
                self._pool = misc.SerialExecutor()
            else:
                self._pool = ThreadPoolExecutor(self._threads)
        return self._pool

    def __del__(self):
        if hasattr(self, "_pool"):
            # only wait on futures, if we specifically ask (see end of the script, so we
            # do not wait if we encounter a fail case)
            self._pool.shutdown(True)

    def conform_and_save(
        self,
        subject: misc.SubjectDirectory,
    ) -> tuple[nib.analyze.SpatialImage, np.ndarray]:
        """
        Conform and saves original image.

        Parameters
        ----------
        subject : misc.SubjectDirectory
            Subject directory object.
        """
        orig, orig_data = dp.load_image(subject.orig_name, "orig image")
        LOGGER.info(f"Successfully loaded image from {subject.orig_name}.")

        # Save input image to standard location
        if subject.can_resolve_attribute("copy_orig_name"):
            self.pool.submit(self.save_img, subject.copy_orig_name, orig_data, orig)

        if not dp.is_conformed(
            orig,
            conform_vox_size=self.vox_size,
            check_dtype=True,
            verbose=True,
            conform_to_1mm_threshold=self.conform_to_1mm_threshold,
        ):
            LOGGER.info("Conforming image")
            orig = dp.conform(
                orig,
                conform_vox_size=self.vox_size,
                conform_to_1mm_threshold=self.conform_to_1mm_threshold,
            )
            orig_data = np.asanyarray(orig.dataobj)

        # Save conformed input image
        if subject.can_resolve_attribute("conf_name"):
            self.pool.submit(self.save_img, subject.conf_name, orig_data, orig, dtype=np.uint8)
        else:
            raise RuntimeError(
                "Cannot resolve the name to the conformed image, please specify an absolute path."
            )

        return orig, orig_data

    def get_prediction(
        self,
        image_name: str,
        orig_data: np.ndarray,
        zoom: np.ndarray | Sequence[int],
        progress_callback: callable = None,
    ) -> np.ndarray:
        """
        Run and get prediction.

        Parameters
        ----------
        image_name : str
            Original image filename.
        orig_data : np.ndarray
            Original image data.
        zoom : np.ndarray, tuple
            Original zoom.
        progress_callback : callable, optional
            Callback function to report progress. Should accept (current_step, total_steps).

        """
        shape = orig_data.shape + (self.num_classes,)
        kwargs = {
            "device": self.viewagg_device,
            "dtype": torch.float16,
            "requires_grad": False,
        }

        pred_prob = torch.zeros(shape, **kwargs)

        # inference and view aggregation
        for i, (plane, model) in enumerate(self.models.items()):
            LOGGER.info(f"Run {plane} prediction")
            self.current_plane = plane
            # pred_prob is updated inplace to conserve memory
            pred_prob = model.run(pred_prob, image_name, orig_data, zoom, out=pred_prob)
            if progress_callback:
                progress_callback(i + 1, 3 + 2)

        # Get hard predictions
        pred_classes = torch.argmax(pred_prob, 3)
        del pred_prob

        if progress_callback:
            progress_callback(3 + 1, 3 + 2)

        pred_classes = dp.aparc_aseg_to_label(pred_classes, self.labels)
        pred_classes = dp.split_cortex_labels(pred_classes.cpu().numpy())

        if progress_callback:
            progress_callback(3 + 2, 3 + 2)

        return pred_classes

    def save_img(
        self,
        save_as: str | Path,
        data: np.ndarray | torch.Tensor,
        orig: nib.analyze.SpatialImage,
        dtype: type | None = None,
    ) -> None:
        """
        Save image as a file.

        Parameters
        ----------
        save_as : str, Path
            Filename to give the image.
        data : np.ndarray, torch.Tensor
            Image data.
        orig : nib.analyze.SpatialImage
            Original Image.
        dtype : type, optional
            Data type to use for saving the image.
        """
        save_as = Path(save_as)

        if not save_as.parent.exists():
            LOGGER.info(
                f"Output image directory {save_as.parent} does not exist. Creating it now..."
            )
            save_as.parent.mkdir(parents=True)

        np_data = data if isinstance(data, np.ndarray) else data.cpu().numpy()
        if dtype is not None:
            _header = orig.header.copy()
            _header.set_data_dtype(dtype)
        else:
            _header = orig.header
        dp.save_image(_header, orig.affine, np_data, save_as, dtype=dtype)
        LOGGER.info(
            f"Successfully saved image {'asynchronously ' if self._async_io else ''}  as {save_as}."
        )

    def async_save_img(
        self,
        save_as: str | Path,
        data: np.ndarray | torch.Tensor,
        orig: nib.analyze.SpatialImage,
        dtype: type | None = None,
    ) -> Future[None]:
        """Save image asynchronously and return Future to track completion."""
        return self.pool.submit(self.save_img, save_as, data, orig, dtype)

    def set_up_model_params(
        self,
        plane: misc.Plane,
        cfg: misc.Config,
        ckpt: "torch.Tensor",
    ) -> None:
        """
        Set up the model parameters from the configuration and checkpoint.
        """
        self.view_ops[plane]["cfg"] = cfg
        self.view_ops[plane]["ckpt"] = ckpt

    def pipeline_conform_and_save(
        self,
        subjects: misc.SubjectList,
    ) -> Iterator[tuple[misc.SubjectDirectory, tuple[nib.analyze.SpatialImage, np.ndarray]]]:
        """
        Pipeline for conforming and saving original images asynchronously.

        Yields
        ------
        tuple[misc.SubjectDirectory, tuple[nib.analyze.SpatialImage, np.ndarray]]
            Subject directory and a tuple with the image and its data.
        """
        if not self._async_io:
            # do not run pipeline, direct iteration and function call
            for subject in subjects:
                # yield subject and load orig
                yield subject, self.conform_and_save(subject)
        else:
            # pipeline the same
            yield from misc.pipeline(self.pool, self.conform_and_save, subjects)


def run_pipeline(
    *,
    orig_name: Path | str,
    out_dir: Path,
    pred_name: str,
    ckpt_ax: Path,
    ckpt_sag: Path,
    ckpt_cor: Path,
    qc_log: str = "",
    conf_name: str = "mri/orig.mgz",
    in_dir: Path | None = None,
    sid: str | None = None,
    search_tag: str | None = None,
    csv_file: str | Path | None = None,
    lut: Path | str | None = None,
    remove_suffix: str = "",
    brainmask_name: str = "mri/mask.mgz",
    aseg_name: str = "mri/aseg.auto_noCC.mgz",
    vox_size: misc.VoxSizeOption = "min",
    device: str = "auto",
    viewagg_device: str = "auto",
    batch_size: int = 1,
    async_io: bool = True,
    threads: int = -1,
    conform_to_1mm_threshold: float = 0.95,
    backend: str = "pytorch",
    progress_callback: callable = None,
    **kwargs,
) -> Literal[0] | str:
    if len(kwargs) > 0:
        LOGGER.warning(f"Unknown arguments {list(kwargs.keys())} in {__file__}:main.")

    qc_file_handle = None
    if qc_log:
        try:
            qc_file_handle = open(qc_log, "w")
        except (NotADirectoryError, OSError):
            LOGGER.warning(f"Cannot create QC log file at {qc_log}. QC log will not be saved.")

    config = misc.SubjectDirectoryConfig(
        orig_name=orig_name,
        pred_name=pred_name,
        conf_name=conf_name,
        in_dir=in_dir,
        csv_file=csv_file,
        sid=sid,
        search_tag=search_tag,
        brainmask_name=brainmask_name,
        remove_suffix=remove_suffix,
        out_dir=out_dir,
    )
    config.copy_orig_name = "mri/orig/001.mgz"

    try:
        subjects = misc.SubjectList(
            config,
            segfile="pred_name",
            copy_orig_name="copy_orig_name",
        )
        subjects.make_subjects_dir()

        pipeline = Pipeline(
            lut=lut,
            ckpt_ax=ckpt_ax,
            ckpt_sag=ckpt_sag,
            ckpt_cor=ckpt_cor,
            device=device,
            viewagg_device=viewagg_device,
            threads=threads,
            batch_size=batch_size,
            vox_size=vox_size,
            async_io=async_io,
            conform_to_1mm_threshold=conform_to_1mm_threshold,
            backend=backend,
        )
    except RuntimeError as e:
        LOGGER.error(f"Failed to initialize models: {e}")
        return str(e)

    qc_failed_subject_count = 0

    iter_subjects = pipeline.pipeline_conform_and_save(subjects)
    futures = []
    for subject, (orig_img, data_array) in iter_subjects:
        # Run model
        try:
            pred_data = pipeline.get_prediction(
                subject.orig_name, data_array, orig_img.header.get_zooms(), progress_callback
            )
            futures.append(
                pipeline.async_save_img(subject.segfile, pred_data, orig_img, dtype=np.int16)
            )
            bm = None
            store_brainmask = subject.can_resolve_filename(brainmask_name)
            store_aseg = subject.can_resolve_filename(aseg_name)
            if store_brainmask or store_aseg:
                LOGGER.info("Creating brainmask based on segmentation...")
                bm = dp.create_mask(copy.deepcopy(pred_data), 5, 4)
            if store_brainmask:
                # get mask
                mask_name = subject.filename_in_subject_folder(brainmask_name)
                futures.append(pipeline.async_save_img(mask_name, bm, orig_img, dtype=np.uint8))
            else:
                LOGGER.info(
                    "Not saving the brainmask, because we could not figure out where "
                    "to store it. Please specify a subject id with {sid[flag]}, or an "
                    "absolute brainmask path with {brainmask_name[flag]}.".format(
                        **subjects.flags,
                    )
                )

            if store_aseg:
                # reduce aparc to aseg and mask regions
                LOGGER.info("Creating aseg based on segmentation...")
                aseg = dp.reduce_to_aseg(pred_data)
                aseg[bm == 0] = 0
                aseg = dp.flip_wm_islands(aseg)
                aseg_name = subject.filename_in_subject_folder(aseg_name)
                futures.append(pipeline.async_save_img(aseg_name, aseg, orig_img, dtype=np.uint8))
            else:
                LOGGER.info(
                    "Not saving the aseg file, because we could not figure out where "
                    "to store it. Please specify a subject id with {sid[flag]}, or an "
                    "absolute aseg path with {aseg_name[flag]}.".format(
                        **subjects.flags,
                    )
                )

            # Run QC check
            LOGGER.info("Running volume-based QC check on segmentation...")
            seg_voxvol = np.prod(orig_img.header.get_zooms())
            if not check_volume(pred_data, seg_voxvol):
                LOGGER.warning(
                    "Total segmentation volume is too small. Segmentation may be corrupted."
                )
                if qc_file_handle is not None:
                    qc_file_handle.write(subject.id + "\n")
                    qc_file_handle.flush()
                qc_failed_subject_count += 1
        except RuntimeError as e:
            if not handle_cuda_memory_exception(e):
                LOGGER.error(f"Prediction failed: {e}")
                return str(e)

    if qc_file_handle is not None:
        qc_file_handle.close()

    # Batch case: report ratio of QC warnings
    if len(subjects) > 1:
        LOGGER.info(
            f"Segmentations from {qc_failed_subject_count} out of {len(subjects)} "
            f"processed cases failed the volume-based QC check."
        )

    # wait for async processes to finish
    for f in futures:
        _ = f.result()
    return 0
