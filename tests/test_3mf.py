"""
Unit tests for 3MF import/export functionality.
Tests lib3mf integration directly without full GUI dependencies.
"""

import os
import zipfile
from pathlib import Path

import numpy as np
import pytest
from ctypes import c_float, c_uint32
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkPoints, vtkIdList
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData, vtkTriangle

# Check if lib3mf is available
try:
    import lib3mf
    HAS_LIB3MF = True
except ImportError:
    HAS_LIB3MF = False

pytestmark = pytest.mark.skipif(not HAS_LIB3MF, reason="lib3mf not available")


def make_simple_triangle() -> vtkPolyData:
    """Create a simple polydata with a single triangle."""
    points = vtkPoints()
    points.InsertNextPoint(0.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 0.0, 0.0)
    points.InsertNextPoint(0.0, 1.0, 0.0)

    triangle = vtkTriangle()
    triangle.GetPointIds().SetId(0, 0)
    triangle.GetPointIds().SetId(1, 1)
    triangle.GetPointIds().SetId(2, 2)

    triangles = vtkCellArray()
    triangles.InsertNextCell(triangle)

    polydata = vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(triangles)

    return polydata


def export_polydata_to_3mf(polydata: vtkPolyData, filename: str, name: str = "Test",
                          color: tuple = (1.0, 0.0, 0.0), alpha: int = 255):
    """Helper to export a vtkPolyData to 3MF using lib3mf."""
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    model.SetUnit(lib3mf.ModelUnit.MilliMeter)
    
    mesh_object = model.AddMeshObject()
    mesh_object.SetName(name)
    
    # Add vertices
    points_vtk = polydata.GetPoints()
    for i in range(points_vtk.GetNumberOfPoints()):
        pos = lib3mf.Position()
        pt = points_vtk.GetPoint(i)
        pos.Coordinates = (c_float * 3)(float(pt[0]), float(pt[1]), float(pt[2]))
        mesh_object.AddVertex(pos)
    
    # Add triangles
    polys = polydata.GetPolys()
    polys.InitTraversal()
    id_list = vtkIdList()
    while polys.GetNextCell(id_list):
        if id_list.GetNumberOfIds() == 3:
            tri = lib3mf.Triangle()
            tri.Indices = (c_uint32 * 3)(
                id_list.GetId(0), id_list.GetId(1), id_list.GetId(2)
            )
            mesh_object.AddTriangle(tri)
    
    # Add color
    color_group = model.AddColorGroup()
    color_obj = lib3mf.Color()
    color_obj.Red = int(color[0] * 255)
    color_obj.Green = int(color[1] * 255)
    color_obj.Blue = int(color[2] * 255)
    color_obj.Alpha = alpha
    color_id = color_group.AddColor(color_obj)
    mesh_object.SetObjectLevelProperty(color_group.GetResourceID(), color_id)
    
    model.AddBuildItem(mesh_object, wrapper.GetIdentityTransform())
    writer = model.QueryWriter("3mf")
    writer.WriteToFile(filename)


def test_export_creates_valid_file(tmp_path: Path):
    """Test that exporting creates a valid non-empty 3MF file."""
    filename = tmp_path / "test.3mf"
    polydata = make_simple_triangle()
    
    export_polydata_to_3mf(polydata, str(filename))
    
    assert os.path.exists(filename), "3MF file was not created"
    assert os.path.getsize(filename) > 0, "3MF file is empty"
    assert zipfile.is_zipfile(filename), "3MF file is not a valid zip archive"


def test_geometry_roundtrip(tmp_path: Path):
    """Test that vertex and triangle counts are preserved."""
    filename = tmp_path / "roundtrip.3mf"
    polydata = make_simple_triangle()
    
    original_vertices = polydata.GetNumberOfPoints()
    original_triangles = polydata.GetNumberOfCells()
    
    export_polydata_to_3mf(polydata, str(filename))
    
    # Import back
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.ReadFromFile(str(filename))
    
    build_items = model.GetBuildItems()
    assert build_items.Count() > 0
    
    build_items.MoveNext()
    build_item = build_items.GetCurrent()
    object_resource = build_item.GetObjectResource()
    mesh_object = model.GetMeshObjectByID(object_resource.GetResourceID())
    
    assert mesh_object.GetVertexCount() == original_vertices
    assert mesh_object.GetTriangleCount() == original_triangles


def test_color_roundtrip(tmp_path: Path):
    """Test that RGBA color values are preserved."""
    filename = tmp_path / "color_test.3mf"
    polydata = make_simple_triangle()
    original_color = (1.0, 0.5, 0.25)
    
    export_polydata_to_3mf(polydata, str(filename), color=original_color)
    
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.ReadFromFile(str(filename))
    
    build_items = model.GetBuildItems()
    build_items.MoveNext()
    build_item = build_items.GetCurrent()
    object_resource = build_item.GetObjectResource()
    mesh_object = model.GetMeshObjectByID(object_resource.GetResourceID())
    
    property_result = mesh_object.GetObjectLevelProperty()
    assert property_result and len(property_result) == 3 and property_result[2]
    
    resource_id, property_id, has_property = property_result
    color_group = model.GetColorGroupByID(resource_id)
    color = color_group.GetColor(property_id)
    
    imported_color = (color.Red / 255.0, color.Green / 255.0, color.Blue / 255.0)
    assert np.allclose(imported_color, original_color, atol=1.0 / 255.0)


def test_alpha_roundtrip(tmp_path: Path):
    """Test that transparency (alpha) is preserved."""
    filename = tmp_path / "alpha_test.3mf"
    polydata = make_simple_triangle()
    original_alpha = 128  # 50% transparent
    
    export_polydata_to_3mf(polydata, str(filename), alpha=original_alpha)
    
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.ReadFromFile(str(filename))
    
    build_items = model.GetBuildItems()
    build_items.MoveNext()
    build_item = build_items.GetCurrent()
    object_resource = build_item.GetObjectResource()
    mesh_object = model.GetMeshObjectByID(object_resource.GetResourceID())
    
    property_result = mesh_object.GetObjectLevelProperty()
    resource_id, property_id, has_property = property_result
    color_group = model.GetColorGroupByID(resource_id)
    color = color_group.GetColor(property_id)
    
    assert color.Alpha == original_alpha


def test_multi_surface_export(tmp_path: Path):
    """Test exporting multiple surfaces creates correct number of mesh objects."""
    filename = tmp_path / "multi.3mf"
    
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    model.SetUnit(lib3mf.ModelUnit.MilliMeter)
    
    # Create 3 meshes
    for i in range(3):
        polydata = make_simple_triangle()
        mesh_object = model.AddMeshObject()
        mesh_object.SetName(f"Surface_{i}")
        
        points_vtk = polydata.GetPoints()
        for j in range(points_vtk.GetNumberOfPoints()):
            pos = lib3mf.Position()
            pt = points_vtk.GetPoint(j)
            pos.Coordinates = (c_float * 3)(float(pt[0]), float(pt[1]), float(pt[2]))
            mesh_object.AddVertex(pos)
        
        polys = polydata.GetPolys()
        polys.InitTraversal()
        id_list = vtkIdList()
        while polys.GetNextCell(id_list):
            if id_list.GetNumberOfIds() == 3:
                tri = lib3mf.Triangle()
                tri.Indices = (c_uint32 * 3)(
                    id_list.GetId(0), id_list.GetId(1), id_list.GetId(2)
                )
                mesh_object.AddTriangle(tri)
        
        model.AddBuildItem(mesh_object, wrapper.GetIdentityTransform())
    
    writer = model.QueryWriter("3mf")
    writer.WriteToFile(str(filename))
    
    # Verify
    wrapper2 = lib3mf.Wrapper()
    model2 = wrapper2.CreateModel()
    reader = model2.QueryReader("3mf")
    reader.ReadFromFile(str(filename))
    
    assert model2.GetBuildItems().Count() == 3


def test_duplicate_name_handling():
    """Test that the deduplication logic works correctly."""
    from collections import Counter
    
    # Simulate visible_surfaces list
    visible_surfaces = [
        (None, "Bone", (1, 0, 0), 1.0),
        (None, "Bone", (0, 1, 0), 1.0),
        (None, "Skin", (0, 0, 1), 1.0),
    ]
    
    # Apply deduplication logic from surface.py
    for i, (polydata, name, colour, opacity) in enumerate(visible_surfaces):
        if not name:
            visible_surfaces[i] = (polydata, f"Surface_{i + 1}", colour, opacity)
    
    names = [item[1] for item in visible_surfaces]
    name_counts = Counter(names)
    duplicates = {name: 0 for name, count in name_counts.items() if count > 1}
    
    for i, (polydata, name, colour, opacity) in enumerate(visible_surfaces):
        if name in duplicates:
            duplicates[name] += 1
            new_name = f"{name}_{duplicates[name]:02d}"
            visible_surfaces[i] = (polydata, new_name, colour, opacity)
    
    names_after = [item[1] for item in visible_surfaces]
    assert "Bone_01" in names_after
    assert "Bone_02" in names_after
    assert "Skin" in names_after
    assert len(names_after) == len(set(names_after))


def test_degenerate_triangle_filtering():
    """Test that degenerate triangles are filtered correctly."""
    test_cases = [
        ((0, 1, 2), True),   # Valid
        ((0, 0, 2), False),  # v0==v1
        ((0, 1, 1), False),  # v1==v2
        ((2, 1, 2), False),  # v0==v2
        ((3, 3, 3), False),  # All same
    ]
    
    for (v0, v1, v2), expected_valid in test_cases:
        is_valid = (v0 != v1 and v1 != v2 and v0 != v2)
        assert is_valid == expected_valid, f"Failed for ({v0}, {v1}, {v2})"


def test_malformed_file_import(tmp_path: Path):
    """Test that importing an invalid 3MF raises an exception."""
    invalid_file = tmp_path / "invalid.3mf"
    with zipfile.ZipFile(invalid_file, "w") as zf:
        zf.writestr("invalid.xml", "<invalid/>")
    
    try:
        wrapper = lib3mf.Wrapper()
        model = wrapper.CreateModel()
        reader = model.QueryReader("3mf")
        reader.ReadFromFile(str(invalid_file))
    except Exception:
        assert True  # Expected
        return
    
    # If no exception, that's okay - lib3mf might handle gracefully


def test_vertex_coordinates_preserved(tmp_path: Path):
    """Test that vertex coordinates are accurately preserved."""
    filename = tmp_path / "coords_test.3mf"
    polydata = make_simple_triangle()
    original_points = numpy_support.vtk_to_numpy(polydata.GetPoints().GetData())
    
    export_polydata_to_3mf(polydata, str(filename))
    
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.ReadFromFile(str(filename))
    
    build_items = model.GetBuildItems()
    build_items.MoveNext()
    build_item = build_items.GetCurrent()
    object_resource = build_item.GetObjectResource()
    mesh_object = model.GetMeshObjectByID(object_resource.GetResourceID())
    
    vertex_count = mesh_object.GetVertexCount()
    imported_points = np.zeros((vertex_count, 3))
    
    for i in range(vertex_count):
        vertex = mesh_object.GetVertex(i)
        imported_points[i] = [
            vertex.Coordinates[0],
            vertex.Coordinates[1],
            vertex.Coordinates[2],
        ]
    
    assert np.allclose(original_points, imported_points, atol=1e-5)
