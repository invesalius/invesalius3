#!/usr/bin/env python3
# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# -------------------------------------------------------------------------

import json
import logging
import logging.config
import os
import sys
from datetime import datetime
from functools import wraps
from typing import Callable, Dict, List

import wx

import invesalius.constants as const
from invesalius import inv_paths
from invesalius.utils import deep_merge_dict

LOG_CONFIG_PATH = os.path.join(inv_paths.USER_INV_DIR, "log_config.json")
DEFAULT_LOGFILE = os.path.join(
    inv_paths.USER_LOG_DIR, datetime.now().strftime("invlog-%Y_%m_%d-%I_%M_%S_%p.log")
)

actionDictionary00 = {
    "TypeError": "invLogger._logger.error('raise TypeError')",
    "ZeroDivisionError": "invLogger._logger.error('Exception ZeroDivisionError found in {func.__name__} call')",
}


class ConsoleLogHandler(logging.StreamHandler):
    def __init__(self, textctrl):
        logging.StreamHandler.__init__(self)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.setFormatter(formatter)
        self.textctrl = textctrl

    def emit(self, record):
        msg = self.format(record)
        # stream = self.stream
        if invLogger._config["console_logging"] == 1:
            self.textctrl.WriteText(msg + "\n")
            self.flush()


class ConsoleRedirectText:
    def __init__(self, textctrl):
        self.out = textctrl

    def write(self, string):
        self.out.WriteText(string)

    def flush(self):
        pass


class ConsoleLogPanel(wx.Panel):
    def __init__(self, parent, logger):
        wx.Panel.__init__(self, parent)

        logText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(logText, 1, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)
        self._parent = parent

        redir = ConsoleRedirectText(logText)
        sys.stdout = redir
        # sys.stderr = redir

        self._logger = logger
        txtHandler = ConsoleLogHandler(logText)
        self._logger.addHandler(txtHandler)

    def onClose(self, event):
        self._logger.info("ConsoleLogPanel window close selected.")
        self._parent.Iconify()


class ConsoleLogFrame(wx.Frame):
    def __init__(self, logger):
        wx.Frame.__init__(
            self,
            None,
            title="Log Console",
            style=wx.DEFAULT_FRAME_STYLE & (~wx.CLOSE_BOX) & (~wx.MAXIMIZE_BOX),
        )
        self._panel = ConsoleLogPanel(self, logger)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Show()

    # To be tested
    def onClose(self, event):
        self._logger.info("ConsoleLogFrame window close selected.")
        self.Hide()


class InvesaliusLogger:  # metaclass=Singleton):
    def __init__(self):
        # create logger
        self._logger = logging.getLogger(__name__)

        self._frame = None
        self._config = {
            "file_logging": 0,
            "file_logging_level": 0,
            "append_log_file": 0,
            "logging_file": DEFAULT_LOGFILE,
            "console_logging": 0,
            "console_logging_level": 0,
            "base_logging_level": logging.DEBUG,
            #'logging_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            "logging_format": "%(asctime)s - %(levelname)s - %(message)s",
        }
        self.ReadConfigFile()
        self._logger.setLevel(self._config["base_logging_level"])

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
            print("Reading Log config file ", fPath)
            print(self._config)
        except Exception as e1:
            print("Error reading config file in ReadConfigFile:", e1)
        return True

    def WriteConfigFile(self):
        self._write_to_json(self._config, LOG_CONFIG_PATH)

    def _write_to_json(self, config_dict, config_filename):
        with open(config_filename, "w") as config_file:
            json.dump(config_dict, config_file, sort_keys=True, indent=4)

    def _read_config_from_json(self, json_filename):
        try:
            config_file = open(json_filename)
            config_dict = json.load(config_file)
            self._config = deep_merge_dict(self._config.copy(), config_dict)
        except Exception as e1:
            print("Error in _read_config_from_json:", e1)

    def getLogger(self, lname=__name__):
        # logger = logging.getLogger(lname)
        return self._logger

    def logMessage(self, level, msg):
        level = level.upper()
        if level == "DEBUG":
            self._logger.debug(msg)
        elif level == "WARNING":
            self._logger.warning(msg)
        elif level == "CRITICAL":
            self._logger.critical(msg)
        elif level == "ERROR":
            self._logger.error(msg)
        else:  #'info'
            self._logger.info(msg)

    def configureLogging(self):
        file_logging = self._config["file_logging"]
        file_logging_level = self._config["file_logging_level"]
        append_log_file = self._config["append_log_file"]
        logging_file = self._config["logging_file"]
        logging_file = os.path.abspath(logging_file)
        print("logging_file:", logging_file)
        console_logging = self._config["console_logging"]
        # console_logging_level = self._config["console_logging_level"]

        self._logger.setLevel(self._config["base_logging_level"])

        if (self._frame is None) & (console_logging != 0):
            print("Initiating console logging ...")
            # self._frame = ConsoleLogFrame(self.getLogger())

            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            ch = logging.StreamHandler(sys.stderr)
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(formatter)
            self._logger.addHandler(ch)

            print("Initiated console logging ...")
            self._logger.info("Initiated console logging ...")

        msg = f"file_logging: {file_logging}, console_logging: {console_logging}"
        print(msg)

        self._logger.info(msg)
        self._logger.info("configureLogging called ...")
        self.logMessage("info", msg)

        if file_logging:
            # print('file_logging called ...')
            self._logger.info("file_logging called ...")
            file_logging_level = getattr(
                logging, const.LOGGING_LEVEL_TYPES[file_logging_level].upper(), None
            )

            # create formatter
            formatter = logging.Formatter(self._config["logging_format"])

            # create file handler
            if logging_file:
                addFileHandler = True
                for handler in self._logger.handlers:
                    if isinstance(handler, logging.FileHandler):
                        if (
                            hasattr(handler, "baseFilename")
                            & os.path.exists(logging_file)
                            & (
                                os.path.normcase(os.path.abspath(logging_file))
                                == os.path.normcase(os.path.abspath(handler.baseFilename))
                            )
                        ):
                            # os.path.samefile(logging_file,handler.baseFilename): #it doesn't seem to work
                            handler.setLevel(file_logging_level)
                            addFileHandler = False
                            msg = f"No change in log file name {logging_file}."
                            self._logger.info(msg)
                        else:
                            msg = f"Closing current log file {handler.baseFilename} as new log file {logging_file} requested."
                            self._logger.info(msg)
                            self._logger.removeHandler(handler)
                            msg = f"Removed existing FILE handler {handler.baseFilename}"
                            print(msg)
                            self._logger.info(msg)
                if addFileHandler:
                    if os.path.exists(logging_file) & append_log_file:
                        fh = logging.FileHandler(os.path.abspath(logging_file), "a", encoding=None)
                    else:
                        fh = logging.FileHandler(os.path.abspath(logging_file), "w", encoding=None)

                    fh.setFormatter(formatter)
                    self._logger.addHandler(fh)
                    msg = f"Added file handler {logging_file}"
                    self._logger.info(msg)
        else:
            self.closeFileLogging()

    def closeFileLogging(self):
        for handler in self._logger.handlers:
            if isinstance(handler, logging.FileHandler):
                msg = f"Removed file handler {handler.baseFilename}"
                self._logger.info(msg)
                # handler.flush()
                self._logger.removeHandler(handler)

    def closeConsoleLogging(self):
        for handler in self._logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                self._logger.info("Removed stream handler")
                # handler.flush()
                self._logger.removeHandler(handler)
        if self._frame is not None:
            self._frame = None

    def closeLogging(self):
        self.closeFileLogging()
        self.closeConsoleLogging()

    def flushHandlers(self):
        for handler in self._logger.handlers:
            handler.flush()


def call_tracking_decorator(function: Callable[[str], None]):
    def wrapper_accepting_arguments(*args):
        msg = f"Function {function.__name__} called"
        invLogger._logger.info(msg)
        function(*args)

    return wrapper_accepting_arguments


#####################################################################################
#  Decorators for error handling


def error_handling_decorator01(func: Callable[[str], None]):
    @wraps(
        func
    )  # adds the functionality of copying over the function name, docstring, arguments list, etc.
    def wrapper_function(*args, **kwargs):
        try:
            msg = f"Function {func.__name__} called"
            invLogger._logger.info(msg)
            # print(f"{func.__name__} called")
            func(*args, **kwargs)
        except Exception as e:
            invLogger._logger.error(f"Exception {e} encountered in Function {func.__name__} call")
            raise

    return wrapper_function


def error_handling_decorator02(errorList: List[str]):
    def Inner(func):
        def wrapper(*args, **kwargs):
            msg = f"Function {func.__name__} called"
            invLogger._logger.info(msg)
            try:
                func(*args, **kwargs)
            except errorList as e:
                invLogger._logger.error(f"Exception {e} found in {func.__name__} call")
                return
            else:
                invLogger._logger.error(f"{func.__name__} ran successfully.")
                pass

        return wrapper

    return Inner


# https://stackoverflow.com/questions/9168340/using-a-dictionary-to-select-function-to-execute
def error_handling_decorator03(errorList: Dict[str, str]):
    def Inner(func):
        def wrapper(*args, **kwargs):
            msg = f"Function {func.__name__} called"
            invLogger._logger.info(msg)
            keys = [key for key in errorList]
            print("keys:", keys)
            values = [errorList[key] for key in errorList]
            # keys, values = zip(*errorList.items())
            invLogger._logger.error(keys)
            invLogger._logger.error(values)
            try:
                func(*args, **kwargs)
            except (TypeError, ZeroDivisionError) as e:  # keys as e: #
                invLogger._logger.error(f"Exception {e} found in {func.__name__} call")
                # print('e:',e, type(e).__name__) #, e.__str__, e.args)
                exec(errorList[type(e).__name__])
            # else:
            # invLogger._logger.error(f"{func.__name__} ran successfully.")
            # pass

        return wrapper

    return Inner


# Decorator template
def get_decorator(errors=(Exception,), default_value=""):
    def decorator(func):
        def new_func(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except errors:
                print("Got error! ")  # , repr(e)
                return default_value

        return new_func

    return decorator


#####################################################################################

invLogger = InvesaliusLogger()
# invLogger.configureLogging()

#####################################################################################
