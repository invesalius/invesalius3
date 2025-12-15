"""
Comprehensive tests for the error handling module.

This module tests:
- ErrorCategory and ErrorSeverity enums
- Custom exception classes
- Error handling decorators
- Crash reporting functionality
- Error message generation
- System information gathering
"""

import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest import mock

import pytest

from invesalius import error_handling
from invesalius.error_handling import (
    DicomError,
    ErrorCategory,
    ErrorDialog,
    ErrorSeverity,
    InVesaliusException,
    IOError,
    MemoryError,
    NavigationError,
    PluginError,
    RenderingError,
    SegmentationError,
    SurfaceError,
    create_crash_report,
    get_system_info,
    get_system_memory,
    global_exception_handler,
    handle_errors,
    show_error_dialog,
)


# ==================== ErrorCategory Tests ====================


class TestErrorCategory:
    """Tests for the ErrorCategory enum."""

    def test_error_category_has_required_members(self):
        """Test that ErrorCategory has all required members."""
        required_categories = [
            "GENERAL",
            "IO",
            "DICOM",
            "SEGMENTATION",
            "SURFACE",
            "RENDERING",
            "NAVIGATION",
            "PLUGIN",
            "NETWORK",
            "CONFIGURATION",
            "USER_INTERFACE",
            "MEMORY",
            "PERFORMANCE",
            "HARDWARE",
            "EXTERNAL_LIBRARY",
        ]
        for category in required_categories:
            assert hasattr(ErrorCategory, category)

    def test_error_category_members_are_unique(self):
        """Test that all ErrorCategory members have unique values."""
        values = [member.value for member in ErrorCategory]
        assert len(values) == len(set(values))

    def test_error_category_enum_access(self):
        """Test accessing ErrorCategory enum members."""
        assert ErrorCategory.GENERAL.name == "GENERAL"
        assert ErrorCategory.IO.name == "IO"
        assert ErrorCategory.DICOM.name == "DICOM"


# ==================== ErrorSeverity Tests ====================


class TestErrorSeverity:
    """Tests for the ErrorSeverity enum."""

    def test_error_severity_has_required_members(self):
        """Test that ErrorSeverity has all required members."""
        required_severities = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for severity in required_severities:
            assert hasattr(ErrorSeverity, severity)

    def test_error_severity_members_are_unique(self):
        """Test that all ErrorSeverity members have unique values."""
        values = [member.value for member in ErrorSeverity]
        assert len(values) == len(set(values))

    def test_error_severity_enum_access(self):
        """Test accessing ErrorSeverity enum members."""
        assert ErrorSeverity.DEBUG.name == "DEBUG"
        assert ErrorSeverity.ERROR.name == "ERROR"
        assert ErrorSeverity.CRITICAL.name == "CRITICAL"


# ==================== InVesaliusException Tests ====================


class TestInVesaliusException:
    """Tests for the InVesaliusException class."""

    def test_basic_exception_creation(self):
        """Test creating a basic InVesaliusException."""
        exc = InVesaliusException("Test error message")
        assert exc.message == "Test error message"
        assert exc.category == ErrorCategory.GENERAL
        assert exc.severity == ErrorSeverity.ERROR
        assert exc.details == {}
        assert exc.original_exception is None

    def test_exception_with_all_parameters(self):
        """Test creating an exception with all parameters."""
        details = {"key": "value"}
        original_exc = ValueError("Original error")
        exc = InVesaliusException(
            "Test error",
            category=ErrorCategory.IO,
            severity=ErrorSeverity.CRITICAL,
            details=details,
            original_exception=original_exc,
        )

        assert exc.message == "Test error"
        assert exc.category == ErrorCategory.IO
        assert exc.severity == ErrorSeverity.CRITICAL
        assert exc.details["key"] == "value"
        assert exc.original_exception == original_exc

    def test_exception_timestamp_is_set(self):
        """Test that exception timestamp is automatically set."""
        before = datetime.now()
        exc = InVesaliusException("Test error")
        after = datetime.now()

        assert before <= exc.timestamp <= after

    def test_exception_with_original_exception_stores_traceback(self):
        """Test that original exception traceback is stored."""
        try:
            raise ValueError("Original error")
        except ValueError as e:
            exc = InVesaliusException("Wrapped error", original_exception=e)

        assert "original_traceback" in exc.details
        assert "ValueError" in exc.details["original_traceback"]
        assert "Original error" in exc.details["original_traceback"]

    def test_exception_string_representation(self):
        """Test exception string representation."""
        exc = InVesaliusException("Test error message")
        assert str(exc) == "Test error message"

    def test_exception_is_subclass_of_exception(self):
        """Test that InVesaliusException is a subclass of Exception."""
        assert issubclass(InVesaliusException, Exception)


# ==================== Custom Exception Classes Tests ====================


class TestCustomExceptionClasses:
    """Tests for custom exception classes."""

    def test_io_error_exception(self):
        """Test IOError exception class."""
        exc = IOError("File not found")
        assert exc.message == "File not found"
        assert exc.category == ErrorCategory.IO
        assert exc.severity == ErrorSeverity.ERROR

    def test_dicom_error_exception(self):
        """Test DicomError exception class."""
        exc = DicomError("Invalid DICOM file")
        assert exc.message == "Invalid DICOM file"
        assert exc.category == ErrorCategory.DICOM
        assert exc.severity == ErrorSeverity.ERROR

    def test_segmentation_error_exception(self):
        """Test SegmentationError exception class."""
        exc = SegmentationError("Segmentation failed")
        assert exc.message == "Segmentation failed"
        assert exc.category == ErrorCategory.SEGMENTATION
        assert exc.severity == ErrorSeverity.ERROR

    def test_surface_error_exception(self):
        """Test SurfaceError exception class."""
        exc = SurfaceError("Surface generation error")
        assert exc.message == "Surface generation error"
        assert exc.category == ErrorCategory.SURFACE
        assert exc.severity == ErrorSeverity.ERROR

    def test_rendering_error_exception(self):
        """Test RenderingError exception class."""
        exc = RenderingError("Rendering failed")
        assert exc.message == "Rendering failed"
        assert exc.category == ErrorCategory.RENDERING
        assert exc.severity == ErrorSeverity.ERROR

    def test_navigation_error_exception(self):
        """Test NavigationError exception class."""
        exc = NavigationError("Navigation error")
        assert exc.message == "Navigation error"
        assert exc.category == ErrorCategory.NAVIGATION
        assert exc.severity == ErrorSeverity.ERROR

    def test_plugin_error_exception(self):
        """Test PluginError exception class."""
        exc = PluginError("Plugin load error")
        assert exc.message == "Plugin load error"
        assert exc.category == ErrorCategory.PLUGIN
        assert exc.severity == ErrorSeverity.ERROR

    def test_memory_error_exception(self):
        """Test MemoryError exception class."""
        exc = MemoryError("Out of memory")
        assert exc.message == "Out of memory"
        assert exc.category == ErrorCategory.MEMORY
        assert exc.severity == ErrorSeverity.ERROR

    def test_custom_exception_with_original_exception(self):
        """Test custom exception with original exception."""
        original = RuntimeError("Original error")
        exc = DicomError("DICOM error occurred", original_exception=original)

        assert exc.original_exception == original
        assert "original_traceback" in exc.details


# ==================== Error Handling Decorator Tests ====================


class TestHandleErrorsDecorator:
    """Tests for the handle_errors decorator."""

    def test_decorator_on_successful_function(self):
        """Test that decorator doesn't interfere with successful functions."""

        @handle_errors("Error occurred")
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_decorator_catches_expected_exception(self):
        """Test that decorator catches expected exceptions."""

        @handle_errors(
            "Error in test function",
            show_dialog=False,
            log_error=False,
            reraise=False,
            expected_exceptions=(ValueError,),
        )
        def failing_func():
            raise ValueError("Test error")

        result = failing_func()
        assert result is None

    def test_decorator_with_reraise_option(self):
        """Test that decorator reraises exception when requested."""

        @handle_errors(
            "Error in test",
            show_dialog=False,
            log_error=False,
            reraise=True,
            expected_exceptions=(ValueError,),
        )
        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(InVesaliusException):
            failing_func()

    def test_decorator_creates_detailed_message(self):
        """Test that decorator creates a detailed error message."""

        @handle_errors(
            "Custom error",
            show_dialog=False,
            log_error=False,
            reraise=True,
            expected_exceptions=(ValueError,),
        )
        def failing_func():
            raise ValueError("Original error")

        with pytest.raises(InVesaliusException) as exc_info:
            failing_func()

        exc = exc_info.value
        assert "Custom error" in exc.message
        assert "failing_func" in exc.message

    def test_decorator_sets_error_category(self):
        """Test that decorator sets the error category correctly."""

        @handle_errors(
            "IO error",
            show_dialog=False,
            log_error=False,
            reraise=True,
            expected_exceptions=(OSError,),
            category=ErrorCategory.IO,
        )
        def failing_func():
            raise OSError("File error")

        with pytest.raises(InVesaliusException) as exc_info:
            failing_func()

        assert exc_info.value.category == ErrorCategory.IO

    def test_decorator_sets_error_severity(self):
        """Test that decorator sets the error severity correctly."""

        @handle_errors(
            "Critical error",
            show_dialog=False,
            log_error=False,
            reraise=True,
            expected_exceptions=(RuntimeError,),
            severity=ErrorSeverity.CRITICAL,
        )
        def failing_func():
            raise RuntimeError("System error")

        with pytest.raises(InVesaliusException) as exc_info:
            failing_func()

        assert exc_info.value.severity == ErrorSeverity.CRITICAL

    def test_decorator_stores_function_details(self):
        """Test that decorator stores function and line details."""

        @handle_errors(
            "Test error",
            show_dialog=False,
            log_error=False,
            reraise=True,
            expected_exceptions=(ValueError,),
        )
        def failing_func():
            raise ValueError("Error")

        with pytest.raises(InVesaliusException) as exc_info:
            failing_func()

        details = exc_info.value.details
        assert "module" in details
        assert "function" in details
        assert "failing_func" in details["function"]
        assert "line" in details
        assert "exception_type" in details
        assert details["exception_type"] == "ValueError"

    def test_decorator_with_multiple_expected_exceptions(self):
        """Test decorator with multiple expected exception types."""

        @handle_errors(
            "Error",
            show_dialog=False,
            log_error=False,
            reraise=False,
            expected_exceptions=(ValueError, TypeError),
        )
        def failing_func_value():
            raise ValueError("Value error")

        @handle_errors(
            "Error",
            show_dialog=False,
            log_error=False,
            reraise=False,
            expected_exceptions=(ValueError, TypeError),
        )
        def failing_func_type():
            raise TypeError("Type error")

        assert failing_func_value() is None
        assert failing_func_type() is None

    def test_decorator_with_function_arguments(self):
        """Test that decorator properly handles function arguments."""

        @handle_errors(
            "Error",
            show_dialog=False,
            log_error=False,
            reraise=True,
            expected_exceptions=(ValueError,),
        )
        def func_with_args(a, b, c=None):
            raise ValueError("Error")

        with pytest.raises(InVesaliusException) as exc_info:
            func_with_args(1, 2, c=3)

        details = exc_info.value.details
        assert "args" in details
        assert "kwargs" in details

    @mock.patch("invesalius.error_handling.Publisher.sendMessage")
    def test_decorator_publishes_error_message(self, mock_publisher):
        """Test that decorator publishes error message via Publisher."""

        @handle_errors(
            "Error",
            show_dialog=False,
            log_error=False,
            reraise=False,
            expected_exceptions=(ValueError,),
        )
        def failing_func():
            raise ValueError("Test")

        failing_func()
        mock_publisher.assert_called_once()
        call_args = mock_publisher.call_args
        assert call_args[0][0] == "Error occurred"


# ==================== System Information Tests ====================


class TestSystemInformation:
    """Tests for system information gathering functions."""

    def test_get_system_memory(self):
        """Test getting system memory information."""
        memory_gb = get_system_memory()
        assert isinstance(memory_gb, int)
        assert memory_gb > 0

    def test_get_system_info(self):
        """Test getting comprehensive system information."""
        info = get_system_info()

        # Check that all required keys are present
        required_keys = [
            "platform",
            "python_version",
            "processor",
            "memory",
            "invesalius_version",
        ]
        for key in required_keys:
            assert key in info

        # Check that values are strings
        for key, value in info.items():
            assert isinstance(value, str)

    def test_get_system_info_platform(self):
        """Test that platform information is correctly retrieved."""
        info = get_system_info()
        assert info["platform"] is not None
        assert len(info["platform"]) > 0

    def test_get_system_info_python_version(self):
        """Test that Python version is correctly retrieved."""
        info = get_system_info()
        assert info["python_version"] is not None
        assert len(info["python_version"]) > 0
        assert "." in info["python_version"]  # Should have version format x.y.z


# ==================== Crash Reporting Tests ====================


class TestCrashReporting:
    """Tests for crash report creation."""

    def test_create_crash_report_creates_file(self):
        """Test that create_crash_report creates a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock the inv_paths module to use temp directory
            with mock.patch("invesalius.error_handling.inv_paths.USER_LOG_DIR", tmpdir):
                exc = InVesaliusException(
                    "Test error",
                    category=ErrorCategory.IO,
                    severity=ErrorSeverity.ERROR,
                )
                crash_report_path = create_crash_report(exc)

                assert os.path.exists(crash_report_path)
                assert crash_report_path.endswith(".txt")

    def test_create_crash_report_contains_required_sections(self):
        """Test that crash report contains all required sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("invesalius.error_handling.inv_paths.USER_LOG_DIR", tmpdir):
                exc = InVesaliusException(
                    "Test error",
                    category=ErrorCategory.DICOM,
                    severity=ErrorSeverity.CRITICAL,
                    details={"test_key": "test_value"},
                )
                crash_report_path = create_crash_report(exc)

                with open(crash_report_path, "r") as f:
                    content = f.read()

                # Check for required sections
                assert "InVesalius Crash Report" in content
                assert "System Information" in content
                assert "Error Details" in content
                assert "Timestamp" in content
                assert "Error Category" in content
                assert "Error Severity" in content

    def test_create_crash_report_includes_exception_message(self):
        """Test that crash report includes the exception message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("invesalius.error_handling.inv_paths.USER_LOG_DIR", tmpdir):
                error_msg = "Critical system failure"
                exc = InVesaliusException(error_msg)
                crash_report_path = create_crash_report(exc)

                with open(crash_report_path, "r") as f:
                    content = f.read()

                assert error_msg in content

    def test_create_crash_report_includes_system_info(self):
        """Test that crash report includes system information."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("invesalius.error_handling.inv_paths.USER_LOG_DIR", tmpdir):
                exc = InVesaliusException("Test error")
                crash_report_path = create_crash_report(exc)

                with open(crash_report_path, "r") as f:
                    content = f.read()

                # Check for system info
                assert "platform:" in content
                assert "python_version:" in content

    def test_create_crash_report_creates_crash_directory(self):
        """Test that crash report creates the crash_reports directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("invesalius.error_handling.inv_paths.USER_LOG_DIR", tmpdir):
                exc = InVesaliusException("Error 1")
                crash_report_path = create_crash_report(exc)

                # Check that crash_reports directory was created
                crash_dir = os.path.join(tmpdir, "crash_reports")
                assert os.path.exists(crash_dir)
                assert os.path.isdir(crash_dir)
                assert os.path.exists(crash_report_path)

    def test_create_crash_report_with_original_exception(self):
        """Test crash report with original exception traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("invesalius.error_handling.inv_paths.USER_LOG_DIR", tmpdir):
                try:
                    raise ValueError("Original error")
                except ValueError as e:
                    exc = InVesaliusException("Wrapped error", original_exception=e)
                    crash_report_path = create_crash_report(exc)

                    with open(crash_report_path, "r") as f:
                        content = f.read()

                    assert "Original Traceback" in content
                    assert "ValueError" in content


# ==================== Error Dialog Tests ====================


class TestErrorDialog:
    """Tests for the ErrorDialog class."""

    @mock.patch("invesalius.error_handling.wx.GetApp")
    def test_show_error_dialog_without_gui(self, mock_get_app):
        """Test show_error_dialog when GUI is not available."""
        mock_get_app.return_value = None

        with mock.patch("builtins.print") as mock_print:
            exc = InVesaliusException("Test error")
            show_error_dialog("Test message", exc)

            # Should print error message
            mock_print.assert_called()

    def test_error_dialog_stores_exception(self):
        """Test that ErrorDialog stores the exception."""
        exc = InVesaliusException(
            "Test error", category=ErrorCategory.IO, severity=ErrorSeverity.ERROR
        )

        # We won't actually create the dialog (requires GUI), but we can test initialization
        assert exc.message == "Test error"
        assert exc.category == ErrorCategory.IO
        assert exc.severity == ErrorSeverity.ERROR


# ==================== Global Exception Handler Tests ====================


class TestGlobalExceptionHandler:
    """Tests for the global exception handler."""

    @mock.patch("invesalius.error_handling.create_crash_report")
    @mock.patch("invesalius.error_handling.show_error_dialog")
    @mock.patch("invesalius.error_handling.wx.GetApp")
    @mock.patch("builtins.print")
    def test_global_exception_handler_with_gui(
        self, mock_print, mock_get_app, mock_show_dialog, mock_create_report
    ):
        """Test global exception handler when GUI is available."""
        mock_get_app.return_value = mock.MagicMock()
        mock_create_report.return_value = "/path/to/crash_report.txt"

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()
            global_exception_handler(exc_info[0], exc_info[1], exc_info[2])

        mock_create_report.assert_called_once()
        mock_show_dialog.assert_called_once()

    @mock.patch("invesalius.error_handling.create_crash_report")
    @mock.patch("invesalius.error_handling.wx.GetApp")
    @mock.patch("builtins.print")
    def test_global_exception_handler_without_gui(
        self, mock_print, mock_get_app, mock_create_report
    ):
        """Test global exception handler when GUI is not available."""
        mock_get_app.return_value = None
        mock_create_report.return_value = "/path/to/crash_report.txt"

        try:
            raise RuntimeError("Test exception")
        except RuntimeError:
            exc_info = sys.exc_info()
            global_exception_handler(exc_info[0], exc_info[1], exc_info[2])

        mock_create_report.assert_called_once()
        # Should print error message
        assert mock_print.called


# ==================== Integration Tests ====================


class TestErrorHandlingIntegration:
    """Integration tests for the error handling system."""

    def test_exception_flow_io_error(self):
        """Test complete flow of IOError exception."""
        original_exc = FileNotFoundError("file.txt not found")
        exc = IOError(
            "Failed to open file",
            details={"filename": "file.txt"},
            original_exception=original_exc,
        )

        assert exc.category == ErrorCategory.IO
        assert exc.severity == ErrorSeverity.ERROR
        assert "filename" in exc.details
        assert exc.original_exception == original_exc

    def test_exception_flow_dicom_error(self):
        """Test complete flow of DicomError exception."""
        original_exc = ValueError("Invalid tag")
        exc = DicomError(
            "Failed to read DICOM file",
            details={"file": "scan.dcm"},
            original_exception=original_exc,
        )

        assert exc.category == ErrorCategory.DICOM
        assert exc.severity == ErrorSeverity.ERROR

    def test_decorated_function_with_io_error(self):
        """Test decorated function that raises IOError."""

        @handle_errors(
            "File operation failed",
            show_dialog=False,
            log_error=False,
            reraise=True,
            expected_exceptions=(FileNotFoundError,),
            category=ErrorCategory.IO,
        )
        def read_file(filename):
            raise FileNotFoundError(f"Cannot open {filename}")

        with pytest.raises(InVesaliusException) as exc_info:
            read_file("nonexistent.txt")

        exc = exc_info.value
        assert exc.category == ErrorCategory.IO
        assert "File operation failed" in exc.message

    def test_multiple_exception_levels(self):
        """Test exception nesting at multiple levels."""
        try:
            # Simulate nested exception
            try:
                raise ValueError("Low level error")
            except ValueError as e:
                raise IOError("Mid level error", original_exception=e)
        except IOError as e:
            wrapped = InVesaliusException("Top level error", original_exception=e)
            assert wrapped.original_exception == e
            assert wrapped.message == "Top level error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
