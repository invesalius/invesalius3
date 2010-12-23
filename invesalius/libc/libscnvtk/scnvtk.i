

/* example.i */
%module scnvtk 

%{
/* Put header files here or function declarations like below */

extern "C" {
  #include "ift.h"
}
#include "vtkImageData.h"

extern char *PointerToString(void *ptr, const char *type);
extern void *StringToPointer(char *ptrText, int len, const char *type);
extern void CopyImageBufferScnToVtk(char *ptrvtk, Scene *scn);
extern void CopyImageBufferVtkToScn(Scene *scn, char *ptrvtk);
 
%}


extern "C" {
  #include "ift.h"
}
#include "vtkImageData.h"

extern char *PointerToString(void *ptr, const char *type);
extern void *StringToPointer(char *ptrText, int len, const char *type);
extern void CopyImageBufferScnToVtk(char *ptrvtk, Scene *scn);
extern void CopyImageBufferVtkToScn(Scene *scn, char *ptrvtk);



