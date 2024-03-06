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
    '''
    msg = 'Number of logger handlers: {}], and are as follows:'.format(len(logger.handlers))
    logger.info(msg)
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            logger.info('FileHandler:')
        elif isinstance(handler, logging.StreamHandler):
            logger.info('StreamHandler:')
        else:
            logger.info('Unknown Handler:')
    '''
    
    if file_logging:
        python_loglevel = getattr(logging,  const.LOGGING_LEVEL_TYPES[file_logging_level].upper(), None)
        
        '''
        msg = 'Loglevel requested {}, Python log level {}'.format( 
             const.LOGGING_LEVEL_TYPES[file_logging_level], python_loglevel)
        logger.info(msg)
        '''
        logLevelChanged = False
        currLogLevel = logging.getLevelName(logger.getEffectiveLevel())
        if (currLogLevel!=const.LOGGING_LEVEL_TYPES[file_logging_level]):
            #if not isinstance(python_loglevel, int):
            #    raise ValueError('Invalid log level to set: %s' % python_loglevel) 
            logLevelChanged = True
            logger.setLevel(python_loglevel)
            msg = 'Logging level will be set to {} from {}'.format( \
                const.LOGGING_LEVEL_TYPES[file_logging_level], currLogLevel)
            logger.info(msg)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # create file handler 
        #msg = 'Logging file requested {}'.format(logging_file)
        #logger.info(msg)
        
        if logging_file:
            addFileHandler = True
            for handler in logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    if hasattr(handler, 'baseFilename') & \
                        os.path.samefile(logging_file,handler.baseFilename):
                        addFileHandler = False
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
                logger.info('Added FILE handler')
    else:
        closeFileLogging()

    if console_logging:
        python_loglevel = getattr(logging,  const.LOGGING_LEVEL_TYPES[console_logging_level].upper(), None)
        '''
        msg = 'Loglevel requested {}, Python log level {}'.format( 
             const.LOGGING_LEVEL_TYPES[console_logging_level], python_loglevel)
        logger.info(msg)
        '''
        logLevelChanged = False
        currLogLevel = logging.getLevelName(logger.getEffectiveLevel())
        if (currLogLevel!=const.LOGGING_LEVEL_TYPES[console_logging_level]): 
            logLevelChanged = True
            logger.setLevel(python_loglevel)
            msg = 'Logging level will be set to {} from {}'.format( \
                const.LOGGING_LEVEL_TYPES[console_logging_level], currLogLevel)
            logger.info(msg)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # create console handler 
        addStreamHandler = True
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                addStreamHandler = False
                #logger.info('Stream handler already set')
        if addStreamHandler:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(python_loglevel)
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            logger.info('Added stream handler')
    else:
        closeConsoleLogging()
 
def closeFileLogging():
    logger = logging.getLogger(__name__)
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()
            logger.removeHandler(handler)    

def closeConsoleLogging():
    logger = logging.getLogger(__name__)
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.flush()
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