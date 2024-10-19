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

import invesalius.constants as const
import invesalius.data.bases as bases
import invesalius.data.coordinates as dco
import invesalius.data.transformations as tr

# TODO: Replace the use of degrees by radians in every part of the navigation pipeline


def object_marker_to_center(coord_raw, obj_id, t_obj_raw, s0_raw, r_s0_raw):
    """Translate and rotate the raw coordinate given by the tracking device to the reference system created during
    the object registration.

    :param coord_raw: Coordinates returned by the tracking device
    :type coord_raw: numpy.ndarray
    :param obj_id:
    :type obj_id: int
    :param t_obj_raw:
    :type t_obj_raw: numpy.ndarray
    :param s0_raw:
    :type s0_raw: numpy.ndarray
    :param r_s0_raw: rotation transformation from marker to object basis
    :type r_s0_raw: numpy.ndarray
    :return: 4 x 4 numpy double array
    :rtype: numpy.ndarray
    """
    as1, bs1, gs1 = np.radians(coord_raw[obj_id, 3:])
    r_probe = tr.euler_matrix(as1, bs1, gs1, "rzyx")
    t_probe_raw = tr.translation_matrix(coord_raw[obj_id, :3])
    t_offset_aux = np.linalg.inv(r_s0_raw) @ r_probe @ t_obj_raw
    t_offset = np.identity(4)
    t_offset[:, -1] = t_offset_aux[:, -1]
    t_probe = s0_raw @ t_offset @ np.linalg.inv(s0_raw) @ t_probe_raw
    ## t_offset_aux = np.linalg.inv(r_s0_raw) @ r_probe @ t_obj_raw
    ##t_offset = np.identity(4)
    ##t_offset[:, -1] = t_offset_aux[:, -1]
    ##t_probe_raw = s0_raw @ np.linalg.inv(t_offset) @ np.linalg.inv(s0_raw) @ t_probe
    m_probe = tr.concatenate_matrices(t_probe, r_probe)

    return m_probe


def object_to_reference(coord_raw, m_probe):
    """Compute affine transformation matrix to the reference basis

    :param coord_raw: Coordinates returned by the tracking device
    :type coord_raw: numpy.ndarray
    :param m_probe: Probe coordinates
    :type m_probe: numpy.ndarray
    :return: 4 x 4 numpy double array
    :rtype: numpy.ndarray
    """
    m_ref = dco.coordinates_to_transformation_matrix(
        position=coord_raw[1, :3],
        orientation=coord_raw[1, 3:],
        axes="rzyx",
    )
    m_dyn = np.linalg.inv(m_ref) @ m_probe
    return m_dyn


def tracker_to_image(m_change, m_probe_ref, r_obj_img, m_obj_raw, s0_dyn):
    """Compute affine transformation matrix to the reference basis

    :param m_change: Corregistration transformation obtained from fiducials
    :type m_change: numpy.ndarray
    :param m_probe_ref: Object or probe in reference coordinate system
    :type m_probe_ref: numpy.ndarray
    :param r_obj_img: Object coordinate system in image space (3d model)
    :type r_obj_img: numpy.ndarray
    :param m_obj_raw: Object basis in raw coordinates from tracker
    :type m_obj_raw: numpy.ndarray
    :param s0_dyn: Initial alignment of probe fixed in the object in reference (or static) frame
    :type s0_dyn: numpy.ndarray
    :return: 4 x 4 numpy double array
    :rtype: numpy.ndarray
    """

    m_img = m_change @ m_probe_ref
    r_obj = r_obj_img @ np.linalg.inv(m_obj_raw) @ np.linalg.inv(s0_dyn) @ m_probe_ref @ m_obj_raw
    m_img[:3, :3] = r_obj[:3, :3]
    return m_img


def image_to_tracker(m_change, coord_raw, target, icp, obj_data):
    """Compute the transformation matrix to the tracker coordinate system.
    The transformation matrix is splitted in two steps, one for rotation and one for translation

    :param m_change: Coregistration transformation obtained from fiducials.
                        Transforms from tracker coordinate system in head base to img coordinate system
    :type m_change: numpy.ndarray
    :param coord_raw: Probe, head and coil in tracker coordinate system
    :type target: numpy.ndarray
    :param target: Target in invesalius coordinate system
    :type target: numpy.ndarray
    :param icp: ICP transformation matrix
    :type icp: numpy.ndarray
    :param obj_data: Transformations matrices for coil
    :type obj_data: list of numpy.ndarray

    :return: The transformation matrices from invesalius coordinate system to tracker coordinate system
    :rtype: numpy.ndarray
    """
    obj_id, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = obj_data
    m_target_in_image = dco.coordinates_to_transformation_matrix(
        position=target[:3],
        orientation=target[3:],
        axes="sxyz",
    )
    if icp.use_icp:
        m_target_in_image = bases.inverse_transform_icp(m_target_in_image, icp.m_icp)

    # transform from invesalius coordinate system to tracker coordinate system. This transformation works from for translation
    m_trk = np.linalg.inv(m_change) @ m_target_in_image

    # invert y coordinate
    m_trk_flip = m_trk.copy()
    m_trk_flip[2, -1] = -m_trk_flip[2, -1]
    # finds the inverse rotation matrix from invesalius coordinate system to head base in tracker coordinate system
    m_probe_ref = (
        s0_dyn @ m_obj_raw @ np.linalg.inv(r_obj_img) @ m_target_in_image @ np.linalg.inv(m_obj_raw)
    )
    m_trk_flip[:3, :3] = m_probe_ref[:3, :3]

    m_ref = dco.coordinates_to_transformation_matrix(
        position=coord_raw[1, :3],
        orientation=coord_raw[1, 3:],
        axes="rzyx",
    )
    # transform from head base to raw tracker coordinate system
    m_probe = m_ref @ m_trk_flip
    t_probe = np.identity(4)
    t_probe[:, -1] = m_probe[:, -1]
    r_probe = np.identity(4)
    r_probe[:, :3] = m_probe[:, :3]
    # translate object center to raw tracker coordinate system
    t_offset_aux = np.linalg.inv(r_s0_raw) @ r_probe @ t_obj_raw
    t_offset = np.identity(4)
    t_offset[:, -1] = t_offset_aux[:, -1]
    t_probe_raw = s0_raw @ np.linalg.inv(t_offset) @ np.linalg.inv(s0_raw) @ t_probe

    m_target_in_tracker = np.identity(4)
    m_target_in_tracker[:, -1] = t_probe_raw[:, -1]
    m_target_in_tracker[:3, :3] = r_probe[:3, :3]

    return m_target_in_tracker


def corregistrate_probe(m_change, r_stylus, coord_raw, ref_mode_id, icp=[None, None]):
    if r_stylus is None:
        # utils.debug("STYLUS ORIENTATION NOT DEFINED!")
        r_stylus = np.eye(3)
        r_stylus[0] = -r_stylus[0]  # Flip over vtk x-axis

    m_probe = compute_marker_transformation(coord_raw, 0)

    # transform probe to reference system if dynamic ref_mode
    if ref_mode_id:
        m_probe_ref = object_to_reference(coord_raw, m_probe)
    else:
        m_probe_ref = m_probe

    # invert y coordinate
    m_probe_ref[2, -1] = -m_probe_ref[2, -1]

    # translate m_probe_ref from tracker to image space
    m_img = m_change @ m_probe_ref
    m_img = apply_icp(m_img, icp)

    # Rotate from trk system where stylus points in x-axis to vtk-system where stylus points in y-axis
    R = tr.euler_matrix(*np.radians([0, 0, -90]), axes="rxyz")[:3, :3]

    # rotate m_probe_ref from tracker to image space
    r_img = r_stylus @ R @ m_probe_ref[:3, :3] @ np.linalg.inv(R)
    m_img[:3, :3] = r_img[:3, :3]

    # compute rotation angles
    angles = np.degrees(tr.euler_from_matrix(m_img, axes="sxyz"))

    # create output coordinate list
    coord = (
        m_img[0, -1],
        m_img[1, -1],
        m_img[2, -1],
        angles[0],
        angles[1],
        angles[2],
    )

    return coord, m_img


def corregistrate_object_dynamic(m_change, obj_data, coord_raw, icp):
    """
    Corregistrate the object define by obj_data in dynamic ref_mode
    """
    obj_id, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = obj_data

    # transform raw marker coordinate to object center
    m_probe = object_marker_to_center(coord_raw, obj_id, t_obj_raw, s0_raw, r_s0_raw)

    # transform object center to reference marker
    m_probe_ref = object_to_reference(coord_raw, m_probe)

    # invert y coordinate
    m_probe_ref[2, -1] = -m_probe_ref[2, -1]

    # corregistrate from tracker to image space
    m_img = tracker_to_image(m_change, m_probe_ref, r_obj_img, m_obj_raw, s0_dyn)
    m_img = apply_icp(m_img, icp)

    # compute rotation angles
    angles = np.degrees(tr.euler_from_matrix(m_img, axes="sxyz"))

    # create output coordinate list
    coord = (
        m_img[0, -1],
        m_img[1, -1],
        m_img[2, -1],
        angles[0],
        angles[1],
        angles[2],
    )

    return coord, m_img


def corregistrate_object_static(m_change, obj_data, coord_raw, icp):
    """
    Corregistrate the object define by obj_data in static ref_mode
    """
    obj_id, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = obj_data

    # transform raw marker coordinate to object center
    m_probe = object_marker_to_center(coord_raw, obj_id, t_obj_raw, s0_raw, r_s0_raw)

    # invert y coordinate
    m_probe[2, -1] = -m_probe[2, -1]

    # corregistrate from tracker to image space
    m_img = tracker_to_image(m_change, m_probe, r_obj_img, m_obj_raw, s0_dyn)
    m_img = apply_icp(m_img, icp)

    # compute rotation angles
    angles = np.degrees(tr.euler_from_matrix(m_img, axes="sxyz"))

    # create output coordinate list
    coord = (
        m_img[0, -1],
        m_img[1, -1],
        m_img[2, -1],
        angles[0],
        angles[1],
        angles[2],
    )

    return coord, m_img


def compute_marker_transformation(coord_raw, obj_id):
    m_probe = dco.coordinates_to_transformation_matrix(
        position=coord_raw[obj_id, :3],
        orientation=coord_raw[obj_id, 3:],
        axes="rzyx",
    )
    return m_probe


def apply_icp(m_img, icp):
    use_icp, m_icp = icp
    if use_icp:
        m_img = bases.transform_icp(m_img, m_icp)

    return m_img


def ComputeRelativeDistanceToTarget(target_coord=None, img_coord=None, m_target=None, m_img=None):
    if m_target is None:
        m_target = dco.coordinates_to_transformation_matrix(
            position=target_coord[:3],
            orientation=target_coord[3:],
            axes="sxyz",
        )
    if m_img is None:
        m_img = dco.coordinates_to_transformation_matrix(
            position=img_coord[:3],
            orientation=img_coord[3:],
            axes="sxyz",
        )
    m_relative_target = np.linalg.inv(m_target) @ m_img

    # compute rotation angles
    angles = tr.euler_from_matrix(m_relative_target, axes="sxyz")

    # create output coordinate list
    distance = [
        m_relative_target[0, -1],
        m_relative_target[1, -1],
        m_relative_target[2, -1],
        np.degrees(angles[0]),
        np.degrees(angles[1]),
        np.degrees(angles[2]),
    ]

    return distance


class CoordinateCorregistrate(threading.Thread):
    def __init__(
        self,
        ref_mode_id,
        tracker,
        coreg_data,
        obj_datas,
        view_tracts,
        queues,
        event,
        sle,
        tracker_id,
        target,
        icp,
        e_field_loaded,
    ):
        threading.Thread.__init__(self, name="CoordCoregObject")
        self.ref_mode_id = ref_mode_id
        self.tracker = tracker
        self.coreg_data = coreg_data
        self.obj_datas = obj_datas
        self.coord_queue = queues[0]
        self.coord_tracts_queue = queues[1]
        self.view_tracts = view_tracts
        self.object_at_target_queue = queues[2]
        self.efield_queue = queues[3]
        self.e_field_loaded = e_field_loaded
        self.event = event
        self.sle = sle
        self.use_icp = icp.use_icp
        self.m_icp = icp.m_icp
        self.last_coord = None
        self.tracker_id = tracker_id
        self.target = target
        self.target_flag = False

        if self.target is not None:
            self.target = np.array(self.target)

            # XXX: Not sure why this is done, but a similar thing is done in OnUpdateTargetCoordinates
            #      in viewer_volume.py, so this makes them match. A better solution would probably be to
            #      do this transformation only once, and doing it in the correct place.
            #
            self.target[1] = -self.target[1]

    def run(self):
        m_change, r_stylus = self.coreg_data
        obj_datas = self.obj_datas

        corregistrate_object = (
            corregistrate_object_dynamic if self.ref_mode_id else corregistrate_object_static
        )

        icp = (self.use_icp, self.m_icp)
        while not self.event.is_set():
            try:
                if not self.object_at_target_queue.empty():
                    self.target_flag = self.object_at_target_queue.get_nowait()

                coord_raw, marker_visibilities = self.tracker.TrackerCoordinates.GetCoordinates()

                coord_probe, m_img_probe = corregistrate_probe(
                    m_change, r_stylus, coord_raw, self.ref_mode_id, icp=icp
                )

                coords = {"probe": coord_probe}
                m_imgs = {"probe": m_img_probe}

                for coil_name in obj_datas:
                    coord_coil, m_img_coil = corregistrate_object(
                        m_change, obj_datas[coil_name], coord_raw, icp
                    )
                    coords[coil_name] = coord_coil
                    m_imgs[coil_name] = m_img_coil

                # LUKATODO: this is an arbitrary coil, so efields/tracts work correctly with 1 coil but may bug out when using multiple
                main_coil = next(iter(obj_datas))
                coord = coords[main_coil]
                m_img = m_imgs[main_coil]

                # XXX: This is not the best place to do the logic related to approaching the target when the
                #      debug tracker is in use. However, the trackers (including the debug trackers) operate in
                #      the tracker space where it is hard to make the tracker approach the target in the image space.
                #      Ideally, the transformation from the tracker space to the image space (the function
                #      corregistrate_object_dynamic above) would be encapsulated in a class together with the
                #      tracker, and then the whole class would be mocked when using the debug tracker.
                if self.tracker_id == const.DEBUGTRACKAPPROACH and self.target is not None:
                    if self.last_coord is None:
                        self.last_coord = np.array(coord)
                    else:
                        coord = self.last_coord + (self.target - self.last_coord) * 0.05
                        coords[main_coil] = coord
                        self.last_coord = coord

                    angles = [np.radians(coord[3]), np.radians(coord[4]), np.radians(coord[5])]
                    translate = coord[0:3]
                    m_imgs[main_coil] = tr.compose_matrix(angles=angles, translate=translate)

                self.coord_queue.put_nowait([coords, marker_visibilities, m_imgs])

                # Compute data for efield/tracts
                m_img_flip = m_img.copy()
                m_img_flip[1, -1] = -m_img_flip[1, -1]

                if self.view_tracts:
                    self.coord_tracts_queue.put_nowait(m_img_flip)
                if self.e_field_loaded:
                    self.efield_queue.put_nowait([m_img, coord])
            except queue.Full:
                pass

            # The sleep has to be in both threads
            sleep(self.sle)
