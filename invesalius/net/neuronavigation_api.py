#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------

from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton

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
    def __init__(self, connection=None):
        if connection is not None:
            self.assert_valid(connection)

            self.__set_callbacks(connection)
            self.__bind_events()

        self.connection = connection

    def _hasmethod(self, obj, name):
        return hasattr(obj, name) and callable(getattr(obj, name))

    def assert_valid(self, connection):
        assert self._hasmethod(connection, 'update_coil_pose')
        assert self._hasmethod(connection, 'update_focus')
        assert self._hasmethod(connection, 'set_callback__set_markers')

    def __bind_events(self):
        Publisher.subscribe(self.update_focus, 'Set cross focal point')

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

    # Functions for InVesalius to receive updates via callbacks.

    def __set_callbacks(self, connection):
        connection.set_callback__set_markers(self.set_markers)

    def set_markers(self, markers):
        Publisher.sendMessage('Set markers', markers=markers)
