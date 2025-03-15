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
from datetime import datetime, timedelta
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
    """Enhanced frame for viewing detailed logs with filtering and searching capabilities."""
    
    def __init__(
        self, 
        parent: Optional[wx.Window], 
        in_memory_handler: InMemoryHandler
    ):
        """Initialize the enhanced log viewer frame."""
        super().__init__(
            parent,
            title=_("InVesalius Enhanced Log Viewer"),
            size=(1000, 700),
            style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER
        )
        
        self.in_memory_handler = in_memory_handler
        
        # Create main panel and sizer
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Create filter controls
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Level filter
        level_label = wx.StaticText(self.panel, label=_("Level:"))
        self.level_choice = wx.Choice(self.panel, choices=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.level_choice.SetSelection(0)
        self.level_choice.Bind(wx.EVT_CHOICE, self.on_filter_changed)
        
        # Component filter
        component_label = wx.StaticText(self.panel, label=_("Component:"))
        self.component_choice = wx.Choice(self.panel, choices=["ALL"])
        self.component_choice.SetSelection(0)
        self.component_choice.Bind(wx.EVT_CHOICE, self.on_filter_changed)
        
        # Time filter
        time_label = wx.StaticText(self.panel, label=_("Time:"))
        self.time_choice = wx.Choice(self.panel, choices=["ALL", "Last hour", "Last day", "Custom..."])
        self.time_choice.SetSelection(0)
        self.time_choice.Bind(wx.EVT_CHOICE, self.on_time_filter_changed)
        
        # Search box
        search_label = wx.StaticText(self.panel, label=_("Search:"))
        self.search_text = wx.SearchCtrl(self.panel, style=wx.TE_PROCESS_ENTER)
        self.search_text.Bind(wx.EVT_SEARCH, self.on_search)
        self.search_text.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        
        # Add filter controls to sizer
        filter_sizer.Add(level_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        filter_sizer.Add(self.level_choice, 0, wx.RIGHT, 10)
        filter_sizer.Add(component_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        filter_sizer.Add(self.component_choice, 0, wx.RIGHT, 10)
        filter_sizer.Add(time_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        filter_sizer.Add(self.time_choice, 0, wx.RIGHT, 10)
        filter_sizer.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        filter_sizer.Add(self.search_text, 1, wx.RIGHT, 5)
        
        main_sizer.Add(filter_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Create splitter window
        self.splitter = wx.SplitterWindow(self.panel, style=wx.SP_3D | wx.SP_LIVE_UPDATE)
        
        # Create log grid
        self.grid_panel = wx.Panel(self.splitter)
        grid_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.log_grid = wx.grid.Grid(self.grid_panel)
        self.log_grid.CreateGrid(0, 6)
        
        # Configure grid columns
        self.log_grid.SetColLabelValue(0, _("Time"))
        self.log_grid.SetColLabelValue(1, _("Level"))
        self.log_grid.SetColLabelValue(2, _("Component"))
        self.log_grid.SetColLabelValue(3, _("Message"))
        self.log_grid.SetColLabelValue(4, _("File"))
        self.log_grid.SetColLabelValue(5, _("Line"))
        
        self.log_grid.SetColSize(0, 150)  # Time
        self.log_grid.SetColSize(1, 80)   # Level
        self.log_grid.SetColSize(2, 150)  # Component
        self.log_grid.SetColSize(3, 300)  # Message
        self.log_grid.SetColSize(4, 200)  # File
        self.log_grid.SetColSize(5, 50)   # Line
        
        self.log_grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_DCLICK, self.on_cell_double_click)
        self.log_grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.on_cell_select)
        
        grid_sizer.Add(self.log_grid, 1, wx.EXPAND)
        self.grid_panel.SetSizer(grid_sizer)
        
        # Create detail panel
        self.detail_panel = wx.Panel(self.splitter)
        detail_sizer = wx.BoxSizer(wx.VERTICAL)
        
        detail_label = wx.StaticText(self.detail_panel, label=_("Details:"))
        self.detail_text = wx.TextCtrl(
            self.detail_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL
        )
        
        detail_sizer.Add(detail_label, 0, wx.ALL, 5)
        detail_sizer.Add(self.detail_text, 1, wx.EXPAND | wx.ALL, 5)
        self.detail_panel.SetSizer(detail_sizer)
        
        # Set up splitter
        self.splitter.SplitHorizontally(self.grid_panel, self.detail_panel)
        self.splitter.SetSashPosition(500)
        self.splitter.SetMinimumPaneSize(100)
        
        main_sizer.Add(self.splitter, 1, wx.EXPAND | wx.ALL, 5)
        
        # Create button panel
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.refresh_button = wx.Button(self.panel, label=_("Refresh"))
        self.refresh_button.Bind(wx.EVT_BUTTON, self.on_refresh)
        
        self.clear_button = wx.Button(self.panel, label=_("Clear"))
        self.clear_button.Bind(wx.EVT_BUTTON, self.on_clear)
        
        self.export_button = wx.Button(self.panel, label=_("Export"))
        self.export_button.Bind(wx.EVT_BUTTON, self.on_export)
        
        button_sizer.Add(self.refresh_button, 0, wx.RIGHT, 5)
        button_sizer.Add(self.clear_button, 0, wx.RIGHT, 5)
        button_sizer.Add(self.export_button, 0)
        
        main_sizer.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        
        self.panel.SetSizer(main_sizer)
        
        # Status bar for showing counts
        self.CreateStatusBar()
        
        # Populate the grid with logs
        self.populate_logs()
        
        # Update component list
        self.update_component_list()
        
        # Center the frame on the screen
        self.Centre()
        
        # Set up auto-refresh timer
        self.refresh_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.refresh_timer)
        self.refresh_timer.Start(5000)  # Refresh every 5 seconds
        
        # Bind the close event
        self.Bind(wx.EVT_CLOSE, self.on_close)
    
    def populate_logs(self):
        """Populate the grid with filtered logs."""
        # Clear the grid
        if self.log_grid.GetNumberRows() > 0:
            self.log_grid.DeleteRows(0, self.log_grid.GetNumberRows())
        
        # Get filtered records
        records = self.get_filtered_records()
        
        # Add records to the grid
        for i, record in enumerate(records):
            self.log_grid.AppendRows(1)
            self.log_grid.SetCellValue(i, 0, record.timestamp)
            self.log_grid.SetCellValue(i, 1, record.level)
            self.log_grid.SetCellValue(i, 2, record.name)
            self.log_grid.SetCellValue(i, 3, record.message)
            
            if record.pathname:
                self.log_grid.SetCellValue(i, 4, os.path.basename(record.pathname))
            
            if record.lineno:
                self.log_grid.SetCellValue(i, 5, str(record.lineno))
            
            # Color the row based on log level
            if record.level == "ERROR" or record.level == "CRITICAL":
                for col in range(6):
                    self.log_grid.SetCellBackgroundColour(i, col, wx.Colour(255, 200, 200))
            elif record.level == "WARNING":
                for col in range(6):
                    self.log_grid.SetCellBackgroundColour(i, col, wx.Colour(255, 255, 200))
            elif record.level == "DEBUG":
                for col in range(6):
                    self.log_grid.SetCellBackgroundColour(i, col, wx.Colour(230, 230, 230))
        
        # Update status bar with counts
        total_records = len(self.in_memory_handler.records)
        filtered_records = len(records)
        self.SetStatusText(f"Showing {filtered_records} of {total_records} log records")
    
    def get_filtered_records(self):
        """Get records filtered by the current filter settings."""
        records = self.in_memory_handler.records
        
        # Filter by level
        level = self.level_choice.GetStringSelection()
        if level != "ALL":
            records = [r for r in records if r.level == level]
        
        # Filter by component
        component = self.component_choice.GetStringSelection()
        if component != "ALL":
            records = [r for r in records if r.name == component]
        
        # Filter by time
        time_filter = self.time_choice.GetStringSelection()
        if time_filter != "ALL":
            now = datetime.now()
            if time_filter == "Last hour":
                one_hour_ago = now - timedelta(hours=1)
                records = [r for r in records if self._parse_timestamp(r.timestamp) > one_hour_ago]
            elif time_filter == "Last day":
                one_day_ago = now - timedelta(days=1)
                records = [r for r in records if self._parse_timestamp(r.timestamp) > one_day_ago]
        
        # Filter by search text
        search_text = self.search_text.GetValue().lower()
        if search_text:
            records = [r for r in records if (
                search_text in r.message.lower() or 
                search_text in r.name.lower() or
                (r.pathname and search_text in r.pathname.lower())
            )]
        
        return records
    
    def _parse_timestamp(self, timestamp_str):
        """Parse a timestamp string into a datetime object."""
        try:
            return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
        except ValueError:
            # If parsing fails, return a very old date
            return datetime(1970, 1, 1)
    
    def update_component_list(self):
        """Update the component filter list with available components."""
        components = set(["ALL"])
        for record in self.in_memory_handler.records:
            components.add(record.name)
        
        current_selection = self.component_choice.GetStringSelection()
        self.component_choice.Clear()
        
        for component in sorted(components):
            self.component_choice.Append(component)
        
        if current_selection in components:
            self.component_choice.SetStringSelection(current_selection)
        else:
            self.component_choice.SetSelection(0)
    
    def on_filter_changed(self, event):
        """Handle filter change events."""
        self.populate_logs()
    
    def on_time_filter_changed(self, event):
        """Handle time filter change events."""
        selection = self.time_choice.GetStringSelection()
        if selection == "Custom...":
            # Show a dialog to select custom time range
            dlg = wx.MessageDialog(
                self,
                _("Custom time range filtering will be implemented in a future version."),
                _("Not Implemented"),
                wx.OK | wx.ICON_INFORMATION
            )
            dlg.ShowModal()
            dlg.Destroy()
            self.time_choice.SetSelection(0)  # Reset to ALL
        
        self.populate_logs()
    
    def on_search(self, event):
        """Handle search events."""
        self.populate_logs()
    
    def on_refresh(self, event):
        """Handle refresh button click."""
        self.update_component_list()
        self.populate_logs()
    
    def on_timer(self, event):
        """Handle timer events for auto-refresh."""
        # Only refresh if there are new logs
        if len(self.in_memory_handler.records) > self.log_grid.GetNumberRows():
            self.update_component_list()
            self.populate_logs()
    
    def on_clear(self, event):
        """Handle clear button click."""
        dlg = wx.MessageDialog(
            self,
            _("Are you sure you want to clear all logs?"),
            _("Confirm Clear"),
            wx.YES_NO | wx.ICON_QUESTION
        )
        
        if dlg.ShowModal() == wx.ID_YES:
            self.in_memory_handler.clear()
            self.populate_logs()
        
        dlg.Destroy()
    
    def on_export(self, event):
        """Handle export button click."""
        with wx.FileDialog(
            self,
            _("Export logs"),
            wildcard="CSV files (*.csv)|*.csv|Text files (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as file_dialog:
            
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return
            
            path = file_dialog.GetPath()
            
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    # Write header
                    f.write("Timestamp,Level,Component,Message,File,Line\n")
                    
                    # Write records
                    records = self.get_filtered_records()
                    for record in records:
                        f.write(f'"{record.timestamp}","{record.level}","{record.name}","{record.message}",')
                        if record.pathname:
                            f.write(f'"{os.path.basename(record.pathname)}",')
                        else:
                            f.write('"",')
                        
                        if record.lineno:
                            f.write(f'"{record.lineno}"\n')
                        else:
                            f.write('""\n')
                
                wx.MessageBox(
                    _("Logs exported successfully."),
                    _("Export Complete"),
                    wx.OK | wx.ICON_INFORMATION
                )
            
            except Exception as e:
                wx.MessageBox(
                    _("Error exporting logs: {0}").format(str(e)),
                    _("Export Error"),
                    wx.OK | wx.ICON_ERROR
                )
    
    def on_cell_select(self, event):
        """Handle cell selection events."""
        row = event.GetRow()
        self._show_details_for_row(row)
        event.Skip()
    
    def on_cell_double_click(self, event):
        """Handle double-click on a grid cell to show details in a separate dialog."""
        row = event.GetRow()
        records = self.get_filtered_records()
        
        if row < len(records):
            record = records[row]
            
            # Create a dialog to show full details
            dlg = wx.Dialog(
                self,
                title=_("Log Record Details"),
                size=(700, 500),
                style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
            )
            
            panel = wx.Panel(dlg)
            sizer = wx.BoxSizer(wx.VERTICAL)
            
            # Create a notebook for different views of the log record
            notebook = wx.Notebook(panel)
            
            # Basic info page
            basic_panel = wx.Panel(notebook)
            basic_sizer = wx.BoxSizer(wx.VERTICAL)
            
            basic_text = wx.TextCtrl(
                basic_panel,
                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL
            )
            
            # Display detailed information
            detail_text = f"Timestamp: {record.timestamp}\n"
            detail_text += f"Level: {record.level}\n"
            detail_text += f"Component: {record.name}\n"
            detail_text += f"Message: {record.message}\n\n"
            
            if record.pathname:
                detail_text += f"File: {record.pathname}\n"
            
            if record.lineno:
                detail_text += f"Line: {record.lineno}\n"
            
            basic_text.SetValue(detail_text)
            basic_sizer.Add(basic_text, 1, wx.EXPAND | wx.ALL, 5)
            basic_panel.SetSizer(basic_sizer)
            
            # Exception info page (if available)
            if record.exc_info:
                exc_panel = wx.Panel(notebook)
                exc_sizer = wx.BoxSizer(wx.VERTICAL)
                
                exc_text = wx.TextCtrl(
                    exc_panel,
                    style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL
                )
                exc_text.SetValue(record.exc_info)
                exc_sizer.Add(exc_text, 1, wx.EXPAND | wx.ALL, 5)
                exc_panel.SetSizer(exc_sizer)
                
                notebook.AddPage(basic_panel, _("Basic Info"))
                notebook.AddPage(exc_panel, _("Exception Info"))
            else:
                notebook.AddPage(basic_panel, _("Details"))
            
            sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)
            
            # Add a close button
            close_button = wx.Button(panel, wx.ID_CLOSE)
            close_button.Bind(wx.EVT_BUTTON, lambda evt: dlg.EndModal(wx.ID_CLOSE))
            sizer.Add(close_button, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
            
            panel.SetSizer(sizer)
            
            dlg.ShowModal()
            dlg.Destroy()
        
        event.Skip()
    
    def _show_details_for_row(self, row):
        """Show details for the selected row in the detail panel."""
        records = self.get_filtered_records()
        
        if 0 <= row < len(records):
            record = records[row]
            
            # Display detailed information
            detail_text = f"Timestamp: {record.timestamp}\n"
            detail_text += f"Level: {record.level}\n"
            detail_text += f"Component: {record.name}\n"
            detail_text += f"Message: {record.message}\n\n"
            
            if record.pathname:
                detail_text += f"File: {record.pathname}\n"
            
            if record.lineno:
                detail_text += f"Line: {record.lineno}\n"
            
            if record.exc_info:
                detail_text += f"\nException Information:\n{record.exc_info}\n"
            
            self.detail_text.SetValue(detail_text)
    
    def on_close(self, event):
        """Handle the close event by hiding the frame instead of destroying it."""
        # Stop the timer when hiding the frame
        if self.refresh_timer.IsRunning():
            self.refresh_timer.Stop()
        
        # Hide the frame instead of destroying it
        self.Hide()
        
        # Log that the viewer was closed
        logging.getLogger("invesalius.enhanced_logging").info("Log viewer closed")
        
        # Don't call event.Skip() to prevent the default close behavior

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
        
        # Register cleanup handler for application exit
        import atexit
        atexit.register(self.cleanup)
    
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
        try:
            if self._log_viewer_frame is None:
                self._log_viewer_frame = LogViewerFrame(parent, self._in_memory_handler)
            else:
                # Restart the timer if it was stopped
                if not self._log_viewer_frame.refresh_timer.IsRunning():
                    self._log_viewer_frame.refresh_timer.Start(5000)
                
                # Refresh the log viewer with the latest logs
                self._log_viewer_frame.update_component_list()
                self._log_viewer_frame.populate_logs()
            
            self._log_viewer_frame.Show()
            self._log_viewer_frame.Raise()
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.error(f"Error showing log viewer: {e}")
    
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
    
    def cleanup(self):
        """Clean up resources when the application exits."""
        try:
            if self._log_viewer_frame is not None:
                # Stop the timer
                if self._log_viewer_frame.refresh_timer.IsRunning():
                    self._log_viewer_frame.refresh_timer.Stop()
                
                # Log the cleanup
                self._logger.info("Cleaning up enhanced logger resources")
        except Exception as e:
            print(f"Error during enhanced logger cleanup: {e}")

# Create the enhanced logger instance
enhanced_logger = EnhancedLogger()

# Function to get the enhanced logger
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger."""
    return enhanced_logger.get_logger(name)

# Function to show the log viewer
def show_log_viewer(parent: Optional[wx.Window] = None) -> None:
    """Show the log viewer."""
    try:
        enhanced_logger.show_log_viewer(parent)
    except Exception as e:
        import traceback
        traceback.print_exc()
        logging.error(f"Error showing log viewer: {e}")

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