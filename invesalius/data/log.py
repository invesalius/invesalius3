import logging 
import logging.config 
from typing import Callable

import invesalius.constants as const
import invesalius.session as ses

def configureLogging():
    session = ses.Session()
    do_logging = session.GetConfig('do_logging')
    logging_level = session.GetConfig('logging_level')
    append_log_file = session.GetConfig('append_log_file')
    logging_file  = session.GetConfig('logging_file')

    logger = logging.getLogger(__name__)
    print('Number of logger handlers: ', len(logger.handlers))
    print(do_logging,logging_level,append_log_file,logging_file, const.LOGGING_LEVEl_TYPES[logging_level])
    
    if do_logging:
        python_loglevel = getattr(logging,  const.LOGGING_LEVEl_TYPES[logging_level].upper(), None)
         # set logging level
        msg = 'Loglevel requested {}, Python log level {}'.format( 
             const.LOGGING_LEVEl_TYPES[logging_level], python_loglevel)
        logging.info(msg)
        
        if not isinstance(python_loglevel, int):
            raise ValueError('Invalid log level: %s' % python_loglevel) 
        logger.setLevel(python_loglevel)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # create console handler 
        ch = logging.StreamHandler()
        ch.setLevel(python_loglevel)
        ch.setFormatter(formatter)
        #if not isinstance(ch, logging.StreamHandler):  #ext://sys.stdout
        #    logger.addHandler(fileHandler)  #removeHandler
        logger.addHandler(ch)

        # create file handler 
        fh = logging.FileHandler(logging_file) 
        fh.setLevel(python_loglevel)
        fh.setFormatter(formatter)
        #if not isinstance(handler, logging.FileHandler) and not isinstance(handler, logging.StreamHandler):
        #            logger.addHandler(fileHandler)
        logger.addHandler(fh)
        
        
def closeLogging():
    logger = logging.getLogger()
    while logger.hasHandlers():
        logger.removeHandler(logger.handlers[0])    
       