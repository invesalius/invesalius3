

from ..libift import libift as libift
from ..libscnvtk import libscnvtk as libscnvtk


def VolumeAlign(img):
   scn = libscnvtk.VtkImageDataToScene(img)
   print "VolumeAlign()"
   scn2 = libift.MSP_Align(scn,None,0,1)
   return libscnvtk.SceneToVtkImageData(scn2)
   


def Interp(img):
    scn = libscnvtk.VtkImageDataToScene(img)
    scn2=libift.LinearInterp(scn,0,0,0)
    return libscnvtk.SceneToVtkImageData(scn2)

