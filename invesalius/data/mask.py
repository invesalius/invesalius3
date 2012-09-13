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

import numpy
import vtk

import constants as const
import imagedata_utils as iu

from wx.lib.pubsub import pub as Publisher

class Mask():
    general_index = -1
    def __init__(self):
        Mask.general_index += 1
        self.index = Mask.general_index
        self.imagedata = '' # vtkImageData
        self.colour = random.choice(const.MASK_COLOUR)
        self.opacity = const.MASK_OPACITY
        self.threshold_range = const.THRESHOLD_RANGE
        self.name = const.MASK_NAME_PATTERN %(Mask.general_index+1)
        self.edition_threshold_range = [const.THRESHOLD_OUTVALUE, const.THRESHOLD_INVALUE]
        self.is_shown = 1
        self.edited_points = {}
        self.was_edited = False
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnFlipVolume, 'Flip volume')
        Publisher.subscribe(self.OnSwapVolumeAxes, 'Swap volume axes')

    def SavePlist(self, dir_temp):
        mask = {}
        filename = u'mask_%d' % self.index 
        mask_filename = u'%s.dat' % filename
        mask_filepath = os.path.join(dir_temp, mask_filename)
        self._save_mask(mask_filepath)

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
        plist_filepath = os.path.join(dir_temp, plist_filename)
        plistlib.writePlist(mask, plist_filepath)
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
