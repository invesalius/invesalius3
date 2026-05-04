# Copyright 2023 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import logging
import os
import sys
from concurrent.futures import Executor, Future
from dataclasses import MISSING, Field, dataclass, fields
from dataclasses import field as _dataclass_field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    TypeVar,
    Union,
    overload,
)


@dataclass
class ModelConfig:
    """Model configuration"""

    NUM_CLASSES: int = 79
    MODEL_NAME: str = "FastSurferVINN"
    HEIGHT: int = 256
    WIDTH: int = 256
    OUT_TENSOR_WIDTH: int = 256
    OUT_TENSOR_HEIGHT: int = 256
    NUM_CHANNELS: int = 7
    BASE_RES: float = 1.0


@dataclass
class DataConfig:
    """Data configuration"""

    PLANE: str = ""
    PADDED_SIZE: int = 320
    SIZES: List[int] = None

    def __post_init__(self):
        if self.SIZES is None:
            self.SIZES = [256, 311, 320]


@dataclass
class TestConfig:
    """Test configuration"""

    BATCH_SIZE: int = 1


@dataclass
class Config:
    """Main configuration object"""

    MODEL: ModelConfig
    DATA: DataConfig
    TEST: TestConfig
    RNG_SEED: int = 42


def create_config(plane: str, batch_size: int = 1) -> Config:
    """create a configuration object."""
    return Config(
        MODEL=ModelConfig(), DATA=DataConfig(PLANE=plane), TEST=TestConfig(BATCH_SIZE=batch_size)
    )


VoxSizeOption = Union[float, Literal["min"]]

PlaneAxial = Literal["axial"]
PlaneCoronal = Literal["coronal"]
PlaneSagittal = Literal["sagittal"]
Plane = Union[PlaneAxial, PlaneCoronal, PlaneSagittal]
PLANES: Tuple[PlaneAxial, PlaneCoronal, PlaneSagittal] = ("axial", "coronal", "sagittal")

LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")
_Ti = TypeVar("_Ti")


def get_num_threads():
    """
    Determine the number of available threads.

    Tries to get the process's CPU affinity for usable thread count; defaults
    to total CPU count on failure.

    Returns
    -------
    int
        Number of threads available to the process or total CPU count.
    """
    try:
        from os import sched_getaffinity as __getaffinity

        return len(__getaffinity(0))
    except ImportError:
        from os import cpu_count

        return cpu_count()


@overload
def field(
    *,
    default: _T,
    help: str = "",
    flags: Tuple[str, ...] = (),
    init: bool = True,
    repr: bool = True,
    hash: Union[bool, None] = None,
    compare: bool = True,
    metadata: Union[Mapping[Any, Any], None] = None,
    kw_only: bool = ...,
) -> _T: ...


@overload
def field(
    *,
    help: str = "",
    flags: Tuple[str, ...] = (),
    init: bool = True,
    repr: bool = True,
    hash: Union[bool, None] = None,
    compare: bool = True,
    metadata: Union[Mapping[Any, Any], None] = None,
    kw_only: bool = ...,
) -> Any: ...


def field(
    *,
    default: _T = MISSING,
    default_factory: Callable[[], _T] = MISSING,
    help: str = "",
    flags: Tuple[str, ...] = (),
    init: bool = True,
    repr: bool = True,
    hash: Union[bool, None] = None,
    compare: bool = True,
    metadata: Union[Mapping[Any, Any], None] = None,
    kw_only: Union[bool, None] = None,
) -> _T:
    """
    Extends dataclasses.field to add help and flags to the metadata.

    Parameters
    ----------
    help : str, default=""
        A help string to be used in argparse description of parameters.
    flags : tuple of str, default=()
        A list of default flags to add for this attribute.

    Returns
    -------
    When used in dataclasses, returns the field.

    See Also
    --------
    dataclasses.field
    """
    if isinstance(metadata, Mapping):
        metadata = dict(metadata)
    elif metadata is None:
        metadata = {}
    else:
        raise TypeError("Invalid type of metadata, must be a Mapping!")

    if help:
        if not isinstance(help, str):
            raise TypeError("help must be a str!")
        metadata["help"] = help
    if flags:
        if not isinstance(flags, tuple):
            raise TypeError("flags must be a tuple!")
        metadata["flags"] = flags

    kwargs = dict(init=init, repr=repr, hash=hash, compare=compare)

    # Check the Python version for kw_only support
    if sys.version_info >= (3, 10) and kw_only is not None:
        kwargs["kw_only"] = kw_only

    if default is not MISSING:
        kwargs["default"] = default
    if default_factory is not MISSING:
        kwargs["default_factory"] = default_factory
    return _dataclass_field(**kwargs, metadata=metadata)


def get_field(dc, fieldname: str) -> Union[Field, None]:
    """
    Return a specific Field object associated with a dataclass class or object.

    Parameters
    ----------
    dc : dataclass, type[dataclass]
        The dataclass containing the field.
    fieldname : str
        The name of the field.

    Returns
    -------
    Field, None
        The Field object associated with fieldname or None if the field does not exist.

    See Also
    --------
    dataclasses.fields
    """
    for field_obj in fields(dc):
        if field_obj.name == fieldname:
            return field_obj
    return None


def handle_cuda_memory_exception(exception: BaseException) -> bool:
    """
    Handle CUDA out of memory exception and print a help text.

    Parameters
    ----------
    exception : builtins.BaseException
        Received exception.

    Returns
    -------
    bool
        Whether the exception was a RuntimeError caused by Cuda out memory.
    """
    if not isinstance(exception, RuntimeError):
        return False
    message = exception.args[0]
    if message.startswith("CUDA out of memory. "):
        LOGGER.critical("ERROR - INSUFFICIENT GPU MEMORY")
        LOGGER.info(
            "The memory requirements exceeds the available GPU memory, try using a "
            "smaller batch size (--batch_size <int>) and/or view aggregation on the "
            "cpu (--viewagg_device 'cpu')."
        )
        LOGGER.info(
            "Note: View Aggregation on the GPU is particularly memory-hungry at "
            "approx. 5 GB for standard 256x256x256 images."
        )
        memory_message = message[message.find("(") + 1 : message.find(")")]
        LOGGER.info(f"Using {memory_message}.")
        return True
    else:
        return False


def pipeline(
    pool: Executor,
    func: Callable[[_Ti], _T],
    iterable: Iterable[_Ti],
    *,
    pipeline_size: int = 1,
) -> Iterator[Tuple[_Ti, _T]]:
    """
    Pipeline a function to be executed in the pool.

    Analogous to iterate, but run func in a different
    thread for the next element while the current element is returned.

    Parameters
    ----------
    pool : Executor
        Thread pool executor for parallel execution.
    func : callable
        Function to use.
    iterable : Iterable
        Iterable containing input elements.
    pipeline_size : int, default=1
        Size of the processing pipeline.

    Yields
    ------
    element : _Ti
        Elements
    _T
        Results of func corresponding to element: func(element).
    """
    # do pipeline loading the next element
    from collections import deque

    futures_queue = deque()
    import itertools

    for i, element in zip(itertools.count(-pipeline_size), iterable):
        # pre-load next element/data
        futures_queue.append((element, pool.submit(func, element)))
        if i >= 0:
            element, future = futures_queue.popleft()
            yield element, future.result()
    while len(futures_queue) > 0:
        element, future = futures_queue.popleft()
        yield element, future.result()


class SerialExecutor(Executor):
    """
    Represent a serial executor.
    """

    def map(
        self,
        fn: Callable[..., _T],
        *iterables: Iterable[Any],
        timeout: Union[float, None] = None,
        chunksize: int = -1,
    ) -> Iterator[_T]:
        """
        The map function.

        Parameters
        ----------
        fn : Callable[..., _T]
            A callable function to be applied to the items in the iterables.
        *iterables : Iterable[Any]
            One or more iterable objects.
        timeout : Optional[float]
            Maximum number of seconds to wait for a result. Default is None.
        chunksize : int
            The size of the chunks, default value is -1.

        Returns
        -------
        Iterator[_T]
            An iterator that yields the results of applying 'fn' to the items of
            'iterables'.
        """
        return map(fn, *iterables)

    def submit(self, __fn: Callable[..., _T], *args, **kwargs) -> "Future[_T]":
        """
        A callable function that returns a Future representing the result.

        Parameters
        ----------
        __fn : Callable[..., _T]
            A callable function to be executed.
        *args :
            Potential arguments to be passed to the callable function.
        **kwargs :
            Keyword arguments to be passed to the callable function.

        Returns
        -------
        "Future[_T]"
            A Future object representing the execution result of the callable function.
        """
        f = Future()
        try:
            f.set_result(__fn(*args, **kwargs))
        except Exception as e:
            f.set_exception(e)
        return f


class SubjectDirectory:
    """
    Represent a subject directory.
    """

    _orig_name: str
    _copy_orig_name: str
    _conf_name: str
    _segfile: str
    _asegdkt_segfile: str
    _main_segfile: str
    _subject_dir: str
    _id: str

    def __init__(self, **kwargs):
        """
        Create a subject, supports generic attributes.

        Parameters
        ----------
        id : str
            The subject id.
        orig_name : str
            Relative or absolute filename of the orig filename.
        conf_name : str
            Relative or absolute filename of the conformed filename.
        segfile : str
            Relative or absolute filename of the segmentation filename.
        main_segfile : str
            Relative or absolute filename of the main segmentation filename.
        asegdkt_segfile : str
            Relative or absolute filename of the aparc+aseg segmentation filename.
        subject_dir : Path
            Path to the subjects directory (containing subject folders).
        """
        for k, v in kwargs.items():
            if k == "subject_dir" and v is not None:
                v = Path(v)
            setattr(self, "_" + k, v)

    def filename_in_subject_folder(self, filepath: Union[str, Path]) -> Path:
        """
        Return the full path to the file.

        Parameters
        ----------
        filepath : str, Path
            Absolute to the file or name of the file.

        Returns
        -------
        Path
            Path to the file.
        """
        if Path(filepath).is_absolute():
            return Path(filepath)
        else:
            return self.subject_dir / self._id / filepath

    def filename_by_attribute(self, attr_name: str) -> Path:
        """
        Retrieve a filename based on the provided attribute name.

        Parameters
        ----------
        attr_name : str
            The name of the attribute associated with the desired filename.

        Returns
        -------
        Path
            The filename corresponding to the provided attribute name.
        """
        return self.filename_in_subject_folder(self.get_attribute(attr_name))

    def fileexists_in_subject_folder(self, filepath: Union[str, Path]) -> bool:
        """
        Check if file exists in the subject folder.

        Parameters
        ----------
        filepath : Path, str
            Path to the file.

        Returns
        -------
        bool
            Whether the file exists or not.
        """
        return self.filename_in_subject_folder(filepath).exists()

    def fileexists_by_attribute(self, attr_name: str) -> bool:
        """
        Check if a file exists based on the provided attribute name.

        Parameters
        ----------
        attr_name : str
            The name of the attribute associated with the file existence check.

        Returns
        -------
        bool
            Whether the file exists or not.
        """
        return self.fileexists_in_subject_folder(self.get_attribute(attr_name))

    @property
    def subject_dir(self) -> Path:
        """
        Gets the subject directory name.

        Returns
        -------
        Path
            The set subject directory.
        """
        assert hasattr(self, "_subject_dir") or "The folder attribute has not been set!"
        return Path(self._subject_dir)

    @subject_dir.setter
    def subject_dir(self, _folder: Union[str, Path]):
        """
        Set the subject directory name.

        Parameters
        ----------
        _folder : str, Path
            The subject directory.
        """
        self._subject_dir = _folder

    @property
    def id(self) -> str:
        """
        Get the id.

        Returns
        -------
        str
            The id.
        """
        assert hasattr(self, "_id") or "The id attribute has not been set!"
        return self._id

    @id.setter
    def id(self, _id: str):
        """
        Set the id.

        Parameters
        ----------
        _id : str
            The id.
        """
        self._id = _id

    @property
    def orig_name(self) -> str:
        """
        Try to return absolute path.

        If the native_t1_file is a relative path, it will be
        interpreted as relative to folder.

        Returns
        -------
        str
            The orig name.
        """
        assert hasattr(self, "_orig_name") or "The orig_name attribute has not been set!"
        return self._orig_name

    @orig_name.setter
    def orig_name(self, _orig_name: str):
        """
        Set the orig name.

        Parameters
        ----------
        _orig_name : str
            The orig name.
        """
        self._orig_name = _orig_name

    @property
    def copy_orig_name(self) -> Path:
        """
        Try to return absolute path.

        If the copy_orig_t1_file is a relative path, it will be
        interpreted as relative to folder.

        Returns
        -------
        Path
            The copy of orig name.
        """
        assert hasattr(self, "_copy_orig_name") or "The copy_orig_name attribute has not been set!"
        return self.filename_in_subject_folder(self._copy_orig_name)

    @copy_orig_name.setter
    def copy_orig_name(self, _copy_orig_name: str):
        """
        Set the copy of orig name.

        Parameters
        ----------
        _copy_orig_name : str
            The copy of the orig name.

        Returns
        -------
        str
            Original name.
        """
        self._copy_orig_name = _copy_orig_name

    @property
    def conf_name(self) -> Path:
        """
        Try to return absolute path.

        If the conformed_t1_file is a relative path, it will be
        interpreted as relative to folder.

        Returns
        -------
        Path
            The path to the conformed image file.
        """
        assert hasattr(self, "_conf_name") or "The conf_name attribute has not been set!"
        return self.filename_in_subject_folder(self._conf_name)

    @conf_name.setter
    def conf_name(self, _conf_name: str):
        """
        Set the path to the conformed image.

        Parameters
        ----------
        _conf_name : str
            Path to the conformed image.

        """
        self._conf_name = _conf_name

    @property
    def segfile(self) -> Path:
        """
        Try to return absolute path.

        If the segfile is a relative path, it will be interpreted as relative to folder.

        Returns
        -------
        Path
            Path to the segfile.
        """
        assert hasattr(self, "_segfile") or "The _segfile attribute has not been set!"
        return self.filename_in_subject_folder(self._segfile)

    @segfile.setter
    def segfile(self, _segfile: str):
        """
        Set segfile.

        Parameters
        ----------
        _segfile : str
            Path to the segmentation file.
        """
        self._segfile = _segfile

    @property
    def asegdkt_segfile(self) -> Path:
        """
        Try to return absolute path.

        If the asegdkt_segfile is a relative path, it will be
        interpreted as relative to folder.

        Returns
        -------
        Path
            Path to segmentation file.
        """
        assert hasattr(self, "_segfile") or "The asegdkt_segfile attribute has not been set!"
        return self.filename_in_subject_folder(self._asegdkt_segfile)

    @asegdkt_segfile.setter
    def asegdkt_segfile(self, _asegdkt_segfile: Union[str, Path]):
        """
        Set path to segmentation file.

        Parameters
        ----------
        _asegdkt_segfile : Path, str
            Path to segmentation file.
        """
        self._asegdkt_segfile = str(_asegdkt_segfile)

    @property
    def main_segfile(self) -> Path:
        """
        Try to return absolute path.

        If the main_segfile is a relative path, it will be
        interpreted as relative to folder.

        Returns
        -------
        Path
            Path to the main segfile.

        """
        assert hasattr(self, "_main_segfile") or "The main_segfile attribute has not been set!"
        return self.filename_in_subject_folder(self._main_segfile)

    @main_segfile.setter
    def main_segfile(self, _main_segfile: str):
        """
        Set the main segfile.

        Parameters
        ----------
        _main_segfile : str
            Path to the main_segfile.
        """
        self._main_segfile = _main_segfile

    def can_resolve_filename(self, filename: str) -> bool:
        """
        Check whether we can resolve the file name.

        Parameters
        ----------
        filename : str
            Name of the filename to check.

        Returns
        -------
        bool
            Whether we can resolve the file name.
        """
        return os.path.isabs(filename) or self._subject_dir is not None

    def can_resolve_attribute(self, attr_name: str) -> bool:
        """
        Check whether we can resolve the attribute.

        Parameters
        ----------
        attr_name : str
            Name of the attribute to check.

        Returns
        -------
        bool
            Whether we can resolve the attribute.
        """
        return self.can_resolve_filename(self.get_attribute(attr_name))

    def has_attribute(self, attr_name: str) -> bool:
        """
        Check if the attribute is set.

        Parameters
        ----------
        attr_name : str
            Name of the attribute to check.

        Returns
        -------
        bool
            Whether the attribute exists or not.
        """
        return getattr(self, "_" + attr_name, None) is not None

    def get_attribute(self, attr_name: str) -> Union[str, Path]:
        """
        Give the requested attribute.

        Parameters
        ----------
        attr_name : str
            Name of the attribute to return.

        Returns
        -------
        str, Path
            The value of the requested attribute.

        Raises
        ------
        AttributeError
            If the subject has no attribute with the given name.
        """
        if not self.has_attribute(attr_name):
            raise AttributeError(f"The subject has no attribute named {attr_name}.")
        return getattr(self, "_" + attr_name)


class SubjectList:
    """
    Represent a list of subjects for processing.

    This is a simplified version that includes only the essential functionality
    needed by the FastSuper inference pipeline.
    """

    def __init__(self, config: "SubjectDirectoryConfig", **assign):
        """
        Initialize SubjectList.

        Parameters
        ----------
        config : SubjectDirectoryConfig
            Configuration object containing subject directory parameters.
        **assign
            Additional attribute mappings for SubjectDirectory objects.
        """
        self.config = config
        self._subjects = []
        self._flags = {}

        assign.setdefault("segfile", "pred_name")
        assign.setdefault("orig_name", "orig_name")
        assign.setdefault("conf_name", "conf_name")

        if hasattr(config, "orig_name") and config.orig_name:
            # Build subject parameters using the assignment mapping like the original
            subject_parameters = {}
            for subject_attribute, config_attribute in assign.items():
                if hasattr(config, config_attribute):
                    subject_parameters[subject_attribute] = getattr(config, config_attribute)

            subject = SubjectDirectory(
                id=getattr(config, "sid", "subject"),
                subject_dir=getattr(config, "out_dir", None),
                **subject_parameters,
            )
            self._subjects.append(subject)

    def __len__(self) -> int:
        """Return the number of subjects."""
        return len(self._subjects)

    def __iter__(self) -> Iterator[SubjectDirectory]:
        """Iterate over subjects."""
        return iter(self._subjects)

    def make_subjects_dir(self):
        """
        Try to create the subject directory.
        """
        if self.config.out_dir is None:
            LOGGER.info("No Subjects directory found, absolute paths for filenames are required.")
            return

        LOGGER.info(f"Output will be stored in Subjects Directory: {self.config.out_dir}")

        if not os.path.exists(self.config.out_dir):
            LOGGER.info("Output directory does not exist. Creating it now...")
            os.makedirs(self.config.out_dir)

    @property
    def flags(self) -> Dict[str, dict]:
        """
        Give the flags.

        Returns
        -------
        dict[str, dict]
            Flags.
        """
        return self._flags

    def __getitem__(self, item: Union[int, str]) -> SubjectDirectory:
        """
        Return a SubjectDirectory object for the i-th subject (if item is an int) or for
        the subject with the given name (if item is a str).

        Parameters
        ----------
        item : int, str
            Index or name of the subject.

        Returns
        -------
        SubjectDirectory
            A SubjectDirectory object corresponding to the provided index or name.
        """
        if isinstance(item, int):
            return self._subjects[item]
        elif isinstance(item, str):
            for subject in self._subjects:
                if subject.id == item:
                    return subject
            raise KeyError(f"Subject with id '{item}' not found")
        else:
            raise TypeError(f"Item must be int or str, not {type(item)}")


@dataclass
class SubjectDirectoryConfig:
    """
    This class describes the 'minimal' parameters used by SubjectList.

    Notes
    -----
    Important:
    Data Types of fields should stay `Optional[<TYPE>]` and not be replaced by `<TYPE> | None`, so the Parser can use
    the type in argparse as the value for `type` of `parser.add_argument()` (`Optional` is a callable, while `Union` is
    not).
    """

    orig_name: str = field(
        default="mri/orig.mgz",
    )
    pred_name: str = field(
        default="mri/aparc.DKTatlas+aseg.deep.mgz",
    )
    conf_name: str = field(
        default="mri/orig.mgz",
    )

    in_dir: Optional[Path] = field(  # noqa: UP007
        default=None,
    )
    csv_file: Optional[Path] = field(  # noqa: UP007
        default=None,
    )
    sid: Optional[str] = field(  # noqa: UP007
        default=None,
    )
    search_tag: str = field(
        default="*",
    )
    brainmask_name: str = field(
        default="mri/mask.mgz",
    )
    remove_suffix: str = field(
        default="",
    )
    out_dir: Optional[Path] = field(  # noqa: UP007
        default=None,
    )
    copy_orig_name: str = field(
        default="mri/orig/001.mgz",
    )
