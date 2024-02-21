import logging 
import logging.config 
from typing import Callable
import invesalius.session as ses

def configureLogging():
    # create logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # create console handler 
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # create file handler 
    logging.config.fileConfig('logging.conf')

def function_call_tracking_decorator(function: Callable[[str], None]):
    def wrapper_accepting_arguments(*args):
        logger = logging.getLogger(__name__)
        print('Function arguments are:')
        for arg in args:
            logger.info(arg)
        function(*args)
    return wrapper_accepting_arguments

#logging.config.dictConfig(loggingDict)
#logger = logging.getLogger(__name__)


