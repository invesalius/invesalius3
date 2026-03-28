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

"""
DICOM metadata extraction module.

This module provides comprehensive DICOM metadata extraction using pydicom or GDCM
as backend libraries. It extracts all DICOM tags from all slices in a series and
prepares them for JSON storage.
"""

import base64
import datetime
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MetadataExtractionError(Exception):
    """Raised when metadata extraction fails."""

    pass


class MetadataExtractor:
    """
    Extracts DICOM metadata using available backend library.

    Supports pydicom (preferred) and GDCM (fallback) as backend libraries.
    Extracts all DICOM tags including private and vendor-specific tags.
    """

    def __init__(self, backend: str = "auto"):
        """
        Initialize extractor with specified backend.

        Args:
            backend: 'auto', 'pydicom', or 'gdcm'
                    'auto' will detect and use the best available backend

        Raises:
            MetadataExtractionError: If specified backend is not available
        """
        if backend == "auto":
            self.backend = self.detect_backend()
        else:
            if backend not in ("pydicom", "gdcm"):
                raise MetadataExtractionError(f"Invalid backend: {backend}")

            # Verify the specified backend is available
            if backend == "pydicom":
                try:
                    import pydicom

                    self.backend = "pydicom"
                except ImportError:
                    raise MetadataExtractionError("pydicom is not installed")
            elif backend == "gdcm":
                try:
                    import gdcm

                    self.backend = "gdcm"
                except ImportError:
                    raise MetadataExtractionError("GDCM Python bindings are not installed")

        logger.info(f"MetadataExtractor initialized with backend: {self.backend}")

    @staticmethod
    def detect_backend() -> str:
        """
        Detect which DICOM library is available.

        Returns:
            'pydicom', 'gdcm', or 'none'

        Priority order:
            1. pydicom (preferred - pure Python, widely used)
            2. GDCM (fallback - C++ library, faster for large datasets)
        """
        # Try pydicom first (preferred)
        try:
            import pydicom

            logger.info("Detected pydicom backend")
            return "pydicom"
        except ImportError:
            pass

        # Try GDCM as fallback
        try:
            import gdcm

            logger.info("Detected GDCM backend")
            return "gdcm"
        except ImportError:
            pass

        logger.warning("No DICOM backend library found (pydicom or GDCM)")
        return "none"

    def extract_from_file(self, dicom_file: str) -> Dict[str, Any]:
        """
        Extract metadata from single DICOM file.

        Args:
            dicom_file: Path to DICOM file

        Returns:
            Dictionary with tag information in format:
            {
                'tag_id': {
                    'vr': 'VR_TYPE',
                    'value': value,
                    'name': 'Tag Name'
                }
            }

        Raises:
            MetadataExtractionError: If file cannot be read
        """
        if self.backend == "none":
            raise MetadataExtractionError("No DICOM backend available")

        try:
            if self.backend == "pydicom":
                return self._extract_with_pydicom(dicom_file)
            elif self.backend == "gdcm":
                return self._extract_with_gdcm(dicom_file)
        except Exception as e:
            logger.error(f"Failed to extract metadata from {dicom_file}: {e}")
            raise MetadataExtractionError(f"Extraction failed: {e}") from e

    def _extract_with_pydicom(self, dicom_file: str) -> Dict[str, Any]:
        """
        Extract metadata using pydicom backend.

        Args:
            dicom_file: Path to DICOM file

        Returns:
            Dictionary with tag information
        """
        import pydicom
        from pydicom.datadict import dictionary_description

        # Read DICOM file
        ds = pydicom.dcmread(dicom_file, force=True)

        metadata = {}

        # Iterate through all data elements
        for elem in ds:
            # Format tag as GGGG|EEEE
            tag_id = f"{elem.tag.group:04X}|{elem.tag.element:04X}"

            # Get tag name from DICOM dictionary
            tag_name = dictionary_description(elem.tag)
            if not tag_name:
                tag_name = "Unknown"

            # Get VR (Value Representation)
            vr = elem.VR

            # Get value and handle different types
            value = self._process_value(elem.value, vr)

            metadata[tag_id] = {"vr": vr, "value": value, "name": tag_name}

        return metadata

    def _extract_with_gdcm(self, dicom_file: str) -> Dict[str, Any]:
        """
        Extract metadata using GDCM backend.

        Args:
            dicom_file: Path to DICOM file

        Returns:
            Dictionary with tag information
        """
        import gdcm

        # Read DICOM file
        reader = gdcm.Reader()
        reader.SetFileName(dicom_file)

        if not reader.Read():
            raise MetadataExtractionError(f"GDCM failed to read file: {dicom_file}")

        file_dataset = reader.GetFile()
        dataset = file_dataset.GetDataSet()

        metadata = {}

        # Iterate through all data elements
        iterator = dataset.GetDES().begin()
        while not iterator.equal(dataset.GetDES().end()):
            data_element = iterator.value()
            tag = data_element.GetTag()

            # Format tag as (GGGG,EEEE)
            tag_id = f"({tag.GetGroup():04X},{tag.GetElement():04X})"

            # Get VR from the data element itself
            vr = str(data_element.GetVR())

            # Get tag name from dictionary
            dict_entry = gdcm.Global.GetInstance().GetDicts().GetDictEntry(tag)
            tag_name = dict_entry.GetName() if dict_entry else "Unknown"
            if not tag_name or tag_name == "":
                tag_name = "Unknown"

            # Get value
            value = self._get_gdcm_value(data_element, vr)

            metadata[tag_id] = {"vr": vr, "value": value, "name": tag_name}

            iterator.next()

        return metadata

    def _process_value(self, value: Any, vr: str) -> Any:
        """
        Process DICOM value for JSON storage.

        Handles different value types including binary data, sequences, etc.

        Args:
            value: Raw DICOM value
            vr: Value Representation

        Returns:
            Processed value suitable for JSON storage
        """
        # Handle None
        if value is None:
            return None

        # Handle binary data (encode as base64)
        if vr in ("OB", "OW", "OD", "OF", "OL", "UN"):
            if isinstance(value, bytes):
                # Limit binary data to 1MB
                if len(value) > 1024 * 1024:
                    logger.warning(f"Binary data exceeds 1MB, truncating")
                    value = value[: 1024 * 1024]
                return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
            return str(value)

        # Handle sequences (nested datasets)
        if vr == "SQ":
            return "[Sequence]"  # Simplified for now

        # Handle multi-valued elements
        if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            try:
                return list(value)
            except:
                return str(value)

        # Handle numeric types
        if isinstance(value, (int, float)):
            return value

        # Convert everything else to string
        return str(value)

    def _get_gdcm_value(self, data_element, vr: str) -> Any:
        """
        Get value from GDCM data element.

        Args:
            data_element: GDCM DataElement
            vr: Value Representation

        Returns:
            Processed value
        """
        import gdcm

        # Handle binary data
        if vr in ("OB", "OW", "OD", "OF", "OL", "UN"):
            byte_value = data_element.GetByteValue()
            if byte_value:
                # Get bytes
                buffer = byte_value.GetBuffer()
                # Handle both string and bytes (GDCM version differences)
                if isinstance(buffer, str):
                    buffer = buffer.encode("latin1")
                if len(buffer) > 1024 * 1024:
                    logger.warning(f"Binary data exceeds 1MB, truncating")
                    buffer = buffer[: 1024 * 1024]
                return {"encoding": "base64", "data": base64.b64encode(buffer).decode("ascii")}
            return None

        # Handle sequences
        if vr == "SQ":
            return "[Sequence]"

        # Get string value
        byte_value = data_element.GetByteValue()
        if byte_value:
            buffer = byte_value.GetBuffer()
            # Handle both string and bytes (GDCM version differences)
            if isinstance(buffer, bytes):
                return buffer.decode("utf-8", errors="replace").strip()
            elif isinstance(buffer, str):
                return buffer.strip()
            else:
                return str(buffer).strip()

        return None

    def extract_from_files(self, dicom_files: List[str]) -> Dict[str, Any]:
        """
        Extract metadata from list of DICOM files with series/slice separation.

        Analyzes tags across all slices to identify constant (series-level) vs
        varying (slice-level) tags.

        Args:
            dicom_files: List of paths to DICOM files

        Returns:
            Dictionary with 'series_metadata', 'per_slice_metadata', and 'extraction_info'
        """
        if not dicom_files:
            return {
                "extraction_info": self._get_extraction_info(),
                "series_metadata": {},
                "per_slice_metadata": [],
            }

        logger.info(f"Extracting metadata from {len(dicom_files)} DICOM files")

        # Extract metadata from all files
        all_metadata = []
        for i, dicom_file in enumerate(dicom_files):
            try:
                metadata = self.extract_from_file(dicom_file)
                all_metadata.append(metadata)

                if (i + 1) % 50 == 0:
                    logger.info(f"Processed {i + 1}/{len(dicom_files)} files")

            except MetadataExtractionError as e:
                logger.error(f"Failed to extract from {dicom_file}: {e}")
                # Continue with remaining files
                all_metadata.append({})

        # Separate series-level and slice-level metadata
        series_metadata, per_slice_metadata = self._separate_metadata(all_metadata)

        logger.info(
            f"Extraction complete: {len(series_metadata)} series tags, "
            f"{len(per_slice_metadata)} slices"
        )

        return {
            "extraction_info": self._get_extraction_info(),
            "series_metadata": series_metadata,
            "per_slice_metadata": per_slice_metadata,
        }

    def _separate_metadata(self, all_metadata: List[Dict[str, Any]]) -> tuple:
        """
        Separate constant (series) and varying (slice) metadata.

        Args:
            all_metadata: List of metadata dictionaries, one per slice

        Returns:
            Tuple of (series_metadata, per_slice_metadata)
        """
        if not all_metadata:
            return {}, []

        # Get all unique tags across all slices
        all_tags = set()
        for metadata in all_metadata:
            all_tags.update(metadata.keys())

        # Identify constant tags (same value across all slices)
        series_tags = {}
        varying_tags = set()

        for tag_id in all_tags:
            # Get values for this tag across all slices
            values = []
            for metadata in all_metadata:
                if tag_id in metadata:
                    values.append(self._normalize_value(metadata[tag_id]["value"]))

            # Check if all values are the same
            if len(values) > 0 and len(set(map(str, values))) == 1:
                # Constant tag - add to series metadata
                # Use first occurrence
                for metadata in all_metadata:
                    if tag_id in metadata:
                        series_tags[tag_id] = metadata[tag_id]
                        break
            else:
                # Varying tag - will be in slice metadata
                varying_tags.add(tag_id)

        # Build per-slice metadata with only varying tags
        per_slice_metadata = []
        for i, metadata in enumerate(all_metadata):
            slice_tags = {}
            for tag_id in varying_tags:
                if tag_id in metadata:
                    slice_tags[tag_id] = metadata[tag_id]

            per_slice_metadata.append({"slice_index": i, "tags": slice_tags})

        return series_tags, per_slice_metadata

    def _normalize_value(self, value: Any) -> Any:
        """
        Normalize value for comparison.

        Args:
            value: Value to normalize

        Returns:
            Normalized value
        """
        # Handle lists
        if isinstance(value, list):
            return tuple(value)

        # Handle dicts (binary data)
        if isinstance(value, dict):
            return str(value)

        return value

    def _get_extraction_info(self) -> Dict[str, Any]:
        """
        Get extraction information for metadata.

        Returns:
            Dictionary with backend, extraction_date, etc.
        """
        import invesalius.constants as const

        return {
            "backend": self.backend,
            "extraction_date": datetime.datetime.now().isoformat(),
            "invesalius_version": const.INVESALIUS_VERSION
            if hasattr(const, "INVESALIUS_VERSION")
            else "unknown",
        }
