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
    e.g., set_callback__set_markers below).

    If connection object is not given or it is None, do not do the updates.
    """
    N_VERTICES_IN_POLYGON: int = 3

    def __init__(self, connection: any = None) -> None:
        if connection is not None:
            self.assert_valid(connection)

            self.__set_callbacks(connection)
            self.__bind_events()

        self.connection = connection

    def _hasmethod(self, obj: any, name: str) -> bool:
        return hasattr(obj, name) and callable(getattr(obj, name))

    def assert_valid(self, connection: any) -> None:
        assert self._hasmethod(connection, 'update_coil_at_target')
        assert self._hasmethod(connection, 'update_coil_pose')
        assert self._hasmethod(connection, 'update_focus')
        assert self._hasmethod(connection, 'set_callback__set_markers')

    def __bind_events(self) -> None:
        Publisher.subscribe(self.update_coil_at_target, 'Coil at target')
        #Publisher.subscribe(self.update_focus, 'Set cross focal point')
        Publisher.subscribe(self.update_target_orientation, 'Update target orientation')

    # Functions for InVesalius to send updates.

    def update_target_orientation(self, target_id: int, orientation: np.ndarray) -> None:
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
    def update_focus(self, position: np.ndarray) -> None:
        if self.connection is not None:
            self.connection.update_focus(
                position=position[:3],
                orientation=position[3:],
            )

    def update_coil_pose(self, position: np.ndarray, orientation: np.ndarray) -> None:
        if self.connection is not None:
            self.connection.update_coil_pose(
                position=position,
                orientation=orientation,
            )

    def update_coil_mesh(self, polydata: any) -> None:
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

    def update_coil_at_target(self, state: bool) -> None:
        if self.connection is not None:
            self.connection.update_coil_at_target(
                state=state
            )

    def update_efield(self, position: np.ndarray, orientation: np.ndarray, T_rot: np.ndarray) -> any:
        if self.connection is not None:
            return self.connection.update_efield(
                position=position,
                orientation=orientation,
                T_rot = T_rot,
            )
        return None

    # Functions for InVesalius to receive updates via callbacks.

    def __set_callbacks(self, connection: any) -> None:
        connection.set_callback__set_markers(self.set_markers)
        connection.set_callback__open_orientation_dialog(self.open_orientation_dialog)

    def add_pedal_callback(self, name: str, callback: any, remove_when_released: bool = False) -> None:
        if self.connection is not None:
            self.connection.add_pedal_callback(
                name=name,
                callback=callback,
                remove_when_released=remove_when_released,
            )

    def remove_pedal_callback(self, name: str) -> None:
        if self.connection is not None:
            self.connection.remove_pedal_callback(name=name)

    def open_orientation_dialog(self, target_id: int) -> None:
        wx.CallAfter(Publisher.sendMessage, 'Open marker orientation dialog', marker_id=target_id)

    def set_markers(self, markers: any) -> None:
        wx.CallAfter(Publisher.sendMessage, 'Set markers', markers=markers)

