# Error Handling System Tests - Comprehensive Testing PR

## Summary
This PR adds comprehensive test coverage for the `invesalius/error_handling.py` module, which was previously untested. The error handling module is critical infrastructure used throughout the InVesalius application.

## What's New

### New Test File
- **`tests/test_error_handling.py`** - 732 lines of comprehensive test coverage with 49 test cases

### Test Coverage Breakdown

#### 1. **ErrorCategory Enum Tests** (3 tests)
- Validation of all 15 error category members
- Uniqueness of enum values
- Enum member access patterns

#### 2. **ErrorSeverity Enum Tests** (3 tests)
- Validation of all 5 severity levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Uniqueness verification
- Proper enum value access

#### 3. **InVesaliusException Base Exception Tests** (6 tests)
- Basic exception creation with default parameters
- Exception creation with all parameters
- Automatic timestamp generation
- Original exception traceback storage
- String representation
- Exception hierarchy validation

#### 4. **Custom Exception Classes Tests** (9 tests)
- IOError exception with correct category and severity
- DicomError for DICOM-related failures
- SegmentationError for segmentation operations
- SurfaceError for surface generation
- RenderingError for rendering issues
- NavigationError for navigation systems
- PluginError for plugin loading
- MemoryError for memory-related failures
- Exception wrapping with original exception information

#### 5. **Error Handling Decorator Tests** (10 tests)
- Successful function execution without interference
- Exception catching for expected exceptions
- Reraise functionality
- Detailed error message creation with function context
- Error category and severity assignment
- Function detail storage (module, function name, line number, arguments)
- Multiple expected exception types handling
- Function arguments preservation
- Publisher event emission on errors

#### 6. **System Information Tests** (4 tests)
- System memory retrieval
- Comprehensive system info gathering
- Platform information validation
- Python version string verification

#### 7. **Crash Report Generation Tests** (6 tests)
- Crash report file creation
- Required sections validation (timestamp, category, severity, details, system info)
- Exception message inclusion
- System information embedding
- Crash directory creation
- Original exception traceback inclusion

#### 8. **Error Dialog Tests** (2 tests)
- Behavior when GUI is unavailable
- Exception storage in dialog

#### 9. **Global Exception Handler Tests** (2 tests)
- Handler behavior with GUI available
- Handler behavior without GUI

#### 10. **Integration Tests** (4 tests)
- Complete IOError exception flow
- Complete DicomError exception flow
- Decorated function with IOError
- Multi-level exception nesting

## Key Features

✅ **Comprehensive Coverage** - Tests cover all major components of the error handling system
✅ **Mock Integration** - Uses `unittest.mock` for GUI and external dependency isolation
✅ **Temporary Directories** - Crash report tests use temporary directories to avoid filesystem pollution
✅ **Well-Organized** - Tests are organized into logical test classes by functionality
✅ **Clear Documentation** - Each test has docstrings explaining its purpose
✅ **Real-World Scenarios** - Tests include integration tests covering common error flows

## Test Results

```
============================== 49 passed in 0.31s ==============================
```

All tests pass successfully!

## Dependencies Added
- No new runtime dependencies
- Testing uses existing test framework (pytest, pytest-mock)

## How to Run

```bash
# Run all error handling tests
pytest tests/test_error_handling.py -v

# Run specific test class
pytest tests/test_error_handling.py::TestErrorCategory -v

# Run with detailed output
pytest tests/test_error_handling.py -vv --tb=long
```

## Future Improvements

While this PR provides comprehensive coverage of the error handling module, potential future enhancements could include:

1. Tests for the `show_error_dialog()` function with mocked wx components
2. Tests for the `show_message()` and convenience functions (`show_info()`, `show_warning()`, etc.)
3. Logging integration tests to verify error messages are properly logged
4. Performance tests for crash report generation under various conditions
5. Tests for error recovery scenarios and error state cleanup

## Impact

This PR significantly improves the reliability and maintainability of the InVesalius error handling infrastructure by:

- Ensuring exception classes behave as expected
- Validating error categorization and severity levels
- Verifying decorator functionality works correctly
- Testing crash report generation and system information gathering
- Providing a safety net for future refactoring

The comprehensive test suite will help catch regressions early and make the error handling system more robust and trustworthy.
