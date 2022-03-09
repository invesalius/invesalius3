#!/usr/bin/env python

from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import (
    vtkCellArray,
    vtkIterativeClosestPointTransform,
    vtkPolyData
)
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter


def main():
    # ============ create source points ==============
    print("Creating source points...")
    sourcePoints = vtkPoints()
    sourceVertices = vtkCellArray()

    sp_id = sourcePoints.InsertNextPoint(1.0, 0.1, 0.0)
    sourceVertices.InsertNextCell(1)
    sourceVertices.InsertCellPoint(sp_id)

    sp_id = sourcePoints.InsertNextPoint(0.1, 1.1, 0.0)
    sourceVertices.InsertNextCell(1)
    sourceVertices.InsertCellPoint(sp_id)

    sp_id = sourcePoints.InsertNextPoint(0.0, 0.1, 1.0)
    sourceVertices.InsertNextCell(1)
    sourceVertices.InsertCellPoint(sp_id)

    source = vtkPolyData()
    source.SetPoints(sourcePoints)
    source.SetVerts(sourceVertices)

    print("Displaying source points...")
    # ============ display source points ==============
    pointCount = 3
    for index in range(pointCount):
        point = [0, 0, 0]
        sourcePoints.GetPoint(index, point)
        print("source point[%s]=%s" % (index, point))

    # ============ create target points ==============
    print("Creating target points...")
    targetPoints = vtkPoints()
    targetVertices = vtkCellArray()

    tp_id = targetPoints.InsertNextPoint(1.0, 0.0, 0.0)
    targetVertices.InsertNextCell(1)
    targetVertices.InsertCellPoint(tp_id)

    tp_id = targetPoints.InsertNextPoint(0.0, 1.0, 0.0)
    targetVertices.InsertNextCell(1)
    targetVertices.InsertCellPoint(tp_id)

    tp_id = targetPoints.InsertNextPoint(0.0, 0.0, 1.0)
    targetVertices.InsertNextCell(1)
    targetVertices.InsertCellPoint(tp_id)

    target = vtkPolyData()
    target.SetPoints(targetPoints)
    target.SetVerts(targetVertices)

    # ============ display target points ==============
    print("Displaying target points...")
    pointCount = 3
    for index in range(pointCount):
        point = [0, 0, 0]
        targetPoints.GetPoint(index, point)
        print("target point[%s]=%s" % (index, point))

    print("Running ICP ----------------")
    # ============ run ICP ==============
    icp = vtkIterativeClosestPointTransform()
    icp.SetSource(source)
    icp.SetTarget(target)
    icp.GetLandmarkTransform().SetModeToRigidBody()
    # icp.DebugOn()
    icp.SetMaximumNumberOfIterations(20)
    icp.StartByMatchingCentroidsOn()
    icp.Modified()
    icp.Update()

    icpTransformFilter = vtkTransformPolyDataFilter()
    icpTransformFilter.SetInputData(source)

    icpTransformFilter.SetTransform(icp)
    icpTransformFilter.Update()

    transformedSource = icpTransformFilter.GetOutput()

    # ============ display transformed points ==============
    pointCount = 3
    for index in range(pointCount):
        point = [0, 0, 0]
        transformedSource.GetPoint(index, point)
        print("transformed source point[%s]=%s" % (index, point))


if __name__ == "__main__":
    main()
