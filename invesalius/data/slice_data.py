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
import vtk

import constants as const
import vtk_utils as vu

class SliceData(object):
    def __init__(self):
        self.actor = None
        self.cursor = None
        self.number = 0
        self.orientation = 'AXIAL'
        self.renderer = None
        self.__create_text()

    def __create_text(self):
        colour = const.ORIENTATION_COLOUR[self.orientation]

        text = vu.Text()
        text.SetColour(colour)
        text.SetSize(const.TEXT_SIZE_LARGE)
        text.SetPosition(const.TEXT_POS_LEFT_DOWN)
        text.SetVerticalJustificationToBottom()
        text.SetValue(self.number)
        self.text = text

    def SetCursor(self, cursor):
        if self.cursor:
            self.renderer.RemoveActor(self.cursor.actor)
        self.renderer.AddActor(cursor.actor)
        self.cursor = cursor

    def SetNumber(self, number):
        self.number = number
        self.text.SetValue("%d" % self.number)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        colour = const.ORIENTATION_COLOUR[self.orientation]
        self.text.SetColour(colour)

    def Hide(self):
        self.renderer.RemoveActor(self.actor)
        self.renderer.RemoveActor(self.text.actor)

    def Show(self):
        self.renderer.AddActor(self.actor)
        self.renderer.AddActor(self.text.actor)
