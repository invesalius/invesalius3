

//extern "C" {
  #include "ift.h"
//}





// Prototypes

void NewDestroyScene(Scene *scn);




void NewDestroyScene(Scene *scn) 
{
  if(scn != NULL){
    if (scn->data != NULL)  free(scn->data);
    if (scn->tby  != NULL)  free(scn->tby);
    if (scn->tbz  != NULL)  free(scn->tbz);
    free(scn);
  }
}


Scene* EraseBackground(Scene *scn) 
{  
  int otsu = (int)(Otsu3(scn)*0.8); // Get 80% of Otsu's threshold
  int i,n = scn->xsize*scn->ysize*scn->zsize;
  Scene *out = CopyScene(scn);
  for (i=0; i < n; i++) {
    if (out->data[i]<otsu) out->data[i]=0;
  }
  return out;
}

Scene* EraseSupport(Scene *scn)
{
  // Check if RemoveBackground was already ran (workaround)
  int c=0,i,n = scn->xsize*scn->ysize*scn->zsize;
  Scene *scn2;
  Scene *labels,*bin;
  AdjRel3 *A;
  int total[2000],p;
  Voxel v;
  int max;
  Scene *out;
  
  for (i=0; i < n; i++) {
    if (scn->data[i]==0) c++; // count zero voxels
  }
  if (c<(n*0.15)) 
    scn2 = EraseBackground(scn);
  else
    scn2 = CopyScene(scn);

  // Get max connected component
  A=Spheric(1.5);
  bin = Threshold3(scn2,1,50000);
  labels  = LabelBinComp3(bin,A);
  DestroyAdjRel3(&A);
  // Count labels
  for (i=0;i<2000;i++) total[i]=0;
  for (v.z=0; v.z < scn->zsize; v.z++)
    for (v.y=0; v.y < scn->ysize; v.y++)
      for (v.x=0; v.x < scn->xsize; v.x++) {
        p = labels->tbz[v.z] + labels->tby[v.y] + v.x;
        if (labels->data[p]<2000) total[labels->data[p]]++;
        if (bin->data[p]==0) total[labels->data[p]]=0; // exclude background
      }
  DestroyScene(&bin);
  max=0;
  for (i=0;i<2000;i++)
    if (total[i]>total[max]) max=i;

  // copy the maxcc to out
  n = scn->xsize*scn->ysize*scn->zsize;
  out = CreateScene(scn->xsize,scn->ysize,scn->zsize);
  out->dx=scn->dx;
  out->dy=scn->dy;
  out->dz=scn->dz;
  for (i=0; i < n; i++) {
    if (labels->data[i]==max) out->data[i]=scn2->data[i];
  }
  DestroyScene(&labels);
  DestroyScene(&scn2);
  return out;
}



int ShiftScene(Scene *scn) 
{
  int n,i, min = MinimumValue3(scn);
  if (min<0) {
    n = scn->xsize*scn->ysize*scn->zsize;
    for (i=0; i < n; i++) 
      scn->data[i] += 1024;
    return 1;
  }
  return 0;
}

void UnShiftScene(Scene *scn, int flag) 
{
  int i,n;
  if (flag!=0) {
    n = scn->xsize*scn->ysize*scn->zsize;
    for (i=0; i < n; i++) 
      scn->data[i] -= 1024;
  }
}
