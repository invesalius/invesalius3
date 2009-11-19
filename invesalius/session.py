import constants as const
from utils import Singleton

class Session(object):
    # Only one project will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__= Singleton

    def __init__(self):
        self.project_status = const.NEW_PROJECT