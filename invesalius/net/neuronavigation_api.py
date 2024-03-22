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

from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton, debug
from invesalius.data.markers.marker import MarkerType

import wx

import numpy as np
from vtkmodules.numpy_interface import dataset_adapter


class NeuronavigationApi(metaclass=Singleton):
    """
    An API used internally in InVesalius to communicate with the
    outside world.

    When an event of one of several types happens while running InVesalius, e.g.,
    the coil is moved during neuronavigation, this class is used to update the
    information conveyed by the event.

    When created for the first time, takes a connection object obtained
    from outside InVesalius (see the main entrypoint in app.py).

    The owner of the connection object can update the state of InVesalius by implementing
    functions to set callbacks, used then to communicate the new state to InVesalius (see,
    e.g., one of the callback functions below).

    If connection object is not given or it is None, do not do the updates.
    """
    N_VERTICES_IN_POLYGON = 3

    def __init__(self, connection=None):
        if connection is not None:
            self.assert_valid(connection)

            self.__set_callbacks(connection)
            self.__bind_events()

        self.connection = connection

    def _hasmethod(self, obj, name):
        return hasattr(obj, name) and callable(getattr(obj, name))

    def assert_valid(self, connection):
        assert self._hasmethod(connection, 'update_neuronavigation_started')
        assert self._hasmethod(connection, 'update_target_mode')
        assert self._hasmethod(connection, 'update_coil_at_target')
        assert self._hasmethod(connection, 'update_coil_pose')
        assert self._hasmethod(connection, 'update_focus')
        assert self._hasmethod(connection, 'set_callback__stimulation_pulse_received')
        assert self._hasmethod(connection, 'set_callback__set_vector_field')

    def __bind_events(self):
        Publisher.subscribe(self.start_navigation, 'Start navigation')
        Publisher.subscribe(self.stop_navigation, 'Stop navigation')
        Publisher.subscribe(self.update_target_mode, 'Set target mode')
        Publisher.subscribe(self.update_coil_at_target, 'Coil at target')
        #Publisher.subscribe(self.update_focus, 'Set cross focal point')
        Publisher.subscribe(self.update_target_orientation, 'Update target orientation')

    # Functions for InVesalius to send updates.

    def start_navigation(self):
        if self.connection is not None:
            self.connection.update_neuronavigation_started(
                started=True,
            )

    def stop_navigation(self):
        if self.connection is not None:
            self.connection.update_neuronavigation_started(
                started=False,
            )

    def update_target_mode(self, enabled):
        if self.connection is not None:
            self.connection.update_target_mode(
                enabled=enabled,
            )

    def update_target_orientation(self, target_id, orientation):
        if self.connection is not None:
            self.connection.update_target_orientation(
                target_id=target_id,
                orientation=orientation
            )

    # Functions for InVesalius to send updates.

    # TODO: Not the cleanest API; for an example of a better API, see update_coil_pose
    #   below, for which position and orientation are sent separately. Changing this
    #   would require changing 'Set cross focal point' publishers and subscribers
    #   throughout the code.
    #
    def update_focus(self, position):
        if self.connection is not None:
            self.connection.update_focus(
                position=position[:3],
                orientation=position[3:],
            )

    def update_coil_pose(self, position, orientation):
        if self.connection is not None:
            self.connection.update_coil_pose(
                position=position,
                orientation=orientation,
            )

    def update_coil_mesh(self, polydata):
        if self.connection is not None:
            wrapped = dataset_adapter.WrapDataObject(polydata)

            points = np.asarray(wrapped.Points)
            polygons_raw = np.asarray(wrapped.Polygons)

            # The polygons are returned as 1d-array of the form
            #
            # [n_0, id_0(0), id_0(1), ..., id_0(n_0),
            #  n_1, id_1(0), id_1(1), ..., id_1(n_1),
            #  ...]
            #
            # where n_i is the number of vertices in polygon i, and id_i's are indices to the vertex list.
            #
            # Assert that all polygons have an equal number of vertices, reshape the array, and drop n_i's.
            #
            assert np.all(polygons_raw[0::self.N_VERTICES_IN_POLYGON + 1] == self.N_VERTICES_IN_POLYGON)

            polygons = polygons_raw.reshape(-1, self.N_VERTICES_IN_POLYGON + 1)[:, 1:]

            self.connection.update_coil_mesh(
                points=points,
                polygons=polygons,
            )

    def update_coil_at_target(self, state):
        if self.connection is not None:
            self.connection.update_coil_at_target(
                state=state
            )

    def initialize_efield(self, cortex_model_path, mesh_models_paths, coil_model_path, coil_set, conductivities_inside, conductivities_outside, dI_per_dt):
        if self.connection is not None:
            return self.connection.initialize_efield(
                cortex_model_path=cortex_model_path,
                mesh_models_paths= mesh_models_paths,
                coil_model_path =coil_model_path,
                coil_set = coil_set,
                conductivities_inside= conductivities_inside,
                conductivities_outside = conductivities_outside,
                dI_per_dt= dI_per_dt,
            )
        return None

    def init_efield_config_file(self, config_file):
        if self.connection is not None:
            return self.connection.init_efield_json(
                config_file=config_file
            )
        return None

    def efield_coil(self, coil_model_path, coil_set):
        if self.connection is not None:
            return self.connection.set_coil(
                coil_model_path=coil_model_path,
                coil_set=coil_set
            )

    def set_dIperdt(self, dIperdt):
        if self.connection is not None:
            return self.connection.set_dIperdt(
                dIperdt=dIperdt,
            )

    def update_efield(self, position, orientation, T_rot):
        if self.connection is not None:
            return self.connection.update_efield(
                position=position,
                orientation=orientation,
                T_rot=T_rot,
            )
        return None

    def update_efield_vector(self, position, orientation, T_rot):
        if self.connection is not None:
            return self.connection.update_efield_vector(
                position=position,
                orientation=orientation,
                T_rot=T_rot,
            )
        return None

    def update_efield_vectorROI(self, position, orientation, T_rot, id_list):
        if self.connection is not None:
            return self.connection.update_efield_vectorROI(
                position=position,
                orientation=orientation,
                T_rot=T_rot,
                id_list=id_list
            )
        return None

    def update_efield_vectorROIMax(self, position, orientation, T_rot, id_list):
        if self.connection is not None:
            return self.connection.update_efield_vectorROIMax(
                position=position,
                orientation=orientation,
                T_rot=T_rot,
                id_list=id_list
            )
        return None
    # Functions for InVesalius to receive updates via callbacks.

    def __set_callbacks(self, connection):
        connection.set_callback__open_orientation_dialog(self.open_orientation_dialog)
        connection.set_callback__stimulation_pulse_received(self.stimulation_pulse_received)
        connection.set_callback__set_vector_field(self.set_vector_field)

    def add_pedal_callback(self, name, callback, remove_when_released=False):
        if self.connection is not None:
            self.connection.add_pedal_callback(
                name=name,
                callback=callback,
                remove_when_released=remove_when_released,
            )

    def remove_pedal_callback(self, name):
        if self.connection is not None:
            self.connection.remove_pedal_callback(name=name)

    def open_orientation_dialog(self, target_id):
        wx.CallAfter(Publisher.sendMessage, 'Open marker orientation dialog', marker_id=target_id)

    def stimulation_pulse_received(self):
        # TODO: If marker should not be created always when receiving a stimulation pulse, add the logic here.
        wx.CallAfter(Publisher.sendMessage, 'Create marker', marker_type=MarkerType.COIL_POSE)

    def set_vector_field(self, vector_field):
        wx.CallAfter(Publisher.sendMessage, 'Set vector field', vector_field=vector_field)
