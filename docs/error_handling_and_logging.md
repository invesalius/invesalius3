# Error Handling and Logging System

## Overview

This document describes the enhanced error handling and logging system implemented in InVesalius. The system provides comprehensive error tracking, user-friendly error reporting, and detailed logging capabilities to improve the application's reliability and maintainability.

## Features

### Enhanced Logging

- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Log rotation to manage log file size
- Structured logging format with timestamps, log levels, and source information
- Console and file logging handlers

### Error Handling

- Centralized error handling system
- Custom exception classes for different types of errors
- User-friendly error messages and dialogs
- Error reporting capabilities
- Automatic logging of errors

### Error Testing Dialog

- A dedicated dialog for testing error handling functionality
- Ability to simulate different types of errors
- Useful for development and testing

## Usage

### Logging

```python
from invesalius.enhanced_logging import Logger

# Get a logger instance
logger = Logger.get_logger(__name__)

# Log messages at different levels
logger.debug("Detailed debug information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical error message")
```

### Error Handling

```python
from invesalius.error_handling import ErrorHandler, InVesaliusException

try:
    # Code that might raise an exception
    result = some_operation()
except Exception as e:
    # Handle the exception
    ErrorHandler.handle_exception(e, "Error during operation")
    
# Or raise a custom exception
raise InVesaliusException("A custom error message")
```

## Configuration

Logging configuration can be adjusted in the `enhanced_logging.py` file. The default configuration includes:

- Console logging at INFO level
- File logging at DEBUG level with log rotation
- Custom formatting for log messages

## Files

The error handling and logging system is implemented in the following files:

- `invesalius/enhanced_logging.py`: Logging functionality
- `invesalius/error_handling.py`: Error handling system
- `invesalius/test_error_handling.py`: Test dialog for error handling
- `invesalius/gui/frame.py`: Integration with the main application frame
- `invesalius/gui/utils.py`: Utility functions for error handling
- `app.py`: Application-level integration

## Future Improvements

- Remote error reporting
- More detailed error analytics
- User-configurable logging settings
- Integration with external monitoring tools 