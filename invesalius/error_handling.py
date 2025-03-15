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
Module for centralized error handling in InVesalius.

This module provides a comprehensive error handling system for InVesalius,
including:
- Custom exception classes for different types of errors
- Error handling decorators for functions and methods
- User-friendly error messages
- Integration with the logging system
- Crash reporting functionality
"""

import functools
import inspect
import logging
import os
import platform
import sys
import traceback
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

import psutil
import wx

import invesalius.constants as const
from invesalius import inv_paths
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

# Import logger after defining the module to avoid circular imports
# The logger will be imported inside functions that need it

# Define error categories
class ErrorCategory(Enum):
    """Enum for categorizing errors in InVesalius."""
    GENERAL = auto()
    IO = auto()
    DICOM = auto()
    SEGMENTATION = auto()
    SURFACE = auto()
    RENDERING = auto()
    NAVIGATION = auto()
    PLUGIN = auto()
    NETWORK = auto()
    CONFIGURATION = auto()
    USER_INTERFACE = auto()
    MEMORY = auto()
    PERFORMANCE = auto()
    HARDWARE = auto()
    EXTERNAL_LIBRARY = auto()

# Define error severity levels
class ErrorSeverity(Enum):
    """Enum for error severity levels in InVesalius."""
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()

# Custom exception classes
class InVesaliusException(Exception):
    """Base exception class for all InVesalius exceptions."""
    
    def __init__(
        self, 
        message: str, 
        category: ErrorCategory = ErrorCategory.GENERAL,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.original_exception = original_exception
        self.timestamp = datetime.now()
        
        # Add the original exception traceback if available
        if original_exception:
            self.details['original_traceback'] = ''.join(
                traceback.format_exception(
                    type(original_exception), 
                    original_exception, 
                    original_exception.__traceback__
                )
            )
        
        super().__init__(message)

class IOError(InVesaliusException):
    """Exception raised for I/O errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.IO,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

class DicomError(InVesaliusException):
    """Exception raised for DICOM-related errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.DICOM,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

class SegmentationError(InVesaliusException):
    """Exception raised for segmentation-related errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.SEGMENTATION,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

class SurfaceError(InVesaliusException):
    """Exception raised for surface-related errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.SURFACE,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

class RenderingError(InVesaliusException):
    """Exception raised for rendering-related errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.RENDERING,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

class NavigationError(InVesaliusException):
    """Exception raised for navigation-related errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.NAVIGATION,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

class PluginError(InVesaliusException):
    """Exception raised for plugin-related errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.PLUGIN,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

class MemoryError(InVesaliusException):
    """Exception raised for memory-related errors."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(
            message, 
            category=ErrorCategory.MEMORY,
            severity=ErrorSeverity.ERROR,
            details=details,
            original_exception=original_exception
        )

# Error handling decorators
def handle_errors(
    error_message: str = "An error occurred",
    show_dialog: bool = True,
    log_error: bool = True,
    reraise: bool = False,
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    category: ErrorCategory = ErrorCategory.GENERAL,
    severity: ErrorSeverity = ErrorSeverity.ERROR
):
    """
    Decorator for handling errors in functions and methods.
    
    Parameters:
        error_message (str): The error message to display to the user.
        show_dialog (bool): Whether to show an error dialog to the user.
        log_error (bool): Whether to log the error.
        reraise (bool): Whether to reraise the exception after handling.
        expected_exceptions (tuple): The exceptions to catch.
        category (ErrorCategory): The category of the error.
        severity (ErrorSeverity): The severity of the error.
        
    Returns:
        The decorated function.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except expected_exceptions as e:
                # Get function information for better error reporting
                module_name = func.__module__
                function_name = func.__qualname__
                
                # Get the line number where the error occurred
                _, _, tb = sys.exc_info()
                while tb.tb_next:
                    tb = tb.tb_next
                line_number = tb.tb_lineno
                
                # Create a detailed error message
                detailed_message = f"{error_message} in {module_name}.{function_name} (line {line_number})"
                
                # Create error details
                details = {
                    'module': module_name,
                    'function': function_name,
                    'line': line_number,
                    'args': str(args),
                    'kwargs': str(kwargs),
                    'exception_type': type(e).__name__,
                    'exception_message': str(e),
                    'traceback': traceback.format_exc()
                }
                
                # Create an InVesalius exception
                inv_exception = InVesaliusException(
                    detailed_message,
                    category=category,
                    severity=severity,
                    details=details,
                    original_exception=e
                )
                
                # Log the error
                if log_error:
                    from invesalius.gui import log
                    logger = log.invLogger.getLogger()
                    
                    if severity == ErrorSeverity.DEBUG:
                        logger.debug(detailed_message, exc_info=True)
                    elif severity == ErrorSeverity.INFO:
                        logger.info(detailed_message, exc_info=True)
                    elif severity == ErrorSeverity.WARNING:
                        logger.warning(detailed_message, exc_info=True)
                    elif severity == ErrorSeverity.ERROR:
                        logger.error(detailed_message, exc_info=True)
                    elif severity == ErrorSeverity.CRITICAL:
                        logger.critical(detailed_message, exc_info=True)
                
                # Show error dialog
                if show_dialog and wx.GetApp() is not None:
                    show_error_dialog(detailed_message, inv_exception)
                
                # Publish error event
                Publisher.sendMessage(
                    "Error occurred",
                    error=inv_exception
                )
                
                # Reraise the exception if requested
                if reraise:
                    raise inv_exception from e
                
                # Return None or a default value
                return None
        
        return wrapper
    
    return decorator

def show_error_dialog(message: str, exception: Optional[InVesaliusException] = None):
    """
    Show an error dialog to the user.
    
    Parameters:
        message (str): The error message to display.
        exception (InVesaliusException, optional): The exception that occurred.
    """
    if wx.GetApp() is None:
        # No GUI available, just print the error
        print(f"ERROR: {message}")
        if exception and exception.details.get('traceback'):
            print(exception.details['traceback'])
        return
    
    # Create a dialog with details that can be expanded
    if exception:
        dlg = ErrorDialog(None, message, exception)
    else:
        dlg = wx.MessageDialog(
            None,
            message,
            _("Error"),
            wx.OK | wx.ICON_ERROR
        )
    
    dlg.ShowModal()
    dlg.Destroy()

def get_system_info() -> Dict[str, str]:
    """
    Get system information for error reporting.
    
    Returns:
        A dictionary containing system information.
    """
    info = {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'processor': platform.processor(),
        'memory': str(get_system_memory()),
        'invesalius_version': const.INVESALIUS_VERSION,
    }
    
    try:
        import wx
        info['wxpython_version'] = wx.version()
    except ImportError:
        info['wxpython_version'] = 'Not available'
    
    try:
        from vtkmodules.vtkCommonCore import vtkVersion
        info['vtk_version'] = vtkVersion.GetVTKVersion()
    except ImportError:
        info['vtk_version'] = 'Not available'
    
    return info

def get_system_memory() -> int:
    """
    Get the total system memory in GB.
    
    Returns:
        The total system memory in GB.
    """
    try:
        import psutil
        return psutil.virtual_memory().total // (1024 ** 3)
    except ImportError:
        return 0

def create_crash_report(exception: InVesaliusException) -> str:
    """
    Create a crash report for an exception.
    
    Parameters:
        exception (InVesaliusException): The exception to create a report for.
        
    Returns:
        The path to the crash report file.
    """
    # Create crash report directory if it doesn't exist
    crash_dir = os.path.join(inv_paths.USER_LOG_DIR, 'crash_reports')
    os.makedirs(crash_dir, exist_ok=True)
    
    # Create a unique filename for the crash report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"crash_report_{timestamp}.txt"
    filepath = os.path.join(crash_dir, filename)
    
    # Get system information
    system_info = get_system_info()
    
    # Write the crash report
    with open(filepath, 'w') as f:
        f.write("InVesalius Crash Report\n")
        f.write("======================\n\n")
        
        f.write(f"Timestamp: {exception.timestamp}\n")
        f.write(f"Error Category: {exception.category.name}\n")
        f.write(f"Error Severity: {exception.severity.name}\n")
        f.write(f"Error Message: {exception.message}\n\n")
        
        f.write("System Information\n")
        f.write("------------------\n")
        for key, value in system_info.items():
            f.write(f"{key}: {value}\n")
        f.write("\n")
        
        f.write("Error Details\n")
        f.write("------------\n")
        for key, value in exception.details.items():
            if key != 'traceback' and key != 'original_traceback':
                f.write(f"{key}: {value}\n")
        f.write("\n")
        
        if 'traceback' in exception.details:
            f.write("Traceback\n")
            f.write("---------\n")
            f.write(exception.details['traceback'])
            f.write("\n\n")
        
        if 'original_traceback' in exception.details:
            f.write("Original Traceback\n")
            f.write("-----------------\n")
            f.write(exception.details['original_traceback'])
    
    return filepath

class ErrorDialog(wx.Dialog):
    """
    Dialog for displaying detailed error information.
    """
    
    def __init__(
        self, 
        parent: Optional[wx.Window], 
        message: str, 
        exception: InVesaliusException
    ):
        """
        Initialize the error dialog.
        
        Parameters:
            parent (wx.Window): The parent window.
            message (str): The error message to display.
            exception (InVesaliusException): The exception that occurred.
        """
        super().__init__(
            parent,
            title=_("Error"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(600, 400)
        )
        
        self.exception = exception
        
        # Create the dialog layout
        self._create_layout(message)
        
        # Center the dialog on the screen
        self.Centre()
    
    def _create_layout(self, message: str):
        """
        Create the dialog layout.
        
        Parameters:
            message (str): The error message to display.
        """
        # Create the main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Add the error icon and message
        error_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Add the error icon
        error_bitmap = wx.ArtProvider.GetBitmap(wx.ART_ERROR, wx.ART_MESSAGE_BOX)
        error_icon = wx.StaticBitmap(self, wx.ID_ANY, error_bitmap)
        error_sizer.Add(error_icon, 0, wx.ALL, 10)
        
        # Add the error message
        error_text = wx.StaticText(self, wx.ID_ANY, message)
        error_sizer.Add(error_text, 1, wx.ALL | wx.EXPAND, 10)
        
        main_sizer.Add(error_sizer, 0, wx.EXPAND)
        
        # Add a separator
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 5)
        
        # Add the details section
        details_notebook = wx.Notebook(self)
        
        # Add the details page
        details_panel = wx.Panel(details_notebook)
        details_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Add the details text
        details_text = wx.TextCtrl(
            details_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.BORDER_NONE
        )
        
        # Add the exception details
        details = []
        details.append(f"Error Category: {self.exception.category.name}")
        details.append(f"Error Severity: {self.exception.severity.name}")
        details.append(f"Timestamp: {self.exception.timestamp}")
        
        for key, value in self.exception.details.items():
            if key != 'traceback' and key != 'original_traceback':
                details.append(f"{key}: {value}")
        
        details_text.SetValue('\n'.join(details))
        details_sizer.Add(details_text, 1, wx.EXPAND)
        details_panel.SetSizer(details_sizer)
        
        details_notebook.AddPage(details_panel, _("Details"))
        
        # Add the traceback page if available
        if 'traceback' in self.exception.details:
            traceback_panel = wx.Panel(details_notebook)
            traceback_sizer = wx.BoxSizer(wx.VERTICAL)
            
            traceback_text = wx.TextCtrl(
                traceback_panel,
                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.BORDER_NONE
            )
            traceback_text.SetValue(self.exception.details['traceback'])
            traceback_sizer.Add(traceback_text, 1, wx.EXPAND)
            traceback_panel.SetSizer(traceback_sizer)
            
            details_notebook.AddPage(traceback_panel, _("Traceback"))
        
        # Add the system info page
        system_panel = wx.Panel(details_notebook)
        system_sizer = wx.BoxSizer(wx.VERTICAL)
        
        system_text = wx.TextCtrl(
            system_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.BORDER_NONE
        )
        
        # Add the system information
        system_info = get_system_info()
        system_details = []
        
        for key, value in system_info.items():
            system_details.append(f"{key}: {value}")
        
        system_text.SetValue('\n'.join(system_details))
        system_sizer.Add(system_text, 1, wx.EXPAND)
        system_panel.SetSizer(system_sizer)
        
        details_notebook.AddPage(system_panel, _("System Info"))
        
        main_sizer.Add(details_notebook, 1, wx.EXPAND | wx.ALL, 10)
        
        # Add the buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Add the "Create Crash Report" button
        crash_report_button = wx.Button(self, wx.ID_ANY, _("Create Crash Report"))
        crash_report_button.Bind(wx.EVT_BUTTON, self._on_crash_report)
        button_sizer.Add(crash_report_button, 0, wx.ALL, 5)
        
        # Add a spacer
        button_sizer.Add((0, 0), 1, wx.EXPAND)
        
        # Add the "OK" button
        ok_button = wx.Button(self, wx.ID_OK)
        button_sizer.Add(ok_button, 0, wx.ALL, 5)
        
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(main_sizer)
    
    def _on_crash_report(self, event: wx.CommandEvent):
        """
        Handle the "Create Crash Report" button click.
        
        Parameters:
            event (wx.CommandEvent): The button click event.
        """
        # Create the crash report
        crash_report_path = create_crash_report(self.exception)
        
        # Show a message dialog with the crash report path
        wx.MessageBox(
            _("Crash report created at:\n\n{0}").format(crash_report_path),
            _("Crash Report Created"),
            wx.OK | wx.ICON_INFORMATION
        )

# Global error handler for unhandled exceptions
def global_exception_handler(exctype, value, tb):
    """
    Global exception handler for unhandled exceptions.
    
    This function is set as the sys.excepthook to catch unhandled exceptions.
    It logs the exception, creates a crash report, and shows an error dialog.
    
    Args:
        exctype: The exception type
        value: The exception value
        tb: The traceback
    """
    # Log the exception
    logging.critical("Unhandled exception", exc_info=(exctype, value, tb))
    
    # Create an InVesalius exception
    exception = InVesaliusException(
        str(value),
        category=ErrorCategory.GENERAL,
        severity=ErrorSeverity.CRITICAL,
        details={
            'traceback': ''.join(traceback.format_exception(exctype, value, tb))
        },
        original_exception=value
    )
    
    # Create a crash report
    crash_report_path = create_crash_report(exception)
    
    # Show an error dialog if the GUI is available
    if wx.GetApp() is not None:
        show_error_dialog(
            _("An unhandled error occurred. A crash report has been created at:\n\n{0}").format(crash_report_path),
            exception
        )
    else:
        # No GUI available, just print the error
        print(f"CRITICAL ERROR: {str(value)}")
        print(f"A crash report has been created at: {crash_report_path}")

# Set the global exception handler
sys.excepthook = global_exception_handler 

def show_message(title, message, style=wx.OK | wx.ICON_INFORMATION, log_level=logging.INFO):
    """
    Show a message to the user and log it.
    
    Parameters:
    -----------
    title : str
        The title of the message box.
    message : str
        The message to display and log.
    style : int
        The style of the message box (wx.OK, wx.ICON_INFORMATION, wx.ICON_WARNING, etc.).
    log_level : int
        The logging level to use (logging.INFO, logging.WARNING, logging.ERROR, etc.).
    
    Returns:
    --------
    int
        The result of the message box.
    """
    # Determine the logger based on the calling module
    frame = inspect.currentframe().f_back
    module_name = frame.f_globals['__name__']
    logger = logging.getLogger(module_name)
    
    # Log the message with the appropriate level
    if log_level == logging.DEBUG:
        logger.debug(f"{title}: {message}")
    elif log_level == logging.INFO:
        logger.info(f"{title}: {message}")
    elif log_level == logging.WARNING:
        logger.warning(f"{title}: {message}")
    elif log_level == logging.ERROR:
        logger.error(f"{title}: {message}")
    elif log_level == logging.CRITICAL:
        logger.critical(f"{title}: {message}")
    
    # Show the message box
    return wx.MessageBox(message, title, style)

# Convenience functions for common message types
def show_info(title, message):
    """Show an information message and log it at INFO level."""
    return show_message(title, message, wx.OK | wx.ICON_INFORMATION, logging.INFO)

def show_warning(title, message):
    """Show a warning message and log it at WARNING level."""
    return show_message(title, message, wx.OK | wx.ICON_WARNING, logging.WARNING)

def show_error(title, message):
    """Show an error message and log it at ERROR level."""
    return show_message(title, message, wx.OK | wx.ICON_ERROR, logging.ERROR)

def show_question(title, message):
    """Show a question message and log it at INFO level."""
    return show_message(title, message, wx.YES_NO | wx.ICON_QUESTION, logging.INFO) 