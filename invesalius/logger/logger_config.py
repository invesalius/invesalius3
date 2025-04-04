import logging
import logging.handlers
import logging.config
import queue

# Create a thread-safe Queue for handling log records
log_queue = queue.Queue()


# Custom handler that adds log records to the queue
class QueueHandler(logging.Handler):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            log_message = self.format(record)
            self.queue.put(log_message)  # Put log message into the queue
        except Exception:
            self.handleError(record)


# Function to set up logging configuration
def setup_logging():
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(levelname)s - %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": "INFO",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed",
                "filename": "app.log",
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 3,
                "level": "DEBUG",
            },
            "queue": {
                "class": "invesalius.logger.logger_config.QueueHandler",  # Use the custom QueueHandler
                "formatter": "detailed",
                "queue": log_queue,
            },
        },
        "loggers": {
            "invesalius": {
                "level": "DEBUG",
                "handlers": ["console", "file", "queue"],
                "propagate": False,
            }
        },
    }

    logging.config.dictConfig(logging_config)