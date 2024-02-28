import logging 
import logging.config 
from typing import Callable
import sys, os

import invesalius.constants as const
import invesalius.session as sess

def configureLogging():
    session = sess.Session()
    do_logging = session.GetConfig('do_logging')
    logging_level = session.GetConfig('logging_level')
    append_log_file = session.GetConfig('append_log_file')
    logging_file  = session.GetConfig('logging_file')

    logger = logging.getLogger(__name__)
    msg = 'Number of logger handlers: {}'.format(len(logger.handlers))
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            print('StreamHandler:')
        elif isinstance(handler, logging.FileHandler):
            print('FileHandler:')
        else:
            print('Unknown Handler:')
    logger.info(msg)
    
    if do_logging:
        python_loglevel = getattr(logging,  const.LOGGING_LEVEl_TYPES[logging_level].upper(), None)
         # set logging level
        msg = 'Loglevel requested {}, Python log level {}'.format( 
             const.LOGGING_LEVEl_TYPES[logging_level], python_loglevel)
        logger.info(msg)
        
        if not isinstance(python_loglevel, int):
            raise ValueError('Invalid log level to set: %s' % python_loglevel) 
        logger.setLevel(python_loglevel)
        msg = 'Logging level set to: {}, Python loglevel: {}'.format( \
            const.LOGGING_LEVEl_TYPES[logging_level], python_loglevel)
        logger.info(msg)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # create console handler 
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(python_loglevel)
        ch.setFormatter(formatter)
        addStreamHandler = True
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                addStreamHandler = False
                #logger.removeHandler(handler)
                logger.info('Stream handler already set')
        if addStreamHandler:
            logger.addHandler(ch)
            logger.info('Added stream handler')

        # create file handler 
        msg = 'Logging file requested {}'.format(logging_file)
        logger.info(msg)
        
        if logging_file:
            addFileHandler = True
            fh = logging.FileHandler(logging_file, 'a', encoding=None)
            fh.setLevel(python_loglevel)
            fh.setFormatter(formatter)
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
                logger.addHandler(fh)
                logger.info('Added FILE handler')
    else:
        closeLogging()
        
def closeLogging():
    logger = logging.getLogger()
    while logger.hasHandlers():
        logger.handlers[0].flush()
        logger.removeHandler(logger.handlers[0])    

def function_call_tracking_decorator(function: Callable[[str], None]):
    def wrapper_accepting_arguments(*args):
        logger = logging.getLogger()
        logger.info('Function called ...')
        function(*args)
    return wrapper_accepting_arguments
       