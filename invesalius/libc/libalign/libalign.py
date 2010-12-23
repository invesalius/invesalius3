

from ..libift import libift as libift
from ..libscnvtk import libscnvtk as libscnvtk


def VolumeAlign(img):
   scn = libscnvtk.VtkImageDataToScene(img)
   print "VolumeAlign()"
   flag=libift.ShiftScene(scn)
   scn2 = libift.MSP_Align(scn,None,0,1)
   libift.UnShiftScene(scn2,flag)
   return libscnvtk.SceneToVtkImageData(scn2)
   


def Interp(img):
    scn = libscnvtk.VtkImageDataToScene(img)
    flag=libift.ShiftScene(scn)
    scn2=libift.LinearInterp(scn,0,0,0)
    libift.UnShiftScene(scn2,flag)
    return libscnvtk.SceneToVtkImageData(scn2)

