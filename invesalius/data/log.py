import logging 
import logging.config 

logging.config.dictConfig(
    { 'version': 1,
      'disable_existing_loggers': False, # this fixes the problem 
      'formatters': { 
            'standard': { 
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            }, 
            'simple': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },
        'handlers': { 
            'default': { 
                'level':'INFO', 
                'class':'logging.StreamHandler',
            }, 
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG',
                'formatter': 'simple',
                'stream': 'ext://sys.stdout',
            },
            'file': {
                'class': 'logging.FileHandler',
                'level': 'INFO',
                'formatter': 'simple',
                'filename': 'myapp.log',
                'mode': 'a'
            }
        },
        'loggers': { 
            '': {
                'handlers': ['default'], 
                'level': 'INFO', 
                'propagate': True
            },
            'development': {
                'level': 'DEBUG',
                'handlers': ['console'],
                'propagate': False
            },
            'staging': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False
            },
            'production': {
                'level': 'WARNING',
                'handlers': ['file'],
                'propagate': False
            }
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['console']
        }
    }
)

def function_call_tracking_decorator(function: Callable[[str], None]):
    def wrapper_accepting_arguments(*args):
        print('Function arguments are:')
        for arg in args:
            print(arg)
        function(*args)
    return wrapper_accepting_arguments

logger = logging.getLogger(__name__)

#@function_call_tracking_decorator
#def testFunction(myMode:str) -> None:
#    myLogger = logging.getLogger(myMode) 

