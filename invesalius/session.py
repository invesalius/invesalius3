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



class Session(object)
    def __init__(self):
        self.project_state = const.PROJ_FREE
        # const.PROJ_FREE
        # const.PROJ_OPEN
        # const.PROJ_CHANGE
        self.language = const.DEFAULT_LANG # en
        self.imagedata_reformat = const.DEFAULT_REFORMAT # 1
        self.layout = const.DEFAULT_LAYOUT #
                                           # const.LAYOUT_RAPID_PROTOTYPING,
                                           # const.LAYOUT_RADIOLOGY,
                                           # const.LAYOUT_NEURO_NAVIGATOR,
                                           # const.LAYOUT_ODONTOLOGY




# USE PICKLE / PLIST !!!!!!
# external - possibly inside controller
#    def SetFileName(self, filename)
#        # try to load config file from home/.invesalius
#        load = self.Load(filename)
#            if load:
#                config = InVesaliusConfig
        
#    def Load(self, filename):
#        # TODO: which file representation?
#        # config?
#        # plist?
#        pass
