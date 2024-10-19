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
import wx

import invesalius.data.bases as db
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.utils import Singleton


class IterativeClosestPoint(metaclass=Singleton):
    def __init__(self):
        self.use_icp = False
        self.m_icp = None
        self.icp_fre = None

        try:
            self.LoadState()
        except:
            ses.Session().DeleteStateFile()

    def SaveState(self):
        m_icp = self.m_icp.tolist() if self.m_icp is not None else None
        state = {
            "use_icp": self.use_icp,
            "m_icp": m_icp,
            "icp_fre": self.icp_fre,
        }

        session = ses.Session()
        session.SetState("icp", state)

    def LoadState(self):
        session = ses.Session()
        state = session.GetState("icp")

        if state is None:
            return

        self.use_icp = state["use_icp"]
        self.m_icp = np.array(state["m_icp"])
        self.icp_fre = state["icp_fre"]

    def RegisterICP(self, navigation, tracker):
        # If ICP is already in use, return.
        if self.use_icp:
            return

        # Show dialog to ask whether to use ICP. If not, return.
        if not dlg.ICPcorregistration(navigation.fre):
            return

        # Show dialog to register ICP.
        dialog = dlg.ICPCorregistrationDialog(navigation=navigation, tracker=tracker)

        success = dialog.ShowModal()
        self.m_icp, point_coord, transformed_points, prev_error, final_error = dialog.GetValue()

        dialog.Destroy()

        if success != wx.ID_OK or self.m_icp is None:
            self.use_icp = False
            return

        # TODO: checkbox in the dialog to transfer the icp points to 3D viewer

        self.use_icp = True
        dlg.ReportICPerror(prev_error, final_error)

        # Compute FRE (fiducial registration error).
        ref_mode_id = navigation.GetReferenceMode()
        self.icp_fre = db.calculate_fre(
            tracker.tracker_fiducials_raw,
            navigation.all_fiducials,
            ref_mode_id,
            navigation.m_change,
            self.m_icp,
        )

        self.SetICP(navigation, self.use_icp)

    def SetICP(self, navigation, use_icp):
        self.use_icp = use_icp

        self.SaveState()

    def ResetICP(self):
        self.use_icp = False
        self.m_icp = None
        self.icp_fre = None

        self.SaveState()

    def GetFreForUI(self):
        return f"{self.icp_fre:.2f}" if self.icp_fre else ""
