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

import queue
import threading
from time import sleep

import numpy as np
import wx

import invesalius.constants as const
import invesalius.data.bases as db
import invesalius.data.coregistration as dcr
import invesalius.data.e_field as e_field
import invesalius.data.serial_port_connection as spc
import invesalius.data.slice_ as sl
import invesalius.data.tractography as dti
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtk_utils
import invesalius.project as prj
import invesalius.session as ses
from invesalius.data.markers.marker import MarkerType
from invesalius.i18n import tr as _
from invesalius.navigation.image import Image
from invesalius.navigation.iterativeclosestpoint import IterativeClosestPoint
from invesalius.navigation.markers import MarkersControl
from invesalius.navigation.robot import Robot
from invesalius.navigation.tracker import Tracker
from invesalius.net.neuronavigation_api import NeuronavigationApi
from invesalius.net.pedal_connection import PedalConnector
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class NavigationHub(metaclass=Singleton):
    """
    Class to initialize and store references to navigation components.
    """

    def __init__(self, window=None):
        self.tracker = Tracker()
        self.image = Image()
        self.icp = IterativeClosestPoint()
        self.neuronavigation_api = NeuronavigationApi()
        self.pedal_connector = PedalConnector(self.neuronavigation_api, window)
        self.navigation = Navigation(
            pedal_connector=self.pedal_connector, neuronavigation_api=self.neuronavigation_api
        )
        self.robot = Robot(
            tracker=self.tracker,
            navigation=self.navigation,
            icp=self.icp,
        )
        self.markers = MarkersControl(robot=self.robot)


class QueueCustom(queue.Queue):
    """
    A custom queue subclass that provides a :meth:`clear` method.
    https://stackoverflow.com/questions/6517953/clear-all-items-from-the-queue
    Modified to a LIFO Queue type (Last-in-first-out). Seems to make sense for the navigation
    threads, as the last added coordinate should be the first to be processed.
    In the first tests in a short run, seems to increase the coord queue size considerably,
    possibly limiting the queue size is good.
    """

    def clear(self):
        """
        Clears all items from the queue.
        """

        with self.mutex:
            unfinished = self.unfinished_tasks - len(self.queue)
            if unfinished <= 0:
                if unfinished < 0:
                    raise ValueError("task_done() called too many times")
                self.all_tasks_done.notify_all()
            self.unfinished_tasks = unfinished
            self.queue.clear()
            self.not_full.notify_all()


class UpdateNavigationScene(threading.Thread):
    def __init__(self, vis_queues, vis_components, event, sle, neuronavigation_api):
        """Class (threading) to update the navigation scene with all graphical elements.

        Sleep function in run method is used to avoid blocking GUI and more fluent, real-time navigation

        :param affine_vtk: Affine matrix in vtkMatrix4x4 instance to update objects position in 3D scene
        :type affine_vtk: vtkMatrix4x4
        :param visualization_queue: Queue instance that manage coordinates to be visualized
        :type visualization_queue: queue.Queue
        :param event: Threading event to coordinate when tasks as done and allow UI release
        :type event: threading.Event
        :param sle: Sleep pause in seconds
        :type sle: float
        :param neuronavigation_api: An API object for communicating the coil position.
        :type neuronavigation_api: invesalius.net.neuronavigation_api.NeuronavigationAPI
        """

        threading.Thread.__init__(self, name="UpdateScene")
        (
            self.serial_port_enabled,
            self.view_tracts,
            self.peel_loaded,
            self.e_field_loaded,
            self.plot_efield_vectors,
        ) = vis_components
        (
            self.coord_queue,
            self.serial_port_queue,
            self.tracts_queue,
            self.icp_queue,
            self.e_field_norms_queue,
            self.e_field_IDs_queue,
        ) = vis_queues
        self.sle = sle
        self.event = event
        self.neuronavigation_api = neuronavigation_api

    def run(self):
        while not self.event.is_set():
            got_coords = False
            object_visible_flag = False
            try:
                coord, marker_visibilities, m_img, view_obj = self.coord_queue.get_nowait()
                got_coords = True
                object_visible_flag = marker_visibilities[2]

                # use of CallAfter is mandatory otherwise crashes the wx interface
                if self.view_tracts:
                    bundle, affine_vtk, coord_offset, coord_offset_w = (
                        self.tracts_queue.get_nowait()
                    )
                    # TODO: Check if possible to combine the Remove tracts with Update tracts in a single command
                    wx.CallAfter(Publisher.sendMessage, "Remove tracts")
                    wx.CallAfter(
                        Publisher.sendMessage,
                        "Update tracts",
                        root=bundle,
                        affine_vtk=affine_vtk,
                        coord_offset=coord_offset,
                        coord_offset_w=coord_offset_w,
                    )
                    self.tracts_queue.task_done()

                if self.serial_port_enabled:
                    trigger_on = self.serial_port_queue.get_nowait()
                    if trigger_on:
                        wx.CallAfter(
                            Publisher.sendMessage, "Create marker", marker_type=MarkerType.COIL_POSE
                        )
                    self.serial_port_queue.task_done()

                # TODO: If using the view_tracts substitute the raw coord from the offset coordinate, so the user
                # see the red cross in the position of the offset marker

                # Update the slice viewers to show the current position of the tracked object.
                wx.CallAfter(Publisher.sendMessage, "Update slices position", position=coord[:3])

                # Update the cross position to the current position of the tracked object, so that, e.g., when a
                # new marker is created, it is created in the current position of the object.
                wx.CallAfter(Publisher.sendMessage, "Set cross focal point", position=coord)

                if self.e_field_loaded and object_visible_flag:
                    wx.CallAfter(
                        Publisher.sendMessage,
                        "Update point location for e-field calculation",
                        m_img=m_img,
                        coord=coord,
                        queue_IDs=self.e_field_IDs_queue,
                    )
                    if not self.e_field_norms_queue.empty():
                        try:
                            enorm_data = self.e_field_norms_queue.get_nowait()
                            wx.CallAfter(
                                Publisher.sendMessage,
                                "Get enorm",
                                enorm_data=enorm_data,
                                plot_vector=self.plot_efield_vectors,
                            )
                        finally:
                            self.e_field_norms_queue.task_done()

                if view_obj:
                    wx.CallAfter(
                        Publisher.sendMessage, "Update coil pose", m_img=m_img, coord=coord
                    )
                    wx.CallAfter(
                        Publisher.sendMessage,
                        "Update object arrow matrix",
                        m_img=m_img,
                        coord=coord,
                        flag=self.peel_loaded,
                    )
                else:
                    wx.CallAfter(
                        Publisher.sendMessage,
                        "Update volume viewer pointer",
                        position=[coord[0], -coord[1], coord[2]],
                    )
                # Render the volume viewer and the slice viewers.
                wx.CallAfter(Publisher.sendMessage, "Render volume viewer")
                wx.CallAfter(Publisher.sendMessage, "Update slice viewer")

                self.coord_queue.task_done()

            except queue.Empty:
                if got_coords:
                    self.coord_queue.task_done()

            sleep(self.sle)


class Navigation(metaclass=Singleton):
    def __init__(self, pedal_connector, neuronavigation_api):
        self.pedal_connector = pedal_connector
        self.neuronavigation_api = neuronavigation_api

        self.correg = None
        self.target = None
        self.object_registration = None
        self.track_obj = False
        self.m_change = None
        self.obj_data = None
        self.all_fiducials = np.zeros((6, 6))
        self.event = threading.Event()
        self.coord_queue = QueueCustom(maxsize=1)
        self.icp_queue = QueueCustom(maxsize=1)
        self.object_at_target_queue = QueueCustom(maxsize=1)
        self.efield_queue = QueueCustom(maxsize=1)
        self.e_field_norms_queue = QueueCustom(maxsize=1)
        self.e_field_IDs_queue = QueueCustom(maxsize=1)
        # self.visualization_queue = QueueCustom(maxsize=1)
        self.serial_port_queue = QueueCustom(maxsize=1)
        self.coord_tracts_queue = QueueCustom(maxsize=1)
        self.tracts_queue = QueueCustom(maxsize=1)

        # Tracker parameters
        self.ref_mode_id = const.DEFAULT_REF_MODE

        self.e_field_loaded = False
        self.plot_efield_vectors = False
        self.debug_efield_enorm = None

        # Tractography parameters
        self.trk_inp = None
        self.trekker = None
        self.n_threads = None
        self.view_tracts = False
        self.peel_loaded = False
        self.enable_act = False
        self.act_data = None
        self.n_tracts = const.N_TRACTS

        # Sleep parameters
        session = ses.Session()
        sleep_nav = session.GetConfig("sleep_nav", const.SLEEP_NAVIGATION)

        self.sleep_nav = sleep_nav

        self.seed_offset = const.SEED_OFFSET
        self.seed_radius = const.SEED_RADIUS

        # Serial port
        self.serial_port_in_use = False
        self.com_port = None
        self.baud_rate = None
        self.serial_port_connection = None

        # During navigation
        self.lock_to_target = False
        self.coil_at_target = False

        self.LoadConfig()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.CoilAtTarget, "Coil at target")
        Publisher.subscribe(self.UpdateSerialPort, "Update serial port")
        Publisher.subscribe(self.UpdateObjectRegistration, "Update object registration")
        Publisher.subscribe(self.TrackObject, "Track object")

    def SaveConfig(self):
        # XXX: This shouldn't be needed, but task_navigator.py currently calls UpdateObjectRegistration with
        #   None parameter when the project is closed, crashing without this checks.
        if self.object_registration is None:
            return

        object_fiducials, object_orientations, object_reference_mode, object_name = (
            self.object_registration
        )

        state = {
            "object_fiducials": object_fiducials.tolist(),
            "object_orientations": object_orientations.tolist(),
            "object_reference_mode": object_reference_mode,
            "object_name": object_name.decode(const.FS_ENCODE),
        }

        session = ses.Session()
        session.SetConfig("navigation", state)

    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig("navigation")

        if state is None:
            return

        object_fiducials = np.array(state["object_fiducials"])
        object_orientations = np.array(state["object_orientations"])
        object_reference_mode = state["object_reference_mode"]
        object_name = state["object_name"].encode(const.FS_ENCODE)
        self.object_registration = (
            object_fiducials,
            object_orientations,
            object_reference_mode,
            object_name,
        )

    def CoilAtTarget(self, state):
        self.coil_at_target = state

    def UpdateNavSleep(self, sleep):
        self.sleep_nav = sleep
        # self.serial_port_connection.sleep_nav = sleep

    def UpdateSerialPort(self, serial_port_in_use, com_port=None, baud_rate=None):
        self.serial_port_in_use = serial_port_in_use
        self.com_port = com_port
        self.baud_rate = baud_rate

    def UpdateObjectRegistration(self, data=None):
        self.object_registration = data

        self.SaveConfig()

    def GetObjectRegistration(self):
        return self.object_registration

    def TrackObject(self, enabled=False):
        self.track_obj = enabled

    def SetLockToTarget(self, value):
        self.lock_to_target = value

    def SetReferenceMode(self, value):
        self.ref_mode_id = value

    def GetReferenceMode(self):
        return self.ref_mode_id

    def UpdateFiducialRegistrationError(self, tracker, image):
        tracker_fiducials, tracker_fiducials_raw = tracker.GetTrackerFiducials()
        image_fiducials = image.GetImageFiducials()

        self.all_fiducials = np.vstack([image_fiducials, tracker_fiducials])

        self.fre = db.calculate_fre(
            tracker_fiducials_raw, self.all_fiducials, self.ref_mode_id, self.m_change
        )

    def GetFiducialRegistrationError(self, icp):
        fre = icp.icp_fre if icp.use_icp else self.fre
        return fre, fre <= const.FIDUCIAL_REGISTRATION_ERROR_THRESHOLD

    def PedalStateChanged(self, state):
        if not self.serial_port_in_use:
            return

        permission_to_stimulate = (
            self.lock_to_target and self.coil_at_target
        ) or not self.lock_to_target

        if state and permission_to_stimulate:
            self.serial_port_connection.SendPulse()

    def EstimateTrackerToInVTransformationMatrix(self, tracker, image):
        tracker_fiducials, tracker_fiducials_raw = tracker.GetTrackerFiducials()
        image_fiducials = image.GetImageFiducials()

        self.all_fiducials = np.vstack([image_fiducials, tracker_fiducials])

        self.m_change = tr.affine_matrix_from_points(
            self.all_fiducials[3:, :].T, self.all_fiducials[:3, :].T, shear=False, scale=False
        )

    def StartNavigation(self, tracker, icp):
        # initialize jobs list
        jobs_list = []

        if self.event.is_set():
            self.event.clear()

        vis_components = [
            self.serial_port_in_use,
            self.view_tracts,
            self.peel_loaded,
            self.e_field_loaded,
            self.plot_efield_vectors,
        ]
        vis_queues = [
            self.coord_queue,
            self.serial_port_queue,
            self.tracts_queue,
            self.icp_queue,
            self.e_field_norms_queue,
            self.e_field_IDs_queue,
        ]

        Publisher.sendMessage("Navigation status", nav_status=True, vis_status=vis_components)
        errors = False

        if self.track_obj:
            # if object tracking is selected
            if self.object_registration is None:
                # check if object registration was performed
                wx.MessageBox(_("Perform coil registration before navigation."), _("InVesalius 3"))
                errors = True
            else:
                # if object registration was correctly performed continue with navigation
                # object_registration[0] is object 3x3 fiducial matrix and object_registration[1] is 3x3 orientation matrix
                obj_fiducials, obj_orients, obj_ref_mode, obj_name = self.object_registration

                coreg_data = [self.m_change, obj_ref_mode]

                if self.ref_mode_id:
                    coord_raw, marker_visibilities = tracker.TrackerCoordinates.GetCoordinates()
                else:
                    coord_raw = np.array([None])

                self.obj_data = db.object_registration(
                    obj_fiducials, obj_orients, coord_raw, self.m_change
                )
                coreg_data.extend(self.obj_data)

                queues = [
                    self.coord_queue,
                    self.coord_tracts_queue,
                    self.icp_queue,
                    self.object_at_target_queue,
                    self.efield_queue,
                ]
                jobs_list.append(
                    dcr.CoordinateCorregistrate(
                        self.ref_mode_id,
                        tracker,
                        coreg_data,
                        self.view_tracts,
                        queues,
                        self.event,
                        self.sleep_nav,
                        tracker.tracker_id,
                        self.target,
                        icp,
                        self.e_field_loaded,
                    )
                )
        else:
            coreg_data = (self.m_change, 0)
            queues = [self.coord_queue, self.coord_tracts_queue, self.icp_queue, self.efield_queue]
            jobs_list.append(
                dcr.CoordinateCorregistrateNoObject(
                    self.ref_mode_id,
                    tracker,
                    coreg_data,
                    self.view_tracts,
                    queues,
                    self.event,
                    self.sleep_nav,
                    icp,
                    self.e_field_loaded,
                )
            )

        if not errors:
            # TODO: Test the serial port thread
            if self.serial_port_in_use:
                self.serial_port_connection = spc.SerialPortConnection(
                    com_port=self.com_port,
                    baud_rate=self.baud_rate,
                    serial_port_queue=self.serial_port_queue,
                    event=self.event,
                    sleep_nav=self.sleep_nav,
                )
                self.serial_port_connection.Connect()
                jobs_list.append(self.serial_port_connection)

            if self.view_tracts:
                # initialize Trekker parameters
                # TODO: This affine and affine_vtk are created 4 times. To improve, create a new affine object inside
                #  Slice() that contains the transformation with the img_shift. Rename it to avoid confusion to the
                #  affine, for instance it can be: affine_world_to_invesalius_vtk
                slic = sl.Slice()
                prj_data = prj.Project()
                matrix_shape = tuple(prj_data.matrix_shape)
                spacing = tuple(prj_data.spacing)
                img_shift = spacing[1] * (matrix_shape[1] - 1)
                affine = slic.affine.copy()
                affine[1, -1] -= img_shift
                affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(affine)

                Publisher.sendMessage("Update marker offset state", create=True)

                self.trk_inp = (
                    self.trekker,
                    affine,
                    self.seed_offset,
                    self.n_tracts,
                    self.seed_radius,
                    self.n_threads,
                    self.act_data,
                    affine_vtk,
                    img_shift,
                )
                # print("Appending the tract computation thread!")
                queues = [self.coord_tracts_queue, self.tracts_queue]
                if self.enable_act:
                    jobs_list.append(
                        dti.ComputeTractsACTThread(self.trk_inp, queues, self.event, self.sleep_nav)
                    )
                else:
                    jobs_list.append(
                        dti.ComputeTractsThread(self.trk_inp, queues, self.event, self.sleep_nav)
                    )

            if self.e_field_loaded:
                queues = [self.efield_queue, self.e_field_norms_queue, self.e_field_IDs_queue]
                jobs_list.append(
                    e_field.Visualize_E_field_Thread(
                        queues,
                        self.event,
                        2 * self.sleep_nav,
                        self.neuronavigation_api,
                        self.debug_efield_enorm,
                        self.plot_efield_vectors,
                    )
                )

            jobs_list.append(
                UpdateNavigationScene(
                    vis_queues=vis_queues,
                    vis_components=vis_components,
                    event=self.event,
                    sle=self.sleep_nav,
                    neuronavigation_api=self.neuronavigation_api,
                )
            )

            for jobs in jobs_list:
                # jobs.daemon = True
                jobs.start()
                # del jobs

            self.pedal_connector.add_callback("navigation", self.PedalStateChanged)

    def StopNavigation(self):
        self.event.set()

        self.pedal_connector.remove_callback("navigation")

        self.coord_queue.clear()
        self.coord_queue.join()

        if self.serial_port_connection is not None:
            self.serial_port_connection.join()

        if self.serial_port_in_use:
            self.serial_port_queue.clear()
            self.serial_port_queue.join()

        if self.view_tracts:
            self.coord_tracts_queue.clear()
            self.coord_tracts_queue.join()

            self.tracts_queue.clear()
            self.tracts_queue.join()

        if self.e_field_loaded:
            self.efield_queue.clear()
            self.efield_queue.join()

            self.e_field_norms_queue.clear()
            self.e_field_norms_queue.join()

            self.e_field_IDs_queue.clear()
            self.e_field_IDs_queue.join()

        vis_components = [
            self.serial_port_in_use,
            self.view_tracts,
            self.peel_loaded,
            self.e_field_loaded,
            self.plot_efield_vectors,
        ]
        Publisher.sendMessage("Navigation status", nav_status=False, vis_status=vis_components)
