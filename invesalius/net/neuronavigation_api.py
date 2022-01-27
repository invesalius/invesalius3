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

    When something noteworthy happens when running InVesalius, e.g.,
    the coil is moved during neuronavigation, an object created from
    this class can be used to update that information.

    When created for the first time, takes a connection object obtained
    from outside InVesalius (see the main entrypoint in app.py).

    If connection object is not given or it is None, skip doing the updates.
    """
    def __init__(self, connection=None):
        if connection is not None:
            assert self._hasmethod(connection, 'update_coil_pose')
            self.__bind_events()

        self.connection = connection

    def _hasmethod(self, obj, name):
        return hasattr(obj, name) and callable(getattr(obj, name))

    def __bind_events(self):
        Publisher.subscribe(self.update_focus, 'Set cross focal point')

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
