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

import logging 
import logging.config 
from typing import Callable
import sys, os
import wx
import json

from datetime import datetime

from invesalius import inv_paths
import invesalius.constants as const
from invesalius.utils import Singleton, deep_merge_dict

LOG_CONFIG_PATH = os.path.join(inv_paths.USER_INV_DIR, 'log_config.json')
DEFAULT_LOGFILE = os.path.join(inv_paths.USER_LOG_DIR,datetime.now().strftime("invlog-%Y_%m_%d-%I_%M_%S_%p.log"))

class MyConsoleHandler(logging.StreamHandler):
    def __init__(self, textctrl):
        logging.StreamHandler.__init__(self)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.setFormatter(formatter)
        self.textctrl = textctrl

    def emit(self, record):
        msg = self.format(record)
        stream = self.stream
        self.textctrl.WriteText(msg + "\n")
        self.flush()

class MyRedirectText(object):
    def __init__(self, textctrl):
        self.out = textctrl
        
    def write(self, string):
        self.out.WriteText(string)

class MyPanel(wx.Panel):
    def __init__(self, parent, logger):
        wx.Panel.__init__(self, parent)
        
        logText = wx.TextCtrl(self, style = wx.TE_MULTILINE|wx.TE_READONLY|wx.HSCROLL)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(logText, 1, wx.EXPAND|wx.ALL, 5)
        #sizer.Add(btn, 0, wx.ALL, 5)
        self.SetSizer(sizer)
        self._parent = parent
     
        redir = MyRedirectText(logText)
        sys.stdout = redir
        #sys.stderr = redir

        self._logger = logger
        txtHandler = MyConsoleHandler(logText)
        self._logger.addHandler(txtHandler)

    def onClose(self, event):
        self._logger.info("MyPanel window close selected.")
        self._parent.Iconify()
        
     
class MyFrame(wx.Frame):
    def __init__(self, logger):
        wx.Frame.__init__(self, None, title="Log Console", 
                    style=wx.DEFAULT_FRAME_STYLE & (~wx.CLOSE_BOX) & (~wx.MAXIMIZE_BOX))
        self._panel = MyPanel(self, logger)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Show()
        
    #To be tested
    def onClose(self, event):
        self._logger.info("MyFrame window close selected.")
        self.Hide()

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
            'logging_file': DEFAULT_LOGFILE,
            'console_logging': 0,
            'console_logging_level': 0,
        }
        self.ReadConfigFile()
        self._logger.setLevel(logging.DEBUG)

    def SetConfig(self, key, value):
        self._config[key] = value
        self.WriteConfigFile()

    def GetConfig(self, key, default_value=None):
        if key in self._config:
            return self._config[key]
        else:
            return default_value

    def ReadConfigFile(self, fPath=LOG_CONFIG_PATH):
        try:
            print(fPath, os.path.abspath(fPath))
            self._read_config_from_json(fPath) 
            #self._read_config_from_json(r'C:\\Users\\hrish\\.config\\invesalius\\log_config.json')
            print('Read Log config file ', fPath)
            print(self._config)
            #self.configureLogging()
        except Exception as e1: 
            print('Error reading config file in ReadConfigFile:', e1)
        return True
    
    def WriteConfigFile(self):
        self._write_to_json(self._config, LOG_CONFIG_PATH)

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
            #print('Came to info ...')
            self._logger.info(msg)

    def configureLogging(self):
        file_logging = self._config['file_logging']
        file_logging_level = self._config['file_logging_level']
        append_log_file = self._config['append_log_file']
        logging_file  = self._config['logging_file']
        logging_file = os.path.abspath(logging_file)
        print('logging_file:', logging_file)
        console_logging = self._config['console_logging']
        #console_logging_level = self._config['console_logging_level']

        if ((self._frame == None) & (console_logging!=0)):
            print('Initiating console logging ...')
            self._frame = MyFrame(self.getLogger())
            print('Initiated console logging ...')
            self._logger.info('Initiated console logging ...')
       
        msg = 'file_logging: {}, console_logging: {}'.format(file_logging, console_logging)
        print(msg)

        self._logger.info(msg)
        self._logger.info('configureLogging called ...')
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
            self._logger.info('file_logging called ...')
            python_loglevel = getattr(logging,  const.LOGGING_LEVEL_TYPES[file_logging_level].upper(), None)

            # create formatter
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

            # create file handler 
            if logging_file:
                addFileHandler = True
                for handler in self._logger.handlers:
                    if isinstance(handler, logging.FileHandler):
                        if hasattr(handler, 'baseFilename') & \
                            os.path.samefile(logging_file,handler.baseFilename):
                            handler.setLevel(python_loglevel)
                            addFileHandler = False
                            msg = 'No change in log file name {}.'.format(logging_file)
                            self._logger.info(msg)
                        else:
                            msg = 'Closing current log file {} as new log file {} requested.'.format( \
                                handler.baseFilename, logging_file)
                            self._logger.info(msg)
                            self._logger.removeHandler(handler)
                            self._logger.info('Removed existing FILE handler')
                if addFileHandler:
                    if append_log_file:
                        fh = logging.FileHandler(os.path.abspath(logging_file), 'a', encoding=None)
                    else:
                        fh = logging.FileHandler(os.path.abspath(logging_file), 'w', encoding=None)
                    #fh.setLevel(python_loglevel)
                    fh.setFormatter(formatter)
                    self._logger.addHandler(fh)
                    msg = 'Added file handler {}'.format(logging_file)
                    self._logger.info(msg)
        else:
            self.closeFileLogging()

    def closeFileLogging(self):
        for handler in self._logger.handlers:
            if isinstance(handler, logging.FileHandler):
                msg = 'Removed file handler {}'.format(handler.baseFilename)
                self._logger.info(msg)
                #handler.flush()
                self._logger.removeHandler(handler)    

    def closeConsoleLogging(self):
        for handler in self._logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                self._logger.info('Removed stream handler')
                #handler.flush()
                self._logger.removeHandler(handler)   
        if (self._frame != None):
            self._frame = None

    def closeLogging(self):
        self.closeFileLogging()  
        self.closeConsoleLogging()

    def flushHandlers(self):
        for handler in self._logger.handlers:
            handler.flush()

def function_call_tracking_decorator(function: Callable[[str], None]):
    def wrapper_accepting_arguments(*args):
        logger = MyLogger() 
        msg = 'Function {} called'.format(function.__name__)
        logger._logger.info(msg)
        function(*args)
    return wrapper_accepting_arguments

            
################################################################################################

invLogger = MyLogger()
#invLogger.configureLogging()

################################################################################################

