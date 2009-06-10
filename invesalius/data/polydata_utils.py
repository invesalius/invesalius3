import vtk
import wx.lib.pubsub as ps

import vtk_utils as vu

# Update progress value in GUI
UpdateProgress = vu.ShowProgress()

def ApplyDecimationFilter(polydata, reduction_factor):
    """
    Reduce number of triangles of the given vtkPolyData, based on 
    reduction_factor.
    """
    # Important: vtkQuadricDecimation presented better results than
    # vtkDecimatePro
    decimation = vtk.vtkQuadricDecimation()
    decimation.SetInput(polydata)
    decimation.SetTargetReduction(reduction_factor)
    decimation.GetOutput().ReleaseDataFlagOn()
    decimation.AddObserver("ProgressEvent", lambda obj, evt:
                  UpdateProgress(decimation, "Reducing number of triangles..."))
    return decimation.GetOutput()

def ApplySmoothFilter(polydata, iterations, relaxation_factor):
    """
    Smooth given vtkPolyData surface, based on iteration and relaxation_factor.
    """
    smoother = vtk.vtkSmoothPolyDataFilter()
    smoother.SetInput(polydata)
    smoother.SetNumberOfIterations(iterations)
    smoother.SetFeatureAngle(80)
    smoother.SetRelaxationFactor(relaxation_factor)
    smoother.FeatureEdgeSmoothingOn()
    smoother.BoundarySmoothingOn()
    smoother.GetOutput().ReleaseDataFlagOn()    
    smoother.AddObserver("ProgressEvent", lambda obj, evt:
                         UpdateProgress(smoother, "Smoothing surface..."))
    
    return smoother.GetOutput()
    
def SelectLargestSurface(polydata):
    """
    """
    pass
    return polydata

def SplitDisconectedSurfaces(polydata):
    """
    """
    return []
    
# TODO: style?    
def SelectSurfaceByCell(polytada, list_index = []):
    """
    """
    pass
    return []

def FillSurfaceHole(polydata):
    """
    Fill holes in the given polydata.
    """
    # Filter used to detect and fill holes. Only fill 
    print "Filling polydata"
    filled_polydata = vtk.vtkFillHolesFilter()
    filled_polydata.SetInput(polydata)
    filled_polydata.SetHoleSize(500)
    return filled_polydata.GetOutput()

def CalculateSurfaceVolume(polydata):
    """
    Calculate the volume from the given polydata
    """
    # Filter used to calculate volume and area from a polydata
    measured_polydata = vtk.vtkMassProperties()
    measured_polydata.SetInput(polydata)
    return measured_polydata.GetVolume()

def CalculateSurfaceArea(polydata):
    """
    Calculate the volume from the given polydata
    """
    # Filter used to calculate volume and area from a polydata
    measured_polydata = vtk.vtkMassProperties()
    measured_polydata.SetInput(polydata)
    return measured_polydata.GetSurfaceArea()
