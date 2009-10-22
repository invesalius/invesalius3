# session.py


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
