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
DICOM metadata storage module.

This module provides JSON-based storage for DICOM metadata with support for
series-level and slice-level metadata separation, lazy loading, and search.
"""

import datetime
import gzip
import json
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MetadataValidationError(Exception):
    """Raised when metadata JSON validation fails."""

    pass


class MetadataStore:
    """
    Manages DICOM metadata storage and retrieval.

    Stores metadata in JSON format with separation between series-level
    (constant across slices) and slice-level (varying) metadata.
    Supports lazy loading for efficient memory usage.
    """

    SCHEMA_VERSION = "1.0"

    # Patient-identifying tags per DICOM PS 3.15 Annex E
    PATIENT_TAGS = {
        "0010|0010",  # Patient Name
        "0010|0020",  # Patient ID
        "0010|0030",  # Patient Birth Date
        "0010|0032",  # Patient Birth Time
        "0010|0040",  # Patient Sex
        "0010|1000",  # Other Patient IDs
        "0010|1001",  # Other Patient Names
        "0010|1005",  # Patient Birth Name
        "0010|1040",  # Patient Address
        "0010|1060",  # Patient Mother Birth Name
        "0010|2154",  # Patient Telephone Numbers
        "0010|2160",  # Patient Ethnic Group
        "0010|21B0",  # Additional Patient History
        "0010|4000",  # Patient Comments
    }

    def __init__(self, metadata_path: Optional[str] = None):
        """
        Initialize metadata store.

        Args:
            metadata_path: Path to metadata.json file (optional)
        """
        self._schema_version = self.SCHEMA_VERSION
        self._extraction_info = {}
        self._series_metadata = {}
        self._per_slice_metadata = []
        self._slice_metadata_cache = OrderedDict()  # LRU cache
        self._search_index = None
        self._json_path = metadata_path

        if metadata_path:
            self.load(metadata_path)

    def set_metadata(self, metadata: Dict[str, Any]):
        """
        Populate store from extracted metadata.

        Args:
            metadata: Dictionary with 'series_metadata' and 'per_slice_metadata'
        """
        self._series_metadata = metadata.get("series_metadata", {})
        self._per_slice_metadata = metadata.get("per_slice_metadata", [])
        self._extraction_info = metadata.get("extraction_info", {})

        # Invalidate search index
        self._search_index = None

    def to_json(self) -> str:
        """
        Convert metadata to JSON string.

        Returns:
            JSON string representation
        """
        data = {
            "schema_version": self._schema_version,
            "extraction_info": self._extraction_info,
            "series_metadata": self._series_metadata,
            "per_slice_metadata": self._per_slice_metadata,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def from_json(self, json_str: str):
        """
        Load metadata from JSON string.

        Args:
            json_str: JSON string

        Raises:
            MetadataValidationError: If JSON is invalid
        """
        try:
            data = json.loads(json_str)
            self._validate_schema(data)

            self._schema_version = data["schema_version"]
            self._extraction_info = data.get("extraction_info", {})
            self._series_metadata = data.get("series_metadata", {})
            self._per_slice_metadata = data.get("per_slice_metadata", [])

            # Invalidate caches
            self._slice_metadata_cache.clear()
            self._search_index = None

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            raise MetadataValidationError(f"Invalid JSON: {e}") from e
        except Exception as e:
            logger.error(f"Failed to load metadata from JSON: {e}")
            raise MetadataValidationError(f"Failed to load: {e}") from e

    def _validate_schema(self, data: Dict[str, Any]):
        """
        Validate JSON structure.

        Args:
            data: Parsed JSON data

        Raises:
            MetadataValidationError: If schema is invalid
        """
        # Check required fields
        required_fields = ["schema_version", "series_metadata", "per_slice_metadata"]
        for field in required_fields:
            if field not in data:
                raise MetadataValidationError(f"Missing required field: {field}")

        # Check schema version
        version = data["schema_version"]
        if not isinstance(version, str):
            raise MetadataValidationError("schema_version must be a string")

        # Check series_metadata is a dict
        if not isinstance(data["series_metadata"], dict):
            raise MetadataValidationError("series_metadata must be a dictionary")

        # Check per_slice_metadata is a list
        if not isinstance(data["per_slice_metadata"], list):
            raise MetadataValidationError("per_slice_metadata must be a list")

    def save(self, output_path: str, compress: bool = False):
        """
        Save metadata to JSON file.

        Args:
            output_path: Path to save metadata.json
            compress: Whether to compress JSON with gzip
        """
        try:
            json_str = self.to_json()

            if compress:
                # Save as gzipped JSON
                with gzip.open(output_path + ".gz", "wt", encoding="utf-8") as f:
                    f.write(json_str)
                logger.info(f"Saved compressed metadata to {output_path}.gz")
            else:
                # Save as plain JSON
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(json_str)
                logger.info(f"Saved metadata to {output_path}")

        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
            raise

    def load(self, input_path: str):
        """
        Load metadata from JSON file.

        Args:
            input_path: Path to metadata.json file

        Raises:
            MetadataValidationError: If file is invalid
        """
        try:
            # Check if file is gzipped
            if input_path.endswith(".gz"):
                with gzip.open(input_path, "rt", encoding="utf-8") as f:
                    json_str = f.read()
            else:
                with open(input_path, "r", encoding="utf-8") as f:
                    json_str = f.read()

            self.from_json(json_str)
            self._json_path = input_path
            logger.info(f"Loaded metadata from {input_path}")

        except FileNotFoundError:
            logger.error(f"Metadata file not found: {input_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to load metadata from {input_path}: {e}")
            raise MetadataValidationError(f"Failed to load: {e}") from e

    def get_slice_metadata(self, slice_index: int) -> Dict[str, Any]:
        """
        Get metadata for specific slice (lazy loaded).

        Args:
            slice_index: Index of slice

        Returns:
            Dictionary with tag information for that slice
        """
        # Check cache first
        if slice_index in self._slice_metadata_cache:
            # Move to end (most recently used)
            self._slice_metadata_cache.move_to_end(slice_index)
            return self._slice_metadata_cache[slice_index]

        # Load from per_slice_metadata
        if 0 <= slice_index < len(self._per_slice_metadata):
            metadata = self._per_slice_metadata[slice_index].get("tags", {})

            # Add to cache
            self._slice_metadata_cache[slice_index] = metadata

            # Evict old entries if cache too large (keep max 10 slices)
            if len(self._slice_metadata_cache) > 10:
                self._slice_metadata_cache.popitem(last=False)

            return metadata

        return {}

    def get_series_metadata(self) -> Dict[str, Any]:
        """
        Get series-level metadata (constant across slices).

        Returns:
            Dictionary with series-level tags
        """
        return self._series_metadata

    def get_all_tags(self) -> List[str]:
        """
        Get list of all tag identifiers.

        Returns:
            List of tag IDs in format 'GGGG|EEEE'
        """
        tags = set(self._series_metadata.keys())

        # Add tags from first slice (representative)
        if self._per_slice_metadata:
            first_slice_tags = self._per_slice_metadata[0].get("tags", {})
            tags.update(first_slice_tags.keys())

        return sorted(list(tags))

    def get_tag_info(self, tag_id: str, slice_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get information for a specific tag.

        Args:
            tag_id: Tag identifier in format 'GGGG|EEEE'
            slice_index: Slice index (for slice-specific tags)

        Returns:
            Dictionary with 'vr', 'value', 'name' or None if not found
        """
        # Check series metadata first
        if tag_id in self._series_metadata:
            return self._series_metadata[tag_id]

        # Check slice metadata
        slice_metadata = self.get_slice_metadata(slice_index)
        if tag_id in slice_metadata:
            return slice_metadata[tag_id]

        return None

    def identify_patient_tags(self) -> List[str]:
        """
        Identify tags containing patient information (for anonymization).

        Returns:
            List of patient-identifying tag IDs present in metadata
        """
        all_tags = set(self.get_all_tags())
        patient_tags = all_tags.intersection(self.PATIENT_TAGS)
        return sorted(list(patient_tags))

    def get_num_slices(self) -> int:
        """
        Get number of slices in the series.

        Returns:
            Number of slices
        """
        return len(self._per_slice_metadata)

    def _build_search_index(self):
        """
        Build search index for fast searching.

        Creates a searchable text index combining tag ID, name, and value.
        """
        self._search_index = {}

        # Index series metadata
        for tag_id, tag_info in self._series_metadata.items():
            searchable = self._make_searchable(tag_id, tag_info)
            self._search_index[tag_id] = searchable

        # Index slice metadata (from first slice as representative)
        if self._per_slice_metadata:
            first_slice_tags = self._per_slice_metadata[0].get("tags", {})
            for tag_id, tag_info in first_slice_tags.items():
                if tag_id not in self._search_index:
                    searchable = self._make_searchable(tag_id, tag_info)
                    self._search_index[tag_id] = searchable

        logger.debug(f"Built search index with {len(self._search_index)} tags")

    def _make_searchable(self, tag_id: str, tag_info: Dict[str, Any]) -> str:
        """
        Create searchable text from tag information.

        Args:
            tag_id: Tag identifier
            tag_info: Tag information dictionary

        Returns:
            Searchable text (lowercase)
        """
        parts = [tag_id, tag_info.get("name", ""), str(tag_info.get("value", ""))]
        return " ".join(parts).lower()

    def search(self, term: str, slice_index: int = 0) -> List[str]:
        """
        Search for tags matching the term.

        Args:
            term: Search term (case-insensitive)
            slice_index: Slice index for slice-specific search

        Returns:
            List of matching tag IDs
        """
        if self._search_index is None:
            self._build_search_index()

        term_lower = term.lower()
        results = []

        for tag_id, searchable_text in self._search_index.items():
            if term_lower in searchable_text:
                results.append(tag_id)

        return results

    def export_to_csv(self, filepath: str, slice_indices: Optional[List[int]] = None):
        """
        Export metadata to CSV file with streaming writes.

        Args:
            filepath: Output CSV path
            slice_indices: List of slice indices to export (None = all slices)
        """
        import csv

        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)

                # Write header
                writer.writerow(["Tag", "Name", "Value", "VR", "Slice Index"])

                # Determine which slices to export
                if slice_indices is None:
                    slice_indices = list(range(self.get_num_slices()))

                # Export series metadata (appears for all slices)
                for tag_id, tag_info in self._series_metadata.items():
                    value = self._format_csv_value(tag_info.get("value"))
                    vr = tag_info.get("vr", "")
                    name = tag_info.get("name", "")

                    for slice_idx in slice_indices:
                        writer.writerow([tag_id, name, value, vr, slice_idx])

                # Export slice-specific metadata
                for slice_idx in slice_indices:
                    slice_metadata = self.get_slice_metadata(slice_idx)

                    for tag_id, tag_info in slice_metadata.items():
                        value = self._format_csv_value(tag_info.get("value"))
                        vr = tag_info.get("vr", "")
                        name = tag_info.get("name", "")

                        writer.writerow([tag_id, name, value, vr, slice_idx])

            logger.info(f"Exported metadata to CSV: {filepath}")

        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            raise

    def _format_csv_value(self, value: Any) -> str:
        """
        Format value for CSV export.

        Args:
            value: Value to format

        Returns:
            Formatted string
        """
        if value is None:
            return ""

        # Handle binary data
        if isinstance(value, dict) and "encoding" in value:
            return f"[Binary data: {value.get('encoding')}]"

        # Handle lists
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)

        # Convert to string and clean
        value_str = str(value)
        value_str = value_str.replace("\x00", "").replace("\r", " ").replace("\n", " ")

        return value_str
