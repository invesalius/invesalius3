#!/usr/bin/env python3
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
#-------------------------------------------------------------------------

try:
    import configparser as ConfigParser
except ImportError:
    import ConfigParser

import logging 
import logging.config 
from typing import Callable
import sys, os
import wx
import json

from invesalius import inv_paths
import invesalius.constants as const
#import invesalius.session as sess
from invesalius.utils import Singleton, deep_merge_dict
#from invesalius.pubsub import pub as Publisher

class CustomConsoleHandler(logging.StreamHandler):
    def __init__(self, textctrl):
        logging.StreamHandler.__init__(self)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.setFormatter(formatter)
        self.textctrl = textctrl

    def emit(self, record):
        print('Came to Emit ...')
        msg = self.format(record)
        stream = self.stream
        self.textctrl.WriteText(msg + "He He He\n")
        self.flush()

class RedirectText(object):
    def __init__(self, textctrl):
        self.out = textctrl
        
    def write(self, string):
        self.out.WriteText(string)

class MyPanel(wx.Panel):
    def __init__(self, parent, logger):
        wx.Panel.__init__(self, parent)
        
        logText = wx.TextCtrl(self,
                              style = wx.TE_MULTILINE|wx.TE_READONLY|wx.HSCROLL)
        
        btn = wx.Button(self, label="Close")
        btn.Bind(wx.EVT_BUTTON, self.onClose)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(logText, 1, wx.EXPAND|wx.ALL, 5)
        sizer.Add(btn, 0, wx.ALL, 5)
        self.SetSizer(sizer)
        
        #Below two lines 
        redir = RedirectText(logText)
        sys.stdout = redir
        
        txtHandler = CustomConsoleHandler(logText)

        #logger = Logger()
        #logging.getLogger(__name__)
        #logger.getLogger().addHandler(txtHandler)
        logger.addHandler(txtHandler)

    def onClose(self, event):
        logger = MyLogger()
        self.logger.info("Informational message")
     
class MyFrame(wx.Frame):
    def __init__(self, logger):
        wx.Frame.__init__(self, None, title="Log Console")
        panel = MyPanel(self, logger)
        #self.logger = getLogger() 
        self.Show()
        
LOG_PATH = os.path.join(inv_paths.USER_INV_DIR, 'log_config.json')

class MyLogger(metaclass=Singleton):
    def __init__(self):
        # create logger
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(logging.DEBUG)
        self._frame = None
        self._config = {
            'file_logging': 0,
            'file_logging_level': 0,
            'append_log_file': 0,
            'logging_file': '',
            'console_logging': 0,
            'console_logging_level': 0,
        }
        self.ReadConfig()

    def CreateConfig(self):
        self._frame = None
        self._config = {
            'file_logging': 0,
            'file_logging_level': 0,
            'append_log_file': 0,
            'logging_file': '',
            'console_logging': 0,
            'console_logging_level': 0,
        }

    def SetConfig(self, key, value):
        self._config[key] = value
        self.WriteConfigFile()

    def GetConfig(self, key, default_value=None):
        if key in self._config:
            return self._config[key]
        else:
            return default_value

    def ReadConfig(self, fPath=LOG_PATH):
        try:
            #self._read_config_from_json(fPath) 
            self._read_config_from_json(r'C:\\Users\\sohan\\.config\\invesalius\\log_config.json')
            print('Read Log config file ', fPath)
            print(self._config)
            self.configureLogging()
        except Exception as e1: 
            print('Log config file not found:', e1)
        return True
    
    def WriteConfigFile(self):
        self._write_to_json(self._config, LOG_PATH)

    def _write_to_json(self, config_dict, config_filename):
        with open(config_filename, 'w') as config_file:
            json.dump(config_dict, config_file, sort_keys=True, indent=4)

    def _read_config_from_json(self, json_filename):
        '''
        with open(json_filename, 'r') as config_file:
            config_dict = json.loads(config_file)
            self._config = deep_merge_dict(self._config.copy(), config_dict)
        '''
        try:
            config_file = open(json_filename, 'r')
            config_dict = json.load(config_file)
            self._config = deep_merge_dict(self._config.copy(), config_dict)
        except Exception as e1:
            print('Error in _read_config_from_json:', e1)
 
    def getLogger(self, lname=__name__):
        #logger = logging.getLogger(lname)
        return self._logger

    def logMessage(self,level, msg):
        level = level.upper()
        if (level=='DEBUG'):
            self._logger.debug(msg)
        elif (level=='WARNING'):
            self._logger.warning(msg)
        elif (level=='CRITICAL'):
            self._logger.critical(msg)
        elif (level=='ERROR'):
            self._logger.error(msg)
        else:  #'info'
            print('Came to info ...')
            self._logger.info(msg)

    def configureLogging(self):
        file_logging = self._config['file_logging']
        file_logging_level = self._config['file_logging_level']
        append_log_file = self._config['append_log_file']
        logging_file  = self._config['logging_file']
        console_logging = self._config['console_logging']
        #console_logging_level = self._config['console_logging_level']

        if ((self._frame == None) & (console_logging!=0)):
            print('Initiating console logging ...')
            self.closeLogging()
            self._frame = MyFrame(self.getLogger())
        
        logger = self.getLogger()
        msg = 'file_logging: {}, console_logging: {}'.format(file_logging, console_logging)
        print(msg)

        logger.info(msg)
        logger.info('configureLogging called ...')
        self.logMessage('info', msg)

        '''
        if console_logging:
            logger.info("console_logging called ...")
            closeConsoleLogging()
            # create formatter
            python_loglevel = getattr(logging,  const.LOGGING_LEVEL_TYPES[console_logging_level].upper(), None)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch = logging.StreamHandler(sys.stderr)
            ch.setLevel(python_loglevel)
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            logger.info('Added stream handler')
        else:
            closeConsoleLogging()
        '''

        if file_logging:
            print('file_logging called ...')
            logger.info('file_logging called ...')
            python_loglevel = getattr(logging,  const.LOGGING_LEVEL_TYPES[file_logging_level].upper(), None)

            # create formatter
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

            # create file handler 
            logger = self.getLogger()
            if logging_file:
                addFileHandler = True
                for handler in logger.handlers:
                    if isinstance(handler, logging.FileHandler):
                        if hasattr(handler, 'baseFilename') & \
                            os.path.samefile(logging_file,handler.baseFilename):
                            handler.setLevel(python_loglevel)
                            addFileHandler = False
                            msg = 'No change in log file name {}.'.format(logging_file)
                            logger.info(msg)
                        else:
                            msg = 'Closing current log file {} as new log file {} requested.'.format( \
                                handler.baseFilename, logging_file)
                            logger.info(msg)
                            logger.removeHandler(handler)
                            logger.info('Removed existing FILE handler')
                if addFileHandler:
                    if append_log_file:
                        fh = logging.FileHandler(logging_file, 'a', encoding=None)
                    else:
                        fh = logging.FileHandler(logging_file, 'w', encoding=None)
                    fh.setLevel(python_loglevel)
                    fh.setFormatter(formatter)
                    logger.addHandler(fh)
                    msg = 'Addeded file handler {}'.format(logging_file)
                    logger.info(msg)
        else:
            self.closeFileLogging()

    def closeFileLogging(self):
        logger = logging.getLogger(__name__)
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                msg = 'Removed file handler {}'.format(handler.baseFilename)
                logger.info(msg)
                #handler.flush()
                logger.removeHandler(handler)    

    def closeConsoleLogging(self):
        logger = logging.getLogger(__name__)
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                logger.info('Removed stream handler')
                #handler.flush()
                logger.removeHandler(handler)   
        if (self._frame != None):
            self._frame = None

    def closeLogging(self):
        self.closeConsoleLogging()
        self.closeFileLogging()  

    def flushHandlers(self):
        logger = logging.getLogger(__name__)
        for handler in logger.handlers:
            handler.flush()

def function_call_tracking_decorator(function: Callable[[str], None]):
    def wrapper_accepting_arguments(*args):
        logger = logging.getLogger(__name__)
        msg = 'Function {} called'.format(function.__name__)
        logger.info(msg)
        function(*args)
    return wrapper_accepting_arguments

            
################################################################################################