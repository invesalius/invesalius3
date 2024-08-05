# --------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------
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
# --------------------------------------------------------------------
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import wx

import itertools


import invesalius.constants as const

def calc_width_needed(widget: "wx.Window", num_chars: int) -> int:

def list_fiducial_labels():
    """Return the list of marker labels denoting fiducials."""
    return list(
        itertools.chain(*(const.BTNS_IMG_MARKERS[i].values() for i in const.BTNS_IMG_MARKERS))
    )

# Given a string, try to parse it as an integer, float, or string.
#
# TODO: This shouldn't be here, but there's currently no good place for the function.
#   If csv-related functions are moved to a separate module, this function should be moved there.
def ParseValue(self, value):
    value = value.strip()

    # Handle None, booleans, empty list, and basic types
    if value == "None":
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    if value == "[]":
        return []

    # Handle lists and dictionaries
    if value.startswith("[") and value.endswith("]"):
        return self._parse_list(value)
    if value.startswith("{") and value.endswith("}"):
        return self._parse_dict(value)

    # Try to convert to int or float
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        # Handle quoted strings
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        return value  # Return as is if not recognized

def _parse_list(self, list_str):
    """Parse a list from string format."""
    return [
        self.ParseValue(el.strip())
        for el in self._split_by_outer_commas(list_str[1:-1].strip())
    ]

def _parse_dict(self, dict_str):
    """Parse a dictionary from string format."""
    items = self._split_by_outer_commas(dict_str[1:-1].strip())
    return {
        self.ParseValue(kv.split(":", 1)[0].strip()): self.ParseValue(
            kv.split(":", 1)[1].strip()
        )
        for kv in items
    }

def _split_by_outer_commas(self, string):
    """Split a string by commas that are not inside brackets or braces."""
    elements = []
    depth = 0
    current_element = []

    for char in string:
        if char in "[{":
            depth += 1
        elif char in "]}" and depth > 0:
            depth -= 1

        if char == "," and depth == 0:
            elements.append("".join(current_element).strip())
            current_element = []
        else:
            current_element.append(char)

    if current_element:
        elements.append("".join(current_element).strip())

    return elements

def GetMarkersFromFile(self, filename, overwrite_image_fiducials):
    try:
        with open(filename) as file:
            magick_line = file.readline()
            assert magick_line.startswith(const.MARKER_FILE_MAGICK_STRING)
            version = int(magick_line.split("_")[-1])
            if version not in const.SUPPORTED_MARKER_FILE_VERSIONS:
                wx.MessageBox(_("Unknown version of the markers file."), _("InVesalius 3"))
                return

            # Use the first line after the magick_line as the names for dictionary keys.
            column_names = file.readline().strip().split("\t")
            column_names_parsed = [self.ParseValue(name) for name in column_names]

            markers_data = []
            for line in file:
                values = line.strip().split("\t")
                values_parsed = [self.ParseValue(value) for value in values]
                marker_data = dict(zip(column_names_parsed, values_parsed))

                markers_data.append(marker_data)

        self.marker_list_ctrl.Hide()

        # Create markers from the dictionary.
        for data in markers_data:
            marker = Marker(version=version)
            marker.from_dict(data)

            # When loading markers from file, we first create a marker with is_target set to False, and then call __set_marker_as_target.
            marker.is_target = False

            # Note that we don't want to render or focus on the markers here for each loop iteration.
            self.markers.AddMarker(marker, render=False)

            if overwrite_image_fiducials and marker.label in self.__list_fiducial_labels():
                Publisher.sendMessage(
                    "Load image fiducials", label=marker.label, position=marker.position
                )

    except Exception as e:
        wx.MessageBox(_("Invalid markers file."), _("InVesalius 3"))
        utils.debug(e)

    self.marker_list_ctrl.Show()
    Publisher.sendMessage("Render volume viewer")
    Publisher.sendMessage("Update UI for refine tab")
    self.markers.SaveState()