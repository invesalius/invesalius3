
#include "vtkImageData.h"


extern "C" {
  #include "ift.h"
}


// Prototypes


char *PointerToString(void *ptr, const char *type);
void *StringToPointer(char *ptrText, int len, const char *type);
void CopyImageBufferScnToVtk(char *ptrvtk, Scene *scn);
void CopyImageBufferVtkToScn(Scene *scn, char *ptrvtk);





//#if defined ( _MSC_VER )
//#  define vtkConvertPtrToLong(x) ((long)(PtrToUlong(x)))
//#else
#  define vtkConvertPtrToLong(x) ((long)(x))
//#endif

//--------------------------------------------------------------------
// mangle a void pointer into a SWIG-style string
char *PointerToString(void *ptr, const char *type)
{
  static char ptrText[128];
  sprintf(ptrText,"_%*.*lx_%s",2*(int)sizeof(void *),2*(int)sizeof(void *),
          vtkConvertPtrToLong(ptr),type);
  return ptrText;
}

//--------------------------------------------------------------------
// unmangle a void pointer from a SWIG-style string
void *StringToPointer(char *ptrText, int len, const char *type)
{
  int i;
  void *ptr;
  char typeCheck[128];
  if (len < 128) {
    i = sscanf(ptrText,"_%lx_%s",(long *)&ptr,typeCheck);
    if (strcmp(type,typeCheck) == 0) { 
      // sucessfully unmangle
      return ptr;
    }
  }
 return NULL;      
}



void CopyImageBufferScnToVtk(char *ptrvtk, Scene *scn) {
  int i;
  int n = scn->xsize*scn->ysize*scn->zsize;
  short int *ptr = (short int *) StringToPointer(ptrvtk,strlen(ptrvtk),"void_p");
  if (ptr==NULL) {
    printf("CopyImageBufferScnToVtk() error! Null Pointer!\n");
    return;
  }
  for (i=0;i<n;i++) 
    *(ptr+i)=(short int) scn->data[i];
}


void CopyImageBufferVtkToScn(Scene *scn, char *ptrvtk) {
  int i;
  int n = scn->xsize*scn->ysize*scn->zsize;
  short int *ptr = (short int *) StringToPointer(ptrvtk,strlen(ptrvtk),"void_p");
  if (ptr==NULL) {
    printf("CopyImageBufferVtkToScn() error! Null Pointer!\n");
    return;
  }
  for (i=0;i<n;i++) 
    scn->data[i] = (int) *(ptr+i);
}






