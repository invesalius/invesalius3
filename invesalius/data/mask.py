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

import vtk

import constants as const
import imagedata_utils as iu

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

    def SavePlist(self, filename):
        mask = {}
        filename = '%s$%s$%d' % (filename, 'mask', self.index)
        d = self.__dict__
        for key in d:
            if isinstance(d[key], vtk.vtkImageData):
                img_name = '%s_%s.vti' % (filename, key)
                iu.Export(d[key], img_name, bin=True)
                mask[key] = {'$vti': img_name}
            elif key == 'edited_points':
                edited_points = {}
                for p in self.edited_points:
                    edited_points[str(p)] = self.edited_points[p]
                mask[key] = edited_points
            else:
                mask[key] = d[key]
        plistlib.writePlist(mask, filename + '.plist')
        return filename + '.plist'

    def OpenPList(self, filename):
        mask = plistlib.readPlist(filename)
        dirpath = os.path.abspath(os.path.split(filename)[0])
        for key in mask:
            print "Key", key
            if key == 'imagedata':
                filepath = os.path.split(mask[key]["$vti"])[-1]
                path = os.path.join(dirpath, filepath)
                self.imagedata = iu.Import(path)
            elif key == 'edited_points':
                edited_points = {}
                for p in mask[key]:
                    k = [float(i) for i in p.replace('(', '').replace(')', '').split(',')]
                    edited_points[tuple(k)] = mask[key][p]
                    
                setattr(self, key, edited_points)
            else:
                setattr(self, key, mask[key])

    def _set_class_index(self, index):
        Mask.general_index = index
