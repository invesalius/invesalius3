import logging 
import logging.config 
from typing import Callable
import sys

import invesalius.constants as const
import invesalius.session as sess

def configureLogging():
    session = sess.Session()
    do_logging = session.GetConfig('do_logging')
    logging_level = session.GetConfig('logging_level')
    append_log_file = session.GetConfig('append_log_file')
    logging_file  = session.GetConfig('logging_file')

    logger = logging.getLogger(__name__)
    print('Number of logger handlers: ', len(logger.handlers))
    print(do_logging,logging_level,append_log_file,logging_file, const.LOGGING_LEVEl_TYPES[logging_level])
    
    if do_logging:
        print('Logging selected')
        python_loglevel = getattr(logging,  const.LOGGING_LEVEl_TYPES[logging_level].upper(), None)
         # set logging level
        msg = 'Loglevel requested {}, Python log level {}'.format( 
             const.LOGGING_LEVEl_TYPES[logging_level], python_loglevel)
        print('Printing:', msg)
        logging.info(msg)
        
        if not isinstance(python_loglevel, int):
            raise ValueError('Invalid log level to set: %s' % python_loglevel) 
        logger.setLevel(python_loglevel)
        print('Logging level set to: {}, Python loglevel: {}'.format( \
            const.LOGGING_LEVEl_TYPES[logging_level], python_loglevel))

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # create console handler 
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(python_loglevel)
        ch.setFormatter(formatter)
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                logger.removeHandler(handler)
                print('Removed existing stream handler')
        logger.addHandler(ch)
        print('Added stream handler')
        logger.info('Added stream handler')

        # create file handler 
        msg = 'Logging file {}'.format(logging_file)
        logging.info(msg)
        if logging_file:
            fh = logging.FileHandler(logging_file, 'w+', encoding=None)
            fh.setLevel(python_loglevel)
            fh.setFormatter(formatter)
            for handler in logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    logger.removeHandler(handler)
                    print('Removed existing FILE handler')
                    logger.error('Removed existing FILE handler')
            logger.addHandler(fh)
            print('Added FILE handler')
            logger.error('Added FILE handler')
    else:
        closeLogging()
        
def closeLogging():
    logger = logging.getLogger()
    while logger.hasHandlers():
        logger.removeHandler(logger.handlers[0])    
       