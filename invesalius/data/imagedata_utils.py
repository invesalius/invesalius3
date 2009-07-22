import math
import vtk

# TODO: Test cases which are originally in sagittal/coronal orientation
# and have gantry

def ResampleMatrix(imagedata, xy_dimension):
    """
    Resample vtkImageData matrix.
    """
    extent = imagedata.GetExtent()
    spacing = imagedata.GetSpacing()

    if extent[1]==extent[3]:
        f = extent[1]
        x = 0
        y = 1

    elif extent[1]==extent[5]:
        f = extent[1]
        x=0
        y=2

    elif extent[3]==extent[5]:
        f = extent[3]
        x = 1
        y = 2

    factor = xy_dimension/float(f+1)
    
    resample = vtk.vtkImageResample()
    resample.SetInput(imagedata)
    resample.SetAxisMagnificationFactor(0, factor)
    resample.SetAxisMagnificationFactor(1, factor)
    resample.SetOutputSpacing(spacing[0] * factor, spacing[1] * factor, spacing[2])
    resample.Update()
    
    
    return resample.GetOutput()
        
            

def FixGantryTilt(imagedata, tilt):
    """
    Fix gantry tilt given a vtkImageData and the tilt value. Return new
    vtkImageData.
    """

    # Retrieve data from original imagedata
    extent = [int(value) for value in imagedata.GetExtent()]
    origin = imagedata.GetOrigin()
    spacing = [float(value) for value in imagedata.GetSpacing()]

    n_slices = int(extent[5])
    new_zspacing = math.cos(tilt*(math.acos(-1.0)/180.0)) * spacing[2] #zspacing
    translate_coef = math.tan(tilt*math.pi/180.0)*new_zspacing*(n_slices-1)

    # Class responsible for translating data
    reslice = vtk.vtkImageReslice()
    reslice.SetInput(imagedata)
    reslice.SetInterpolationModeToLinear()
    # Translation will create new pixels. Let's set new pixels' colour to black.
    reslice.SetBackgroundLevel(imagedata.GetScalarRange()[0])

    # Class responsible for append translated data
    append = vtk.vtkImageAppend()
    append.SetAppendAxis(2)

    # Translate and append each slice
    for i in xrange(n_slices+1):
        slice_imagedata = vtk.vtkImageData()
        value = math.tan(tilt*math.pi/180.0) * new_zspacing * i
        new_origin1 = origin[1] + value - translate_coef
        # Translate data
        reslice.SetOutputOrigin(origin[0], new_origin1, origin[2])
        reslice.SetOutputExtent(extent[0], extent[1], extent[2], extent[3], i,i)
        reslice.Update()
        # Append data
        slice_imagedata.DeepCopy(reslice.GetOutput())
        slice_imagedata.UpdateInformation()

        append.AddInput(slice_imagedata)

    append.Update()

    # Final imagedata
    imagedata = vtk.vtkImageData()
    imagedata.DeepCopy(append.GetOutput())
    imagedata.SetSpacing(spacing[0], spacing[1], new_zspacing)
    imagedata.SetExtent(extent)
    imagedata.UpdateInformation()

    return imagedata
