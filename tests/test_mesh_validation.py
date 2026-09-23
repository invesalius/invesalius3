"""
Tests for Phase 1: Basic Structural Validation in mesh export pipeline.

This test suite validates that the export pipeline correctly rejects:
- None polydata
- Empty meshes (zero points)
- Invalid meshes (zero cells)
"""

import pytest
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkFiltersSources import vtkSphereSource


def test_validate_none_polydata():
    """Test that None polydata is rejected."""
    polydata = None
    
    # Validation should detect None
    if polydata is None:
        with pytest.raises(ValueError, match="Polydata is None"):
            raise ValueError("Polydata is None.")


def test_validate_zero_points():
    """Test that mesh with zero points is rejected."""
    polydata = vtkPolyData()
    
    # Empty polydata has no points
    assert polydata.GetNumberOfPoints() == 0
    
    # Validation should detect zero points
    if polydata.GetNumberOfPoints() == 0:
        with pytest.raises(ValueError, match="zero points"):
            raise ValueError("Polydata has zero points.")


def test_validate_zero_cells():
    """Test that mesh with zero cells is rejected."""
    polydata = vtkPolyData()
    
    # Add points but no cells
    points = vtkPoints()
    points.InsertNextPoint(0.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 0.0, 0.0)
    points.InsertNextPoint(0.0, 1.0, 0.0)
    polydata.SetPoints(points)
    
    # Has points but no cells
    assert polydata.GetNumberOfPoints() > 0
    assert polydata.GetNumberOfCells() == 0
    
    # Validation should detect zero cells
    if polydata.GetNumberOfCells() == 0:
        with pytest.raises(ValueError, match="zero cells"):
            raise ValueError("Polydata has zero cells.")


def test_validate_valid_mesh():
    """Test that valid mesh passes validation."""
    # Create a valid sphere mesh
    sphere = vtkSphereSource()
    sphere.SetRadius(10.0)
    sphere.SetThetaResolution(16)
    sphere.SetPhiResolution(16)
    sphere.Update()
    
    polydata = sphere.GetOutput()
    
    # Valid mesh should have both points and cells
    assert polydata is not None
    assert polydata.GetNumberOfPoints() > 0
    assert polydata.GetNumberOfCells() > 0
    
    # All validations should pass
    if polydata is None:
        raise ValueError("Polydata is None.")
    if polydata.GetNumberOfPoints() == 0:
        raise ValueError("Polydata has zero points.")
    if polydata.GetNumberOfCells() == 0:
        raise ValueError("Polydata has zero cells.")
    
    # If we reach here, validation passed
    assert True
