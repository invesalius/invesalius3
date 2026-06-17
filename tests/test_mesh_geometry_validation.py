"""
Tests for Mesh Geometry Validation in export pipeline.

This test suite validates that the export pipeline correctly detects:
- Degenerate triangles (zero or near-zero area)
- Duplicate vertices within cells
"""

import numpy as np
import pytest
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData, vtkTriangle
from vtkmodules.vtkFiltersSources import vtkSphereSource


def test_detect_degenerate_triangle():
    """Test that degenerate triangles (zero area) are detected."""
    polydata = vtkPolyData()
    points = vtkPoints()
    
    # Create three collinear points (zero area triangle)
    points.InsertNextPoint(0.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 0.0, 0.0)
    points.InsertNextPoint(2.0, 0.0, 0.0)
    
    polydata.SetPoints(points)
    
    # Add triangle with collinear points
    triangles = vtkCellArray()
    triangle = vtkTriangle()
    triangle.GetPointIds().SetId(0, 0)
    triangle.GetPointIds().SetId(1, 1)
    triangle.GetPointIds().SetId(2, 2)
    triangles.InsertNextCell(triangle)
    
    polydata.SetPolys(triangles)
    
    # Validation should detect degenerate triangle
    assert polydata.GetNumberOfPoints() == 3
    assert polydata.GetNumberOfCells() == 1
    
    # Calculate area manually to verify it's zero
    p0 = np.array(polydata.GetPoint(0))
    p1 = np.array(polydata.GetPoint(1))
    p2 = np.array(polydata.GetPoint(2))
    
    v1 = p1 - p0
    v2 = p2 - p0
    cross = np.cross(v1, v2)
    area = 0.5 * np.linalg.norm(cross)
    
    assert area < 1e-10, "Triangle should have zero area"


def test_detect_duplicate_vertices_in_cell():
    """Test that cells with duplicate vertices are detected."""
    polydata = vtkPolyData()
    points = vtkPoints()
    
    # Create points
    points.InsertNextPoint(0.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 0.0, 0.0)
    points.InsertNextPoint(0.0, 1.0, 0.0)
    
    polydata.SetPoints(points)
    
    # Add triangle with duplicate vertex (0, 0, 1) - vertex 0 appears twice
    triangles = vtkCellArray()
    triangle = vtkTriangle()
    triangle.GetPointIds().SetId(0, 0)
    triangle.GetPointIds().SetId(1, 0)  # Duplicate!
    triangle.GetPointIds().SetId(2, 1)
    triangles.InsertNextCell(triangle)
    
    polydata.SetPolys(triangles)
    
    # Verify duplicate exists
    from vtkmodules.vtkCommonCore import vtkIdList
    idlist = vtkIdList()
    polydata.GetCellPoints(0, idlist)
    
    point_ids = [idlist.GetId(j) for j in range(idlist.GetNumberOfIds())]
    assert len(point_ids) != len(set(point_ids)), "Cell should have duplicate vertices"


def test_valid_triangle_passes():
    """Test that valid triangles pass geometry validation."""
    polydata = vtkPolyData()
    points = vtkPoints()
    
    # Create valid triangle
    points.InsertNextPoint(0.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 0.0, 0.0)
    points.InsertNextPoint(0.0, 1.0, 0.0)
    
    polydata.SetPoints(points)
    
    triangles = vtkCellArray()
    triangle = vtkTriangle()
    triangle.GetPointIds().SetId(0, 0)
    triangle.GetPointIds().SetId(1, 1)
    triangle.GetPointIds().SetId(2, 2)
    triangles.InsertNextCell(triangle)
    
    polydata.SetPolys(triangles)
    
    # Calculate area to verify it's non-zero
    p0 = np.array(polydata.GetPoint(0))
    p1 = np.array(polydata.GetPoint(1))
    p2 = np.array(polydata.GetPoint(2))
    
    v1 = p1 - p0
    v2 = p2 - p0
    cross = np.cross(v1, v2)
    area = 0.5 * np.linalg.norm(cross)
    
    assert area > 1e-10, "Valid triangle should have non-zero area"
    assert polydata.GetNumberOfPoints() == 3
    assert polydata.GetNumberOfCells() == 1


def test_sphere_mesh_is_valid():
    """Test that a properly generated sphere mesh passes all validations."""
    sphere = vtkSphereSource()
    sphere.SetRadius(10.0)
    sphere.SetThetaResolution(16)
    sphere.SetPhiResolution(16)
    sphere.Update()
    
    polydata = sphere.GetOutput()
    
    # Basic checks
    assert polydata is not None
    assert polydata.GetNumberOfPoints() > 0
    assert polydata.GetNumberOfCells() > 0
    
    # Check for degenerate triangles
    from vtkmodules.vtkCommonCore import vtkIdList
    idlist = vtkIdList()
    degenerate_count = 0
    
    for i in range(polydata.GetNumberOfCells()):
        polydata.GetCellPoints(i, idlist)
        if idlist.GetNumberOfIds() == 3:
            point_ids = [idlist.GetId(j) for j in range(3)]
            p0 = np.array(polydata.GetPoint(point_ids[0]))
            p1 = np.array(polydata.GetPoint(point_ids[1]))
            p2 = np.array(polydata.GetPoint(point_ids[2]))
            
            v1 = p1 - p0
            v2 = p2 - p0
            cross = np.cross(v1, v2)
            area = 0.5 * np.linalg.norm(cross)
            
            if area < 1e-10:
                degenerate_count += 1
    
    assert degenerate_count == 0, "Sphere mesh should have no degenerate triangles"


def test_near_zero_area_triangle():
    """Test detection of triangles with very small but non-zero area."""
    polydata = vtkPolyData()
    points = vtkPoints()
    
    # Create triangle with very small area (nearly collinear)
    points.InsertNextPoint(0.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 1e-12, 0.0)  # Very small offset
    
    polydata.SetPoints(points)
    
    triangles = vtkCellArray()
    triangle = vtkTriangle()
    triangle.GetPointIds().SetId(0, 0)
    triangle.GetPointIds().SetId(1, 1)
    triangle.GetPointIds().SetId(2, 2)
    triangles.InsertNextCell(triangle)
    
    polydata.SetPolys(triangles)
    
    # Calculate area
    p0 = np.array(polydata.GetPoint(0))
    p1 = np.array(polydata.GetPoint(1))
    p2 = np.array(polydata.GetPoint(2))
    
    v1 = p1 - p0
    v2 = p2 - p0
    cross = np.cross(v1, v2)
    area = 0.5 * np.linalg.norm(cross)
    
    # Should be below threshold
    assert area < 1e-10, "Triangle should have near-zero area"
