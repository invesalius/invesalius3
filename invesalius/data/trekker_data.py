# import psutil
import threading
import time

import numpy as np
import queue
import wx
from wx.lib.pubsub import pub as Publisher
import vtk

import invesalius.constants as const
import invesalius.data.imagedata_utils as img_utils

# Nice print for arrays
# np.set_printoptions(precision=2)
# np.set_printoptions(suppress=True)


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


class ComputeTractsThread(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, inp, affine_vtk, pipeline, visualization_queue, event, sle):
        threading.Thread.__init__(self, name='ComputeTractsThread')
        self.inp = inp
        self.affine_vtk = affine_vtk
        self.pipeline = pipeline
        self.visualization_queue = visualization_queue
        self.event = event
        self.sle = sle

    def run(self):

        trekker, affine, offset, n_tracts_total, seed_radius, n_threads = self.inp
        n_threads = n_tracts_total
        p_old = np.array([[0., 0., 0.]])
        n_tracts = 0
        count = 0
        trk_list = []
        root = vtk.vtkMultiBlockDataSet()

        # Compute the tracts
        # while True:
        # print('ComputeTractsThread: event {}'.format(self.event.is_set()))
        while not self.event.is_set():
            try:
                # if self.pipeline.event.is_set():
                # print("Computing tracts")
                coord, m_img, m_img_flip = self.pipeline.get_nowait()
                # print('ComputeTractsThread: get {}'.format(count))
                # m_img_flip = self.pipeline.get_message()

                # if np.any(m_img_flip):

                # 20200402: in this new refactored version the m_img comes different than the position
                # the new version m_img is already flixped in y, which means that Y is negative
                # if only the Y is negative maybe no need for the flip_x funtcion at all in the navigation
                # but check all pipeline before why now the m_img comes different than position
                # 20200403: indeed flip_x is just a -1 multiplication to the Y coordinate, remove function flip_x
                # m_img_flip = m_img.copy()
                # m_img_flip[1, -1] = -m_img_flip[1, -1]

                # translate the coordinate along the normal vector of the object/coil
                p_new = m_img_flip[:3, -1] - offset * m_img_flip[:3, 2]
                # p_new = np.array([[27.53, -77.37, 46.42]])
                dist = abs(np.linalg.norm(p_old - np.asarray(p_new)))
                p_old = p_new.copy()

                seed_trk = img_utils.convert_world_to_voxel(p_new, affine)
                # Juuso's
                # seed_trk = np.array([[-8.49, -8.39, 2.5]])
                # Baran M1
                # seed_trk = np.array([[27.53, -77.37, 46.42]])
                # print("Seed: {}".format(seed))
                trekker.seed_coordinates(np.repeat(seed_trk, n_threads, axis=0))

                # wx.CallAfter(Publisher.sendMessage, 'Update cross position', arg=m_img, position=position)
                # wx.CallAfter(Publisher.sendMessage, 'Update object matrix', m_img=m_img, coord=position)

                if trekker.run():
                    # print("dist: {}".format(dist))
                    if dist >= seed_radius:
                        n_tracts = 0
                        trk_list = trekker.run()
                        root = tracts_computation(trk_list, root, n_tracts)
                        n_tracts = len(trk_list)



                        # print("New tracts: ", n_tracts)
                        # count += 1
                        # wx.CallAfter(Publisher.sendMessage, 'Remove tracts', count=count)
                        # wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root,
                        #              affine_vtk=self.affine_vtk, count=count)


                    # elif dist < seed_radius and n_tracts < n_tracts_total:
                    #     # Compute the tracts
                    #     trk_list.extend(trekker.run())
                    #     root = tracts_computation(trk_list, root, n_tracts)
                    #     n_tracts = len(trk_list)



                        # print("Adding tracts: ", n_tracts)
                        # count += 1
                    # else:
                    #     root = None
                        # wx.CallAfter(Publisher.sendMessage, 'Remove tracts', count=count)
                        # wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root,
                        #              affine_vtk=self.affine_vtk, count=count)
                    # rethink if this should be inside the if condition, it may lock the thread if no tracts are found
                    # maybe use a flag that indicates the existence or not of the root and in the update scene check for it
                    self.visualization_queue.put_nowait([coord, m_img, root])
                    # print('ComputeTractsThread: put {}'.format(count))
                    # count += 1
                    # this logic is a bit stupid because it has to compute the actors every loop, better would be
                    # to check the distance and update actors in viewer volume, but that would require that each
                    # loop outputs one actor which is a fiber bundle, and if the dist is < 3 and n_tract > n_total
                    # do nothing

                self.pipeline.task_done()
                # print('ComputeTractsThread: done {}'.format(count))
                time.sleep(self.sle)
            except queue.Empty:
                pass
            except queue.Full:
                self.pipeline.task_done()


class UpdateNavigationScene(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, affine_vtk, visualization_queue, event, sle):
        threading.Thread.__init__(self, name='UpdateScene')
        self.visualization_queue = visualization_queue
        self.affine_vtk = affine_vtk
        self.sle = sle
        self.event = event

    def run(self):
        count = 0
        while not self.event.is_set():
            try:
                coord, m_img, root = self.visualization_queue.get_nowait()
                # print('UpdateScene: get {}'.format(count))

                wx.CallAfter(Publisher.sendMessage, 'Remove tracts', count=root)
                wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root,
                             affine_vtk=self.affine_vtk, count=0)
                wx.CallAfter(Publisher.sendMessage, 'Update cross position', arg=m_img, position=coord)
                wx.CallAfter(Publisher.sendMessage, 'Update object matrix', m_img=m_img, coord=coord)

                self.visualization_queue.task_done()
                # print('UpdateScene: done {}'.format(count))
                # count += 1

                time.sleep(self.sle)
            except queue.Empty:
                pass




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
    seed_trk = img_utils.convert_world_to_voxel(position, affine)
    # print("seed example: {}".format(seed_trk))
    trekker.seed_coordinates(np.repeat(seed_trk, n_tracts, axis=0))
    # print("trk list len: ", len(trekker.run()))
    if trekker.run():
        trk_list = trekker.run()
        root = tracts_computation(trk_list, root, 0)
        # wx.CallAfter(Publisher.sendMessage, 'Remove tracts')
        # wx.CallAfter(Publisher.sendMessage, 'Update tracts', flag=True, root=root,
        #              affine_vtk=affine_vtk)
        Publisher.sendMessage('Remove tracts')
        Publisher.sendMessage('Update tracts', flag=True, root=root,
                     affine_vtk=affine_vtk)
    else:
        Publisher.sendMessage('Remove tracts')


def SetTrekkerParameters(trekker, params):

    trekker.seed_maxTrials(params['seed_max'])
    # trekker.stepSize(params['step_size'])
    trekker.minFODamp(params['min_fod'])
    # trekker.probeQuality(params['probe_quality'])
    # trekker.maxEstInterval(params['max_interval'])
    # trekker.minRadiusOfCurvature(params['min_radius_curv'])
    # trekker.probeLength(params['probe_length'])
    trekker.writeInterval(params['write_interval'])
    trekker.maxLength(200)
    trekker.minLength(20)
    trekker.maxSamplingPerStep(100)

    # check number if number of cores is valid in configuration file,
    # otherwise use the maximum number of threads which is usually 2*N_CPUS
    n_threads = 2 * const.N_CPU
    if isinstance((params['numb_threads']), int) and params['numb_threads'] <= 2*const.N_CPU:
        n_threads = params['numb_threads']

    trekker.numberOfThreads(n_threads)
    # print("Trekker config updated: n_threads, {}; seed_max, {}".format(n_threads, params['seed_max']))
    return trekker, n_threads
