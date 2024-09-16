# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

# Author: Victor Hugo Souza (victorhos-at-hotmail.com)
# Contributions: Dogu Baran Aydogan
# Initial date: 8 May 2020

import queue
import threading
import time

import numpy as np
from vtkmodules.vtkCommonCore import vtkPoints, vtkUnsignedCharArray
from vtkmodules.vtkCommonDataModel import (
    vtkCellArray,
    vtkMultiBlockDataSet,
    vtkPolyData,
)
from vtkmodules.vtkFiltersCore import vtkTubeFilter

import invesalius.constants as const
import invesalius.data.imagedata_utils as img_utils
from invesalius.pubsub import pub as Publisher

# Nice print for arrays
# np.set_printoptions(precision=2)
# np.set_printoptions(suppress=True)


def compute_directions(trk_n, alpha=255):
    """Compute direction of a single tract in each point and return as an RGBA color

    :param trk_n: nx3 array of doubles (x, y, z) point coordinates composing the tract
    :type trk_n: numpy.ndarray
    :param alpha: opacity value in the interval [0, 255]. The 0 is no opacity (total transparency).
    :type alpha: int
    :return: nx3 array of int (x, y, z) RGB colors in the range 0 - 255
    :rtype: numpy.ndarray
    """

    # trk_d = np.diff(trk_n, axis=0, append=2*trk_n[np.newaxis, -1, :])
    trk_d = np.diff(trk_n, axis=0, append=trk_n[np.newaxis, -2, :])
    trk_d[-1, :] *= -1
    # check that linalg norm makes second norm
    # https://stackoverflow.com/questions/21030391/how-to-normalize-an-array-in-numpy
    direction = 255 * np.absolute(trk_d / np.linalg.norm(trk_d, axis=1)[:, None])
    direction = np.hstack([direction, alpha * np.ones([direction.shape[0], 1])])
    return direction.astype(int)


def compute_tubes(trk, direction):
    """Compute and assign colors to a vtkTube for visualization of a single tract

    :param trk: nx3 array of doubles (x, y, z) point coordinates composing the tract
    :type trk: numpy.ndarray
    :param direction: nx3 array of int (x, y, z) RGB colors in the range 0 - 255
    :type direction: numpy.ndarray
    :return: a vtkTubeFilter instance
    :rtype: vtkTubeFilter
    """

    numb_points = trk.shape[0]
    points = vtkPoints()
    lines = vtkCellArray()

    colors = vtkUnsignedCharArray()
    colors.SetNumberOfComponents(4)

    k = 0
    lines.InsertNextCell(numb_points)
    for j in range(numb_points):
        points.InsertNextPoint(trk[j, :])
        colors.InsertNextTuple(direction[j, :])
        lines.InsertCellPoint(k)
        k += 1

    trk_data = vtkPolyData()
    trk_data.SetPoints(points)
    trk_data.SetLines(lines)
    trk_data.GetPointData().SetScalars(colors)

    # make it a tube
    trk_tube = vtkTubeFilter()
    trk_tube.SetRadius(0.5)
    trk_tube.SetNumberOfSides(4)
    trk_tube.SetInputData(trk_data)
    trk_tube.Update()

    return trk_tube


def create_branch(out_list, n_block):
    """Adds a set of tracts to given position in a given vtkMultiBlockDataSet

    :param out_list: List of vtkTubeFilters representing the tracts
    :type out_list: list
    :param n_block: The location in the given vtkMultiBlockDataSet to insert the new tracts
    :type n_block: int
    :return: The collection of tracts (streamlines) as a vtkMultiBlockDataSet
    :rtype: vtkMultiBlockDataSet
    """

    # create a branch and add the streamlines
    branch = vtkMultiBlockDataSet()

    # create tracts only when at least one was computed
    # print("Len outlist in root: ", len(out_list))
    # TODO: check if this if statement is required, because we should
    #  call this function only when tracts exist
    if not out_list.count(None) == len(out_list):
        for n, tube in enumerate(out_list):
            branch.SetBlock(n_block + n, tube.GetOutput())

    return branch


def compute_tracts(trk_list, n_tract=0, alpha=255):
    """Convert the list of all computed tracts given by Trekker run and returns a vtkMultiBlockDataSet

    :param trk_list: List of lists containing the computed tracts and corresponding coordinates
    :type trk_list: list
    :param n_tract: The integer ID of the block in the vtkMultiBlockDataSet
    :type n_tract: int
    :param alpha: The transparency of the streamlines from 0 to 255 (transparent to opaque)
    :type alpha: int
    :return: The updated collection of tracts as a vtkMultiBlockDataSet
    :rtype: vtkMultiBlockDataSet
    """

    # Transform tracts to array
    trk_arr = [np.asarray(trk_n).T if trk_n else None for trk_n in trk_list]
    # Compute the directions
    trk_dir = [compute_directions(trk_n, alpha) for trk_n in trk_arr]
    # Compute the vtk tubes
    out_list = [
        compute_tubes(trk_arr_n, trk_dir_n) for trk_arr_n, trk_dir_n in zip(trk_arr, trk_dir)
    ]
    # create a branch and add the tracts
    branch = create_branch(out_list, n_tract)

    return branch


def compute_and_visualize_tracts(trekker, position, affine, affine_vtk, n_tracts_max):
    """Compute tractograms using the Trekker library.

    :param trekker: Trekker library instance
    :type trekker: Trekker.T
    :param position: 3 double coordinates (x, y, z) in list or array
    :type position: list
    :param affine: 4 x 4 numpy double array
    :type affine: numpy.ndarray
    :param affine_vtk: vtkMatrix4x4 isntance with affine transformation matrix
    :type affine_vtk: vtkMatrix4x4
    :param n_tracts_max: maximum number of tracts to compute
    :type n_tracts_max: int
    """

    # root = vtk.vtkMultiBlockDataSet()
    # Juuso's
    # seed = np.array([[-8.49, -8.39, 2.5]])
    # Baran M1
    # seed = np.array([[27.53, -77.37, 46.42]])
    seed_trk = img_utils.convert_world_to_voxel(position, affine)
    bundle = vtkMultiBlockDataSet()
    n_branches, n_tracts, count_loop = 0, 0, 0
    n_threads = 2 * const.N_CPU - 1

    while n_tracts < n_tracts_max:
        n_param = 1 + (count_loop % 10)
        # rescale the alpha value that defines the opacity of the branch
        # the n interval is [1, 10] and the new interval is [51, 255]
        # the new interval is defined to have no 0 opacity (minimum is 51, i.e., 20%)
        alpha = (n_param - 1) * (255 - 51) / (10 - 1) + 51
        trekker.minFODamp(n_param * 0.01)

        # print("seed example: {}".format(seed_trk))
        trekker.seed_coordinates(np.repeat(seed_trk, n_threads, axis=0))
        # print("trk list len: ", len(trekker.run()))
        trk_list = trekker.run()
        n_tracts += len(trk_list)
        if len(trk_list):
            branch = compute_tracts(trk_list, n_tract=0, alpha=alpha)
            bundle.SetBlock(n_branches, branch)
            n_branches += 1

        count_loop += 1

        if (count_loop == 20) and (n_tracts == 0):
            break

    Publisher.sendMessage("Remove tracts")
    if n_tracts:
        Publisher.sendMessage(
            "Update tracts",
            root=bundle,
            affine_vtk=affine_vtk,
            coord_offset=position,
            coord_offset_w=seed_trk[0].tolist(),
        )


class ComputeTractsThread(threading.Thread):
    # TODO: Remove this class and create a case where no ACT is provided in the class ComputeTractsACTThread

    def __init__(self, inp, queues, event, sle):
        """Class (threading) to compute real time tractography data for visualization.

        Tracts are computed using the Trekker library by Baran Aydogan (https://dmritrekker.github.io/)
        For VTK visualization, each tract (fiber) is a constructed as a tube and many tubes combined in one
        vtkMultiBlockDataSet named as a branch. Several branches are combined in another vtkMultiBlockDataSet named as
        bundle, to obtain fast computation and visualization. The bundle dataset is mapped to a single vtkActor.
        Mapper and Actor are computer in the data/viewer_volume.py module for easier handling in the invesalius 3D scene.

        Sleep function in run method is used to avoid blocking GUI and more fluent, real-time navigation

        :param inp: List of inputs: trekker instance, affine numpy array, seed_offset, seed_radius, n_threads
        :type inp: list
        :param queues: Queue list with coord_tracts_queue (Queue instance that manage co-registered coordinates) and
         tracts_queue (Queue instance that manage the tracts to be visualized)
        :type queues: list[queue.Queue, queue.Queue]
        :param event: Threading event to coordinate when tasks as done and allow UI release
        :type event: threading.Event
        :param sle: Sleep pause in seconds
        :type sle: float
        """

        threading.Thread.__init__(self, name="ComputeTractsThread")
        self.inp = inp
        # self.coord_queue = coord_queue
        self.coord_tracts_queue = queues[0]
        self.tracts_queue = queues[1]
        # self.visualization_queue = visualization_queue
        self.event = event
        self.sle = sle

    def run(self):
        (
            trekker,
            affine,
            offset,
            n_tracts_total,
            seed_radius,
            n_threads,
            act_data,
            affine_vtk,
            img_shift,
        ) = self.inp
        # n_threads = n_tracts_total
        n_threads = int(n_threads / 4)
        p_old = np.array([[0.0, 0.0, 0.0]])
        n_tracts = 0

        # Compute the tracts
        # print('ComputeTractsThread: event {}'.format(self.event.is_set()))
        while not self.event.is_set():
            try:
                # print("Computing tracts")
                # get from the queue the coordinates, coregistration transformation matrix, and flipped matrix
                # print("Here")
                m_img_flip = self.coord_tracts_queue.get_nowait()
                # coord, m_img, m_img_flip = self.coord_queue.get_nowait()
                # print('ComputeTractsThread: get {}'.format(count))

                # TODO: Remove this is not needed
                # 20200402: in this new refactored version the m_img comes different than the position
                # the new version m_img is already flixped in y, which means that Y is negative
                # if only the Y is negative maybe no need for the flip_x funtcion at all in the navigation
                # but check all coord_queue before why now the m_img comes different than position
                # 20200403: indeed flip_x is just a -1 multiplication to the Y coordinate, remove function flip_x
                # m_img_flip = m_img.copy()
                # m_img_flip[1, -1] = -m_img_flip[1, -1]

                # translate the coordinate along the normal vector of the object/coil
                coord_offset = m_img_flip[:3, -1] - offset * m_img_flip[:3, 2]
                # coord_offset = np.array([[27.53, -77.37, 46.42]])
                dist = abs(np.linalg.norm(p_old - np.asarray(coord_offset)))
                p_old = coord_offset.copy()

                # print("p_new_shape", coord_offset.shape)
                # print("m_img_flip_shape", m_img_flip.shape)
                seed_trk = img_utils.convert_world_to_voxel(coord_offset, affine)
                coord_offset_w = np.hstack((coord_offset, 1.0)).reshape([4, 1])
                # Juuso's
                # seed_trk = np.array([[-8.49, -8.39, 2.5]])
                # Baran M1
                # seed_trk = np.array([[27.53, -77.37, 46.42]])
                # print("Seed: {}".format(seed))

                # set the seeds for trekker, one seed is repeated n_threads times
                # trekker has internal multiprocessing approach done in C. Here the number of available threads is give,
                # but in case a large number of tracts is requested, it will compute all in parallel automatically
                # for a more fluent navigation, better to compute the maximum number the computer handles
                trekker.seed_coordinates(np.repeat(seed_trk, n_threads, axis=0))

                # run the trekker, this is the slowest line of code, be careful to just use once!
                trk_list = trekker.run()

                if len(trk_list) > 2:
                    # print("dist: {}".format(dist))
                    if dist >= seed_radius:
                        # when moving the coil further than the seed_radius restart the bundle computation
                        bundle = vtkMultiBlockDataSet()
                        n_branches = 0
                        branch = compute_tracts(trk_list, n_tract=0, alpha=255)
                        bundle.SetBlock(n_branches, branch)
                        n_branches += 1
                        n_tracts = branch.GetNumberOfBlocks()

                    # TODO: maybe keep computing even if reaches the maximum
                    elif dist < seed_radius and n_tracts < n_tracts_total:
                        # compute tracts blocks and add to bungle until reaches the maximum number of tracts
                        branch = compute_tracts(trk_list, n_tract=0, alpha=255)
                        if bundle:
                            bundle.SetBlock(n_branches, branch)
                            n_tracts += branch.GetNumberOfBlocks()
                            n_branches += 1

                else:
                    bundle = None

                coord_offset_w = np.linalg.inv(affine) @ coord_offset_w
                coord_offset_w = np.squeeze(coord_offset_w.T[:, :3])
                # rethink if this should be inside the if condition, it may lock the thread if no tracts are found
                # use no wait to ensure maximum speed and avoid visualizing old tracts in the queue, this might
                # be more evident in slow computer or for heavier tract computations, it is better slow update
                # than visualizing old data
                # self.visualization_queue.put_nowait([coord, m_img, bundle])
                self.tracts_queue.put_nowait((bundle, affine_vtk, coord_offset, coord_offset_w))
                # print('ComputeTractsThread: put {}'.format(count))

                self.coord_tracts_queue.task_done()
                # self.coord_queue.task_done()
                # print('ComputeTractsThread: done {}'.format(count))

            # if no coordinates pass
            except queue.Empty:
                # print("Empty queue in tractography")
                pass
            # if queue is full mark as done (may not be needed in this new "nowait" method)
            except queue.Full:
                # self.coord_queue.task_done()
                self.coord_tracts_queue.task_done()

            # sleep required to prevent user interface from being unresponsive
            time.sleep(self.sle)


class ComputeTractsACTThread(threading.Thread):
    def __init__(self, input_list, queues, event, sleep_thread):
        """Class (threading) to compute real time tractography data for visualization.

        Tracts are computed using the Trekker library by Baran Aydogan (https://dmritrekker.github.io/)
        For VTK visualization, each tract (fiber) is a constructed as a tube and many tubes combined in one
        vtkMultiBlockDataSet named as a branch. Several branches are combined in another vtkMultiBlockDataSet named as
        bundle, to obtain fast computation and visualization. The bundle dataset is mapped to a single vtkActor.
        Mapper and Actor are computer in the data/viewer_volume.py module for easier handling in the
         invesalius 3D scene.

        Sleep function in run method is used to avoid blocking GUI and more fluent, real-time navigation

        :param input_list: List of inputs: trekker instance, affine numpy array, seed offset, total number of tracts,
         seed radius, number of threads in computer, ACT data array, affine vtk matrix,
          image shift for vtk to mri transformation
        :type input_list: list
        :param queues: Queue list with coord_tracts_queue (Queue instance that manage co-registered coordinates) and
         tracts_queue (Queue instance that manage the tracts to be visualized)
        :type queues: list[queue.Queue, queue.Queue]
        :param event: Threading event to coordinate when tasks as done and allow UI release
        :type event: threading.Event
        :param sleep_thread: Sleep pause in seconds
        :type sleep_thread: float
        """

        threading.Thread.__init__(self, name="ComputeTractsThreadACT")
        self.input_list = input_list
        self.coord_tracts_queue = queues[0]
        self.tracts_queue = queues[1]
        self.event = event
        self.sleep_thread = sleep_thread

    def run(self):
        (
            trekker,
            affine,
            offset,
            n_tracts_total,
            seed_radius,
            n_threads,
            act_data,
            affine_vtk,
            img_shift,
        ) = self.input_list

        p_old = np.array([[0.0, 0.0, 0.0]])
        n_branches, n_tracts, count_loop = 0, 0, 0
        bundle = None
        dist_radius = 1.5

        # TODO: Try a denser and bigger grid, because it's just a matrix multiplication
        #  maybe 15 mm below the coil offset by default and 5 cm deep
        # create the rectangular grid to find the gray-white matter boundary
        coord_list_w = img_utils.create_grid((-2, 2), (0, 20), offset - 5, 1)

        # create the spherical grid to sample around the seed location
        samples_in_sphere = img_utils.random_sample_sphere(radius=seed_radius, size=100)
        coord_list_sphere = np.hstack(
            [samples_in_sphere, np.ones([samples_in_sphere.shape[0], 1])]
        ).T
        m_seed = np.identity(4)

        # Compute the tracts
        while not self.event.is_set():
            try:
                # get from the queue the coordinates, coregistration transformation matrix, and flipped matrix
                m_img_flip = self.coord_tracts_queue.get_nowait()

                # DEBUG: Uncomment the m_img_flip below so that distance is fixed and tracts keep computing
                # m_img_flip[:3, -1] = (5., 10., 12.)
                dist = abs(np.linalg.norm(p_old - np.asarray(m_img_flip[:3, -1])))
                p_old = m_img_flip[:3, -1].copy()

                # Uncertainty visualization  --
                # each tract branch is computed with one minFODamp adjusted from 0.01 to 0.1
                # the higher the minFODamp the more the streamlines are faithful to the data, so they become more strict
                # but also may loose some connections.
                # the lower the more relaxed streamline also increases the chance of false positives
                n_param = 1 + (count_loop % 10)
                # rescale the alpha value that defines the opacity of the branch
                # the n interval is [1, 10] and the new interval is [51, 255]
                # the new interval is defined to have no 0 opacity (minimum is 51, i.e., 20%)
                alpha = (n_param - 1) * (255 - 51) / (10 - 1) + 51
                trekker.minFODamp(n_param * 0.01)
                # ---

                try:
                    # The original seed location is replaced by the gray-white matter interface that is closest to
                    # the coil center
                    coord_list_w_tr = m_img_flip @ coord_list_w
                    coord_offset = grid_offset(act_data, coord_list_w_tr, img_shift)
                except IndexError:
                    # This error might be caused by the coordinate exceeding the image array dimensions.
                    # This happens during navigation because the coil location can have coordinates outside the image
                    # boundaries
                    # Translate the coordinate along the normal vector of the object/coil
                    coord_offset = m_img_flip[:3, -1] - offset * m_img_flip[:3, 2]
                # ---

                # Spherical sampling of seed coordinates ---
                # compute the samples of a sphere centered on seed coordinate offset by the grid
                # given in the invesalius-vtk space
                samples = np.random.default_rng().choice(coord_list_sphere.shape[1], size=100)
                m_seed[:-1, -1] = coord_offset.copy()
                # translate the spherical grid samples to the coil location in invesalius-vtk space
                seed_trk_r_inv = m_seed @ coord_list_sphere[:, samples]

                coord_offset_w = np.hstack((coord_offset, 1.0)).reshape([4, 1])

                try:
                    # Anatomic constrained seed computation ---
                    # find only the samples inside the white matter as with the ACT enabled in the Trekker,
                    # it does not compute any tracts outside the white matter
                    # convert from inveslaius-vtk to mri space
                    seed_trk_r_mri = seed_trk_r_inv[:3, :].T.astype(int) + np.array(
                        [[0, img_shift, 0]], dtype=np.int32
                    )
                    labs = act_data[
                        seed_trk_r_mri[..., 0], seed_trk_r_mri[..., 1], seed_trk_r_mri[..., 2]
                    ]
                    # find all samples in the white matter
                    labs_id = np.where(labs == 1)
                    # Trekker has internal multiprocessing approach done in C. Here the number of available threads - 1
                    # is given, but in case a large number of tracts is requested, it will compute all in parallel
                    # automatically for a more fluent navigation, better to compute the maximum number the computer can
                    # handle otherwise gets too slow for the multithreading in Python
                    seed_trk_r_inv_sampled = seed_trk_r_inv[:, labs_id[0][:n_threads]]

                except IndexError:
                    # same as on the grid offset above, if the coil is too far from the mri volume the array indices
                    # are beyond the mri boundaries
                    # in this case use the grid center instead of the spherical samples
                    seed_trk_r_inv_sampled = coord_offset_w.copy()

                # convert to the world coordinate system for trekker
                seed_trk_r_world_sampled = np.linalg.inv(affine) @ seed_trk_r_inv_sampled
                seed_trk_r_world_sampled = seed_trk_r_world_sampled.T[:, :3]

                # convert to the world coordinate system for saving in the marker list
                coord_offset_w = np.linalg.inv(affine) @ coord_offset_w
                coord_offset_w = np.squeeze(coord_offset_w.T[:, :3])

                # DEBUG: uncomment the seed_trk below
                # seed_trk.shape == [1, 3]
                # Juuso's
                # seed_trk = np.array([[-8.49, -8.39, 2.5]])
                # Baran M1
                # seed_trk = np.array([[27.53, -77.37, 46.42]])
                # print("Given: {}".format(seed_trk.shape))
                # print("Seed: {}".format(seed))
                # joonas seed that has good tracts
                # seed_trk = np.array([[29.12, -13.33, 31.65]])
                # seed_trk_img = np.array([[117, 127, 161]])

                # When moving the coil further than the seed_radius restart the bundle computation
                # Currently, it stops to compute tracts when the maximum number of tracts is reached maybe keep
                # computing even if reaches the maximum
                if dist >= dist_radius:
                    bundle = None
                    n_tracts, n_branches = 0, 0

                    # we noticed that usually the navigation lags or crashes when moving the coil location
                    # to reduce the overhead for when the coil is moving, we compute only half the number of tracts
                    # that should be computed when the coil is fixed in the same location
                    # required input is Nx3 array
                    trekker.seed_coordinates(seed_trk_r_world_sampled[::2, :])
                    # run the trekker, this is the slowest line of code, be careful to just use once!
                    trk_list = trekker.run()

                    # check if any tract was found, otherwise doesn't count
                    if len(trk_list):
                        # a bundle consists for multiple branches and each branch consists of multiple streamlines
                        # every iteration in the main loop adds a branch to the bundle
                        branch = compute_tracts(trk_list, n_tract=0, alpha=alpha)
                        n_tracts = branch.GetNumberOfBlocks()

                        # create and add branch to the bundle
                        bundle = vtkMultiBlockDataSet()
                        bundle.SetBlock(n_branches, branch)
                        n_branches = 1

                elif dist < dist_radius and n_tracts < n_tracts_total:
                    # when the coil is fixed in place and the number of tracts is smaller than the total
                    if not bundle:
                        # same as above, when creating the bundle (vtkMultiBlockDataSet) we only compute half the number
                        # of tracts to reduce the overhead
                        bundle = vtkMultiBlockDataSet()
                        # required input is Nx3 array
                        trekker.seed_coordinates(seed_trk_r_world_sampled[::2, :])
                        n_tracts, n_branches = 0, 0
                    else:
                        # if the bundle exists compute all tracts requested
                        # required input is Nx3 array
                        trekker.seed_coordinates(seed_trk_r_world_sampled)

                    trk_list = trekker.run()

                    if len(trk_list):
                        # compute tract blocks and add to bundle until reaches the maximum number of tracts
                        # the alpha changes depending on the parameter set
                        branch = compute_tracts(trk_list, n_tract=0, alpha=alpha)
                        n_tracts += branch.GetNumberOfBlocks()
                        # add branch to the bundle
                        bundle.SetBlock(n_branches, branch)
                        n_branches += 1

                # keep adding to the number of loops even if the tracts were not find
                # this will keep the minFODamp changing and new seed coordinates being tried which would allow
                # higher probability of finding tracts
                count_loop += 1

                # use "nowait" to ensure maximum speed and avoid visualizing old tracts in the queue, this might
                # be more evident in slow computer or for heavier tract computations, it is better slow update
                # than visualizing old data
                self.tracts_queue.put_nowait((bundle, affine_vtk, coord_offset, coord_offset_w))
                self.coord_tracts_queue.task_done()

            # if no coordinates pass
            except queue.Empty:
                pass
            # if queue is full mark as done (may not be needed in this new "nowait" method)
            except queue.Full:
                self.coord_tracts_queue.task_done()

            # sleep required to prevent user interface from being unresponsive
            time.sleep(self.sleep_thread)


def set_trekker_parameters(trekker, params):
    """Set all user-defined parameters for tractography computation using the Trekker library

    :param trekker: Trekker instance
    :type trekker: Trekker.T
    :param params: Dictionary containing the parameters values to set in Trekker. Initial values are in constants.py
    :type params: dict
    :return: List containing the Trekker instance and number of threads for parallel processing in the computer
    :rtype: list
    """
    trekker.seed_maxTrials(params["seed_max"])
    trekker.stepSize(params["step_size"])
    # minFODamp is not set because it should vary in the loop to create the
    # different transparency tracts
    # trekker.minFODamp(params['min_fod'])
    trekker.probeQuality(params["probe_quality"])
    trekker.maxEstInterval(params["max_interval"])
    trekker.minRadiusOfCurvature(params["min_radius_curvature"])
    trekker.probeLength(params["probe_length"])
    trekker.writeInterval(params["write_interval"])
    # these two does not need to be set in the new package
    # trekker.maxLength(params['max_length'])
    trekker.minLength(params["min_length"])
    trekker.maxSamplingPerStep(params["max_sampling_step"])
    trekker.dataSupportExponent(params["data_support_exponent"])
    # trekker.useBestAtInit(params['use_best_init'])
    # trekker.initMaxEstTrials(params['init_max_est_trials'])

    # check number if number of cores is valid in configuration file,
    # otherwise use the maximum number of threads which is usually 2*N_CPUS
    n_threads = 2 * const.N_CPU - 1
    if isinstance((params["numb_threads"]), int) and params["numb_threads"] <= (
        2 * const.N_CPU - 1
    ):
        n_threads = params["numb_threads"]

    trekker.numberOfThreads(n_threads)
    # print("Trekker config updated: n_threads, {}; seed_max, {}".format(n_threads, params['seed_max']))
    return trekker, n_threads


def grid_offset(data, coord_list_w_tr, img_shift):
    # convert to int so coordinates can be used as indices in the MRI image space
    coord_list_w_tr_mri = coord_list_w_tr[:3, :].T.astype(int) + np.array([[0, img_shift, 0]])

    # FIX: IndexError: index 269 is out of bounds for axis 2 with size 256
    # error occurs when running line "labs = data[coord..."
    # need to check why there is a coordinate outside the MRI bounds

    # extract the first occurrence of a specific label from the MRI image
    labs = data[
        coord_list_w_tr_mri[..., 0], coord_list_w_tr_mri[..., 1], coord_list_w_tr_mri[..., 2]
    ]
    lab_first = np.where(labs == 1)
    if not lab_first:
        pt_found_inv = None
    else:
        pt_found = coord_list_w_tr[:, lab_first[0][0]][:3]
        # convert coordinate back to invesalius 3D space
        pt_found_inv = pt_found - np.array([0.0, img_shift, 0.0])

    # lab_first = np.argmax(labs == 1)
    # if labs[lab_first] == 1:
    #     pt_found = coord_list_w_tr_mri[lab_first, :]
    #     # convert coordinate back to invesalius 3D space
    #     pt_found_inv = pt_found - np.array([0., img_shift, 0.])
    # else:
    #     pt_found_inv = None

    # # convert to world coordinate space to use as seed for fiber tracking
    # pt_found_tr = np.append(pt_found, 1)[np.newaxis, :].T
    # # default affine in invesalius is actually the affine inverse
    # pt_found_tr = np.linalg.inv(affine) @ pt_found_tr
    # pt_found_tr = pt_found_tr[:3, 0, np.newaxis].T

    return pt_found_inv
