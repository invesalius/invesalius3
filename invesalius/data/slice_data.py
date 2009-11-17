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

class SliceData(object):
    def __init__(self):
        self.renderer = None
        self.actor = None
        self.number = 0
        self.cursor = None
        self.__create_text()

    def __create_text(self):
        text_property = vtk.vtkTextProperty()
        text_property.SetFontSize(16)
        text_property.SetFontFamilyToTimes()
        text_property.BoldOn()
        #text_property.SetColor(colour)

        text_actor = vtk.vtkTextActor()
        text_actor.SetInput("%d" % self.number)
        text_actor.GetTextProperty().ShallowCopy(text_property)
        text_actor.SetPosition(1,1)
        self.text_actor = text_actor

    def SetNumber(self, number):
        self.number = number
        self.text_actor.SetInput("%d" % self.number)

    def SetCursor(self, cursor):
        if self.cursor:
            self.renderer.RemoveActor(self.cursor.actor)
        self.renderer.AddActor(cursor.actor)
        self.cursor = cursor

    def Hide(self):
        self.renderer.RemoveActor(self.actor)
        self.renderer.RemoveActor(self.text_actor)

    def Show(self):
        self.renderer.AddActor(self.actor)
        self.renderer.AddActor(self.text_actor)
