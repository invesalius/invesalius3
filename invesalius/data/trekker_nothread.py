import threading
import time

import numpy as np
import wx
from wx.lib.pubsub import pub as Publisher
import vtk
import invesalius.data.bases as db


class ComputeTracts:
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, tracker, position, affine, affine_vtk, n_tracts):
        # threading.Thread.__init__(self)
        self.tracker = tracker
        self.position = position
        self.affine = affine
        self.affine_vtk = affine_vtk
        self.n_tracts = n_tracts
        # self.run_id = run_id
        # self._pause_ = False

    def run(self):

        # while self.run_id:
            # procs = 5
            # out_list = list()
        # start_time = time.time()
        actor = False
        out_list = [None]*self.n_tracts
        tract_exist = False

        pos_world_aux = np.ones([4, 1])
        # pos_world_aux[:3, -1] = db.flip_x(self.position)[:3]
        pos_world_aux[:3, -1] = self.position[:3]
        pos_world = np.linalg.inv(self.affine) @ pos_world_aux
        seed = pos_world.reshape([1, 4])[0, :3]

        for n in range(self.n_tracts):
            # print("out_list: ", out_list)
            out_list[n] = self.trk2vtkActor(self.tracker, seed[np.newaxis, :])
            # print("out_list {} and seed {}".format(out_list, seed))

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

        return actor
        # wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, actor=actor)

        # time.sleep(1.)

        # if self._pause_:
        #     return

    def trk2vtkActor(self, tracker, seed):
        tracker.set_seeds(seed)
        # convert trk to vtkPolyData
        trk_run = tracker.run()
        if trk_run:
            trk = np.transpose(np.asarray(trk_run[0]))
            numb_points = trk.shape[0]

            points = vtk.vtkPoints()
            lines = vtk.vtkCellArray()

            # colors = vtk.vtkFloatArray()
            colors = vtk.vtkUnsignedCharArray()
            colors.SetNumberOfComponents(3)
            # colors.SetName("tangents")

            k = 0
            lines.InsertNextCell(numb_points)
            for j in range(numb_points):
                points.InsertNextPoint(trk[j, :])
                lines.InsertCellPoint(k)
                k = k + 1

                if j < (numb_points - 1):
                    direction = trk[j + 1, :] - trk[j, :]
                    direction = direction / np.linalg.norm(direction)
                    direc = [int(255*abs(s)) for s in direction]
                    # colors.InsertNextTuple(np.abs([direc[0], direc[1], direc[2], 1]))
                    colors.InsertNextTuple(direc)
                else:
                    # colors.InsertNextTuple(np.abs([direc[0], direc[1], direc[2], 1]))
                    colors.InsertNextTuple(direc)

            trkData = vtk.vtkPolyData()
            trkData.SetPoints(points)
            trkData.SetLines(lines)
            trkData.GetPointData().SetScalars(colors)

            # make it a tube
            trkTube = vtk.vtkTubeFilter()
            trkTube.SetRadius(0.3)
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
