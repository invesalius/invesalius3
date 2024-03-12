import logging 
import logging.config 
from typing import Callable
import sys, os

import invesalius.constants as const
import invesalius.session as sess

def configureLogging():
    session = sess.Session()
    file_logging = session.GetConfig('file_logging')
    file_logging_level = session.GetConfig('file_logging_level')
    append_log_file = session.GetConfig('append_log_file')
    logging_file  = session.GetConfig('logging_file')
    console_logging = session.GetConfig('console_logging')
    console_logging_level = session.GetConfig('console_logging_level')

    logger = logging.getLogger(__name__)

    msg = 'file_logging: {}, console_logging: {}'.format(file_logging, console_logging)
    print(msg)
    logger.info(msg)
    logger.info("configureLogging called ...")

    python_loglevel = getattr(logging,  const.LOGGING_LEVEL_TYPES[file_logging_level].upper(), None)
    logger.setLevel(python_loglevel)

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


    if file_logging:
        logger.info("file_logging called ...")
        python_loglevel = getattr(logging,  const.LOGGING_LEVEL_TYPES[file_logging_level].upper(), None)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # create file handler 
        
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
        closeFileLogging()


 
def closeFileLogging():
    logger = logging.getLogger(__name__)
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            msg = 'Removed file handler {}'.format(handler.baseFilename)
            logger.info(msg)
            #handler.flush()
            logger.removeHandler(handler)    

def closeConsoleLogging():
    logger = logging.getLogger(__name__)
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            logger.info('Removed stream handler')
            #handler.flush()
            logger.removeHandler(handler)    

def closeLogging():
    closeConsoleLogging()
    closeFileLogging()  

def flushHandlers():
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
       
def error_catching_decorator(function: Callable[[str], None]):
    def wrapper_accepting_arguments(*args):
        logger = logging.getLogger(__name__)
        try:
            function(*args)
        except Exception as inst:
            msg = 'Exception in Function {}: Type {}, Args{}'.format(\
                function.__name__, type(inst), inst.args)     
            logger.info(msg)
            raise
    return wrapper_accepting_arguments

def exception_handler(func):
    def inner_function(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except TypeError:
            print(f"{func.__name__} only takes numbers as the argument")
    return inner_function
