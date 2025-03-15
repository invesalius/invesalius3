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
Module for enhanced logging in InVesalius.

This module provides a comprehensive logging system for InVesalius,
including:
- Structured logging with different levels
- Log rotation
- Log filtering
- Log viewing GUI
- Integration with the error handling system
"""

import json
import logging
import logging.config
import logging.handlers
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import wx
import wx.grid
import wx.lib.agw.aui as aui

import invesalius.constants as const
from invesalius import inv_paths
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.utils import deep_merge_dict

# Constants
LOG_CONFIG_PATH = os.path.join(inv_paths.USER_INV_DIR, "log_config.json")
DEFAULT_LOGFILE = os.path.join(
    inv_paths.USER_LOG_DIR, datetime.now().strftime("invlog-%Y_%m_%d-%I_%M_%S_%p.log")
)

# Default logging configuration
DEFAULT_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s"
        },
        "simple": {
            "format": "%(asctime)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "simple",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": DEFAULT_LOGFILE,
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "encoding": "utf8"
        }
    },
    "loggers": {
        "invesalius": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
            "propagate": False
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
        "propagate": True
    }
}

class LogRecord:
    """Class to represent a log record for the GUI."""
    
    def __init__(
        self, 
        timestamp: str, 
        level: str, 
        name: str, 
        message: str,
        pathname: Optional[str] = None,
        lineno: Optional[int] = None,
        exc_info: Optional[str] = None
    ):
        self.timestamp = timestamp
        self.level = level
        self.name = name
        self.message = message
        self.pathname = pathname
        self.lineno = lineno
        self.exc_info = exc_info
    
    @classmethod
    def from_record(cls, record: logging.LogRecord) -> 'LogRecord':
        """Create a LogRecord from a logging.LogRecord."""
        exc_info = None
        if record.exc_info:
            import traceback
            exc_info = ''.join(traceback.format_exception(*record.exc_info))
        
        return cls(
            timestamp=datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S,%f')[:-3],
            level=record.levelname,
            name=record.name,
            message=record.getMessage(),
            pathname=record.pathname,
            lineno=record.lineno,
            exc_info=exc_info
        )

class InMemoryHandler(logging.Handler):
    """Logging handler that keeps records in memory for the GUI."""
    
    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.capacity = capacity
        self.records = []
        self.formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s"
        )
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record."""
        try:
            log_record = LogRecord.from_record(record)
            self.records.append(log_record)
            if len(self.records) > self.capacity:
                self.records.pop(0)
        except Exception:
            self.handleError(record)
    
    def get_records(self, level: Optional[str] = None) -> List[LogRecord]:
        """Get records, optionally filtered by level."""
        if level is None:
            return self.records
        
        return [r for r in self.records if r.level == level]
    
    def clear(self) -> None:
        """Clear all records."""
        self.records = []

class LogViewerFrame(wx.Frame):
    """Frame for viewing logs."""
    
    def __init__(
        self, 
        parent: Optional[wx.Window], 
        in_memory_handler: InMemoryHandler
    ):
        """Initialize the log viewer frame."""
        super().__init__(
            parent,
            title=_("InVesalius Log Viewer"),
            size=(800, 600),
            style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER
        )
        
        self.in_memory_handler = in_memory_handler
        
        # Create a simple UI for testing
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Add a text control to display logs
        self.log_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL
        )
        sizer.Add(self.log_text, 1, wx.EXPAND | wx.ALL, 5)
        
        # Add a refresh button
        refresh_button = wx.Button(panel, label=_("Refresh"))
        refresh_button.Bind(wx.EVT_BUTTON, self._on_refresh)
        sizer.Add(refresh_button, 0, wx.ALL, 5)
        
        panel.SetSizer(sizer)
        
        # Populate the text control with logs
        self._populate_logs()
        
        # Center the frame on the screen
        self.Centre()
    
    def _populate_logs(self):
        """Populate the text control with logs."""
        # Clear the text control
        self.log_text.Clear()
        
        # Add logs to the text control
        for record in self.in_memory_handler.records:
            self.log_text.AppendText(f"{record.timestamp} - {record.level} - {record.name} - {record.message}\n")
    
    def _on_refresh(self, event):
        """Handle refresh button click."""
        self._populate_logs()

class EnhancedLogger:
    """Enhanced logger for InVesalius."""
    
    def __init__(self):
        """Initialize the enhanced logger."""
        self._config = DEFAULT_LOG_CONFIG.copy()
        self._logger = logging.getLogger("invesalius")
        self._in_memory_handler = InMemoryHandler()
        self._logger.addHandler(self._in_memory_handler)
        self._log_viewer_frame = None
        
        # Create the log directory if it doesn't exist
        os.makedirs(inv_paths.USER_LOG_DIR, exist_ok=True)
        
        # Read the configuration file if it exists
        self._read_config()
        
        # Configure logging
        self._configure_logging()
    
    def _read_config(self) -> None:
        """Read the logging configuration from the config file."""
        try:
            if os.path.exists(LOG_CONFIG_PATH):
                with open(LOG_CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    self._config = deep_merge_dict(self._config.copy(), config)
        except Exception as e:
            print(f"Error reading log config: {e}")
    
    def _write_config(self) -> None:
        """Write the logging configuration to the config file."""
        try:
            with open(LOG_CONFIG_PATH, 'w') as f:
                json.dump(self._config, f, indent=4)
        except Exception as e:
            print(f"Error writing log config: {e}")
    
    def _configure_logging(self) -> None:
        """Configure logging based on the configuration."""
        try:
            # Configure logging
            logging.config.dictConfig(self._config)
            
            # Get the logger
            self._logger = logging.getLogger("invesalius")
            
            # Add the in-memory handler if it's not already added
            if not any(isinstance(h, InMemoryHandler) for h in self._logger.handlers):
                self._logger.addHandler(self._in_memory_handler)
            
            # Log the configuration
            self._logger.info("Logging configured")
        except Exception as e:
            print(f"Error configuring logging: {e}")
    
    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """Get a logger."""
        if name is None:
            return self._logger
        
        return logging.getLogger(f"invesalius.{name}")
    
    def show_log_viewer(self, parent: Optional[wx.Window] = None) -> None:
        """Show the log viewer."""
        print("show_log_viewer called")  # Debug output
        try:
            if self._log_viewer_frame is None:
                self._log_viewer_frame = LogViewerFrame(parent, self._in_memory_handler)
            
            self._log_viewer_frame.Show()
            self._log_viewer_frame.Raise()
            print("Log viewer should be visible now")
        except Exception as e:
            print(f"Error showing log viewer: {e}")
            import traceback
            traceback.print_exc()
    
    def set_level(self, level: Union[str, int]) -> None:
        """Set the logging level."""
        self._logger.setLevel(level)
        
        # Update the configuration
        self._config["loggers"]["invesalius"]["level"] = level if isinstance(level, str) else logging.getLevelName(level)
        
        # Write the configuration
        self._write_config()
    
    def get_level(self) -> int:
        """Get the logging level."""
        return self._logger.level
    
    def set_file_logging(self, enabled: bool) -> None:
        """Enable or disable file logging."""
        # Update the configuration
        if enabled:
            if "file" not in self._config["handlers"]:
                self._config["handlers"]["file"] = {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "DEBUG",
                    "formatter": "detailed",
                    "filename": DEFAULT_LOGFILE,
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                    "encoding": "utf8"
                }
            
            if "file" not in self._config["loggers"]["invesalius"]["handlers"]:
                self._config["loggers"]["invesalius"]["handlers"].append("file")
        else:
            if "file" in self._config["loggers"]["invesalius"]["handlers"]:
                self._config["loggers"]["invesalius"]["handlers"].remove("file")
        
        # Reconfigure logging
        self._configure_logging()
        
        # Write the configuration
        self._write_config()
    
    def set_console_logging(self, enabled: bool) -> None:
        """Enable or disable console logging."""
        # Update the configuration
        if enabled:
            if "console" not in self._config["handlers"]:
                self._config["handlers"]["console"] = {
                    "class": "logging.StreamHandler",
                    "level": "INFO",
                    "formatter": "simple",
                    "stream": "ext://sys.stdout"
                }
            
            if "console" not in self._config["loggers"]["invesalius"]["handlers"]:
                self._config["loggers"]["invesalius"]["handlers"].append("console")
        else:
            if "console" in self._config["loggers"]["invesalius"]["handlers"]:
                self._config["loggers"]["invesalius"]["handlers"].remove("console")
        
        # Reconfigure logging
        self._configure_logging()
        
        # Write the configuration
        self._write_config()
    
    def set_log_file(self, path: str) -> None:
        """Set the log file path."""
        # Update the configuration
        if "file" in self._config["handlers"]:
            self._config["handlers"]["file"]["filename"] = path
        
        # Reconfigure logging
        self._configure_logging()
        
        # Write the configuration
        self._write_config()
    
    def get_log_file(self) -> str:
        """Get the log file path."""
        if "file" in self._config["handlers"]:
            return self._config["handlers"]["file"]["filename"]
        
        return DEFAULT_LOGFILE

# Create the enhanced logger instance
enhanced_logger = EnhancedLogger()

# Function to get the enhanced logger
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger."""
    return enhanced_logger.get_logger(name)

# Function to show the log viewer
def show_log_viewer(parent: Optional[wx.Window] = None) -> None:
    """Show the log viewer."""
    print("show_log_viewer called")  # Debug output
    try:
        enhanced_logger.show_log_viewer(parent)
        print("Log viewer should be visible now")
    except Exception as e:
        print(f"Error showing log viewer: {e}")
        import traceback
        traceback.print_exc()

# Function to set the logging level
def set_level(level: Union[str, int]) -> None:
    """Set the logging level."""
    enhanced_logger.set_level(level)

# Function to get the logging level
def get_level() -> int:
    """Get the logging level."""
    return enhanced_logger.get_level()

# Function to enable or disable file logging
def set_file_logging(enabled: bool) -> None:
    """Enable or disable file logging."""
    enhanced_logger.set_file_logging(enabled)

# Function to enable or disable console logging
def set_console_logging(enabled: bool) -> None:
    """Enable or disable console logging."""
    enhanced_logger.set_console_logging(enabled)

# Function to set the log file path
def set_log_file(path: str) -> None:
    """Set the log file path."""
    enhanced_logger.set_log_file(path)

# Function to get the log file path
def get_log_file() -> str:
    """Get the log file path."""
    return enhanced_logger.get_log_file()

# Register a menu handler for the log viewer
def register_menu_handler() -> None:
    """Register a menu handler for the log viewer."""
    Publisher.subscribe(show_log_viewer, "Show log viewer") 