#!/usr/bin/env python3
# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# -------------------------------------------------------------------------

"""
Module for testing error handling and logging in InVesalius.

This module provides functions and classes for testing the error handling
and logging features in InVesalius.
"""

import traceback
from typing import Optional, Type

import wx

from invesalius import enhanced_logging
from invesalius.error_handling import (
    DicomError,
    ErrorCategory,
    ErrorSeverity,
    InVesaliusException,
    IOError,
    MemoryError,
    NavigationError,
    PluginError,
    RenderingError,
    SegmentationError,
    SurfaceError,
    handle_errors,
    show_error_dialog,
)
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

# Get a logger
logger = enhanced_logging.get_logger("test_error_handling")


# Test functions with error handling decorator
@handle_errors(
    error_message="Error in test function",
    show_dialog=True,
    log_error=True,
    reraise=False,
    category=ErrorCategory.GENERAL,
    severity=ErrorSeverity.ERROR,
)
def test_function_with_error():
    """Test function that raises an error."""
    logger.info("Starting test function with error")
    raise ValueError("This is a test error")


@handle_errors(
    error_message="Error in test function with custom exception",
    show_dialog=True,
    log_error=True,
    reraise=False,
    category=ErrorCategory.IO,
    severity=ErrorSeverity.ERROR,
)
def test_function_with_custom_exception():
    """Test function that raises a custom exception."""
    logger.info("Starting test function with custom exception")
    raise IOError(
        "This is a test IO error",
        details={"file": "test.txt"},
        original_exception=FileNotFoundError("File not found"),
    )


@handle_errors(
    error_message="Error in test function with different severity",
    show_dialog=True,
    log_error=True,
    reraise=False,
    category=ErrorCategory.GENERAL,
    severity=ErrorSeverity.WARNING,
)
def test_function_with_warning():
    """Test function that raises a warning."""
    logger.info("Starting test function with warning")
    raise Warning("This is a test warning")


# Test function without error handling decorator
def test_function_without_decorator():
    """Test function without error handling decorator."""
    logger.info("Starting test function without decorator")
    try:
        # Intentionally cause an error
        raise ValueError("This is a test error")
    except Exception as e:
        # Handle the error manually
        from invesalius.error_handling import ErrorCategory, ErrorSeverity, InVesaliusException

        # Log the error
        logger.error(f"Caught error in test function: {str(e)}", exc_info=True)

        # Publish error event
        Publisher.sendMessage(
            "Error occurred",
            error=InVesaliusException(
                f"Error in test function without decorator: {str(e)}",
                category=ErrorCategory.GENERAL,
                severity=ErrorSeverity.ERROR,
                details={
                    "function": "test_function_without_decorator",
                    "exception_type": type(e).__name__,
                    "exception_message": str(e),
                    "traceback": traceback.format_exc(),
                },
                original_exception=e,
            ),
        )


# Test function that logs messages at different levels
def test_logging_levels():
    """Test function that logs messages at different levels."""
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")


# Test function that demonstrates different exception types
def test_exception_types():
    """Test function that demonstrates different exception types."""
    # Create different types of exceptions
    exceptions = [
        IOError("This is an IO error"),
        DicomError("This is a DICOM error"),
        SegmentationError("This is a segmentation error"),
        SurfaceError("This is a surface error"),
        RenderingError("This is a rendering error"),
        NavigationError("This is a navigation error"),
        PluginError("This is a plugin error"),
        MemoryError("This is a memory error"),
    ]

    for exception in exceptions:
        try:
            raise exception
        except InVesaliusException as e:
            logger.error(f"Caught exception: {e.message}", exc_info=True)


# Test function that demonstrates the log viewer
def test_log_viewer(parent: Optional[wx.Window] = None):
    """Test function that demonstrates the log viewer."""
    # Log some messages
    test_logging_levels()

    # Show the log viewer
    enhanced_logging.show_log_viewer(parent)


# Main function to run the tests
def run_tests(parent: Optional[wx.Window] = None):
    """Run the error handling and logging tests."""
    logger.info("Running error handling and logging tests")
    try:
        test_function_with_error()
        test_function_with_custom_exception()
        test_function_with_warning()
        test_function_without_decorator()
        test_logging_levels()
        test_exception_types()

        # Show success message
        dialog = wx.MessageDialog(
            parent,
            "Error handling tests completed successfully!",
            "Test Results",
            wx.OK | wx.ICON_INFORMATION,
        )
        dialog.ShowModal()
        dialog.Destroy()

        # Log some test messages
        logger.debug("This is a debug message from the tests")
        logger.info("This is an info message from the tests")
        logger.warning("This is a warning message from the tests")
        logger.error("This is an error message from the tests")

        # Show the log viewer
        enhanced_logging.show_log_viewer(parent)

    except Exception as e:
        print(f"Error running tests: {e}")
        import traceback

        traceback.print_exc()

        # Show error dialog
        error_dialog = wx.MessageDialog(
            parent, f"Error running tests: {e}", "Test Error", wx.OK | wx.ICON_ERROR
        )
        error_dialog.ShowModal()
        error_dialog.Destroy()


# Register a menu handler for running the tests
def register_menu_handler():
    """Register a menu handler for running the tests."""
    Publisher.subscribe(run_tests, "Run error handling tests")
