

/* example.i */
%module libift 

%{
/* Put header files here or function declarations like below */

#include "ift.h"

extern void NewDestroyScene(Scene *scn);
extern Scene* EraseBackground(Scene *scn);
extern Scene* EraseSupport(Scene *scn);
extern int ShiftScene(Scene *scn);
extern void UnShiftScene(Scene *scn, int flag);

/* From ift library */
extern float GetDx(Scene *scn);
extern float GetDy(Scene *scn);
extern float GetDz(Scene *scn);
extern int GetXSize(Scene *scn);
extern int GetYSize(Scene *scn);
extern int GetZSize(Scene *scn);
extern Scene  *CreateScene(int xsize,int ysize,int zsize);
extern void SetDx(Scene *scn, float dx);
extern void SetDy(Scene *scn, float dy);
extern void SetDz(Scene *scn, float dz);
extern Scene* ReadScene(char *filename);
extern void WriteScene(Scene *scn, char *filename);
extern Scene* MSP_Align(Scene *in, Scene *mask, int input_ori, int quality);
extern Scene  *LinearInterp(Scene *scn,float dx,float dy,float dz);
extern Kernel3 *NormalizeKernel3(Kernel3 *K);
extern Kernel3 *GaussianKernel3(AdjRel3 *A, float stddev);
extern Kernel3 *LaplacianKernel3(AdjRel3 *A, float stddev);
extern void     DestroyKernel3(Kernel3 **K);
extern Scene   *LinearFilter3(Scene *scn, Kernel3 *K);
extern Scene   *SobelFilter3(Scene *scn);
extern Scene   *MedianFilter3(Scene *scn, AdjRel3 *A);
extern Scene    *ModeFilter3(Scene *scn, AdjRel3 *A);
extern AdjRel3 *Spheric(float r);
extern Scene *Equalize3(Scene *scn, int Imax);
extern int Otsu3(Scene *scn);



%}



#include "ift.h"

extern void NewDestroyScene(Scene *scn);
extern Scene* EraseBackground(Scene *scn);
extern Scene* EraseSupport(Scene *scn);
extern int ShiftScene(Scene *scn);
extern void UnShiftScene(Scene *scn, int flag);

/* From ift library */
extern float GetDx(Scene *scn);
extern float GetDy(Scene *scn);
extern float GetDz(Scene *scn);
extern int GetXSize(Scene *scn);
extern int GetYSize(Scene *scn);
extern int GetZSize(Scene *scn);
extern Scene  *CreateScene(int xsize,int ysize,int zsize);
extern void SetDx(Scene *scn, float dx);
extern void SetDy(Scene *scn, float dy);
extern void SetDz(Scene *scn, float dz);
extern Scene* ReadScene(char *filename);
extern void WriteScene(Scene *scn, char *filename);
extern Scene* MSP_Align(Scene *in, Scene *mask, int input_ori, int quality);
extern Scene  *LinearInterp(Scene *scn,float dx,float dy,float dz);
extern Kernel3 *NormalizeKernel3(Kernel3 *K);
extern Kernel3 *GaussianKernel3(AdjRel3 *A, float stddev);
extern Kernel3 *LaplacianKernel3(AdjRel3 *A, float stddev);
extern void     DestroyKernel3(Kernel3 **K);
extern Scene   *LinearFilter3(Scene *scn, Kernel3 *K);
extern Scene   *SobelFilter3(Scene *scn);
extern Scene   *MedianFilter3(Scene *scn, AdjRel3 *A);
extern Scene    *ModeFilter3(Scene *scn, AdjRel3 *A);
extern AdjRel3 *Spheric(float r);
extern Scene *Equalize3(Scene *scn, int Imax);

