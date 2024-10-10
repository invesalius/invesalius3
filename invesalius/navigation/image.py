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

import numpy as np

import invesalius.constants as const
import invesalius.project as prj
import invesalius.session as ses
from invesalius.data.markers.marker import MarkerType
from invesalius.pubsub import pub as Publisher


class Image:
    def __init__(self):
        self.__bind_events()
        self._fiducials = np.full([3, 3], np.nan)
        self.load_from_state = not ses.Session().ExitedSuccessfullyLastTime()

    @property
    def fiducials(self):
        return self._fiducials

    @fiducials.setter
    def fiducials(self, value):
        self._fiducials = value

    def __bind_events(self):
        Publisher.subscribe(self.OnStateProject, "Enable state project")

    def SaveState(self):
        state = {"image_fiducials": self.fiducials.tolist()}
        session = ses.Session()
        session.SetState("image", state)
        prj.Project().image_fiducials = self._fiducials

    def LoadState(self):
        session = ses.Session()
        state = session.GetState("image")
        if state is not None:
            self.fiducials = np.array(state["image_fiducials"])

    def LoadProject(self):
        self.fiducials = prj.Project().image_fiducials

    def SetImageFiducial(self, fiducial_index, position):
        self.fiducials[fiducial_index, :] = position
        self.UpdateFiducialMarker(fiducial_index)

        print(f"Image fiducial {fiducial_index} set to coordinates {position}")
        ses.Session().ChangeProject()
        self.SaveState()

    def GetImageFiducials(self):
        return self.fiducials

    def ResetImageFiducials(self):
        self.fiducials = np.full([3, 3], np.nan)
        ses.Session().ChangeProject()
        Publisher.sendMessage("Reset image fiducials")
        self.SaveState()

    def GetImageFiducialForUI(self, fiducial_index, coordinate):
        value = self.fiducials[fiducial_index, coordinate]
        if np.isnan(value):
            value = 0

        return value

    def AreImageFiducialsSet(self):
        return not np.isnan(self.fiducials).any()

    def IsImageFiducialSet(self, fiducial_index):
        return not np.isnan(self.fiducials)[fiducial_index].any()

    def UpdateFiducialMarker(self, fiducial_index):
        fiducial_name = next(
            (
                f["fiducial_name"]
                for f in const.IMAGE_FIDUCIALS
                if f["fiducial_index"] == fiducial_index
            ),
            "unknown",
        )

        label = fiducial_name + "I"
        position_np = self.fiducials[fiducial_index, :3]
        position = position_np.tolist()
        orientation = [None, None, None]
        colour = (0.0, 1.0, 0.0)
        size = 2
        seed = 3 * [0.0]

        Publisher.sendMessage("Delete fiducial marker", label=label)
        if not np.isnan(position_np).any():
            marker_type = MarkerType.FIDUCIAL
            Publisher.sendMessage(
                "Create marker",
                marker_type=marker_type,
                position=position,
                orientation=orientation,
                colour=colour,
                size=size,
                label=label,
                seed=seed,
            )

    def UpdateFiducialMarkers(self):
        for fiducial in const.IMAGE_FIDUCIALS:
            fiducial_index = fiducial["fiducial_index"]
            self.UpdateFiducialMarker(fiducial_index)

    def OnStateProject(self, state):
        if state:
            if self.load_from_state:
                self.load_from_state = False
                try:
                    self.LoadState()
                except:
                    ses.Session.DeleteStateFile()
                    self.LoadProject()  # Load project if failed to load from state
            else:
                self.LoadProject()

        self.SaveState()
        self.UpdateFiducialMarkers()
