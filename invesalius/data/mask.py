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

import os
import plistlib
import random
import shutil
import tempfile
import time
import weakref

import numpy as np
from scipy import ndimage

import invesalius.constants as const
import invesalius.data.converters as converters
import invesalius.session as ses
from invesalius.data.volume import VolumeMask
from invesalius.pubsub import pub as Publisher
from invesalius_cy import floodfill


class EditionHistoryNode:
    def __init__(self, index, orientation, array, clean=False):
        self.index = index
        self.orientation = orientation
        self.fd, self.filename = tempfile.mkstemp(suffix=".npy")
        self.clean = clean

        self._save_array(array)

    def _save_array(self, array):
        np.save(self.filename, array)
        print("Saving history", self.index, self.orientation, self.filename, self.clean)

    def commit_history(self, mvolume):
        array = np.load(self.filename)
        if self.orientation == "AXIAL":
            mvolume[self.index + 1, 1:, 1:] = array
            if self.clean:
                mvolume[self.index + 1, 0, 0] = 1
        elif self.orientation == "CORONAL":
            mvolume[1:, self.index + 1, 1:] = array
            if self.clean:
                mvolume[0, self.index + 1, 0] = 1
        elif self.orientation == "SAGITAL":
            mvolume[1:, 1:, self.index + 1] = array
            if self.clean:
                mvolume[0, 0, self.index + 1] = 1
        elif self.orientation == "VOLUME":
            mvolume[:] = array

        print("applying to", self.orientation, "at slice", self.index)

    def __del__(self):
        print("Removing", self.filename)
        os.close(self.fd)
        os.remove(self.filename)


class EditionHistory:
    def __init__(self, size=50):
        self.history = []
        self.index = -1
        self.size = size * 2

        Publisher.sendMessage("Enable undo", value=False)
        Publisher.sendMessage("Enable redo", value=False)

    def new_node(self, index, orientation, array, p_array, clean):
        # Saving the previous state, used to undo/redo correctly.
        p_node = EditionHistoryNode(index, orientation, p_array, clean)
        self.add(p_node)

        node = EditionHistoryNode(index, orientation, array, clean)
        self.add(node)

    def add(self, node):
        if self.index == self.size:
            self.history.pop(0)
            self.index -= 1

        if self.index < len(self.history):
            self.history = self.history[: self.index + 1]
        self.history.append(node)
        self.index += 1

        print("INDEX", self.index, len(self.history), self.history)
        Publisher.sendMessage("Enable undo", value=True)
        Publisher.sendMessage("Enable redo", value=False)

    def undo(self, mvolume, actual_slices=None):
        h = self.history
        if self.index > 0:
            # if self.index > 0 and h[self.index].clean:
            ##self.index -= 1
            ##h[self.index].commit_history(mvolume)
            # self._reload_slice(self.index - 1)
            if h[self.index - 1].orientation == "VOLUME":
                self.index -= 1
                h[self.index].commit_history(mvolume)
                self._reload_slice(self.index)
                Publisher.sendMessage("Enable redo", value=True)
            elif (
                actual_slices
                and actual_slices[h[self.index - 1].orientation] != h[self.index - 1].index
            ):
                self._reload_slice(self.index - 1)
            else:
                self.index -= 1
                h[self.index].commit_history(mvolume)
                if (
                    actual_slices
                    and self.index
                    and actual_slices[h[self.index - 1].orientation] == h[self.index - 1].index
                ):
                    self.index -= 1
                    h[self.index].commit_history(mvolume)
                self._reload_slice(self.index)
                Publisher.sendMessage("Enable redo", value=True)

        if self.index == 0:
            Publisher.sendMessage("Enable undo", value=False)
        print("AT", self.index, len(self.history), self.history[self.index].filename)

    def redo(self, mvolume, actual_slices=None):
        h = self.history
        if self.index < len(h) - 1:
            # if self.index < len(h) - 1 and h[self.index].clean:
            ##self.index += 1
            ##h[self.index].commit_history(mvolume)
            # self._reload_slice(self.index + 1)

            if h[self.index + 1].orientation == "VOLUME":
                self.index += 1
                h[self.index].commit_history(mvolume)
                self._reload_slice(self.index)
                Publisher.sendMessage("Enable undo", value=True)
            elif (
                actual_slices
                and actual_slices[h[self.index + 1].orientation] != h[self.index + 1].index
            ):
                self._reload_slice(self.index + 1)
            else:
                self.index += 1
                h[self.index].commit_history(mvolume)
                if (
                    actual_slices
                    and self.index < len(h) - 1
                    and actual_slices[h[self.index + 1].orientation] == h[self.index + 1].index
                ):
                    self.index += 1
                    h[self.index].commit_history(mvolume)
                self._reload_slice(self.index)
                Publisher.sendMessage("Enable undo", value=True)

        if self.index == len(h) - 1:
            Publisher.sendMessage("Enable redo", value=False)
        print("AT", self.index, len(h), h[self.index].filename)

    def _reload_slice(self, index):
        Publisher.sendMessage(
            ("Set scroll position", self.history[index].orientation),
            index=self.history[index].index,
        )

    def _config_undo_redo(self, visible):
        v_undo = False
        v_redo = False

        if self.history and visible:
            v_undo = True
            v_redo = True
            if self.index == 0:
                v_undo = False
            elif self.index == len(self.history) - 1:
                v_redo = False

        Publisher.sendMessage("Enable undo", value=v_undo)
        Publisher.sendMessage("Enable redo", value=v_redo)

    def clear_history(self):
        self.history = []
        self.index = -1
        Publisher.sendMessage("Enable undo", value=False)
        Publisher.sendMessage("Enable redo", value=False)


class Mask:
    general_index = -1

    def __init__(self):
        Mask.general_index += 1
        self.index = Mask.general_index
        self.matrix = None
        self.spacing = (1.0, 1.0, 1.0)
        self.imagedata = None
        self.colour = random.choice(const.MASK_COLOUR)
        self.opacity = const.MASK_OPACITY
        self.threshold_range = const.THRESHOLD_RANGE
        self.name = const.MASK_NAME_PATTERN % (Mask.general_index + 1)
        self.edition_threshold_range = [const.THRESHOLD_OUTVALUE, const.THRESHOLD_INVALUE]
        self.is_shown = 1
        self.edited_points = {}
        self.was_edited = False
        self.volume = None
        self.auto_update_mask = True
        self.modified_time = 0
        self.__bind_events()
        self._modified_callbacks = []

        self.history = EditionHistory()

    def __bind_events(self):
        Publisher.subscribe(self.OnFlipVolume, "Flip volume")
        Publisher.subscribe(self.OnSwapVolumeAxes, "Swap volume axes")

    def as_vtkimagedata(self):
        print("Converting to VTK")
        vimg = converters.to_vtk_mask(self.matrix, self.spacing)
        print("Converted")
        return vimg

    def set_colour(self, colour):
        self.colour = colour
        if self.volume is not None:
            self.volume.set_colour(colour)
            Publisher.sendMessage("Render volume viewer")

    def save_history(self, index, orientation, array, p_array, clean=False):
        self.history.new_node(index, orientation, array, p_array, clean)

    def undo_history(self, actual_slices):
        self.history.undo(self.matrix, actual_slices)
        self.modified()

        # Marking the project as changed
        session = ses.Session()
        session.ChangeProject()

    def redo_history(self, actual_slices):
        self.history.redo(self.matrix, actual_slices)
        self.modified()

        # Marking the project as changed
        session = ses.Session()
        session.ChangeProject()

    def on_show(self):
        self.history._config_undo_redo(self.is_shown)

        session = ses.Session()
        if session.mask_3d_preview:
            Publisher.sendMessage("Show mask preview", index=self.index, flag=bool(self.is_shown))
            Publisher.sendMessage("Render volume viewer")

    def create_3d_preview(self):
        if self.volume is None:
            if self.imagedata is None:
                self.imagedata = self.as_vtkimagedata()
            self.volume = VolumeMask(self)
            self.volume.create_volume()

    def _update_imagedata(self, update_volume_viewer=True):
        if self.imagedata is not None:
            dz, dy, dx = self.matrix.shape
            #  np_image = numpy_support.vtk_to_numpy(self.imagedata.GetPointData().GetScalars())
            #  np_image[:] = self.matrix.reshape(-1)
            self.imagedata.SetDimensions(dx - 1, dy - 1, dz - 1)
            self.imagedata.SetSpacing(self.spacing)
            self.imagedata.SetExtent(0, dx - 1, 0, dy - 1, 0, dz - 1)
            self.imagedata.Modified()
            self.volume._actor.Update()

            if update_volume_viewer:
                Publisher.sendMessage("Render volume viewer")

    def SavePlist(self, dir_temp, filelist):
        mask = {}
        filename = "mask_%d" % self.index
        mask_filename = f"{filename}.dat"
        # mask_filepath = os.path.join(dir_temp, mask_filename)
        filelist[self.temp_file] = mask_filename
        # self._save_mask(mask_filepath)

        mask["index"] = self.index
        mask["name"] = self.name
        mask["colour"] = self.colour[:3]
        mask["opacity"] = self.opacity
        mask["threshold_range"] = self.threshold_range
        mask["edition_threshold_range"] = self.edition_threshold_range
        mask["visible"] = self.is_shown
        mask["mask_file"] = mask_filename
        mask["mask_shape"] = self.matrix.shape
        mask["edited"] = self.was_edited

        plist_filename = filename + ".plist"
        # plist_filepath = os.path.join(dir_temp, plist_filename)

        temp_fd, temp_plist = tempfile.mkstemp()
        with open(temp_plist, "w+b") as f:
            plistlib.dump(mask, f)

        filelist[temp_plist] = plist_filename
        os.close(temp_fd)

        return plist_filename

    def OpenPList(self, filename):
        with open(filename, "r+b") as f:
            mask = plistlib.load(f, fmt=plistlib.FMT_XML)

        self.index = mask["index"]
        self.name = mask["name"]
        self.colour = mask["colour"]
        self.opacity = mask["opacity"]
        self.threshold_range = mask["threshold_range"]
        self.edition_threshold_range = mask["edition_threshold_range"]
        self.is_shown = mask["visible"]
        mask_file = mask["mask_file"]
        shape = mask["mask_shape"]
        self.was_edited = mask.get("edited", False)

        dirpath = os.path.abspath(os.path.split(filename)[0])
        path = os.path.join(dirpath, mask_file)
        self._open_mask(path, tuple(shape))

    def OnFlipVolume(self, axis):
        submatrix = self.matrix[1:, 1:, 1:]
        if axis == 0:
            submatrix[:] = submatrix[::-1]
            self.matrix[1::, 0, 0] = self.matrix[:0:-1, 0, 0]
        elif axis == 1:
            submatrix[:] = submatrix[:, ::-1]
            self.matrix[0, 1::, 0] = self.matrix[0, :0:-1, 0]
        elif axis == 2:
            submatrix[:] = submatrix[:, :, ::-1]
            self.matrix[0, 0, 1::] = self.matrix[0, 0, :0:-1]
        self.modified()

    def OnSwapVolumeAxes(self, axes):
        axis0, axis1 = axes
        self.matrix = self.matrix.swapaxes(axis0, axis1)
        if self.volume:
            self.imagedata = self.as_vtkimagedata()
            self.volume.change_imagedata()
        self.modified()

    def _save_mask(self, filename):
        shutil.copyfile(self.temp_file, filename)

    def _open_mask(self, filename, shape, dtype="uint8"):
        self.temp_file = filename
        self.matrix = np.memmap(filename, shape=shape, dtype=dtype, mode="r+")

    def _set_class_index(self, index):
        Mask.general_index = index

    def add_modified_callback(self, callback):
        ref = weakref.WeakMethod(callback)
        self._modified_callbacks.append(ref)

    def remove_modified_callback(self, callback):
        callbacks = []
        removed = False
        for cb in self._modified_callbacks:
            if cb() is not None:
                if cb() != callback:
                    callbacks.append(cb)
                else:
                    removed = True
        self._modified_callbacks = callbacks
        return removed

    def create_mask(self, shape):
        """
        Creates a new mask object. This method do not append this new mask into the project.

        Parameters:
            shape(int, int, int): The shape of the new mask.
        """
        self.temp_fd, self.temp_file = tempfile.mkstemp()
        shape = shape[0] + 1, shape[1] + 1, shape[2] + 1
        self.matrix = np.memmap(self.temp_file, mode="w+", dtype="uint8", shape=shape)

    def modified(self, all_volume=False):
        if all_volume:
            self.matrix[0] = 1
            self.matrix[:, 0, :] = 1
            self.matrix[:, :, 0] = 1

        session = ses.Session()
        if session.GetConfig("auto_reload_preview"):
            self._update_imagedata()

        self.modified_time = time.monotonic()
        callbacks = []
        for callback in self._modified_callbacks:
            if callback() is not None:
                callback()()
                callbacks.append(callback)
        self._modified_callbacks = callbacks

    def clean(self):
        self.matrix[1:, 1:, 1:] = 0
        self.modified(all_volume=True)

    def cleanup(self):
        if self.is_shown:
            self.history._config_undo_redo(False)
        if self.volume:
            Publisher.sendMessage("Unload volume", volume=self.volume._actor)
            Publisher.sendMessage("Render volume viewer")
            self.imagedata = None
            self.volume = None
        del self.matrix

    def copy(self, copy_name):
        """
        creates and return a copy from the mask instance.

        params:
            copy_name: the name from the copy
        """
        new_mask = Mask()
        new_mask.name = copy_name
        new_mask.colour = self.colour
        new_mask.opacity = self.opacity
        new_mask.threshold_range = self.threshold_range
        new_mask.edition_threshold_range = self.edition_threshold_range
        new_mask.is_shown = self.is_shown
        new_mask.was_edited = self.was_edited

        new_mask.create_mask(shape=[i - 1 for i in self.matrix.shape])
        new_mask.matrix[:] = self.matrix[:]
        new_mask.spacing = self.spacing

        return new_mask

    def clear_history(self):
        self.history.clear_history()

    def fill_holes_auto(self, target, conn, orientation, index, size):
        CON2D = {4: 1, 8: 2}
        CON3D = {6: 1, 18: 2, 26: 3}

        if target == "3D":
            cp_mask = self.matrix.copy()
            matrix = self.matrix[1:, 1:, 1:]
            bstruct = ndimage.generate_binary_structure(3, CON3D[conn])

            imask = ~(matrix > 127)
            labels, nlabels = ndimage.label(imask, bstruct, output=np.uint16)

            if nlabels == 0:
                return

            ret = floodfill.fill_holes_automatically(matrix, labels, nlabels, size)
            if ret:
                self.save_history(index, orientation, self.matrix.copy(), cp_mask)
        else:
            bstruct = ndimage.generate_binary_structure(2, CON2D[conn])

            if orientation == "AXIAL":
                matrix = self.matrix[index + 1, 1:, 1:]
            elif orientation == "CORONAL":
                matrix = self.matrix[1:, index + 1, 1:]
            elif orientation == "SAGITAL":
                matrix = self.matrix[1:, 1:, index + 1]

            cp_mask = matrix.copy()

            imask = ~(matrix > 127)
            labels, nlabels = ndimage.label(imask, bstruct, output=np.uint16)

            if nlabels == 0:
                return

            labels = labels.reshape(1, labels.shape[0], labels.shape[1])
            matrix = matrix.reshape(1, matrix.shape[0], matrix.shape[1])

            ret = floodfill.fill_holes_automatically(matrix, labels, nlabels, size)
            if ret:
                self.save_history(index, orientation, matrix.copy(), cp_mask)

    def __del__(self):
        # On Linux self.matrix is already removed so it gives an error
        try:
            del self.matrix
        except AttributeError:
            pass

        # Used for masks not loaded from plist project.
        try:
            os.close(self.temp_fd)
        except AttributeError:
            pass

        os.remove(self.temp_file)
