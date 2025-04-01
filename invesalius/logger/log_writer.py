import threading
import time
from . import logger_config as Config
from . import log_writer as Logger
import logging




def log_writer():
    while True:
        log_message = Config.log_queue.get()  # Wait for a log message from the queue
        if log_message is None:
            break  # Graceful shutdown (None is the shutdown signal)
        with open("app.log", "a") as log_file:
            log_file.write(log_message + "\n")
        time.sleep(0)  # Yield control to the event loop


# This starts the log writer thread
def start_log_writer():
    log_thread = threading.Thread(target=log_writer, daemon=True)
    log_thread.start()


def start():
    # initialise the config
    Config.setup_logging()

    # Start the logging thread
    Logger.start_log_writer()
    logger = logging.getLogger(__name__)
    logger.info("This is a log message")
    
    
    
if __name__ == "__main__":
    start()