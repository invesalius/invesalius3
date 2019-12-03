import threading
import time

import numpy as np
import wx
from wx.lib.pubsub import pub as Publisher
import vtk
import math


def compute_seed(position, affine):
    pos_world_aux = np.ones([4, 1])
    # pos_world_aux[:3, -1] = db.flip_x(self.position)[:3]
    pos_world_aux[:3, -1] = position[:3]
    pos_world = np.linalg.inv(affine) @ pos_world_aux
    seed = pos_world.reshape([1, 4])[0, :3]

    return seed[np.newaxis, :]


def simple_direction(trk_n):
    # trk_d = np.diff(trk_n, axis=0, append=2*trk_n[np.newaxis, -1, :])
    trk_d = np.diff(trk_n, axis=0, append=trk_n[np.newaxis, -2, :])
    trk_d[-1, :] *= -1
    # check that linalg norm makes second norm
    # https://stackoverflow.com/questions/21030391/how-to-normalize-an-array-in-numpy
    direction = 255 * np.absolute((trk_d / np.linalg.norm(trk_d, axis=1)[:, None]))
    return direction.astype(int)


def compute_tubes_vtk(trk, direc):
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
        k += 1

        # if j < (numb_points - 1):
        colors.InsertNextTuple(direc[j, :])
        # else:
        #     colors.InsertNextTuple(direc[j, :])

    trkData = vtk.vtkPolyData()
    trkData.SetPoints(points)
    trkData.SetLines(lines)
    trkData.GetPointData().SetScalars(colors)

    # make it a tube
    # trkTube = vtk.vtkTubeFilter()
    # trkTube.SetRadius(0.5)
    # trkTube.SetNumberOfSides(4)
    # trkTube.SetInputData(trkData)
    # trkTube.Update()

    # return trkTube
    return trkData


def tracts_actor(out_list, affine_vtk):
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
        actor.SetUserMatrix(affine_vtk)

    return actor


def tracts_root(out_list, root, n_tracts):
    # create tracts only when at least one was computed
    # print("Len outlist in root: ", len(out_list))
    if not out_list.count(None) == len(out_list):
        for n, tube in enumerate(out_list):
            if tube:
                # root.SetBlock(n_tracts + n, tube.GetOutput())
                root.SetBlock(n_tracts + n, tube)

    return root


class ComputeTractsRoot(threading.Thread):
        """
        Thread to update the coordinates with the fiducial points
        co-registration method while the Navigation Button is pressed.
        Sleep function in run method is used to avoid blocking GUI and
        for better real-time navigation
        """

        def __init__(self, tracker, position, affine, affine_vtk, n_tracts):
            threading.Thread.__init__(self)
            # trekker variables
            self.tracker = tracker
            self.position = position
            self.affine = affine
            self.affine_vtk = affine_vtk
            self.n_tracts = n_tracts
            # threading variables
            # self.run_id = run_id
            self._pause_ = False
            # self.start()

        def stop(self):
            self._pause_ = True

        def run(self):

            seed = compute_seed(self.position, self.affine)

            chunck_size = 2
            nchuncks = math.floor(self.n_tracts/chunck_size)
            # print("The nchuncks: ", nchuncks)

            root = vtk.vtkMultiBlockDataSet()
            # n = 1
            n_tracts = 0
            # while n <= nchuncks:
            for n in range(nchuncks):
                # Compute the tracts
                trk_list = []
                for _ in range(chunck_size):
                    self.tracker.set_seeds(seed)
                    if self.tracker.run():
                        trk_list.append(self.tracker.run()[0])

                # Transform tracts to array
                trk_arr = [np.asarray(trk_n).T if trk_n else None for trk_n in trk_list]

                # Compute the directions
                trk_dir = [simple_direction(trk_n) for trk_n in trk_arr]

                # Compute the vtk tubes
                out_list = [compute_tubes_vtk(trk_arr_n, trk_dir_n) for trk_arr_n, trk_dir_n in zip(trk_arr, trk_dir)]
                # Compute the actor
                # root = tracts_root(out_list, root, n_tracts)
                root = tracts_actor(out_list, root, n_tracts)
                n_tracts += len(out_list)

                wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root, affine_vtk=self.affine_vtk)

                time.sleep(0.05)
                # n += 1

            if self._pause_:
                return


class ComputeTractsParallel(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, tracker, position, affine, affine_vtk, n_tracts):
        threading.Thread.__init__(self)
        # trekker variables
        self.tracker = tracker
        self.position = position
        self.affine = affine
        self.affine_vtk = affine_vtk
        self.n_tracts = n_tracts
        # threading variables
        # self.run_id = run_id
        self._pause_ = False
        self.mutex = threading.Lock()
        # self.start()

    def stop(self):
        # self.mutex.release()
        self._pause_ = True

    def run(self):
        if self._pause_:
            return
        else:
            # self.mutex.acquire()
            # try:
            seed = compute_seed(self.position, self.affine)

            chunck_size = 6
            nchuncks = math.floor(self.n_tracts / chunck_size)
            # print("The chunck_size: ", chunck_size)
            # print("The nchuncks: ", nchuncks)

            root = vtk.vtkMultiBlockDataSet()
            # n = 1
            n_tracts = 0
            # while n <= nchuncks:
            for n in range(nchuncks):
                # Compute the tracts
                trk_list = []
                # for _ in range(chunck_size):
                self.tracker.set_seeds(np.repeat(seed, chunck_size, axis=0))
                if self.tracker.run():
                    trk_list.extend(self.tracker.run())

                # Transform tracts to array
                trk_arr = [np.asarray(trk_n).T if trk_n else None for trk_n in trk_list]

                # Compute the directions
                trk_dir = [simple_direction(trk_n) for trk_n in trk_arr]

                # Compute the vtk tubes
                out_list = [compute_tubes_vtk(trk_arr_n, trk_dir_n) for trk_arr_n, trk_dir_n in zip(trk_arr, trk_dir)]
                # Compute the actor
                root = tracts_root(out_list, root, n_tracts)
                n_tracts += len(out_list)

                wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root, affine_vtk=self.affine_vtk)
            # finally:
            #     self.mutex.release()

                # time.sleep(0.05)
                # n += 1


class ComputeTracts(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, tracker, position, affine, affine_vtk, n_tracts):
        threading.Thread.__init__(self)
        # trekker variables
        self.tracker = tracker
        self.position = position
        self.affine = affine
        self.affine_vtk = affine_vtk
        self.n_tracts = n_tracts
        # threading variables
        # self.run_id = run_id
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def run(self):

        seed = compute_seed(self.position, self.affine)

        # Compute the tracts
        trk_list = []
        for n in range(self.n_tracts):
            self.tracker.set_seeds(seed)
            if self.tracker.run()[0]:
                trk_list.append(self.tracker.run()[0])

        # Transform tracts to array
        trk_arr = [np.asarray(trk_n).T if trk_n else None for trk_n in trk_list]

        # Compute the directions
        trk_dir = [simple_direction(trk_n) for trk_n in trk_arr]

        # Compute the vtk tubes
        out_list = [compute_tubes_vtk(trk_arr_n, trk_dir_n) for trk_arr_n, trk_dir_n in zip(trk_arr, trk_dir)]

        # Compute the actor
        actor = tracts_actor(out_list, affine_vtk=self.affine_vtk)

        wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, actor=actor)

        # time.sleep(1.)

        if self._pause_:
            return
        else:
            return actor


class ComputeTractsSimple:
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

    def run(self):

        seed = compute_seed(self.position, self.affine)

        # Compute the tracts
        trk_list = []
        for n in range(self.n_tracts):
            self.tracker.set_seeds(seed)
            if self.tracker.run()[0]:
                trk_list.append(self.tracker.run()[0])

        # Transform tracts to array
        trk_arr = [np.asarray(trk_n).T if trk_n else None for trk_n in trk_list]

        # Compute the directions
        trk_dir = [simple_direction(trk_n) for trk_n in trk_arr]

        # Compute the vtk tubes
        out_list = [compute_tubes_vtk(trk_arr_n, trk_dir_n) for trk_arr_n, trk_dir_n in zip(trk_arr, trk_dir)]

        # Compute the actor
        actor = tracts_actor(out_list, affine_vtk=self.affine_vtk)

        return actor


class ComputeTractsDev:
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

    def run(self):

        seed = compute_seed(self.position, self.affine)

        # Compute the tracts
        start_time = time.time()
        trk_list = []
        for n in range(self.n_tracts):
            self.tracker.set_seeds(seed)
            if self.tracker.run()[0]:
                trk_list.append(self.tracker.run()[0])

        duration = time.time() - start_time
        print(f"Tract run duration duration {duration} seconds")

        # Transform tracts to array
        start_time = time.time()
        trk_arr = [np.asarray(trk_n).T if trk_n else None for trk_n in trk_list]
        duration = time.time() - start_time
        print(f"Tract run trk_arr duration {duration} seconds")

        # Compute the directions
        start_time = time.time()
        trk_dir = [simple_direction(trk_n) for trk_n in trk_arr]
        duration = time.time() - start_time
        print(f"Tract run trk_dir duration {duration} seconds")

        # Compute the vtk tubes
        start_time = time.time()
        out_list = [compute_tubes_vtk(trk_arr_n, trk_dir_n) for trk_arr_n, trk_dir_n in zip(trk_arr, trk_dir)]
        duration = time.time() - start_time
        print(f"Tract run to_vtk duration {duration} seconds")

        # Compute the actor
        start_time = time.time()
        actor = tracts_actor(out_list, affine_vtk=self.affine_vtk)
        duration = time.time() - start_time
        print(f"Visualize duration {duration} seconds")

        return actor