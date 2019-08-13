import threading
import time

import numpy as np
import wx
from wx.lib.pubsub import pub as Publisher
import vtk


class ComputeTracts(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, tracker, seed, affine_vtk, run_id):
        threading.Thread.__init__(self)
        self.tracker = tracker
        self.seed = seed
        self.affine_vtk = affine_vtk
        self.run_id = run_id
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def run(self):

        # while self.run_id:
            # procs = 5
            # out_list = list()
        # start_time = time.time()
        actor = False
        out_list = [None]*5
        tract_exist = False
        for n in range(5):
            # print("out_list: ", out_list)
            out_list[n] = self.trk2vtkActor(self.tracker, self.seed)
        # print("out_list depois: ", out_list)

        # create tracts only when at least one was computed
        if not out_list.count(None) == len(out_list):
            root = vtk.vtkMultiBlockDataSet()

            for n, tube in enumerate(out_list):
                if tube:
                    root.SetBlock(n, tube.GetOutput())

            # https://lorensen.github.io/VTKExamples/site/Python/CompositeData/CompositePolyDataMapper/
            mapper = vtk.vtkCompositePolyDataMapper2()
            mapper.SetInputDataObject(root)

            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.SetUserMatrix(self.affine_vtk)
            # duration = time.time() - start_time
            # print(f"Tract computing duration {duration} seconds")

        wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, actor=actor)

        # time.sleep(1.)

        if self._pause_:
            return

    def trk2vtkActor(self, tracker, seed):
        tracker.set_seeds(seed)
        # convert trk to vtkPolyData
        trk_run = tracker.run()
        if trk_run:
            trk = np.transpose(np.asarray(trk_run[0]))
            numb_points = trk.shape[0]

            points = vtk.vtkPoints()
            lines = vtk.vtkCellArray()

            colors = vtk.vtkFloatArray()
            colors.SetNumberOfComponents(4)
            colors.SetName("tangents")

            k = 0
            lines.InsertNextCell(numb_points)
            for j in range(numb_points):
                points.InsertNextPoint(trk[j, :])
                lines.InsertCellPoint(k)
                k = k + 1

                if j < (numb_points - 1):
                    direction = trk[j + 1, :] - trk[j, :]
                    direction = direction / np.linalg.norm(direction)
                    colors.InsertNextTuple(np.abs([direction[0], direction[1], direction[2], 1]))
                else:
                    colors.InsertNextTuple(np.abs([direction[0], direction[1], direction[2], 1]))

            trkData = vtk.vtkPolyData()
            trkData.SetPoints(points)
            trkData.SetLines(lines)
            trkData.GetPointData().SetScalars(colors)

            # make it a tube
            trkTube = vtk.vtkTubeFilter()
            trkTube.SetRadius(0.1)
            trkTube.SetNumberOfSides(4)
            trkTube.SetInputData(trkData)
            trkTube.Update()
            # print("trkTube: ", trkTube)

            # # mapper
            # trkMapper = vtk.vtkPolyDataMapper()
            # trkMapper.SetInputData(trkTube.GetOutput())
            #
            # # actor
            # trkActor = vtk.vtkActor()
            # trkActor.SetMapper(trkMapper)
        else:
            trkTube = None

        return trkTube
