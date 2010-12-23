


import scnvtk
import vtk
from ..libift import libift as libift



def Interp(img):
    scn = VtkImageDataToScene(img)
    scn2=libift.LinearInterp(scn,0,0,0)
    libift.NewDestroyScene(scn)
    return SceneToVtkImageData(scn2)


def SceneToVtkImageData(scn):
    dx = libift.GetDx(scn)
    dy = libift.GetDy(scn)
    dz = libift.GetDz(scn)
    xsize = libift.GetXSize(scn)
    ysize = libift.GetYSize(scn)
    zsize =  libift.GetZSize(scn)
    img = vtk.vtkImageData()
    img.SetSpacing(dx,dy,dz)
    img.SetOrigin(0,0,0)
    img.SetDimensions(xsize,ysize,zsize)
    img.SetScalarTypeToUnsignedShort()
    img.SetNumberOfScalarComponents(1)
    img.AllocateScalars()
    scnvtk.CopyImageBufferScnToVtk(img.GetScalarPointer(),scn)
    return img

def VtkImageDataToScene(img):
    d = img.GetSpacing()
    dx=d[0]
    dy=d[1]
    dz=d[2]
    d = img.GetDimensions()
    xsize=d[0]
    ysize=d[1]
    zsize=d[2]
    scn=libift.CreateScene(xsize,ysize,zsize)
    libift.SetDx(scn,dx)
    libift.SetDy(scn,dy)
    libift.SetDz(scn,dz)
    scnvtk.CopyImageBufferVtkToScn(scn,img.GetScalarPointer())
    return scn



def WriteVtkImageData(img,filename):
    scn = VtkImageDataToScene(img)
    libift.WriteScene(scn,filename)
    libift.NewDestroyScene(scn)

def ReadVtkImageData(filename):
    scn = libift.ReadScene(filename)
    img=SceneToVtkImageData(scn)
    libift.NewDestroyScene(scn)
    return img


