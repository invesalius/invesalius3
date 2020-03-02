import psutil
import threading
import time

import numpy as np
import wx
from wx.lib.pubsub import pub as Publisher
import vtk

import invesalius.data.bases as db


def compute_seed(position, affine):
    # pos_world_aux = np.ones([4, 1])
    # pos_world_aux[:3, -1] = position[:3]
    pos_world_aux = np.hstack((position, 1.)).reshape([4, 1])
    pos_world = np.linalg.inv(affine) @ pos_world_aux
    # seed = pos_world.reshape([1, 4])[0, :3]
    # seed = pos_world.T[np.newaxis, 0, :3]
    seed = pos_world.T[np.newaxis, 0, :3]

    return seed

def compute_seed_old(position, affine):
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


def compute_tubes_vtk(trk, direction):
    numb_points = trk.shape[0]
    points = vtk.vtkPoints()
    lines = vtk.vtkCellArray()

    colors = vtk.vtkUnsignedCharArray()
    colors.SetNumberOfComponents(3)

    k = 0
    lines.InsertNextCell(numb_points)
    for j in range(numb_points):
        points.InsertNextPoint(trk[j, :])
        colors.InsertNextTuple(direction[j, :])
        lines.InsertCellPoint(k)
        k += 1

    trk_data = vtk.vtkPolyData()
    trk_data.SetPoints(points)
    trk_data.SetLines(lines)
    trk_data.GetPointData().SetScalars(colors)

    # make it a tube
    trk_tube = vtk.vtkTubeFilter()
    trk_tube.SetRadius(0.5)
    trk_tube.SetNumberOfSides(4)
    trk_tube.SetInputData(trk_data)
    trk_tube.Update()

    return trk_tube


def tracts_root(out_list, root, n_tracts):
    # create tracts only when at least one was computed
    # print("Len outlist in root: ", len(out_list))
    if not out_list.count(None) == len(out_list):
        for n, tube in enumerate(out_list):
            #TODO: substitute to try + except (better to ask forgiveness than please)
            if tube:
                root.SetBlock(n_tracts + n, tube.GetOutput())

    return root


def tracts_computation(trk_list, root, n_tracts):
    # Transform tracts to array
    trk_arr = [np.asarray(trk_n).T if trk_n else None for trk_n in trk_list]

    # Compute the directions
    trk_dir = [simple_direction(trk_n) for trk_n in trk_arr]

    # Compute the vtk tubes
    out_list = [compute_tubes_vtk(trk_arr_n, trk_dir_n) for trk_arr_n, trk_dir_n in zip(trk_arr, trk_dir)]

    root = tracts_root(out_list, root, n_tracts)

    return root


class ComputeVisualizeParallel(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, inp, affine_vtk, pipeline, event, sle):
        threading.Thread.__init__(self, name='CompVisTractsParallel')
        self.inp = inp
        self.affine_vtk = affine_vtk
        self.pipeline = pipeline
        self.event = event
        self.sle = sle

    def run(self):

        tracker, affine, offset, n_tracts_total, seed_radius, n_threads = self.inp
        p_old = np.array([[0., 0., 0.]])
        n_tracts = 0
        # ncores = psutil.cpu_count()
        # chunck_size = 2*ncores
        trk_list = []
        root = vtk.vtkMultiBlockDataSet()
        # Compute the tracts
        while not self.event.is_set():
            if self.pipeline.event.is_set():
                # print("Computing tracts")
                position, m_img = self.pipeline.get_message()

                if np.any(m_img):
                    # #TODO: Refactor and create a function for the offset computation
                    # # m_img[:3, -1] = np.asmatrix(db.flip_x_m((m_img[0, -1], m_img[1, -1], m_img[2, -1]))).reshape([3, 1])
                    m_img[:, -1] = db.flip_x_m(m_img[:3, -1])[:, 0]
                    # # norm_vec = m_img[:3, 2].reshape([1, 3]).tolist()
                    # # p0 = m_img[:3, -1].reshape([1, 3]).tolist()
                    # # p_new = [x - offset * y for x, y in zip(p0[0], norm_vec[0])]
                    # # translate the coordinate along the normal vector of the object/coil
                    # # p_new = np.array([[-8.49, -8.39, 2.5]])
                    # p_new = m_img[:3, -1] - offset * m_img[:3, 2]
                    # dist = np.linalg.norm(p_old - p_new)
                    # print("Distance: {}".format(dist))
                    # p_old = p_new.copy()
                    #
                    # seed = compute_seed(p_new, affine)
                    # print("Seed: {}".format(seed))
                    # # seed = np.array([[-8.49, -8.39, 2.5]])
                    # # tracker.seed_coordinates(np.repeat(seed, chunck_size, axis=0))
                    # tracker.seed_coordinates(np.tile(seed, (n_threads, 1)))
                    #
                    # print("Trekker run: {}".format(tracker.run()))

                    # m_img[:3, -1] = np.asmatrix(db.flip_x_m((m_img[0, -1], m_img[1, -1], m_img[2, -1]))).reshape([3, 1])
                    norm_vec = m_img[:3, 2].reshape([1, 3]).tolist()
                    p0 = m_img[:3, -1].reshape([1, 3]).tolist()
                    p_new = [x - offset * y for x, y in zip(p0[0], norm_vec[0])]
                    # p_new = [-8.49, -8.39, 2.5]
                    dist = abs(np.linalg.norm(p_old - np.asarray(p_new)))
                    p_old = np.asarray(p_new)

                    seed = compute_seed_old(p_new, affine)
                    # seed = np.array([[-8.49, -8.39, 2.5]])
                    tracker.seed_coordinates(np.repeat(seed, n_threads, axis=0))

                    if tracker.run():
                        if dist < seed_radius and n_tracts < n_tracts_total:
                            # Compute the tracts
                            trk_list.extend(tracker.run())
                            # print("Menor que seed_radius com n tracts and dist: ", n_tracts, dist)
                            root = tracts_computation(trk_list, root, n_tracts)
                            n_tracts = len(trk_list)
                            print("Total new tracts: ", n_tracts)
                            wx.CallAfter(Publisher.sendMessage, 'Remove tracts')
                            wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root,
                                         affine_vtk=self.affine_vtk)
                        elif dist >= seed_radius:
                            n_tracts = 0
                            trk_list = tracker.run()
                            print("trk list len: ", len(trk_list))
                            root = tracts_computation(trk_list, root, n_tracts)
                            n_tracts = len(trk_list)
                            # print("Total tracts: ", n_tracts)
                            wx.CallAfter(Publisher.sendMessage, 'Remove tracts')
                            wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root,
                                         affine_vtk=self.affine_vtk)

                        # this logic is a bit stupid because it has to compute the actors every loop, better would be
                        # to check the distance and update actors in viewer volume, but that would require that each
                        # loop outputs one actor which is a fiber bundle, and if the dist is < 3 and n_tract > n_total
                        # do nothing

            time.sleep(self.sle)


def ComputeTracts(trekker, position, affine, affine_vtk, n_tracts, seed_radius):
    """
    Compute tractograms using the Trekker library.

    :param trekker: Trekker library instance
    :param position: 3 double coordinates (x, y, z) in list or array
    :param affine: 4 x 4 numpy double array
    :param affine_vtk: vtkMatrix4x4 isntance with affine transformation matrix
    :param n_tracts: number of tracts to compute
    :param seed_radius: radius that current coordinate should exceed to recompute tracts
    """
    # during neuronavigation, root needs to be initialized outisde the while loop so the new tracts
    # can be appended to the root block set
    root = vtk.vtkMultiBlockDataSet()
    # Juuso's
    # seed = np.array([[-8.49, -8.39, 2.5]])
    # Baran M1
    # seed = np.array([[27.53, -77.37, 46.42]])
    seed_trk = compute_seed(position, affine)
    # print("seed example: {}".format(seed_trk))
    trekker.seed_coordinates(np.repeat(seed_trk, n_tracts, axis=0))
    # print("trk list len: ", len(trekker.run()))
    if trekker.run():
        trk_list = trekker.run()
        root = tracts_computation(trk_list, root, 0)
        wx.CallAfter(Publisher.sendMessage, 'Remove tracts')
        wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root,
                     affine_vtk=affine_vtk)
    else:
        wx.CallAfter(Publisher.sendMessage, 'Remove tracts')


def SetTrekkerParameters(trekker, params):
    import invesalius.constants as const

    trekker.seed_maxTrials(params['seed_max'])
    trekker.stepSize(params['step_size'])
    trekker.minFODamp(params['min_fod'])
    trekker.probeQuality(params['probe_quality'])
    trekker.maxEstInterval(params['max_interval'])
    trekker.minRadiusOfCurvature(params['min_radius_curv'])
    trekker.probeLength(params['probe_length'])
    trekker.writeInterval(params['write_interval'])

    # check number if number of cores is valid in configuration file,
    # otherwise use the maximum number of threads which is usually 2*N_CPUS
    n_threads = 2 * const.N_CPU
    if isinstance((params['numb_threads']), int) and params['numb_threads'] <= 2*const.N_CPU:
        n_threads = params['numb_threads']

    trekker.numberOfThreads(n_threads)
    print("Trekker config updated: n_threads, {}; seed_max, {}".format(n_threads, params['seed_max']))
    return trekker, n_threads
