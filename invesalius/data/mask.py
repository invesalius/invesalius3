#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------

import os
import plistlib
import random
import shutil
import tempfile
import weakref

import numpy
import vtk

import constants as const
import imagedata_utils as iu

from wx.lib.pubsub import pub as Publisher


class EditionHistoryNode(object):
    def __init__(self, index, orientation, array, clean=False):
        self.index = index
        self.orientation = orientation
        self.filename = tempfile.mktemp(suffix='.npy')
        self.clean = clean

        self._save_array(array)

    def _save_array(self, array):
        numpy.save(self.filename, array)
        print "Saving history", self.index, self.orientation, self.filename, self.clean

    def commit_history(self, mvolume):
        array = numpy.load(self.filename)
        if self.orientation == 'AXIAL':
            mvolume[self.index+1,1:,1:] = array
            if self.clean:
                mvolume[self.index+1, 0, 0] = 1
        elif self.orientation == 'CORONAL':
            mvolume[1:, self.index+1, 1:] = array
            if self.clean:
                mvolume[0, self.index+1, 0] = 1
        elif self.orientation == 'SAGITAL':
            mvolume[1:, 1:, self.index+1] = array
            if self.clean:
                mvolume[0, 0, self.index+1] = 1

        print "applying to", self.orientation, "at slice", self.index

    def __del__(self):
        print "Removing", self.filename
        os.remove(self.filename)


class EditionHistory(object):
    def __init__(self, size=50):
        self.history = []
        self._copies = weakref.WeakValueDictionary()
        self.index = -1
        self.size = size

        Publisher.sendMessage("Enable undo", False)
        Publisher.sendMessage("Enable redo", False)

    def new_node(self, index, orientation, array, p_array, clean):
        try:
            p_node = self.history[self.index]
        except IndexError:
            p_node = None

        if self.index == -1 or (orientation != p_node.orientation or p_node.index != index): 
            try:
                node = self._copies[(orientation, index)]
            except KeyError:
                node = EditionHistoryNode(index, orientation, p_array, clean)
                self._copies[(orientation, index)] = node
            self.add(node)

        node = EditionHistoryNode(index, orientation, array, clean)
        self._copies[(orientation, index)] = node
        self.add(node)

    def add(self, node):
        if self.index == self.size:
            self.history.pop(0)
            self.index -= 1

        if self.index < len(self.history):
            self.history = self.history[:self.index + 1]
        self.history.append(node)
        self.index += 1

        print "INDEX", self.index, len(self.history), self.history
        Publisher.sendMessage("Enable undo", True)
        Publisher.sendMessage("Enable redo", False)

    def undo(self, mvolume, actual_slices=None):
        h = self.history
        if self.index > 0:
            #if self.index > 0 and h[self.index].clean:
                ##self.index -= 1
                ##h[self.index].commit_history(mvolume)
                #self._reload_slice(self.index - 1)
            if actual_slices and actual_slices[h[self.index - 1].orientation] != h[self.index - 1].index:
                self._reload_slice(self.index - 1)
            else:
                self.index -= 1
                h[self.index].commit_history(mvolume)
                if actual_slices and self.index and actual_slices[h[self.index - 1].orientation] == h[self.index - 1].index:
                    self.index -= 1
                    h[self.index].commit_history(mvolume)
                self._reload_slice(self.index)
                Publisher.sendMessage("Enable redo", True)
        
        if self.index == 0:
            Publisher.sendMessage("Enable undo", False)
        print "AT", self.index, len(self.history), self.history[self.index].filename

    def redo(self, mvolume, actual_slices=None):
        h = self.history
        if self.index < len(h) - 1:
            #if self.index < len(h) - 1 and h[self.index].clean:
                ##self.index += 1
                ##h[self.index].commit_history(mvolume)
                #self._reload_slice(self.index + 1)

            if actual_slices and actual_slices[h[self.index + 1].orientation] != h[self.index + 1].index:
                self._reload_slice(self.index + 1)
            else:
                self.index += 1
                h[self.index].commit_history(mvolume)
                if actual_slices and self.index < len(h) - 1 and actual_slices[h[self.index + 1].orientation] == h[self.index + 1].index:
                    self.index += 1
                    h[self.index].commit_history(mvolume)
                self._reload_slice(self.index)
                Publisher.sendMessage("Enable undo", True)
        
        if self.index == len(h) - 1:
            Publisher.sendMessage("Enable redo", False)
        print "AT", self.index, len(h), h[self.index].filename

    def _reload_slice(self, index):
        Publisher.sendMessage(('Set scroll position', self.history[index].orientation),
                              self.history[index].index)

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
            
        Publisher.sendMessage("Enable undo", v_undo)
        Publisher.sendMessage("Enable redo", v_redo)

    def clear_history(self):
        self.history = []
        self.index = -1
        Publisher.sendMessage("Enable undo", False)
        Publisher.sendMessage("Enable redo", False)


class Mask():
    general_index = -1
    def __init__(self):
        Mask.general_index += 1
        self.index = Mask.general_index
        self.imagedata = ''
        self.colour = random.choice(const.MASK_COLOUR)
        self.opacity = const.MASK_OPACITY
        self.threshold_range = const.THRESHOLD_RANGE
        self.name = const.MASK_NAME_PATTERN %(Mask.general_index+1)
        self.edition_threshold_range = [const.THRESHOLD_OUTVALUE, const.THRESHOLD_INVALUE]
        self.is_shown = 1
        self.edited_points = {}
        self.was_edited = False
        self.__bind_events()

        self.history = EditionHistory()

    def __bind_events(self):
        Publisher.subscribe(self.OnFlipVolume, 'Flip volume')
        Publisher.subscribe(self.OnSwapVolumeAxes, 'Swap volume axes')

    def save_history(self, index, orientation, array, p_array, clean=False):
        self.history.new_node(index, orientation, array, p_array, clean)

    def undo_history(self, actual_slices):
        self.history.undo(self.matrix, actual_slices)

    def redo_history(self, actual_slices):
        self.history.redo(self.matrix, actual_slices)

    def on_show(self):
        self.history._config_undo_redo(self.is_shown)

    def SavePlist(self, dir_temp, filelist):
        mask = {}
        filename = u'mask_%d' % self.index 
        mask_filename = u'%s.dat' % filename
        mask_filepath = os.path.join(dir_temp, mask_filename)
        filelist[self.temp_file] = mask_filename
        #self._save_mask(mask_filepath)

        mask['index'] = self.index
        mask['name'] = self.name
        mask['colour'] = self.colour
        mask['opacity'] = self.opacity
        mask['threshold_range'] = self.threshold_range
        mask['edition_threshold_range'] = self.edition_threshold_range
        mask['visible'] = self.is_shown
        mask['mask_file'] = mask_filename
        mask['mask_shape'] = self.matrix.shape

        plist_filename = filename + '.plist'
        #plist_filepath = os.path.join(dir_temp, plist_filename)

        temp_plist = tempfile.mktemp()
        plistlib.writePlist(mask, temp_plist)

        filelist[temp_plist] = plist_filename

        return plist_filename

    def OpenPList(self, filename):
        mask = plistlib.readPlist(filename)

        self.index = mask['index']
        self.name = mask['name']
        self.colour = mask['colour']
        self.opacity = mask['opacity']
        self.threshold_range = mask['threshold_range']
        self.edition_threshold_range = mask['edition_threshold_range']
        self.is_shown = mask['visible']
        mask_file = mask['mask_file']
        shape = mask['mask_shape']
        dirpath = os.path.abspath(os.path.split(filename)[0])
        path = os.path.join(dirpath, mask_file)
        self._open_mask(path, tuple(shape))

    def OnFlipVolume(self, pubsub_evt):
        axis = pubsub_evt.data
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

    def OnSwapVolumeAxes(self, pubsub_evt):
        axis0, axis1 = pubsub_evt.data
        self.matrix = self.matrix.swapaxes(axis0, axis1)
        print type(self.matrix)

    def _save_mask(self, filename):
        shutil.copyfile(self.temp_file, filename)

    def _open_mask(self, filename, shape, dtype='uint8'):
        print ">>", filename, shape
        self.temp_file = filename
        self.matrix = numpy.memmap(filename, shape=shape, dtype=dtype, mode="r+")

    def _set_class_index(self, index):
        Mask.general_index = index

    def create_mask(self, shape):
        print "Creating a mask"
        self.temp_file = tempfile.mktemp()
        shape = shape[0] + 1, shape[1] + 1, shape[2] + 1
        self.matrix = numpy.memmap(self.temp_file, mode='w+', dtype='uint8', shape=shape)

    def clear_history(self):
        self.history.clear_history()

    def __del__(self):
        if self.is_shown:
            self.history._config_undo_redo(False)
