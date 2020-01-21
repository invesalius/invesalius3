import time

import numpy as np
import vtk


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
    trkTube = vtk.vtkTubeFilter()
    trkTube.SetRadius(0.5)
    trkTube.SetNumberOfSides(4)
    trkTube.SetInputData(trkData)
    trkTube.Update()

    return trkTube


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
        start_time = time.time()
        trk_list = []
        for n in range(self.n_tracts):
            self.tracker.seed_coordinates(seed)
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
